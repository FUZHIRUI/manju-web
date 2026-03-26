import asyncio
import base64
import json
import math
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Generator
from contextlib import asynccontextmanager, contextmanager
from concurrent.futures import ThreadPoolExecutor

import aiohttp
from volcenginesdkarkruntime import Ark

from . import runtime_config
from .. import status_service
from .retry_runtime import ErrorInfo, ResponseData, execute_async, execute_sync, get_retry_policy
from .. import throttle_service


class WorkflowRuntimeError(Exception):
    """工作流运行时错误基类。"""


class ImageGenerationError(WorkflowRuntimeError):
    """图片生成错误。"""
    def __init__(self, message: str, prompt_text: Optional[str] = None, cause: Optional[Exception] = None):
        super().__init__(message)
        self.prompt_text = prompt_text
        self.cause = cause


class FenjingPromptError(WorkflowRuntimeError):
    """分镜提示词生成错误。"""
    def __init__(self, message: str, chapter: Optional[str] = None, cause: Optional[Exception] = None):
        super().__init__(message)
        self.chapter = chapter
        self.cause = cause


class RetryExceededError(WorkflowRuntimeError):
    """重试次数超限错误。"""
    def __init__(self, message: str, attempts: int, cause: Optional[Exception] = None):
        super().__init__(message)
        self.attempts = attempts
        self.cause = cause


class TosClientWrapper:
    def __init__(self) -> None:
        self._client = None
        try:
            from tos.clientv2 import TosClientV2

            access_key = runtime_config.TOS_ACCESS_KEY
            secret_key = runtime_config.TOS_SECRET_KEY
            endpoint = runtime_config.TOS_ENDPOINT
            region = runtime_config.TOS_REGION
            if access_key and secret_key and endpoint and region:
                self._client = TosClientV2(access_key, secret_key, endpoint, region)
        except (ImportError, IOError, OSError):
            self._client = None

    def available(self) -> bool:
        return self._client is not None

    def upload_file(self, bucket: str, key: str, local_path: Path) -> Optional[str]:
        if not self._client:
            return None
        try:
            self._client.put_object_from_file(bucket, key, file_path=str(local_path))
            return f"tos://{bucket}/{key}"
        except (IOError, OSError):
            return None

    def presign_get(self, bucket: str, key: str, expire_seconds: int = 3600) -> Optional[str]:
        if not self._client:
            return None
        try:
            import tos

            out = self._client.pre_signed_url(tos.HttpMethodType.Http_Method_Get, bucket, key, expire_seconds)
            return out.signed_url
        except (IOError, OSError):
            return None

    def delete_object(self, bucket: str, key: str) -> bool:
        if not self._client:
            return False
        try:
            self._client.delete_object(bucket, key)
            return True
        except (IOError, OSError):
            return False


def ark_client() -> Ark:
    return Ark(base_url=runtime_config.ARK_BASE_URL, api_key=runtime_config.ARK_API_KEY or "", timeout=runtime_config.ARK_TIMEOUT)


def emit_event(
    level: str,
    flow: str,
    event: str,
    message: str,
    step: Optional[str] = None,
    phase: Optional[str] = None,
    project: Optional[str] = None,
    chapter: Optional[str] = None,
    trace_id: Optional[str] = None,
    job_id: Optional[str] = None,
    fenjing_id: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
) -> None:
    payload: Dict[str, Any] = {
        "time": time.strftime("%y%m%d %H:%M:%S"),
        "level": level,
        "flow": flow,
        "event": event,
        "message": message,
    }
    if step:
        payload["step"] = step
    if phase:
        payload["phase"] = phase
    if project:
        payload["project"] = project
    if chapter:
        payload["chapter"] = chapter
    if trace_id:
        payload["trace_id"] = trace_id
    if job_id:
        payload["job_id"] = job_id
    if fenjing_id:
        payload["fenjing_id"] = fenjing_id
    if data:
        payload["data"] = data
    try:
        print(json.dumps(payload, ensure_ascii=False))
    except (IOError, OSError, ValueError):
        pass
    try:
        # 使用传入的project参数，如果为None则跳过状态更新
        # 避免使用runtime_config.PROJECT_NAME全局变量导致并发问题
        if project:
            status_service.update_from_event(
                flow,
                event,
                level,
                step,
                phase,
                project,
            )
    except (IOError, OSError, ValueError):
        pass


_LOG_PROMPT_MAX_LEN = int(os.environ.get("LOG_PROMPT_MAX_LEN", "4000"))
_LOG_PAYLOAD_MAX_LEN = int(os.environ.get("LOG_PAYLOAD_MAX_LEN", "12000"))
_SENSITIVE_KEYS = ("api_key", "access_key", "secret", "token", "authorization")


def _should_redact(key: str) -> bool:
    lowered = key.lower()
    return any(item in lowered for item in _SENSITIVE_KEYS)


def _truncate_text(value: str, limit: int) -> str:
    if limit <= 0 or len(value) <= limit:
        return value
    return f"{value[:limit]}...[truncated:{len(value)}]"


