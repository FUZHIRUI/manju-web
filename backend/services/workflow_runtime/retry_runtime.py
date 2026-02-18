"""
retry_runtime.py - 统一重试策略与错误分类模块

【模块职责】
提供统一的API请求重试机制，支持多种错误类型的识别和分类处理

【核心功能】
1. 重试策略配置：支持从配置文件加载重试参数
2. 错误分类：将各种错误映射为标准错误类型
3. 风控规则：支持风控场景的特殊重试策略
4. 指数退避：自动计算重试间隔时间
5. 同步/异步执行：统一的重试执行接口

【错误类型定义】
- timeout: 超时错误
- network: 网络连接错误
- rate_limit: 限流/429错误
- risk_control: 风控触发
- server_error: 服务端5xx错误
- non_retryable: 客户端4xx错误(不可重试)

【重试策略配置】
通过config_repo.load_global_retry_config()加载配置，包含：
- max_attempts: 最大重试次数
- base_backoff_ms: 基础退避时间(毫秒)
- max_backoff_ms: 最大退避时间(毫秒)
- timeout_ms: 请求超时时间(毫秒)
- error_retryable_map: 错误类型到是否可重试的映射

【使用示例】
```python
from backend.services.workflow_runtime.retry_runtime import execute_async, get_retry_policy

# 获取重试策略
policy, risk_rule, tts_map = get_retry_policy("ark_llm")

# 异步执行带重试
result = await execute_async("ark_llm", request_fn, log_retry, log_summary)
```
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

from ...repositories import config_repo


@dataclass
class ResponseData:
    """
    API响应数据封装
    
    【字段说明】
    - ok: 请求是否成功
    - status_code: HTTP状态码
    - response_json: JSON格式的响应体
    - response_text: 文本格式的响应体
    - headers: 响应头
    - finish_reason: 完成原因(如content_filter)
    - tts_code: TTS特定的返回码
    - request_id: 请求ID
    """
    ok: bool
    status_code: Optional[int]
    response_json: Any
    response_text: Optional[str]
    headers: Optional[Dict[str, Any]]
    finish_reason: Optional[str]
    tts_code: Optional[int]
    request_id: Optional[str]


@dataclass
class RetryPolicy:
    """
    重试策略配置
    
    【字段说明】
    - api_type: API类型标识
    - max_attempts: 最大重试次数
    - base_backoff_ms: 基础退避时间(毫秒)
    - max_backoff_ms: 最大退避时间(毫秒)
    - timeout_ms: 请求超时时间(毫秒)
    - error_retryable_map: 错误类型到是否可重试的映射
    - risk_rule_ref: 风控规则引用
    - tts_code_map_ref: TTS错误码映射引用
    """
    api_type: str
    max_attempts: int
    base_backoff_ms: int
    max_backoff_ms: int
    timeout_ms: int
    error_retryable_map: Dict[str, bool]
    risk_rule_ref: Optional[str] = None
    tts_code_map_ref: Optional[str] = None


@dataclass
class RiskRule:
    """
    风控规则配置
    
    【字段说明】
    - cooldown_ms: 风控冷却时间(毫秒)
    - max_attempts: 风控场景下的最大重试次数
    - codes: 风控错误码列表
    - finish_reason: 风控完成原因列表
    - code_field_paths: 错误码字段路径(用于从响应中提取)
    - message_keywords: 错误消息关键词列表
    """
    cooldown_ms: int
    max_attempts: int
    codes: Tuple[str, ...]
    finish_reason: Tuple[str, ...]
    code_field_paths: Tuple[str, ...]
    message_keywords: Tuple[str, ...]


@dataclass
class ErrorInfo:
    """
    错误信息封装
    
    【字段说明】
    - error_type: 标准化的错误类型
    - retryable: 是否可重试
    - raw_error_code: 原始错误码
    - raw_error_type: 原始错误类型
    - raw_message: 原始错误消息
    - finish_reason: 完成原因
    - raw_logid: 原始日志ID
    """
    error_type: str
    retryable: bool
    raw_error_code: Optional[str] = None
    raw_error_type: Optional[str] = None
    raw_message: Optional[str] = None
    finish_reason: Optional[str] = None
    raw_logid: Optional[str] = None


# 默认重试配置
DEFAULT_RETRY_CONFIG: Dict[str, Any] = {
    "default": {
        "max_attempts": 3,
        "base_backoff_ms": 500,
        "max_backoff_ms": 8000,
        "timeout_ms": 60000,
    },
    "policies": {},
    "risk_rules": {},
    "tts_code_maps": {},
}


def load_retry_config() -> Dict[str, Any]:
    """
    加载重试配置
    
    【加载逻辑】
    1. 从config_repo加载全局重试配置
    2. 与默认配置合并
    3. 确保必要字段存在
    
    【返回值】
    合并后的配置字典
    """
    loaded = config_repo.load_global_retry_config()
    if not isinstance(loaded, dict):
        loaded = {}
    merged: Dict[str, Any] = {**DEFAULT_RETRY_CONFIG, **loaded}
    for key in ("default", "policies", "risk_rules", "tts_code_maps"):
        if key not in merged or not isinstance(merged[key], dict):
            merged[key] = DEFAULT_RETRY_CONFIG.get(key, {})
    return merged


def _merge_policy(defaults: Dict[str, Any], policy: Dict[str, Any], api_type: str) -> RetryPolicy:
    """合并默认配置和特定策略配置"""
    combined = {**defaults, **policy}
    return RetryPolicy(
        api_type=api_type,
        max_attempts=int(combined.get("max_attempts", 3)),
        base_backoff_ms=int(combined.get("base_backoff_ms", 500)),
        max_backoff_ms=int(combined.get("max_backoff_ms", 8000)),
        timeout_ms=int(combined.get("timeout_ms", 60000)),
        error_retryable_map=dict(combined.get("error_retryable_map", {})),
        risk_rule_ref=combined.get("risk_rule_ref"),
        tts_code_map_ref=combined.get("tts_code_map_ref"),
    )


def get_retry_policy(api_type: str) -> Tuple[RetryPolicy, Optional[RiskRule], Dict[str, str]]:
    """
    获取指定API类型的重试策略
    
    【参数】
    - api_type: API类型标识(如"ark_llm", "tts", "image_generation")
    
    【返回值】
    - RetryPolicy: 重试策略配置
    - RiskRule: 风控规则(如有)
    - Dict[str, str]: TTS错误码映射(如有)
    """
    cfg = load_retry_config()
    defaults = cfg.get("default", {})
    policies = cfg.get("policies", {})
    policy_data = policies.get(api_type, {}) if isinstance(policies, dict) else {}
    policy = _merge_policy(defaults, policy_data if isinstance(policy_data, dict) else {}, api_type)
    risk_rules = cfg.get("risk_rules", {}) if isinstance(cfg.get("risk_rules"), dict) else {}
    risk_rule = None
    if policy.risk_rule_ref and policy.risk_rule_ref in risk_rules:
        raw = risk_rules.get(policy.risk_rule_ref, {})
        if isinstance(raw, dict):
            risk_rule = RiskRule(
                cooldown_ms=int(raw.get("cooldown_ms", 0)),
                max_attempts=int(raw.get("max_attempts", 0)),
                codes=tuple(raw.get("codes", []) or []),
                finish_reason=tuple(raw.get("finish_reason", []) or []),
                code_field_paths=tuple(raw.get("code_field_paths", []) or []),
                message_keywords=tuple(raw.get("message_keywords", []) or []),
            )
    tts_code_maps = cfg.get("tts_code_maps", {}) if isinstance(cfg.get("tts_code_maps"), dict) else {}
    tts_map: Dict[str, str] = {}
    if policy.tts_code_map_ref and policy.tts_code_map_ref in tts_code_maps:
        raw_map = tts_code_maps.get(policy.tts_code_map_ref, {})
        if isinstance(raw_map, dict):
            tts_map = {str(k): str(v) for k, v in raw_map.items()}
    return policy, risk_rule, tts_map


def _get_by_path(payload: Any, path: str) -> Optional[Any]:
    """从嵌套字典中按路径获取值"""
    current = payload
    for key in path.split("."):
        if not isinstance(current, dict) or key not in current:
            return None
        current = current.get(key)
    return current


def _extract_error_fields(response_json: Any) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """从响应中提取错误字段(code, type, message)"""
    raw_code = None
    raw_type = None
    raw_message = None
    if isinstance(response_json, dict):
        err = response_json.get("error") if isinstance(response_json.get("error"), dict) else None
        if isinstance(err, dict):
            raw_code = err.get("code") or err.get("Code")
            raw_type = err.get("type") or err.get("Type")
            raw_message = err.get("message") or err.get("Message")
        if raw_code is None:
            raw_code = response_json.get("code") if isinstance(response_json.get("code"), (str, int)) else None
        if raw_message is None:
            raw_message = response_json.get("message") if isinstance(response_json.get("message"), str) else None
        if raw_type is None:
            raw_type = response_json.get("type") if isinstance(response_json.get("type"), str) else None
    return (
        str(raw_code) if raw_code is not None else None,
        str(raw_type) if raw_type is not None else None,
        str(raw_message) if raw_message is not None else None,
    )


def _extract_logid(response_json: Any) -> Optional[str]:
    """从响应中提取日志ID"""
    if isinstance(response_json, dict):
        for key in ("logid", "log_id", "request_id", "id"):
            value = response_json.get(key)
            if value is not None:
                return str(value)
    return None


def _matches_risk(rule: RiskRule, response_json: Any, response_text: Optional[str], finish_reason: Optional[str]) -> bool:
    """检查是否匹配风控规则"""
    if finish_reason and finish_reason in rule.finish_reason:
        return True
    raw_code, raw_type, raw_message = _extract_error_fields(response_json)
    for path in rule.code_field_paths:
        value = _get_by_path(response_json, path) if isinstance(response_json, dict) else None
        if value is not None and str(value) in rule.codes:
            return True
    if raw_code and raw_code in rule.codes:
        return True
    if raw_type and raw_type in rule.codes:
        return True
    message = raw_message or response_text or ""
    for keyword in rule.message_keywords:
        if keyword and keyword in message:
            return True
    return False


def _is_timeout(exc: BaseException) -> bool:
    """判断异常是否为超时错误"""
    name = exc.__class__.__name__.lower()
    if "timeout" in name:
        return True
    if isinstance(exc, asyncio.TimeoutError):
        return True
    try:
        import aiohttp

        if isinstance(exc, aiohttp.ClientTimeout):
            return True
    except ImportError:
        pass
    try:
        import requests

        if isinstance(exc, requests.exceptions.Timeout):
            return True
    except ImportError:
        pass
    return False


def _is_network_error(exc: BaseException) -> bool:
    """判断异常是否为网络错误"""
    name = exc.__class__.__name__.lower()
    if "connection" in name or "connector" in name or "network" in name:
        return True
    try:
        import aiohttp

        if isinstance(exc, aiohttp.ClientConnectionError):
            return True
    except ImportError:
        pass
    try:
        import requests

        if isinstance(exc, requests.exceptions.ConnectionError):
            return True
    except ImportError:
        pass
    return False


def classify_error(
    policy: RetryPolicy,
    risk_rule: Optional[RiskRule],
    tts_code_map: Dict[str, str],
    status_code: Optional[int],
    response_json: Any,
    response_text: Optional[str],
    finish_reason: Optional[str],
    tts_code: Optional[int],
    exc: Optional[BaseException],
) -> ErrorInfo:
    """
    分类错误类型
    
    【分类逻辑】
    1. TTS错误码优先按映射策略判断
    2. 异常类型判断(超时/网络)
    3. HTTP状态码判断(429/5xx/4xx)
    4. 风控规则匹配
    
    【参数】
    - policy: 重试策略
    - risk_rule: 风控规则
    - tts_code_map: TTS错误码映射
    - status_code: HTTP状态码
    - response_json: 响应JSON
    - response_text: 响应文本
    - finish_reason: 完成原因
    - tts_code: TTS错误码
    - exc: 异常对象
    
    【返回值】
    标准化的错误信息
    """
    # 统一将响应/异常映射为标准 error_type，并决定是否可重试
    raw_code, raw_type, raw_message = _extract_error_fields(response_json)
    raw_logid = _extract_logid(response_json)
    if tts_code is not None:
        # TTS 30xx 返回码优先按映射策略判断
        mapped = tts_code_map.get(str(tts_code)) if tts_code_map else None
        error_type = mapped or ("non_retryable" if 3000 <= int(tts_code) < 4000 else "server_error")
        retryable = policy.error_retryable_map.get(error_type, False)
        return ErrorInfo(
            error_type=error_type,
            retryable=retryable,
            raw_error_code=str(tts_code),
            raw_error_type=raw_type,
            raw_message=raw_message or response_text,
            finish_reason=finish_reason,
            raw_logid=raw_logid,
        )
    if exc is not None:
        # 网络/超时异常优先归类
        if _is_timeout(exc):
            error_type = "timeout"
        elif _is_network_error(exc):
            error_type = "network"
        else:
            error_type = "server_error"
        retryable = policy.error_retryable_map.get(error_type, False)
        return ErrorInfo(
            error_type=error_type,
            retryable=retryable,
            raw_error_code=raw_code,
            raw_error_type=raw_type or exc.__class__.__name__,
            raw_message=str(exc),
            finish_reason=finish_reason,
            raw_logid=raw_logid,
        )
    if status_code == 429 or raw_code == "TooManyRequests" or raw_type == "TooManyRequests":
        # 过载/限流视为 rate_limit，重试策略由配置驱动
        error_type = "rate_limit"
        retryable = policy.error_retryable_map.get(error_type, False)
        return ErrorInfo(
            error_type=error_type,
            retryable=retryable,
            raw_error_code=raw_code,
            raw_error_type=raw_type,
            raw_message=raw_message or response_text,
            finish_reason=finish_reason,
            raw_logid=raw_logid,
        )
    if risk_rule and _matches_risk(risk_rule, response_json, response_text, finish_reason):
        # 命中风控规则时，使用风控专属重试策略
        error_type = "risk_control"
        retryable = policy.error_retryable_map.get(error_type, False)
        return ErrorInfo(
            error_type=error_type,
            retryable=retryable,
            raw_error_code=raw_code,
            raw_error_type=raw_type,
            raw_message=raw_message or response_text,
            finish_reason=finish_reason,
            raw_logid=raw_logid,
        )
    if status_code is not None and 500 <= status_code < 600:
        error_type = "server_error"
    elif status_code is not None and 400 <= status_code < 500:
        error_type = "non_retryable"
    else:
        error_type = "server_error"
    retryable = policy.error_retryable_map.get(error_type, False)
    return ErrorInfo(
        error_type=error_type,
        retryable=retryable,
        raw_error_code=raw_code,
        raw_error_type=raw_type,
        raw_message=raw_message or response_text,
        finish_reason=finish_reason,
        raw_logid=raw_logid,
    )


def _compute_backoff_ms(policy: RetryPolicy, attempt: int, risk_rule: Optional[RiskRule], error_type: str) -> int:
    """
    计算退避时间(毫秒)
    
    【算法】
    指数退避：base * 2^(attempt-1)，并受max_backoff_ms上限约束
    风控场景使用cooldown_ms
    """
    # 指数退避：base * 2^(attempt-1)，并受 max_backoff_ms 上限约束
    base = max(0, policy.base_backoff_ms)
    backoff = min(policy.max_backoff_ms, base * (2 ** max(0, attempt - 1))) if base > 0 else 0
    # 风控场景可提高为 cooldown_ms，确保冷却窗口生效
    if error_type == "risk_control" and risk_rule and risk_rule.cooldown_ms > backoff:
        backoff = risk_rule.cooldown_ms
    return int(backoff)


def _effective_max_attempts(policy: RetryPolicy, risk_rule: Optional[RiskRule], error_type: str) -> int:
    """
    计算有效最大重试次数
    
    【逻辑】
    风控场景使用风控规则中定义的max_attempts
    """
    # 风控场景允许用更小的 max_attempts 做上限裁剪
    max_attempts = policy.max_attempts
    if error_type == "risk_control" and risk_rule and risk_rule.max_attempts > 0:
        max_attempts = min(max_attempts, risk_rule.max_attempts)
    return max(1, max_attempts)


async def execute_async(
    api_type: str,
    request_fn: Callable[[], Awaitable[ResponseData]],
    log_retry: Callable[[int, int, int, ErrorInfo, Optional[int], Optional[str]], None],
    log_summary: Callable[[int, str, Optional[ErrorInfo], int], None],
) -> Optional[ResponseData]:
    """
    异步执行请求并支持重试
    
    【执行流程】
    1. 获取重试策略
    2. 循环执行请求
    3. 成功时返回结果
    4. 失败时分类错误
    5. 可重试时计算退避时间并等待
    6. 不可重试或达到最大次数时返回None
    
    【参数】
    - api_type: API类型
    - request_fn: 异步请求函数
    - log_retry: 重试日志回调
    - log_summary: 总结日志回调
    
    【返回值】
    成功时返回ResponseData，失败时返回None
    """
    # 执行异步请求并按策略重试，超限或超时即失败退出
    policy, risk_rule, tts_code_map = get_retry_policy(api_type)
    start_ts = time.monotonic()
    attempts = 0
    while attempts < policy.max_attempts:
        attempts += 1
        response: Optional[ResponseData] = None
        try:
            response = await request_fn()
            if response.ok:
                total_ms = int((time.monotonic() - start_ts) * 1000)
                log_summary(attempts, "success", None, total_ms)
                return response
            error_info = classify_error(
                policy,
                risk_rule,
                tts_code_map,
                response.status_code,
                response.response_json,
                response.response_text,
                response.finish_reason,
                response.tts_code,
                None,
            )
        except Exception as exc:
            error_info = classify_error(policy, risk_rule, tts_code_map, None, None, None, None, None, exc)
        max_attempts = _effective_max_attempts(policy, risk_rule, error_info.error_type)
        backoff_ms = _compute_backoff_ms(policy, attempts, risk_rule, error_info.error_type)
        log_retry(
            attempts,
            max_attempts,
            backoff_ms,
            error_info,
            response.status_code if response else None,
            response.request_id if response else None,
        )
        if not error_info.retryable or attempts >= max_attempts:
            # 不可重试或已达最大重试次数，直接失败并汇总
            total_ms = int((time.monotonic() - start_ts) * 1000)
            log_summary(attempts, "failed", error_info, total_ms)
            return None
        if backoff_ms > 0:
            # 退避等待后再发起下一次尝试
            await asyncio.sleep(backoff_ms / 1000)
    total_ms = int((time.monotonic() - start_ts) * 1000)
    log_summary(attempts, "failed", None, total_ms)
    return None


def execute_sync(
    api_type: str,
    request_fn: Callable[[], ResponseData],
    log_retry: Callable[[int, int, int, ErrorInfo, Optional[int], Optional[str]], None],
    log_summary: Callable[[int, str, Optional[ErrorInfo], int], None],
) -> Optional[ResponseData]:
    """
    同步执行请求并支持重试
    
    【说明】
    逻辑与execute_async一致，但使用同步函数
    """
    # 执行同步请求并按策略重试，逻辑与异步一致
    policy, risk_rule, tts_code_map = get_retry_policy(api_type)
    start_ts = time.monotonic()
    attempts = 0
    while attempts < policy.max_attempts:
        attempts += 1
        response: Optional[ResponseData] = None
        try:
            response = request_fn()
            if response.ok:
                total_ms = int((time.monotonic() - start_ts) * 1000)
                log_summary(attempts, "success", None, total_ms)
                return response
            error_info = classify_error(
                policy,
                risk_rule,
                tts_code_map,
                response.status_code,
                response.response_json,
                response.response_text,
                response.finish_reason,
                response.tts_code,
                None,
            )
        except Exception as exc:
            error_info = classify_error(policy, risk_rule, tts_code_map, None, None, None, None, None, exc)
        max_attempts = _effective_max_attempts(policy, risk_rule, error_info.error_type)
        backoff_ms = _compute_backoff_ms(policy, attempts, risk_rule, error_info.error_type)
        log_retry(
            attempts,
            max_attempts,
            backoff_ms,
            error_info,
            response.status_code if response else None,
            response.request_id if response else None,
        )
        if not error_info.retryable or attempts >= max_attempts:
            total_ms = int((time.monotonic() - start_ts) * 1000)
            log_summary(attempts, "failed", error_info, total_ms)
            return None
        if backoff_ms > 0:
            time.sleep(backoff_ms / 1000)
    total_ms = int((time.monotonic() - start_ts) * 1000)
    log_summary(attempts, "failed", None, total_ms)
    return None