def _sanitize_value(value: Any, limit: int, prompt_limit: int, key: Optional[str] = None) -> Any:
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for k, v in value.items():
            key_str = str(k)
            if _should_redact(key_str):
                out[k] = "***"
                continue
            out[k] = _sanitize_value(v, limit, prompt_limit, key_str)
        return out
    if isinstance(value, list):
        return [_sanitize_value(v, limit, prompt_limit, key) for v in value]
    if isinstance(value, (bytes, bytearray)):
        return f"[binary:{len(value)}]"
    if isinstance(value, str):
        use_limit = prompt_limit if key and "prompt" in key.lower() else limit
        return _truncate_text(value, use_limit)
    return value


def _prepare_payload(payload: Any) -> Any:
    if payload is None:
        return None
    return _sanitize_value(payload, _LOG_PAYLOAD_MAX_LEN, _LOG_PROMPT_MAX_LEN)


def api_log_event(
    level: str,
    flow: str,
    event: str,
    message: str,
    api_name: str,
    endpoint: str,
    method: str,
    model: Optional[str] = None,
    status_code: Optional[int] = None,
    duration_ms: Optional[int] = None,
    request_id: Optional[str] = None,
    request_payload: Any = None,
    response_payload: Any = None,
    error_type: Optional[str] = None,
    error_message: Optional[str] = None,
    step: Optional[str] = None,
    phase: Optional[str] = None,
    project: Optional[str] = None,
    chapter: Optional[str] = None,
    trace_id: Optional[str] = None,
    job_id: Optional[str] = None,
    fenjing_id: Optional[str] = None,
) -> None:
    data: Dict[str, Any] = {
        "api_name": api_name,
        "endpoint": endpoint,
        "method": method,
    }
    if model:
        data["model"] = model
    if status_code is not None:
        data["status_code"] = status_code
    if duration_ms is not None:
        data["duration_ms"] = duration_ms
    if request_id:
        data["request_id"] = request_id
    if request_payload is not None:
        data["request_payload"] = _prepare_payload(request_payload)
    if response_payload is not None:
        data["response_payload"] = _prepare_payload(response_payload)
    if error_type:
        data["error_type"] = error_type
    if error_message:
        data["error_message"] = _truncate_text(error_message, _LOG_PAYLOAD_MAX_LEN)
    emit_event(
        level,
        flow,
        event,
        message,
        step=step,
        phase=phase,
        project=project,
        chapter=chapter,
        trace_id=trace_id,
        job_id=job_id,
        fenjing_id=fenjing_id,
        data=data,
    )


def _build_retry_loggers(
    api_name: str,
    endpoint: str,
    method: str,
    model: Optional[str],
    step: str,
    request_payload: Any,
    project: Optional[str] = None,
    chapter: Optional[str] = None,
    fenjing_id: Optional[str] = None,
) -> Any:
    def log_retry(
        attempt: int,
        max_attempts: int,
        backoff_ms: int,
        error_info: ErrorInfo,
        status_code: Optional[int],
        request_id: Optional[str],
    ) -> None:
        response_payload = {
            "retry": {
                "attempt": attempt,
                "max_attempts": max_attempts,
                "backoff_ms": backoff_ms,
                "result": "retrying",
            },
            "raw_error_code": error_info.raw_error_code,
            "raw_error_type": error_info.raw_error_type,
            "raw_message": error_info.raw_message,
            "finish_reason": error_info.finish_reason,
            "raw_logid": error_info.raw_logid,
        }
        api_log_event(
            "WARN",
            "api",
            "api_retry",
            "api retry",
            api_name=api_name,
            endpoint=endpoint,
            method=method,
            model=model,
            status_code=status_code,
            request_id=request_id,
            request_payload=request_payload,
            response_payload=response_payload,
            error_type=error_info.error_type,
            error_message=error_info.raw_message,
            step=step,
            project=project,
            chapter=chapter,
            fenjing_id=fenjing_id,
        )

    def log_summary(attempts: int, result: str, error_info: Optional[ErrorInfo], total_ms: int) -> None:
        level = "INFO" if result == "success" else "ERROR"
        response_payload = {
            "retry_summary": {
                "attempts": attempts,
                "result": result,
                "total_elapsed_ms": total_ms,
            }
        }
        if error_info:
            response_payload.update(
                {
                    "raw_error_code": error_info.raw_error_code,
                    "raw_error_type": error_info.raw_error_type,
                    "raw_message": error_info.raw_message,
                    "finish_reason": error_info.finish_reason,
                    "raw_logid": error_info.raw_logid,
                }
            )
        api_log_event(
            level,
            "api",
            "api_retry_summary",
            "api retry summary",
            api_name=api_name,
            endpoint=endpoint,
            method=method,
            model=model,
            duration_ms=total_ms,
            request_payload=request_payload,
            response_payload=response_payload,
            error_type=error_info.error_type if error_info else None,
            error_message=error_info.raw_message if error_info else None,
            step=step,
            project=project,
            chapter=chapter,
            fenjing_id=fenjing_id,
        )

    return log_retry, log_summary


async def _ark_chat_completion(
    messages: List[Dict[str, Any]],
    model: str,
    thinking: Optional[str],
    reasoning_effort: Optional[str],
    max_completion_tokens: int = 65536,
    api_name: str = "ark_chat",
) -> Dict[str, Any]:
    url = f"{runtime_config.ARK_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {runtime_config.ARK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_completion_tokens": max_completion_tokens,
    }
    if thinking:
        payload["thinking"] = {"type": thinking}
    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort
    api_type = "ark_vlm" if "vlm" in api_name else "ark_llm"
    policy, _, _ = get_retry_policy(api_type)
    timeout_sec = max(1, int(policy.timeout_ms)) / 1000 if policy.timeout_ms else runtime_config.ARK_TIMEOUT
    request_payload = {"headers": headers, "payload": payload}
    log_retry, log_summary = _build_retry_loggers(api_name, url, "POST", model, api_name, request_payload)

    async def request_once() -> ResponseData:
        start_time = time.time()
        api_log_event(
            "INFO",
            "api",
            "api_request",
            "ark chat request",
            api_name=api_name,
            endpoint=url,
            method="POST",
            model=model,
            request_payload=request_payload,
            step=api_name,
        )
        async with aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=timeout_sec)) as session:
            async with session.post(url, json=payload) as resp:
                duration_ms = int((time.time() - start_time) * 1000)
                if resp.status != 200:
                    text = await resp.text()
                    return ResponseData(
                        ok=False,
                        status_code=resp.status,
                        response_json=None,
                        response_text=text,
                        headers=dict(resp.headers),
                        finish_reason=None,
                        tts_code=None,
                        request_id=None,
                    )
                resp_json = await resp.json()
                request_id = None
                if isinstance(resp_json, dict):
                    request_id = resp_json.get("id") or resp_json.get("request_id")
                api_log_event(
                    "INFO",
                    "api",
                    "api_response",
                    "ark chat response",
                    api_name=api_name,
                    endpoint=url,
                    method="POST",
                    model=model,
                    status_code=resp.status,
                    duration_ms=duration_ms,
                    request_id=request_id,
                    response_payload=resp_json,
                    step=api_name,
                )
                finish_reason = None
                if isinstance(resp_json, dict):
                    choices = resp_json.get("choices")
                    if isinstance(choices, list) and choices:
                        choice = choices[0]
                        if isinstance(choice, dict):
                            finish_reason = choice.get("finish_reason")
                if finish_reason == "content_filter":
                    return ResponseData(
                        ok=False,
                        status_code=resp.status,
                        response_json=resp_json,
                        response_text=None,
                        headers=dict(resp.headers),
                        finish_reason=finish_reason,
                        tts_code=None,
                        request_id=request_id,
                    )
                return ResponseData(
                    ok=True,
                    status_code=resp.status,
                    response_json=resp_json,
                    response_text=None,
                    headers=dict(resp.headers),
                    finish_reason=finish_reason,
                    tts_code=None,
                    request_id=request_id,
                )

    result = await execute_async(api_type, request_once, log_retry, log_summary)
    if not result:
        raise RuntimeError("ark_chat_failed")
    if not isinstance(result.response_json, dict):
        raise RuntimeError("ark_chat_invalid_response")
    return result.response_json


def chat(
    system_texts: List[str],
    user_texts: List[str],
    model: Optional[str] = None,
    thinking: Optional[str] = None,
    reasoning_effort: Optional[str] = None,
) -> Dict[str, Any]:
    limiter = throttle_service.get_model_limiter("ark")
    if limiter:
        run_async(limiter.acquire())
    try:
        client = ark_client()
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": [{"type": "text", "text": "\n".join(system_texts)}]},
            {"role": "user", "content": [{"type": "text", "text": "\n".join(user_texts)}]},
        ]
        kwargs: Dict[str, Any] = {
            "model": model or runtime_config.ARK_CHAT_MODEL,
            "messages": messages,
            "max_completion_tokens": 65536,
        }
        if thinking:
            kwargs["thinking"] = {"type": thinking}
        if reasoning_effort:
            kwargs["reasoning_effort"] = reasoning_effort
        request_payload = kwargs
        log_retry, log_summary = _build_retry_loggers("ark_chat", "ark_sdk", "SDK", kwargs.get("model"), "ark_chat", request_payload)

        def request_once() -> ResponseData:
            start_time = time.time()
            api_log_event(
                "INFO",
                "api",
                "api_request",
                "ark sdk chat request",
                api_name="ark_chat",
                endpoint="ark_sdk",
                method="SDK",
                model=kwargs.get("model"),
                request_payload=request_payload,
                step="ark_chat",
            )
            resp = client.chat.completions.create(**kwargs)
            duration_ms = int((time.time() - start_time) * 1000)
            content = resp.choices[0].message.content
            api_log_event(
                "INFO",
                "api",
                "api_response",
                "ark sdk chat response",
                api_name="ark_chat",
                endpoint="ark_sdk",
                method="SDK",
                model=kwargs.get("model"),
                duration_ms=duration_ms,
                response_payload={"content": content},
                step="ark_chat",
            )
            return ResponseData(
                ok=True,
                status_code=None,
                response_json={"content": content},
                response_text=None,
                headers=None,
                finish_reason=None,
                tts_code=None,
                request_id=None,
            )

        result = execute_sync("ark_llm", request_once, log_retry, log_summary)
        if not result:
            raise RuntimeError("ark_chat_failed")
        content = result.response_json.get("content") if isinstance(result.response_json, dict) else ""
        return {"content": content}
    finally:
        if limiter:
            limiter.release()


def size_for_2k_9x16() -> str:
    return "1440x2560"


def get_image_concurrency() -> int:
    """获取图片生成并发数配置。

    统一使用 model.image.seedream_4_5_concurrency 配置，
    确保所有图片生成不超过 model 上限。

    Returns:
        并发数，0 表示不限制
    """
    return runtime_config.IMAGE_MODEL_CONCURRENCY


@asynccontextmanager
async def with_concurrency_limit(concurrency: Optional[int] = None):
    """并发限制上下文管理器。

    纯技术抽象，不涉及任何业务逻辑。
    默认使用 model 级别的统一配置。

    Args:
        concurrency: 并发限制数，None 表示使用全局配置，0 表示无限制
    """
    if concurrency is None:
        concurrency = get_image_concurrency()
    semaphore = asyncio.Semaphore(concurrency) if concurrency > 0 else None
    if semaphore:
        async with semaphore:
            yield
    else:
        yield


@contextmanager
def with_thread_pool_limit(max_workers: Optional[int] = None) -> Generator[ThreadPoolExecutor, None, None]:
    """线程池并发限制上下文管理器。

    纯技术抽象，用于同步调用的并发控制。
    默认使用 model 级别的统一配置。

    Args:
        max_workers: 最大工作线程数，None 表示使用全局配置

    Example:
        with with_thread_pool_limit() as pool:
            futures = [pool.submit(task) for task in tasks]
    """
    if max_workers is None:
        max_workers = get_image_concurrency()
    pool = ThreadPoolExecutor(max_workers=max_workers)
    try:
        yield pool
    finally:
        pool.shutdown(wait=True)


async def generate_image(prompt_text: str, out_dir: Path, name_prefix: str, size: Optional[str] = None) -> Optional[Path]:
    """执行图片生成的最底层调用。

    纯技术抽象，仅封装 generate_and_download 调用，
    不包含任何业务逻辑（如日志、回调、上传等）。

    Args:
        prompt_text: 提示词文本
        out_dir: 输出目录
        name_prefix: 文件名前缀
        size: 图片尺寸（可选）

    Returns:
        生成的图片路径，失败返回 None
    """
    return await generate_and_download(prompt_text, out_dir, name_prefix, size=size)


def _resolve_video_model_key(model: Optional[str]) -> Optional[str]:
    if not model:
        return None
    if "1.0" in model or "1_0" in model:
        return "video_1_0"
    if "1.5" in model or "1_5" in model:
        return "video_1_5"
    return None


async def _generate_image_internal(prompt: str, size: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """内部图片生成函数（底层实现）。"""
    limiter = await throttle_service.acquire_model_limit("seedream_4_5")
    payload = {
        "model": runtime_config.SEEDREAM_MODEL,
        "prompt": prompt,
        "size": size or size_for_2k_9x16(),
        "watermark": False,
        "sequential_image_generation": "disabled",
    }
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {runtime_config.ARK_API_KEY or ''}"}
    url = f"{runtime_config.ARK_BASE_URL}/images/generations"
    try:
        policy, _, _ = get_retry_policy("image_generation")
        timeout_sec = max(1, int(policy.timeout_ms)) / 1000 if policy.timeout_ms else runtime_config.ARK_TIMEOUT
        request_payload = {"headers": headers, "payload": payload}
        log_retry, log_summary = _build_retry_loggers(
            "image_generation",
            url,
            "POST",
            payload.get("model"),
            "image_generation",
            request_payload,
        )

        async def request_once() -> ResponseData:
            start_time = time.time()
            api_log_event(
                "INFO",
                "api",
                "api_request",
                "image generation request",
                api_name="image_generation",
                endpoint=url,
                method="POST",
                model=payload.get("model"),
                request_payload=request_payload,
                step="image_generation",
            )
            async with aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=timeout_sec)) as session:
                async with session.post(url, json=payload) as resp:
                    duration_ms = int((time.time() - start_time) * 1000)
                    if resp.status != 200:
                        text = await resp.text()
                        return ResponseData(
                            ok=False,
                            status_code=resp.status,
                            response_json=None,
                            response_text=text,
                            headers=dict(resp.headers),
                            finish_reason=None,
                            tts_code=None,
                            request_id=None,
                        )
                    resp_json = await resp.json()
                    request_id = resp_json.get("id") if isinstance(resp_json, dict) else None
                    api_log_event(
                        "INFO",
                        "api",
                        "api_response",
                        "image generation response",
                        api_name="image_generation",
                        endpoint=url,
                        method="POST",
                        model=payload.get("model"),
                        status_code=resp.status,
                        duration_ms=duration_ms,
                        request_id=request_id,
                        response_payload=resp_json,
                        step="image_generation",
                    )
                    return ResponseData(
                        ok=True,
                        status_code=resp.status,
                        response_json=resp_json,
                        response_text=None,
                        headers=dict(resp.headers),
                        finish_reason=None,
                        tts_code=None,
                        request_id=request_id,
                    )

        result = await execute_async("image_generation", request_once, log_retry, log_summary)
        if not result:
            return None
        return result.response_json if isinstance(result.response_json, dict) else None
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        api_log_event(
            "ERROR",
            "api",
            "api_error",
            "image generation exception",
            api_name="image_generation",
            endpoint=url,
            method="POST",
            model=payload.get("model"),
            error_type=type(exc).__name__,
            error_message=str(exc),
            step="image_generation",
        )
        return None
    finally:
        if limiter:
            limiter.release()


async def download(url: str, save_path: Path) -> bool:
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=runtime_config.ARK_TIMEOUT)) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return False
                data = await resp.read()
                save_path.parent.mkdir(parents=True, exist_ok=True)
                with open(save_path, "wb") as f:
                    f.write(data)
                return True
    except (aiohttp.ClientError, asyncio.TimeoutError, IOError, OSError):
        return False


async def generate_and_download(
    prompt: str,
    output_dir: Path,
    name_prefix: str,
    size: Optional[str] = None,
) -> Optional[Path]:
    result = await _generate_image_internal(prompt, size=size)
    if not result or "data" not in result or not result["data"]:
        return None
    image_url = result["data"][0].get("url")
    if not image_url:
        return None
    save_path = output_dir / f"{name_prefix}.png"
    ok = await download(image_url, save_path)
    return save_path if ok else None


async def generate_image_with_refs(
    prompt: str,
    ref_urls: List[str],
    size: Optional[str] = None,
    fenjing_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    limiter = await throttle_service.acquire_model_limit("seedream_4_5")
    payload: Dict[str, Any] = {
        "model": runtime_config.SEEDREAM_MODEL,
        "prompt": prompt,
        "size": size or size_for_2k_9x16(),
        "watermark": False,
        "sequential_image_generation": "disabled",
    }
    if ref_urls:
        payload["image"] = ref_urls[0] if len(ref_urls) == 1 else ref_urls
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {runtime_config.ARK_API_KEY or ''}"}
    url = f"{runtime_config.ARK_BASE_URL}/images/generations"
    try:
        policy, _, _ = get_retry_policy("image_generation")
        timeout_sec = max(1, int(policy.timeout_ms)) / 1000 if policy.timeout_ms else runtime_config.ARK_TIMEOUT
        request_payload = {"headers": headers, "payload": payload}
        log_retry, log_summary = _build_retry_loggers(
            "image_generation",
            url,
            "POST",
            payload.get("model"),
            "image_generation",
            request_payload,
        )

        async def request_once() -> ResponseData:
            start_time = time.time()
            api_log_event(
                "INFO",
                "api",
                "api_request",
                "image generation request",
                api_name="image_generation",
                endpoint=url,
                method="POST",
                model=payload.get("model"),
                request_payload=request_payload,
                step="image_generation",
            )
            async with aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=timeout_sec)) as session:
                async with session.post(url, json=payload) as resp:
                    duration_ms = int((time.time() - start_time) * 1000)
                    if resp.status != 200:
                        text = await resp.text()
                        return ResponseData(
                            ok=False,
                            status_code=resp.status,
                            response_json=None,
                            response_text=text,
                            headers=dict(resp.headers),
                            finish_reason=None,
                            tts_code=None,
                            request_id=None,
                        )
                    resp_json = await resp.json()
                    request_id = resp_json.get("id") if isinstance(resp_json, dict) else None
                    api_log_event(
                        "INFO",
                        "api",
                        "api_response",
                        "image generation response",
                        api_name="image_generation",
                        endpoint=url,
                        method="POST",
                        model=payload.get("model"),
                        status_code=resp.status,
                        duration_ms=duration_ms,
                        request_id=request_id,
                        response_payload=resp_json,
                        step="image_generation",
                    )
                    return ResponseData(
                        ok=True,
                        status_code=resp.status,
                        response_json=resp_json,
                        response_text=None,
                        headers=dict(resp.headers),
                        finish_reason=None,
                        tts_code=None,
                        request_id=request_id,
                    )

        result = await execute_async("image_generation", request_once, log_retry, log_summary)
        if not result:
            return None
        return result.response_json if isinstance(result.response_json, dict) else None
    finally:
        if limiter:
            limiter.release()


async def generate_and_download_with_refs(
    prompt: str,
    ref_urls: List[str],
    output_dir: Path,
    name_prefix: str,
    fenjing_id: Optional[int] = None,
) -> Optional[Path]:
    result = await generate_image_with_refs(prompt, ref_urls, fenjing_id=fenjing_id)
    if not result or "data" not in result or not result["data"]:
        result = await _generate_image_internal(prompt)
        if not result or "data" not in result or not result["data"]:
            return None
    image_url = result["data"][0].get("url")
    if not image_url:
        return None
    save_path = output_dir / f"{name_prefix}.png"
    ok = await download(image_url, save_path)
    return save_path if ok else None


def run_async(coro_or_factory: Any) -> Any:
    try:
        asyncio.get_running_loop()
        import threading
        import concurrent.futures
        future = concurrent.futures.Future()
        def run_in_thread():
            try:
                coro = coro_or_factory() if callable(coro_or_factory) else coro_or_factory
                result = asyncio.run(coro)
                future.set_result(result)
            except Exception as e:
                future.set_exception(e)
        t = threading.Thread(target=run_in_thread)
        t.start()
        t.join()
        return future.result()
    except RuntimeError:
        coro = coro_or_factory() if callable(coro_or_factory) else coro_or_factory
        return asyncio.run(coro)



async def tts_single_request(
    session: aiohttp.ClientSession,
    storyboard_id: int,
    text: str,
    yuqici: str,
    output_dir: Path,
    tos: TosClientWrapper,
    semaphore: asyncio.Semaphore,
    custom_tos_prefix: Optional[str] = None,
    project_name: Optional[str] = None,
    chapter_name: Optional[str] = None,
) -> Optional[str]:
    async with semaphore:
        try:
            fenjing_id = str(storyboard_id)
            emit_event(
                "INFO",
                "visual_audio_assets",
                "tts_start",
                f"TTS start for fenjing {fenjing_id}",
                step="generate_tts",
                project=project_name,
                chapter=chapter_name,
                fenjing_id=fenjing_id,
            )
            headers = {
                "X-Api-App-Id": runtime_config.TTS_APP_ID,
                "X-Api-Access-Key": runtime_config.TTS_ACCESS_KEY,
                "X-Api-Resource-Id": runtime_config.TTS_RESOURCE_ID,
                "Content-Type": "application/json",
                "Connection": "keep-alive",
            }
            payload = {
                "user": {"uid": f"storyboard_{storyboard_id}"},
                "req_params": {
                    "text": text,
                    "speaker": runtime_config.TTS_SPEAKER,
                    "audio_params": {
                        "format": "mp3",
                        "sample_rate": 24000,
                        "enable_timestamp": True,
                    },
                    "additions": json.dumps(
                        {
                            "explicit_language": "zh",
                            "disable_markdown_filter": True,
                            "enable_timestamp": True,
                            "context_texts": [yuqici],
                        }
                    ),
                },
            }
            audio_filename = f"fenjing_{storyboard_id}_tts.mp3"
            local_audio_path = output_dir / audio_filename
            request_payload = {"headers": headers, "payload": payload}
            log_retry, log_summary = _build_retry_loggers(
                "tts",
                runtime_config.TTS_URL,
                "POST",
                None,
                "tts",
                request_payload,
                project=project_name,
                chapter=chapter_name,
                fenjing_id=fenjing_id,
            )
            policy, _, _ = get_retry_policy("tts")
            timeout_sec = max(1, int(policy.timeout_ms)) / 1000 if policy.timeout_ms else runtime_config.ARK_TIMEOUT

            async def request_once() -> ResponseData:
                start_time = time.time()
                api_log_event(
                    "INFO",
                    "api",
                    "api_request",
                    "tts request",
                    api_name="tts",
                    endpoint=runtime_config.TTS_URL,
                    method="POST",
                    request_payload=request_payload,
                    step="tts",
                    project=project_name,
                    chapter=chapter_name,
                    fenjing_id=fenjing_id,
                )
                async with session.post(
                    runtime_config.TTS_URL,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=timeout_sec),
                ) as response:
                    duration_ms = int((time.time() - start_time) * 1000)
                    if response.status != 200:
                        return ResponseData(
                            ok=False,
                            status_code=response.status,
                            response_json=None,
                            response_text=await response.text(),
                            headers=dict(response.headers),
                            finish_reason=None,
                            tts_code=None,
                            request_id=None,
                        )
                    audio_data = bytearray()
                    tts_code = None
                    tts_message = None
                    error_payload = None
                    async for line in response.content:
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        code = data.get("code", 0)
                        if code == 0 and data.get("data"):
                            chunk_audio = base64.b64decode(data["data"])
                            audio_data.extend(chunk_audio)
                            continue
                        if code == 20000000:
                            break
                        if code:
                            try:
                                tts_code = int(code)
                            except (ValueError, TypeError):
                                tts_code = None
                            tts_message = data.get("message") if isinstance(data.get("message"), str) else None
                            error_payload = data if isinstance(data, dict) else None
                            break
                    if tts_code:
                        return ResponseData(
                            ok=False,
                            status_code=response.status,
                            response_json=error_payload or {"code": tts_code, "message": tts_message},
                            response_text=None,
                            headers=dict(response.headers),
                            finish_reason=None,
                            tts_code=tts_code,
                            request_id=None,
                        )
                    if audio_data:
                        api_log_event(
                            "INFO",
                            "api",
                            "api_response",
                            "tts response",
                            api_name="tts",
                            endpoint=runtime_config.TTS_URL,
                            method="POST",
                            status_code=response.status,
                            duration_ms=duration_ms,
                            response_payload={"status": response.status, "audio_bytes": len(audio_data)},
                            step="tts",
                            project=project_name,
                            chapter=chapter_name,
                            fenjing_id=fenjing_id,
                        )
                        return ResponseData(
                            ok=True,
                            status_code=response.status,
                            response_json={"audio_data": bytes(audio_data)},
                            response_text=None,
                            headers=dict(response.headers),
                            finish_reason=None,
                            tts_code=None,
                            request_id=None,
                        )
                    return ResponseData(
                        ok=False,
                        status_code=500,
                        response_json={"error": {"code": "empty_audio", "message": "empty_audio"}},
                        response_text="empty_audio",
                        headers=dict(response.headers),
                        finish_reason=None,
                        tts_code=None,
                        request_id=None,
                    )

            result = await execute_async("tts", request_once, log_retry, log_summary)
            if not result or not result.ok:
                emit_event(
                    "WARN",
                    "visual_audio_assets",
                    "tts_failed",
                    "TTS request failed",
                    step="generate_tts",
                    project=project_name,
                    chapter=chapter_name,
                    fenjing_id=fenjing_id,
                )
                return None
            response_json = result.response_json if isinstance(result.response_json, dict) else {}
            audio_data = response_json.get("audio_data") if isinstance(response_json, dict) else None
            if not isinstance(audio_data, (bytes, bytearray)):
                emit_event(
                    "WARN",
                    "visual_audio_assets",
                    "tts_failed",
                    "TTS empty audio data",
                    step="generate_tts",
                    project=project_name,
                    chapter=chapter_name,
                    fenjing_id=fenjing_id,
                )
                return None
            with open(local_audio_path, "wb") as f:
                f.write(audio_data)
            os.chmod(local_audio_path, 0o644)
            if tos.available():
                if custom_tos_prefix:
                    prefix = custom_tos_prefix
                else:
                    # 使用项目特定的TOS前缀，支持多项目并行
                    project_prefixes = runtime_config.get_project_prefixes(project_name) if project_name else []
                    prefix = project_prefixes["TOS_TTS_PREFIX"]
                tos_key = f"{prefix}/{audio_filename}"
                if tos.upload_file(runtime_config.TOS_BUCKET, tos_key, local_audio_path):
                    emit_event(
                        "INFO",
                        "visual_audio_assets",
                        "tts_complete",
                        f"TTS uploaded: {tos_key}",
                        step="generate_tts",
                        project=project_name,
                        chapter=chapter_name,
                        fenjing_id=fenjing_id,
                        data={"key": tos_key},
                    )
                    return tos.presign_get(runtime_config.TOS_BUCKET, tos_key)
                emit_event(
                    "WARN",
                    "visual_audio_assets",
                    "tts_failed",
                    "TTS upload failed",
                    step="generate_tts",
                    project=project_name,
                    chapter=chapter_name,
                    fenjing_id=fenjing_id,
                    data={"key": tos_key},
                )
                return None
            emit_event(
                "INFO",
                "visual_audio_assets",
                "tts_complete",
                f"TTS saved locally: {local_audio_path}",
                step="generate_tts",
                project=project_name,
                chapter=chapter_name,
                fenjing_id=fenjing_id,
                data={"file": str(local_audio_path)},
            )
            return str(local_audio_path)
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            emit_event(
                "ERROR",
                "visual_audio_assets",
                "tts_error",
                f"TTS exception: {exc}",
                step="generate_tts",
                project=project_name,
                chapter=chapter_name,
                fenjing_id=str(storyboard_id),
            )
            api_log_event(
                "ERROR",
                "api",
                "api_error",
                "tts exception",
                api_name="tts",
                endpoint=runtime_config.TTS_URL,
                method="POST",
                error_type=type(exc).__name__,
                error_message=str(exc),
                step="tts",
                project=project_name,
                chapter=chapter_name,
                fenjing_id=str(storyboard_id),
            )
            return None


async def generate_tts_audios(
    tts_prompt_jsonl: Path,
    output_dir: Path,
    tos: TosClientWrapper,
    max_concurrency: int = 10,
    custom_tos_prefix: Optional[str] = None,
    semaphore: Optional[asyncio.Semaphore] = None,
    project_name: Optional[str] = None,
    chapter_name: Optional[str] = None,
) -> List[str]:
    from .io_jsonl import read_jsonl

    output_dir.mkdir(parents=True, exist_ok=True)
    tts_prompts = read_jsonl(str(tts_prompt_jsonl))
    tts_semaphore = semaphore if semaphore else asyncio.Semaphore(max_concurrency)
    async with aiohttp.ClientSession() as session:
        tasks = []
        for prompt in tts_prompts:
            storyboard_id = prompt.get("Storyboard_id")
            text = prompt.get("jieshuo")
            yuqici = prompt.get("yuqici")
            if not storyboard_id or not text or not yuqici:
                continue
            task = tts_single_request(
                session=session,
                storyboard_id=storyboard_id,
                text=text,
                yuqici=yuqici,
                output_dir=output_dir,
                tos=tos,
                semaphore=tts_semaphore,
                custom_tos_prefix=custom_tos_prefix,
                project_name=project_name,
                chapter_name=chapter_name,
            )
            tasks.append(task)
        results = await asyncio.gather(*tasks, return_exceptions=True)
    audio_urls: List[str] = []
    for result in results:
        if isinstance(result, str):
            audio_urls.append(result)
    return audio_urls


async def create_video_task(
    model: str,
    prompt: str,
    image_url: str,
    resolution: str,
    ratio: str,
    duration: float,
    generate_audio: bool = False,
) -> Optional[str]:
    limiter = await throttle_service.acquire_model_limit(_resolve_video_model_key(model))
    url = f"{runtime_config.ARK_BASE_URL}/contents/generations/tasks"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {runtime_config.ARK_API_KEY}",
    }
    duration_int = math.ceil(duration)
    prompt_with_params = f"{prompt} --resolution {resolution} --ratio {ratio} --duration {duration_int}"
    payload: Dict[str, Any] = {
        "model": model,
        "content": [
            {"type": "text", "text": prompt_with_params},
            {"type": "image_url", "image_url": {"url": image_url}},
        ],
        "parameters": {
            "resolution": resolution,
            "ratio": ratio,
            "duration": duration_int,
        },
    }
    payload["parameters"]["generate_audio"] = generate_audio
    try:
        policy, _, _ = get_retry_policy("video_task_create")
        timeout_sec = max(1, int(policy.timeout_ms)) / 1000 if policy.timeout_ms else 30
        request_payload = {"headers": headers, "payload": payload}
        log_retry, log_summary = _build_retry_loggers(
            "video_task_create",
            url,
            "POST",
            model,
            "video_task_create",
            request_payload,
        )

        async def request_once() -> ResponseData:
            start_time = time.time()
            api_log_event(
                "INFO",
                "api",
                "api_request",
                "video task create request",
                api_name="video_task_create",
                endpoint=url,
                method="POST",
                model=model,
                request_payload=request_payload,
                step="video_task_create",
            )
            async with aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=timeout_sec)) as session:
                async with session.post(url, json=payload) as resp:
                    duration_ms = int((time.time() - start_time) * 1000)
                    if resp.status != 200:
                        text = await resp.text()
                        return ResponseData(
                            ok=False,
                            status_code=resp.status,
                            response_json=None,
                            response_text=text,
                            headers=dict(resp.headers),
                            finish_reason=None,
                            tts_code=None,
                            request_id=None,
                        )
                    data = await resp.json()
                    request_id = data.get("id") if isinstance(data, dict) else None
                    api_log_event(
                        "INFO",
                        "api",
                        "api_response",
                        "video task create response",
                        api_name="video_task_create",
                        endpoint=url,
                        method="POST",
                        model=model,
                        status_code=resp.status,
                        duration_ms=duration_ms,
                        request_id=request_id,
                        response_payload=data,
                        step="video_task_create",
                    )
                    return ResponseData(
                        ok=True,
                        status_code=resp.status,
                        response_json=data,
                        response_text=None,
                        headers=dict(resp.headers),
                        finish_reason=None,
                        tts_code=None,
                        request_id=request_id,
                    )

        result = await execute_async("video_task_create", request_once, log_retry, log_summary)
        if not result:
            return None
        if not isinstance(result.response_json, dict):
            return None
        return result.response_json.get("id")
    except (aiohttp.ClientError, asyncio.TimeoutError):
        api_log_event(
            "ERROR",
            "api",
            "api_error",
            "video task create exception",
            api_name="video_task_create",
            endpoint=url,
            method="POST",
            model=model,
            error_type="exception",
            error_message="video_task_create_exception",
            step="video_task_create",
        )
        return None
    finally:
        if limiter:
            limiter.release()


async def get_video_task_result(task_id: str) -> Optional[Dict[str, Any]]:
    url = f"{runtime_config.ARK_BASE_URL}/contents/generations/tasks/{task_id}"
    headers = {"Authorization": f"Bearer {runtime_config.ARK_API_KEY}"}
    try:
        policy, _, _ = get_retry_policy("video_task_poll")
        timeout_sec = max(1, int(policy.timeout_ms)) / 1000 if policy.timeout_ms else 30
        request_payload = {"headers": headers, "task_id": task_id}
        log_retry, log_summary = _build_retry_loggers(
            "video_task_poll",
            url,
            "GET",
            None,
            "video_task_poll",
            request_payload,
        )

        async def request_once() -> ResponseData:
            start_time = time.time()
            api_log_event(
                "INFO",
                "api",
                "api_request",
                "video task poll request",
                api_name="video_task_poll",
                endpoint=url,
                method="GET",
                request_payload=request_payload,
                step="video_task_poll",
            )
            async with aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=timeout_sec)) as session:
                async with session.get(url) as resp:
                    duration_ms = int((time.time() - start_time) * 1000)
                    if resp.status != 200:
                        text = await resp.text()
                        return ResponseData(
                            ok=False,
                            status_code=resp.status,
                            response_json=None,
                            response_text=text,
                            headers=dict(resp.headers),
                            finish_reason=None,
                            tts_code=None,
                            request_id=task_id,
                        )
                    resp_json = await resp.json()
                    api_log_event(
                        "INFO",
                        "api",
                        "api_response",
                        "video task poll response",
                        api_name="video_task_poll",
                        endpoint=url,
                        method="GET",
                        status_code=resp.status,
                        duration_ms=duration_ms,
                        request_id=task_id,
                        response_payload=resp_json,
                        step="video_task_poll",
                    )
                    return ResponseData(
                        ok=True,
                        status_code=resp.status,
                        response_json=resp_json,
                        response_text=None,
                        headers=dict(resp.headers),
                        finish_reason=None,
                        tts_code=None,
                        request_id=task_id,
                    )

        result = await execute_async("video_task_poll", request_once, log_retry, log_summary)
        if not result:
            return None
        return result.response_json if isinstance(result.response_json, dict) else None
    except (aiohttp.ClientError, asyncio.TimeoutError):
        api_log_event(
            "ERROR",
            "api",
            "api_error",
            "video task poll exception",
            api_name="video_task_poll",
            endpoint=url,
            method="GET",
            error_type="exception",
            error_message="video_task_poll_exception",
            step="video_task_poll",
        )
        return None
