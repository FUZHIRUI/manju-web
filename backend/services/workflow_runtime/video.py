import asyncio
import json
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from . import runtime_config
from .io_jsonl import read_jsonl, write_jsonl
from .json_parse import parse_jsonl_or_array
from .provider_runtime import TosClientWrapper, create_video_task, download, get_video_task_result, chat as llm_chat, emit_event

PROMPT_DIR = Path(__file__).resolve().parent / "prompt"

def _video_download_file_from_tos(bucket: str, key: str, local_path: Path, tos_client: Optional[TosClientWrapper] = None, project_name: Optional[str] = None) -> bool:
    if tos_client is None:
        tos_client = TosClientWrapper()
    if not tos_client.available():
        return False
    try:
        client = tos_client._client if hasattr(tos_client, "_client") else None
        if not client:
            return False
        resp = client.get_object(bucket, key)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with open(local_path, "wb") as f:
            f.write(resp.read())
        return True
    except (IOError, OSError) as e:
        emit_event(
            "WARN",
            "video",
            "log",
            f"Failed to download {key}: {e}",
            step="download_assets",
            project=project_name,
        )
        return False

def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)

def normalize_output_dir(output_dir: Path, project_name: Optional[str] = None) -> Path:
    proj = project_name
    if proj in output_dir.parts:
        return output_dir
    return output_dir / proj

def parse_tos_uri(uri: str) -> Optional[Dict[str, str]]:
    if not isinstance(uri, str) or not uri.startswith("tos://"):
        return None
    rest = uri[6:]
    if not rest:
        return None
    if "/" not in rest:
        return {"bucket": rest, "prefix": ""}
    bucket, prefix = rest.split("/", 1)
    return {"bucket": bucket, "prefix": prefix.rstrip("/")}

def resolve_tos_assets_scope(prefix: str) -> Dict[str, Optional[str]]:
    if not isinstance(prefix, str) or not prefix:
        return {"assets_prefix": None, "chapter_name": None}
    clean = prefix.rstrip("/")
    if "/storyboards/" in clean:
        base, tail = clean.split("/storyboards/", 1)
        if tail.startswith("storyboard_chapter_"):
            chapter = tail.split("/", 1)[0]
            return {"assets_prefix": base, "chapter_name": chapter}
        return {"assets_prefix": base, "chapter_name": None}
    if clean.endswith("/storyboards"):
        return {"assets_prefix": clean[:-len("/storyboards")], "chapter_name": None}
    return {"assets_prefix": clean, "chapter_name": None}

def extract_chapter_from_key(key: str) -> Optional[str]:
    if not isinstance(key, str) or "storyboards/" not in key:
        return None
    tail = key.split("storyboards/", 1)[1]
    if tail.startswith("storyboard_chapter_"):
        return tail.split("/", 1)[0].replace(".jsonl", "")
    return None

def list_tos_keys(bucket: str, prefix: str, project_name: Optional[str] = None) -> List[str]:
    tos_client = TosClientWrapper()
    if not tos_client.available():
        return []
    client = tos_client._client if hasattr(tos_client, "_client") else None
    if not client:
        return []
    keys: List[str] = []
    try:
        continuation_token: Optional[str] = None
        is_truncated = True
        while is_truncated:
            resp = None
            if hasattr(client, "list_objects_type2"):
                kwargs = {"prefix": prefix}
                if continuation_token:
                    kwargs["continuation_token"] = continuation_token
                resp = client.list_objects_type2(bucket, **kwargs)
            elif hasattr(client, "list_objects"):
                kwargs = {"prefix": prefix}
                if continuation_token:
                    kwargs["marker"] = continuation_token
                resp = client.list_objects(bucket, **kwargs)
            if resp is None:
                break
            contents = getattr(resp, "contents", None) or getattr(resp, "contents_list", None) or getattr(resp, "Contents", None)
            if contents:
                for it in contents:
                    key = getattr(it, "key", None) or getattr(it, "Key", None) or it.get("Key") if isinstance(it, dict) else None
                    if isinstance(key, str) and key:
                        keys.append(key)
            else:
                if isinstance(resp, dict):
                    for it in resp.get("Contents", []) or []:
                        key = it.get("Key")
                        if isinstance(key, str) and key:
                            keys.append(key)
            is_truncated = bool(getattr(resp, "is_truncated", None) or getattr(resp, "IsTruncated", None) or (resp.get("IsTruncated") if isinstance(resp, dict) else False))
            next_token = (
                getattr(resp, "next_continuation_token", None)
                or getattr(resp, "NextContinuationToken", None)
                or (resp.get("NextContinuationToken") if isinstance(resp, dict) else None)
                or getattr(resp, "next_marker", None)
                or getattr(resp, "NextMarker", None)
                or (resp.get("NextMarker") if isinstance(resp, dict) else None)
            )
            if is_truncated and isinstance(next_token, str) and next_token:
                continuation_token = next_token
                continue
            break
    except (IOError, OSError) as e:
        emit_event(
            "WARN",
            "video",
            "log",
            f"Failed to list TOS keys for prefix : {e}",
            step="general",
            project=project_name,
        )
        return []
    return keys

def generate_video_prompts(
    fenjing_prompts_path: Path, 
    output_dir: Path,
    chapter_name: Optional[str] = None,
    project_name: Optional[str] = None
) -> Path:
    """
    基于 LLM 生成视频生成提示词
    """
    prompt_file = PROMPT_DIR / "shengshipin.txt"
    if not prompt_file.exists():
        raise FileNotFoundError(f"Video prompt file not found: {prompt_file}")
    
    system_prompt = read_text(str(prompt_file))
    fenjing_items = read_jsonl(str(fenjing_prompts_path))
    
    user_content = json.dumps(fenjing_items, ensure_ascii=False)
    
    project_info = f"[{project_name}] " if project_name else ""
    chapter_info = f"[{chapter_name}] " if isinstance(chapter_name, str) and chapter_name else ""
    label = f"{project_info}{chapter_info}"
    emit_event(
        "INFO",
        "video",
        "log",
        f"{label}[Phase 1] Generating video prompts with LLM, total items: {len(fenjing_items)}",
        step="fenjing_prompts",
        project=project_name,
    )
    
    thinking = runtime_config.VIDEO_PROMPT_THINKING if runtime_config.VIDEO_PROMPT_THINKING != "disabled" else None
    reasoning_effort = runtime_config.VIDEO_PROMPT_REASONING_EFFORT if runtime_config.VIDEO_PROMPT_REASONING_EFFORT != "disabled" else None
    
    response = llm_chat(
        system_texts=[system_prompt],
        user_texts=[user_content],
        thinking=thinking,
        reasoning_effort=reasoning_effort
    )
    
    content = response.get("content", "")
    
    output_path = output_dir / "shipin_prompts.jsonl"
    ensure_dir(output_dir)
    items = parse_jsonl_or_array(content)
    write_jsonl(str(output_path), items)
    emit_event(
        "INFO",
        "video",
        "log",
        f"{label}[Phase 1] Video prompts saved to {output_path}, total valid items: {len(items)}",
        step="general",
        project=project_name,
    )
    return output_path

def get_duration_ffmpeg(file_path: str, fenjing_id: str, prefix: str = "", project_name: Optional[str] = None) -> float:
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        duration = float(result.stdout.strip())
        emit_event(
            "INFO",
            "video",
            "log",
            f"[Phase 2] Fenjing {fenjing_id}: Audio duration = {duration:.2f}s",
            step="fenjing_prompts",
            project=project_name,
        )
        return duration
    except (subprocess.SubprocessError, ValueError) as e:
        emit_event(
            "ERROR",
            "video",
            "log",
            f"[Phase 2] Fenjing {fenjing_id}: ffprobe failed for {file_path}: {e}",
            step="fenjing_prompts",
            project=project_name,
        )
        return 0.0

async def get_audio_duration_with_retry(
    fenjing_id: str, 
    output_dir: Path,
    chapter_name: Optional[str] = None,
    max_retries: int = 3,
    prefix: str = "",
    project_name: Optional[str] = None
) -> float:
    """
    获取音频时长，优先查找本地，否则从 TOS 下载
    支持重试机制
    """
    # 使用合理的默认值（4.0秒，同时满足1.0和1.5模型的最低要求）
    default_duration = 4.0
    
    # 创建TOS客户端
    tos = TosClientWrapper()
    
    # 使用项目特定的TOS前缀，支持多项目并行
    project_prefixes = runtime_config.get_project_prefixes(project_name) if project_name else {}
    tos_tts_prefix = project_prefixes.get("TOS_TTS_PREFIX", "")
    
    for attempt in range(max_retries):
        try:
            if chapter_name:
                local_path = output_dir / "tts_audio" / chapter_name / f"fenjing_{fenjing_id}_tts.mp3"
            else:
                local_path = output_dir / "tts_audio" / f"fenjing_{fenjing_id}_tts.mp3"
            if not local_path.exists():
                legacy_path = output_dir / "tts_audios" / f"fenjing_{fenjing_id}_tts.mp3"
                if legacy_path.exists():
                    local_path = legacy_path
            if local_path.exists():
                return get_duration_ffmpeg(str(local_path), fenjing_id, prefix=prefix, project_name=project_name)

            key = f"{tos_tts_prefix}/{chapter_name}/fenjing_{fenjing_id}_tts.mp3" if chapter_name else f"{tos_tts_prefix}/fenjing_{fenjing_id}_tts.mp3"
            temp_dir = output_dir / "temp_tts"
            ensure_dir(temp_dir)
            temp_path = temp_dir / f"{fenjing_id}.mp3"

            emit_event(
                "INFO",
                "video",
                "log",
                f"[Phase 2] Fenjing {fenjing_id}: Downloading TTS audio from TOS (attempt {attempt + 1}/{max_retries}), key={key}",
                step="fenjing_prompts",
                project=project_name,
            )
            presigned = tos.presign_get(runtime_config.TOS_BUCKET, key)
            if presigned:
                if await download(presigned, temp_path):
                    return get_duration_ffmpeg(str(temp_path), fenjing_id, prefix=prefix, project_name=project_name)

            emit_event(
                "WARN",
                "video",
                "log",
                f"[Phase 2] Fenjing {fenjing_id}: Failed to get presigned URL or download audio (attempt {attempt + 1}/{max_retries})",
                step="fenjing_prompts",
                project=project_name,
            )
            if attempt < max_retries - 1:
                await asyncio.sleep(2)
        except (IOError, OSError, ValueError) as e:
            emit_event(
                "ERROR",
                "video",
                "log",
                f"[Phase 2] Fenjing {fenjing_id}: Exception while getting audio duration (attempt {attempt + 1}/{max_retries}): {e}",
                step="fenjing_prompts",
                project=project_name,
            )
            if attempt < max_retries - 1:
                await asyncio.sleep(2)

    emit_event(
        "WARN",
        "video",
        "log",
        f"[Phase 2] Fenjing {fenjing_id}: Could not get duration after {max_retries} retries, defaulting to {default_duration:.1f}s",
        step="fenjing_prompts",
        project=project_name,
    )
    return default_duration

async def batch_get_audio_durations(
    fenjing_ids: List[str],
    output_dir: Path,
    chapter_name: Optional[str] = None,
    qps: float = runtime_config.VIDEO_AUDIO_DURATION_QPS,
    prefix: str = "",
    project_name: Optional[str] = None
) -> Dict[str, float]:
    """
    批量获取音频时长，支持并发控制
    """
    emit_event(
        "INFO",
        "video",
        "log",
        f"[Phase 2] Starting batch audio duration retrieval for {len(fenjing_ids)} items, QPS={qps}",
        step="fenjing_prompts",
        project=project_name,
    )
    
    concurrency = int(qps) if qps > 0 else 1
    sem = asyncio.Semaphore(max(1, concurrency))
    duration_map: Dict[str, float] = {}
    
    async def get_duration(fenjing_id: str):
        async with sem:
            duration = await get_audio_duration_with_retry(fenjing_id, output_dir, chapter_name=chapter_name, prefix=prefix, project_name=project_name)
            duration_map[fenjing_id] = duration
    
    tasks = [get_duration(fid) for fid in fenjing_ids]
    await asyncio.gather(*tasks)
    
    emit_event(
        "INFO",
        "video",
        "log",
        f"[Phase 2] Audio duration retrieval completed, got {len(duration_map)} durations",
        step="general",
        project=project_name,
    )
    return duration_map

async def create_video_task_with_retry(
    fenjing_id: str,
    model: str,
    prompt: str,
    image_url: str,
    resolution: str,
    ratio: str,
    duration: float,
    max_retries: int = 3,
    prefix: str = "",
    chapter_name: Optional[str] = None,
    project_name: Optional[str] = None
) -> Optional[str]:
    """
    创建视频生成任务，支持重试机制
    """
    generate_audio = False
    
    for attempt in range(max_retries):
        try:
            emit_event(
                "INFO",
                "video",
                "log",
                f"[Phase 3] Fenjing {fenjing_id}: Creating video task (attempt {attempt + 1}/{max_retries}), generate_audio={generate_audio}",
                step="fenjing_prompts",
                project=project_name,
            )
            emit_event(
                "INFO",
                "video",
                "fenjing_video_task_create_start",
                f"Fenjing {fenjing_id} creating video task (attempt {attempt + 1}/{max_retries})",
                step="fenjing_video_task_create",
                project=project_name,
                chapter=chapter_name,
                fenjing_id=fenjing_id,
                data={"attempt": attempt + 1, "max_retries": max_retries, "model": model},
            )
            task_id = await create_video_task(
                model=model,
                prompt=prompt,
                image_url=image_url,
                resolution=resolution,
                ratio=ratio,
                duration=duration,
                generate_audio=generate_audio
            )

            if task_id:
                emit_event(
                    "INFO",
                    "video",
                    "log",
                    f"[Phase 3] Fenjing {fenjing_id}: Video task created successfully, TaskID={task_id}",
                    step="fenjing_prompts",
                    project=project_name,
                )
                emit_event(
                    "INFO",
                    "video",
                    "fenjing_video_task_created",
                    f"Fenjing {fenjing_id} video task created",
                    step="fenjing_video_task_create",
                    project=project_name,
                    chapter=chapter_name,
                    fenjing_id=fenjing_id,
                    data={"task_id": task_id},
                )
                return task_id
            else:
                emit_event(
                    "WARN",
                    "video",
                    "log",
                    f"[Phase 3] Fenjing {fenjing_id}: create_video_task returned None (attempt {attempt + 1}/{max_retries})",
                    step="fenjing_prompts",
                    project=project_name,
                )
                emit_event(
                    "WARN",
                    "video",
                    "fenjing_video_task_create_empty",
                    f"Fenjing {fenjing_id} create_video_task returned None",
                    step="fenjing_video_task_create",
                    project=project_name,
                    chapter=chapter_name,
                    fenjing_id=fenjing_id,
                    data={"attempt": attempt + 1, "max_retries": max_retries},
                )

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            error_str = str(e)
            is_retryable = "400" in error_str or "404" in error_str or "timeout" in error_str.lower()

            if is_retryable and attempt < max_retries - 1:
                emit_event(
                    "WARN",
                    "video",
                    "log",
                    f"[Phase 3] Fenjing {fenjing_id}: Retryable error (attempt {attempt + 1}/{max_retries}): {e}",
                    step="fenjing_prompts",
                    project=project_name,
                )
                await asyncio.sleep(2 * (attempt + 1))
            else:
                emit_event(
                    "ERROR",
                    "video",
                    "log",
                    f"[Phase 3] Fenjing {fenjing_id}: Failed to create video task after {attempt + 1} attempts: {e}",
                    step="fenjing_prompts",
                    project=project_name,
                )
                emit_event(
                    "ERROR",
                    "video",
                    "fenjing_video_task_create_error",
                    f"Fenjing {fenjing_id} create task failed: {e}",
                    step="fenjing_video_task_create",
                    project=project_name,
                    chapter=chapter_name,
                    fenjing_id=fenjing_id,
                    data={"attempt": attempt + 1, "max_retries": max_retries},
                )
                emit_event(
                    "ERROR",
                    "video",
                    "flow_error",
                    f"Fenjing {fenjing_id} 视频任务创建重试超限",
                    step="fenjing_video_task_create",
                    project=project_name,
                    chapter=chapter_name,
                    fenjing_id=fenjing_id,
                    data={"attempt": attempt + 1, "max_retries": max_retries, "error": str(e)},
                )
                return None
    
    return None

async def process_single_video_independent(
    fenjing_id: str,
    model_ep: str,
    prompt: str,
    image_url: str,
    audio_duration: float,
    min_duration: float,
    video_dir: Path,
    chapter_name: Optional[str] = None,
    video_filename: Optional[str] = None,
    project_name: Optional[str] = None,
    skip_upload: bool = False,
) -> bool:
    """
    独立处理单个视频生成任务，包括轮询、下载、上传
    完全异步，不阻塞其他任务
    返回 True 表示成功，False 表示失败
    """
    # 创建TOS客户端
    tos = TosClientWrapper()
    
    # audio_duration 已经在 Phase 0 中加了 0.3 秒，直接使用
    # 确保不低于最小生成时长
    final_duration = max(audio_duration, min_duration)
    
    project_info = f"[{project_name}] " if project_name else ""
    chapter_info = f"[{chapter_name}] " if chapter_name else ""
    prefix = f"{project_info}{chapter_info}"
    
    emit_event(
        "INFO",
        "video",
        "log",
        f"[Phase 3] Fenjing {fenjing_id}: Starting video processing, Model={model_ep}, Duration={final_duration:.2f}s (Audio+0.3s: {audio_duration:.2f}s, Min: {min_duration}s)",
        step="fenjing_prompts",
        project=project_name,
    )
    emit_event(
        "INFO",
        "video",
        "fenjing_video_start",
        f"Fenjing {fenjing_id} start video processing",
        step="fenjing_video",
        project=project_name,
        chapter=chapter_name,
        fenjing_id=fenjing_id,
        data={"model": model_ep, "duration": final_duration, "min_duration": min_duration},
    )
    
    max_retries = 3
    max_polls_per_retry = 100
    poll_interval = 2
    video_url = None
    
    for retry_count in range(max_retries):
        emit_event(
            "INFO",
            "video",
            "log",
            f"[Phase 3] Fenjing {fenjing_id}: Creating video task (retry {retry_count + 1}/{max_retries})",
            step="fenjing_prompts",
            project=project_name,
        )
        
        task_id = await create_video_task_with_retry(
            fenjing_id=fenjing_id,
            model=model_ep,
            prompt=prompt,
            image_url=image_url,
            resolution=runtime_config.VIDEO_RESOLUTION,
            ratio=runtime_config.VIDEO_RATIO,
            duration=final_duration,
            prefix=prefix,
            chapter_name=chapter_name,
            project_name=project_name
        )
        
        if not task_id:
            emit_event(
                "ERROR",
                "video",
                "log",
                f"[Phase 3] Fenjing {fenjing_id}: Failed to create video task after retries",
                step="fenjing_prompts",
                project=project_name,
            )
            emit_event(
                "ERROR",
                "video",
                "fenjing_video_task_create_failed",
                f"Fenjing {fenjing_id} failed to create video task",
                step="fenjing_video_task_create",
                project=project_name,
                chapter=chapter_name,
                fenjing_id=fenjing_id,
            )
            if retry_count < max_retries - 1:
                emit_event(
                    "WARN",
                    "video",
                    "log",
                    f"[Phase 3] Fenjing {fenjing_id}: Retrying video task creation...",
                    step="fenjing_prompts",
                    project=project_name,
                )
                continue
            else:
                emit_event(
                    "ERROR",
                    "video",
                    "flow_error",
                    f"Fenjing {fenjing_id} 视频任务创建重试超限",
                    step="fenjing_video_task_create",
                    project=project_name,
                    chapter=chapter_name,
                    fenjing_id=fenjing_id,
                    data={"attempt": retry_count + 1, "max_retries": max_retries},
                )
                return False

        emit_event(
            "INFO",
            "video",
            "log",
            f"[Phase 4] Fenjing {fenjing_id}: Waiting 20s before polling, TaskID={task_id}",
            step="fenjing_prompts",
            project=project_name,
        )
        emit_event(
            "INFO",
            "video",
            "fenjing_video_polling_wait",
            f"Fenjing {fenjing_id} wait before polling",
            step="fenjing_video_polling",
            project=project_name,
            chapter=chapter_name,
            fenjing_id=fenjing_id,
            data={"task_id": task_id},
        )
        await asyncio.sleep(20)
        
        for poll_count in range(max_polls_per_retry):
            try:
                result = await get_video_task_result(task_id)
                if not result:
                    emit_event(
                        "WARN",
                        "video",
                        "log",
                        f"[Phase 4] Fenjing {fenjing_id}: Poll returned None, retrying (poll {poll_count + 1}/{max_polls_per_retry})",
                        step="fenjing_prompts",
                        project=project_name,
                    )
                    await asyncio.sleep(poll_interval)
                    continue
                    
                status = result.get("status")
                if status == "succeeded":
                    video_url = result.get("content", {}).get("video_url")
                    emit_event(
                        "INFO",
                        "video",
                        "log",
                        f"[Phase 4] Fenjing {fenjing_id}: Video generation succeeded, URL={video_url}",
                        step="fenjing_prompts",
                        project=project_name,
                    )
                    emit_event(
                        "INFO",
                        "video",
                        "fenjing_video_succeeded",
                        f"Fenjing {fenjing_id} video generation succeeded",
                        step="fenjing_video_polling",
                        project=project_name,
                        chapter=chapter_name,
                        fenjing_id=fenjing_id,
                        data={"task_id": task_id, "video_url": video_url},
                    )
                    break
                elif status == "failed":
                    emit_event(
                        "ERROR",
                        "video",
                        "log",
                        f"[Phase 4] Fenjing {fenjing_id}: Video generation failed, result={result}",
                        step="fenjing_prompts",
                        project=project_name,
                    )
                    emit_event(
                        "ERROR",
                        "video",
                        "fenjing_video_failed",
                        f"Fenjing {fenjing_id} video generation failed",
                        step="fenjing_video_polling",
                        project=project_name,
                        chapter=chapter_name,
                        fenjing_id=fenjing_id,
                        data={"task_id": task_id, "result": result},
                    )
                    if retry_count < max_retries - 1:
                        emit_event(
                            "WARN",
                            "video",
                            "log",
                            f"[Phase 4] Fenjing {fenjing_id}: Retrying video task creation...",
                            step="fenjing_prompts",
                            project=project_name,
                        )
                        break
                    else:
                        emit_event(
                            "ERROR",
                            "video",
                            "flow_error",
                            f"Fenjing {fenjing_id} 视频生成重试超限",
                            step="fenjing_video_polling",
                            project=project_name,
                            chapter=chapter_name,
                            fenjing_id=fenjing_id,
                            data={"attempt": retry_count + 1, "max_retries": max_retries, "status": "failed"},
                        )
                        return False
                elif status in ["cancelled", "cancelling"]:
                    emit_event(
                        "WARN",
                        "video",
                        "log",
                        f"[Phase 4] Fenjing {fenjing_id}: Video task cancelled",
                        step="fenjing_prompts",
                        project=project_name,
                    )
                    emit_event(
                        "WARN",
                        "video",
                        "fenjing_video_cancelled",
                        f"Fenjing {fenjing_id} video task cancelled",
                        step="fenjing_video_polling",
                        project=project_name,
                        chapter=chapter_name,
                        fenjing_id=fenjing_id,
                        data={"task_id": task_id},
                    )
                    if retry_count < max_retries - 1:
                        emit_event(
                            "WARN",
                            "video",
                            "log",
                            f"[Phase 4] Fenjing {fenjing_id}: Retrying video task creation...",
                            step="fenjing_prompts",
                            project=project_name,
                        )
                        break
                    else:
                        emit_event(
                            "ERROR",
                            "video",
                            "flow_error",
                            f"Fenjing {fenjing_id} 视频生成重试超限",
                            step="fenjing_video_polling",
                            project=project_name,
                            chapter=chapter_name,
                            fenjing_id=fenjing_id,
                            data={"attempt": retry_count + 1, "max_retries": max_retries, "status": "cancelled"},
                        )
                        return False
                else:
                    emit_event(
                        "INFO",
                        "video",
                        "log",
                        f"[Phase 4] Fenjing {fenjing_id}: Status={status}, polling... (poll {poll_count + 1}/{max_polls_per_retry})",
                        step="fenjing_prompts",
                        project=project_name,
                    )
                    
                await asyncio.sleep(poll_interval)
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                emit_event(
                    "ERROR",
                    "video",
                    "log",
                    f"[Phase 4] Fenjing {fenjing_id}: Exception during polling (poll {poll_count + 1}/{max_polls_per_retry}): {e}",
                    step="fenjing_prompts",
                    project=project_name,
                )
                emit_event(
                    "ERROR",
                    "video",
                    "fenjing_video_polling_error",
                    f"Fenjing {fenjing_id} polling error: {e}",
                    step="fenjing_video_polling",
                    project=project_name,
                    chapter=chapter_name,
                    fenjing_id=fenjing_id,
                    data={"task_id": task_id, "poll": poll_count + 1},
                )
                await asyncio.sleep(poll_interval)
        
        # 如果成功获取到视频URL，跳出重试循环
        if video_url:
            break
        
        # 如果轮询100次后还在running，继续重试
        if retry_count < max_retries - 1:
            emit_event(
                "WARN",
                "video",
                "log",
                f"[Phase 4] Fenjing {fenjing_id}: Video task still running after {max_polls_per_retry * poll_interval}s, retrying...",
                step="fenjing_prompts",
                project=project_name,
            )
            continue
        else:
            emit_event(
                "ERROR",
                "video",
                "log",
                f"[Phase 4] Fenjing {fenjing_id}: Video task timed out after {max_retries} retries",
                step="fenjing_prompts",
                project=project_name,
            )
            emit_event(
                "ERROR",
                "video",
                "flow_error",
                f"Fenjing {fenjing_id} 视频轮询重试超限",
                step="fenjing_video_polling",
                project=project_name,
                chapter=chapter_name,
                fenjing_id=fenjing_id,
                data={"attempt": retry_count + 1, "max_retries": max_retries, "reason": "timeout"},
            )
            return False
    
    if not video_url:
        emit_event(
            "ERROR",
            "video",
            "log",
            f"[Phase 4] Fenjing {fenjing_id}: Video task failed to complete",
            step="fenjing_prompts",
            project=project_name,
        )
        emit_event(
            "ERROR",
            "video",
            "fenjing_video_no_url",
            f"Fenjing {fenjing_id} video task completed without url",
            step="fenjing_video_polling",
            project=project_name,
            chapter=chapter_name,
            fenjing_id=fenjing_id,
        )
        emit_event(
            "ERROR",
            "video",
            "flow_error",
            f"Fenjing {fenjing_id} 视频生成重试超限",
            step="fenjing_video_polling",
            project=project_name,
            chapter=chapter_name,
            fenjing_id=fenjing_id,
            data={"max_retries": max_retries, "reason": "no_url"},
        )
        return False
    
    emit_event(
        "INFO",
        "video",
        "log",
        f"[Phase 5] Fenjing {fenjing_id}: Downloading video from {video_url}",
        step="fenjing_prompts",
        project=project_name,
    )
    emit_event(
        "INFO",
        "video",
        "fenjing_video_download_start",
        f"Fenjing {fenjing_id} start download",
        step="fenjing_video_download",
        project=project_name,
        chapter=chapter_name,
        fenjing_id=fenjing_id,
        data={"video_url": video_url},
    )
    if video_filename:
        save_path = video_dir / video_filename
    else:
        save_path = video_dir / f"fenjing_{fenjing_id}_video.mp4"
    
    emit_event(
        "INFO",
        "video",
        "log",
        f"[Phase 5] Fenjing {fenjing_id}: Target save path: {save_path}",
        step="fenjing_prompts",
        project=project_name,
    )
    
    try:
        download_success = await download(video_url, save_path)
        
        if download_success:
            emit_event(
                "INFO",
                "video",
                "log",
                f"[Phase 5] Fenjing {fenjing_id}: Video downloaded successfully to {save_path}",
                step="fenjing_prompts",
                project=project_name,
            )
            emit_event(
                "INFO",
                "video",
                "fenjing_video_downloaded",
                f"Fenjing {fenjing_id} downloaded",
                step="fenjing_video_download",
                project=project_name,
                chapter=chapter_name,
                fenjing_id=fenjing_id,
                data={"path": str(save_path)},
            )

            if skip_upload:
                return True

            # 使用项目特定的TOS前缀，支持多项目并行
            project_prefixes = runtime_config.get_project_prefixes(project_name) if project_name else {}
            tos_video_prefix = project_prefixes.get("TOS_VIDEO_PREFIX", "")
            if video_filename:
                tos_key = f"{tos_video_prefix}/{chapter_name}/{video_filename}" if chapter_name else f"{tos_video_prefix}/{video_filename}"
            else:
                tos_key = f"{tos_video_prefix}/{chapter_name}/fenjing_{fenjing_id}_video.mp4" if chapter_name else f"{tos_video_prefix}/fenjing_{fenjing_id}_video.mp4"
            emit_event(
                "INFO",
                "video",
                "log",
                f"[Phase 5] Fenjing {fenjing_id}: Starting upload to TOS, bucket={runtime_config.TOS_BUCKET}, key={tos_key}",
                step="fenjing_prompts",
                project=project_name,
            )
            emit_event(
                "INFO",
                "video",
                "fenjing_video_upload_start",
                f"Fenjing {fenjing_id} upload to TOS start",
                step="fenjing_video_upload",
                project=project_name,
                chapter=chapter_name,
                fenjing_id=fenjing_id,
                data={"key": tos_key, "path": str(save_path)},
            )
            uploaded_url = tos.upload_file(runtime_config.TOS_BUCKET, tos_key, save_path)
            if uploaded_url:
                emit_event(
                    "INFO",
                    "video",
                    "log",
                    f"[Phase 5] Fenjing {fenjing_id}: Video uploaded to TOS successfully: {uploaded_url}",
                    step="fenjing_prompts",
                    project=project_name,
                )
                emit_event(
                    "INFO",
                    "video",
                    "fenjing_video_uploaded",
                    f"Fenjing {fenjing_id} uploaded to TOS",
                    step="fenjing_video_upload",
                    project=project_name,
                    chapter=chapter_name,
                    fenjing_id=fenjing_id,
                    data={"key": tos_key, "url": uploaded_url},
                )
                return True
            else:
                emit_event(
                    "ERROR",
                    "video",
                    "log",
                    f"[Phase 5] Fenjing {fenjing_id}: Failed to upload video to TOS, key={tos_key}",
                    step="fenjing_prompts",
                    project=project_name,
                )
                emit_event(
                    "ERROR",
                    "video",
                    "fenjing_video_upload_error",
                    f"Fenjing {fenjing_id} upload to TOS failed",
                    step="fenjing_video_upload",
                    project=project_name,
                    chapter=chapter_name,
                    fenjing_id=fenjing_id,
                    data={"key": tos_key},
                )
                return False
        else:
            emit_event(
                "ERROR",
                "video",
                "log",
                f"[Phase 5] Fenjing {fenjing_id}: Download function returned False",
                step="fenjing_prompts",
                project=project_name,
            )
            emit_event(
                "ERROR",
                "video",
                "fenjing_video_download_error",
                f"Fenjing {fenjing_id} download failed",
                step="fenjing_video_download",
                project=project_name,
                chapter=chapter_name,
                fenjing_id=fenjing_id,
            )
            return False
    except (IOError, OSError) as e:
        emit_event(
            "ERROR",
            "video",
            "log",
            f"[Phase 5] Fenjing {fenjing_id}: Exception during download/upload: {e}",
            step="fenjing_prompts",
            project=project_name,
        )
        emit_event(
            "ERROR",
            "video",
            "fenjing_video_download_upload_error",
            f"Fenjing {fenjing_id} download/upload exception: {e}",
            step="fenjing_video_download",
            project=project_name,
            chapter=chapter_name,
            fenjing_id=fenjing_id,
        )
        return False

async def submit_video_tasks_batch(
    prompts: List[Dict[str, Any]],
    duration_map: Dict[str, float],
    video_dir: Path,
    qps: float = runtime_config.VIDEO_TASK_QPS,
    chapter_name: Optional[str] = None,
    project_name: Optional[str] = None
) -> List[asyncio.Task]:
    """
    批量提交视频生成任务，QPS控制
    每个任务提交后立即独立处理，互不阻塞
    返回所有创建的任务列表，用于等待完成
    """
    # 在函数内部创建TosClientWrapper实例，确保runtime_config已加载
    tos_client = TosClientWrapper()
    
    project_info = f"[{project_name}] " if project_name else ""
    chapter_info = f"[{chapter_name}] " if chapter_name else ""
    prefix = f"{project_info}{chapter_info}"
    
    emit_event(
        "INFO",
        "video",
        "log",
        f"[Phase 3] Starting video task submission for {len(prompts)} items, QPS={qps}",
        step="general",
        project=project_name,
    )
    emit_event(
        "INFO",
        "video",
        "video_task_queue_start",
        "video task submission queue start",
        step="video_task_queue",
        project=project_name,
        chapter=chapter_name,
        data={"total": len(prompts), "qps": qps},
    )
    
    interval = 1.0 / qps
    submitted_count = 0
    tasks = []
    
    for item in prompts:
        fenjing_id = str(item.get("fenjing_id", ""))
        model_version = str(item.get("model", "1.5"))
        prompt = item.get("prompt", "")
        
        if not fenjing_id or not prompt:
            emit_event(
                "WARN",
                "video",
                "log",
                f"[Phase 3] Skipping item with missing fenjing_id or prompt: {item}",
                step="fenjing_prompts",
                project=project_name,
            )
            emit_event(
                "WARN",
                "video",
                "video_task_queue_skip",
                "video task submission skipped due to missing fields",
                step="video_task_queue",
                project=project_name,
                chapter=chapter_name,
                fenjing_id=str(fenjing_id) if fenjing_id else "",
            )
            continue
        
        if "1.0" in model_version:
            model_ep = runtime_config.VIDEO_MODEL_1_0_EP
            min_duration = runtime_config.VIDEO_MIN_DURATION_1_0
        else:
            model_ep = runtime_config.VIDEO_MODEL_1_5_EP
            min_duration = runtime_config.VIDEO_MIN_DURATION_1_5
        
        # 使用项目特定的TOS前缀，支持多项目并行
        project_prefixes = runtime_config.get_project_prefixes(project_name) if project_name else {}
        tos_fenjing_prefix = project_prefixes.get("TOS_FENJING_PREFIX", "")
        image_key = f"{tos_fenjing_prefix}/{chapter_name}/fenjing{fenjing_id}.png" if chapter_name else f"{tos_fenjing_prefix}/fenjing{fenjing_id}.png"
        image_url = tos_client.presign_get(runtime_config.TOS_BUCKET, image_key)
        
        if not image_url:
            emit_event(
                "ERROR",
                "video",
                "log",
                f"[Phase 3] Fenjing {fenjing_id}: Failed to get presigned URL for image: {image_key}",
                step="fenjing_prompts",
                project=project_name,
            )
            emit_event(
                "ERROR",
                "video",
                "video_task_queue_image_missing",
                f"Fenjing {fenjing_id} image presign failed",
                step="video_task_queue",
                project=project_name,
                chapter=chapter_name,
                fenjing_id=fenjing_id,
                data={"image_key": image_key},
            )
            continue
        
        audio_duration = duration_map.get(fenjing_id, 5.0)
        
        task = asyncio.create_task(process_single_video_independent(
            fenjing_id=fenjing_id,
            model_ep=model_ep,
            prompt=prompt,
            image_url=image_url,
            audio_duration=audio_duration,
            min_duration=min_duration,
            video_dir=video_dir,
            chapter_name=chapter_name,
            project_name=project_name
        ))
        tasks.append(task)
        
        submitted_count += 1
        emit_event(
            "INFO",
            "video",
            "log",
            f"[Phase 3] Fenjing {fenjing_id}: Task submitted ({submitted_count}/{len(prompts)})",
            step="fenjing_prompts",
            project=project_name,
        )
        emit_event(
            "INFO",
            "video",
            "video_task_submitted",
            f"Fenjing {fenjing_id} task submitted",
            step="video_task_queue",
            project=project_name,
            chapter=chapter_name,
            fenjing_id=fenjing_id,
            data={"submitted": submitted_count, "total": len(prompts), "qps": qps},
        )
        emit_event(
            "INFO",
            "video",
            "video_task_throttle_sleep",
            "video task submission throttling",
            step="video_task_queue",
            project=project_name,
            chapter=chapter_name,
            fenjing_id=fenjing_id,
            data={"sleep": interval, "qps": qps},
        )
        await asyncio.sleep(interval)
    
    emit_event(
        "INFO",
        "video",
        "log",
        f"[Phase 3] All {submitted_count} video tasks submitted, each task will process independently",
        step="general",
        project=project_name,
    )
    emit_event(
        "INFO",
        "video",
        "video_task_queue_complete",
        "video task submission queue complete",
        step="video_task_queue",
        project=project_name,
        chapter=chapter_name,
        data={"submitted": submitted_count, "total": len(prompts)},
    )
    return tasks

async def run_video_workflow(
    fenjing_prompts_path: Path,
    output_dir: Path,
    chapter_name: Optional[str] = None,
    video_prompts_path: Optional[Path] = None,
    project_name: Optional[str] = None
) -> None:
    project_info = f"[{project_name}] " if project_name else ""
    chapter_info = f"[{chapter_name}] " if chapter_name else ""
    prefix = f"{project_info}{chapter_name}"
    
    emit_event(
        "INFO",
        "video",
        "flow_start",
        "Video workflow started",
        step="start",
        project=project_name,
        chapter=chapter_name,
    )
    
    output_dir = normalize_output_dir(output_dir, project_name)
    video_dir = output_dir / "video" / chapter_name if chapter_name else output_dir / "video"
    ensure_dir(video_dir)
    
    # Phase 1：生成视频分镜提示词（含音频时长）
    emit_event(
        "INFO",
        "video",
        "phase_start",
        "phase1_video_prompts",
        step="phase1_video_prompts",
        phase="phase1_video_prompts",
        project=project_name,
        chapter=chapter_name,
    )
    emit_event(
        "INFO",
        "video",
        "phase_start",
        "PHASE 1: Get Audio Durations & Update Fenjing Prompts",
        step="phase1_video_prompts",
        phase="phase1_video_prompts",
        project=project_name,
        chapter=chapter_name,
    )

    fenjing_prompts = read_jsonl(str(fenjing_prompts_path))
    fenjing_ids = [str(item.get("fenjing_id", "")) for item in fenjing_prompts]
    
    emit_event(
        "INFO",
        "video",
        "log",
        f"[Phase 1] Found {len(fenjing_prompts)} fenjing items, getting audio durations...",
        step="fenjing_prompts",
        project=project_name,
    )
    
    # 批量获取音频时长
    duration_map = await batch_get_audio_durations(fenjing_ids, output_dir, chapter_name=chapter_name, qps=runtime_config.VIDEO_AUDIO_DURATION_QPS, prefix=prefix, project_name=project_name)
    
    # 将时长写入到 fenjing_prompts 中
    updated_prompts = []
    for item in fenjing_prompts:
        fenjing_id = str(item.get("fenjing_id", ""))
        duration = duration_map.get(fenjing_id, 5.0)
        final_duration = duration + 0.3  # 加0.3秒
        item["duration"] = final_duration  # 添加 duration 字段（已加0.3秒）
        updated_prompts.append(item)
        emit_event(
            "INFO",
            "video",
            "log",
            f"[Phase 1] Fenjing {fenjing_id}: Audio duration={duration:.2f}s, Final duration={final_duration:.2f}s (added 0.3s)",
            step="fenjing_prompts",
            project=project_name,
        )
    
    # 保存更新后的 fenjing_prompts.jsonl
    with open(fenjing_prompts_path, 'w', encoding='utf-8') as f:
        for item in updated_prompts:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')
    
    emit_event(
        "INFO",
        "video",
        "log",
        f"[Phase 1] Updated fenjing_prompts.jsonl with {len(updated_prompts)} items",
        step="fenjing_prompts",
        project=project_name,
    )

    # Phase 1: 生成视频提示词（同步，一次性）
    if not video_prompts_path or not video_prompts_path.exists():
        chapter_output_dir = fenjing_prompts_path.parent
        video_prompts_path = generate_video_prompts(fenjing_prompts_path, chapter_output_dir, chapter_name=chapter_name, project_name=project_name)

    emit_event(
        "INFO",
        "video",
        "phase_complete",
        f"phase1_video_prompts completed: {len(updated_prompts)}",
        step="phase1_video_prompts",
        phase="phase1_video_prompts",
        project=project_name,
        chapter=chapter_name,
        data={"count": len(updated_prompts)},
    )
    
    # Phase 2: 批量获取音频时长（并行，QPS=20）
    # 注意：这里已经不需要再获取音频时长了，因为已经在 Phase 0 获取并写入到 fenjing_prompts.jsonl 中
    # 但是为了保持原有逻辑，我们还是读取 video_prompts.jsonl 来获取 fenjing_ids
    prompts = read_jsonl(str(video_prompts_path))
    fenjing_ids = [str(item.get("fenjing_id", "")) for item in prompts]

    # Phase 2：提交任务、轮询、下载与上传
    # Phase 3: 批量提交视频生成任务（QPS=10，带重试）
    # Phase 4-5: 每个任务独立等待、轮询、下载、上传（完全独立，互不阻塞）
    
    # 从 fenjing_prompts.jsonl 中读取 duration（因为 video_prompts.jsonl 可能不包含 duration 字段）
    fenjing_duration_map = {str(item.get("fenjing_id", "")): item.get("duration", 5.0) for item in updated_prompts}
    emit_event(
        "INFO",
        "video",
        "phase_start",
        "phase2_video_generation",
        step="phase2_video_generation",
        phase="phase2_video_generation",
        project=project_name,
        chapter=chapter_name,
    )
    
    tasks = await submit_video_tasks_batch(prompts, fenjing_duration_map, video_dir, qps=runtime_config.VIDEO_TASK_QPS, chapter_name=chapter_name, project_name=project_name)
    emit_event(
        "INFO",
        "video",
        "step_progress",
        f"submitted video tasks: {len(tasks)}",
        step="video_task_submit",
        phase="phase2_video_generation",
        project=project_name,
        chapter=chapter_name,
        data={"total": len(tasks)},
    )
    
    # 等待所有任务完成
    results = await asyncio.gather(*tasks, return_exceptions=True)
    success_count = sum(1 for r in results if r is True)
    error_count = sum(1 for r in results if isinstance(r, Exception) or r is False)
    emit_event(
        "INFO",
        "video",
        "phase_complete",
        "phase2_video_generation completed",
        step="phase2_video_generation",
        phase="phase2_video_generation",
        project=project_name,
        chapter=chapter_name,
        data={"success": success_count, "error": error_count, "total": len(results)},
    )
    emit_event(
        "INFO",
        "video",
        "log",
        f"Video task summary: Success={success_count}, Error={error_count}, Total={len(results)}",
        step="general",
        project=project_name,
    )

async def run_video_workflow_multi(
    output_dir: Path,
    qps: float = runtime_config.VIDEO_TASK_QPS,
    tos_assets_prefix: Optional[str] = None,
    tos_bucket: Optional[str] = None,
    project_name: Optional[str] = None
) -> None:
    # 尝试从 output_dir 提取项目名称（在normalize之前）
    if not project_name:
        if "storyboard_assets" in output_dir.parts:
            project_idx = output_dir.parts.index("storyboard_assets")
            if project_idx > 0:
                project_name = output_dir.parts[project_idx - 1]
    
    output_dir = normalize_output_dir(output_dir, project_name)
    storyboards_dir = output_dir / "storyboards"
    
    scope = resolve_tos_assets_scope(tos_assets_prefix or "")
    assets_prefix = scope["assets_prefix"] or runtime_config.TOS_ASSETS_PREFIX
    fixed_chapter = scope["chapter_name"]
    chapters = sorted(storyboards_dir.glob("storyboard_chapter_*.jsonl"))
    if not chapters and tos_assets_prefix:
        ensure_dir(storyboards_dir)
        bucket = tos_bucket or runtime_config.TOS_BUCKET
        if fixed_chapter:
            chapter_jsonl_key = f"{assets_prefix.rstrip('/')}/storyboards/{fixed_chapter}.jsonl"
            chapter_jsonl_path = storyboards_dir / f"{fixed_chapter}.jsonl"
            if not chapter_jsonl_path.exists():
                _video_download_file_from_tos(bucket, chapter_jsonl_key, chapter_jsonl_path)
        else:
            prefix = f"{assets_prefix.rstrip('/')}/storyboards/"
            keys = list_tos_keys(bucket, prefix)
            for key in keys:
                name = key.split("/")[-1]
                if not (name.startswith("storyboard_chapter_") and name.endswith(".jsonl")):
                    continue
                local_path = storyboards_dir / name
                if not local_path.exists():
                    _video_download_file_from_tos(bucket, key, local_path)
        chapters = sorted(storyboards_dir.glob("storyboard_chapter_*.jsonl"))
    if not chapters and tos_assets_prefix:
        bucket = tos_bucket or runtime_config.TOS_BUCKET
        prefix = f"{assets_prefix.rstrip('/')}/storyboards/"
        keys = list_tos_keys(bucket, prefix)
        chapter_names = []
        for key in keys:
            chapter = extract_chapter_from_key(key)
            if chapter and chapter not in chapter_names:
                chapter_names.append(chapter)
        if chapter_names:
            chapters = [storyboards_dir / f"{name}.jsonl" for name in chapter_names]
    
    project_info = f"[{project_name}] " if project_name else ""
    prefix = project_info
    
    emit_event(
        "INFO",
        "video",
        "flow_start",
        "video workflow start",
        step="start",
        project=project_name,
    )
    if chapters:
        emit_event(
            "INFO",
            "video",
            "log",
            f"Found {len(chapters)} chapters for video workflow",
            step="general",
            project=project_name,
        )
    if not chapters:
        emit_event(
            "ERROR",
            "video",
            "flow_error",
            "No storyboard chapter files found",
            step="start",
            project=project_name,
        )
        emit_event(
            "WARN",
            "video",
            "log",
            f"No storyboard chapter files found.",
            step="general",
            project=project_name,
        )
        return

    tasks: List[asyncio.Task] = []
    bucket = tos_bucket or runtime_config.TOS_BUCKET
    loop = asyncio.get_running_loop()
    prompt_jobs: List[asyncio.Task] = []
    chapter_entries: List[Dict[str, Any]] = []
    interval = 1.0 / qps if qps > 0 else 0
    async def build_video_prompts_for_chapter(chapter_name: str, fenjing_prompts_path: Path, chapter_dir: Path) -> Path:
        video_prompts_path = chapter_dir / "shipin_prompts.jsonl"
        if video_prompts_path.exists():
            return video_prompts_path
        return await loop.run_in_executor(None, generate_video_prompts, fenjing_prompts_path, chapter_dir, chapter_name, project_name)
    for chapter_file in chapters:
        chapter_name = chapter_file.stem
        chapter_dir = storyboards_dir / chapter_name
        fenjing_prompts_path = chapter_dir / "fenjing_prompts.jsonl"
        if not fenjing_prompts_path.exists():
            key = f"{assets_prefix.rstrip('/')}/storyboards/{chapter_name}/fenjing_prompts.jsonl"
            _video_download_file_from_tos(bucket, key, fenjing_prompts_path)
        if not fenjing_prompts_path.exists():
            prefix = f"{assets_prefix.rstrip('/')}/storyboards/{chapter_name}/"
            keys = list_tos_keys(bucket, prefix)
            fallback_key = None
            for k in keys:
                if isinstance(k, str) and k.endswith("fenjing_prompts.jsonl"):
                    fallback_key = k
                    break
            if fallback_key:
                _video_download_file_from_tos(bucket, fallback_key, fenjing_prompts_path)
        if not fenjing_prompts_path.exists():
            emit_event(
                "WARN",
                "video",
                "log",
                f"Fenjing prompts not found for {chapter_name}, prefix={assets_prefix.rstrip('/')}/storyboards/{chapter_name}/",
                step="fenjing_prompts",
                project=project_name,
            )
            continue
        chapter_entries.append({
            "chapter_name": chapter_name,
            "fenjing_prompts_path": fenjing_prompts_path,
            "chapter_dir": chapter_dir
        })

    emit_event(
        "INFO",
        "video",
        "log",
        f"Prepared {len(chapter_entries)} chapters for video prompt generation, QPS={qps}",
        step="general",
        project=project_name,
    )
    if not chapter_entries:
        emit_event(
            "ERROR",
            "video",
            "flow_error",
            "No chapters with fenjing_prompts.jsonl found",
            step="prepare",
            project=project_name,
        )
        emit_event(
            "WARN",
            "video",
            "log",
            f"No chapters with fenjing_prompts.jsonl found.",
            step="fenjing_prompts",
            project=project_name,
        )
        return

    emit_event(
        "INFO",
        "video",
        "phase_complete",
        "prepare completed",
        step="prepare",
        phase="prepare",
        project=project_name,
    )

    for entry in chapter_entries:
        task = asyncio.create_task(build_video_prompts_for_chapter(entry["chapter_name"], entry["fenjing_prompts_path"], entry["chapter_dir"]))
        prompt_jobs.append(task)
        if interval > 0:
            await asyncio.sleep(interval)

    prompt_results = await asyncio.gather(*prompt_jobs, return_exceptions=True)
    for entry, result in zip(chapter_entries, prompt_results):
        if isinstance(result, Exception):
            emit_event(
                "ERROR",
                "video",
                "log",
                f"[{entry['chapter_name']}] Video prompt generation failed: {result}",
                step="general",
                project=project_name,
            )
            continue
        tasks.append(asyncio.create_task(
            run_video_workflow(
                entry["fenjing_prompts_path"],
                output_dir,
                chapter_name=entry["chapter_name"],
                video_prompts_path=result,
                project_name=project_name
            )
        ))
        if interval > 0:
            await asyncio.sleep(interval)
    results = await asyncio.gather(*tasks, return_exceptions=True)
    error_count = 0
    for r in results:
        if isinstance(r, Exception):
            error_count += 1
            emit_event(
                "ERROR",
                "video",
                "log",
                f"Video workflow failed: {r}",
                step="general",
                project=project_name,
            )

    if tasks:
        success_count = len(results) - error_count

        emit_event(
            "INFO",
            "video",
            "log",
            f"\nTask Summary: Success={success_count}, Error={error_count}, Total={len(results)}",
            step="general",
            project=project_name,
        )
    
    emit_event(
        "INFO",
        "video",
        "phase_complete",
        "fenjing_video_upload completed",
        step="fenjing_video_upload",
        phase="fenjing_video_upload",
        project=project_name,
    )
    
    if error_count > 0 and error_count == len(results):
        emit_event(
            "ERROR",
            "video",
            "flow_error",
            "Video Workflow Failed",
            step="complete",
            project=project_name,
        )
    else:
        emit_event(
            "INFO",
            "video",
            "flow_complete",
            "Video Workflow Completed",
            step="complete",
            project=project_name,
        )

async def run_video_prepare_prompts(
    output_dir: Path,
    qps: float = runtime_config.VIDEO_TASK_QPS,
    tos_assets_prefix: Optional[str] = None,
    tos_bucket: Optional[str] = None,
    project_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Phase: prepare_prompts - discover chapters, download fenjing_prompts, generate video prompts.

    Returns a list of chapter entry dicts (chapter_name, fenjing_prompts_path, chapter_dir, video_prompts_path).
    """
    if not project_name:
        if "storyboard_assets" in output_dir.parts:
            project_idx = output_dir.parts.index("storyboard_assets")
            if project_idx > 0:
                project_name = output_dir.parts[project_idx - 1]

    output_dir = normalize_output_dir(output_dir, project_name)
    storyboards_dir = output_dir / "storyboards"

    scope = resolve_tos_assets_scope(tos_assets_prefix or "")
    assets_prefix = scope["assets_prefix"] or runtime_config.TOS_ASSETS_PREFIX
    fixed_chapter = scope["chapter_name"]
    chapters = sorted(storyboards_dir.glob("storyboard_chapter_*.jsonl"))
    if not chapters and tos_assets_prefix:
        ensure_dir(storyboards_dir)
        bucket = tos_bucket or runtime_config.TOS_BUCKET
        if fixed_chapter:
            chapter_jsonl_key = f"{assets_prefix.rstrip('/')}/storyboards/{fixed_chapter}.jsonl"
            chapter_jsonl_path = storyboards_dir / f"{fixed_chapter}.jsonl"
            if not chapter_jsonl_path.exists():
                _video_download_file_from_tos(bucket, chapter_jsonl_key, chapter_jsonl_path)
        else:
            prefix = f"{assets_prefix.rstrip('/')}/storyboards/"
            keys = list_tos_keys(bucket, prefix)
            for key in keys:
                name = key.split("/")[-1]
                if not (name.startswith("storyboard_chapter_") and name.endswith(".jsonl")):
                    continue
                local_path = storyboards_dir / name
                if not local_path.exists():
                    _video_download_file_from_tos(bucket, key, local_path)
        chapters = sorted(storyboards_dir.glob("storyboard_chapter_*.jsonl"))
    if not chapters and tos_assets_prefix:
        bucket = tos_bucket or runtime_config.TOS_BUCKET
        prefix = f"{assets_prefix.rstrip('/')}/storyboards/"
        keys = list_tos_keys(bucket, prefix)
        chapter_names_list: List[str] = []
        for key in keys:
            chapter = extract_chapter_from_key(key)
            if chapter and chapter not in chapter_names_list:
                chapter_names_list.append(chapter)
        if chapter_names_list:
            chapters = [storyboards_dir / f"{name}.jsonl" for name in chapter_names_list]

    emit_event(
        "INFO",
        "video",
        "flow_start",
        "video workflow start (prepare_prompts)",
        step="start",
        project=project_name,
    )

    if not chapters:
        emit_event(
            "ERROR",
            "video",
            "flow_error",
            "No storyboard chapter files found",
            step="start",
            project=project_name,
        )
        return []

    emit_event(
        "INFO",
        "video",
        "log",
        f"Found {len(chapters)} chapters for video prompt preparation",
        step="general",
        project=project_name,
    )

    bucket = tos_bucket or runtime_config.TOS_BUCKET
    chapter_entries: List[Dict[str, Any]] = []
    for chapter_file in chapters:
        chapter_name = chapter_file.stem
        chapter_dir = storyboards_dir / chapter_name
        fenjing_prompts_path = chapter_dir / "fenjing_prompts.jsonl"
        if not fenjing_prompts_path.exists():
            key = f"{assets_prefix.rstrip('/')}/storyboards/{chapter_name}/fenjing_prompts.jsonl"
            _video_download_file_from_tos(bucket, key, fenjing_prompts_path)
        if not fenjing_prompts_path.exists():
            prefix = f"{assets_prefix.rstrip('/')}/storyboards/{chapter_name}/"
            keys = list_tos_keys(bucket, prefix)
            fallback_key = None
            for k in keys:
                if isinstance(k, str) and k.endswith("fenjing_prompts.jsonl"):
                    fallback_key = k
                    break
            if fallback_key:
                _video_download_file_from_tos(bucket, fallback_key, fenjing_prompts_path)
        if not fenjing_prompts_path.exists():
            emit_event(
                "WARN",
                "video",
                "log",
                f"Fenjing prompts not found for {chapter_name}",
                step="fenjing_prompts",
                project=project_name,
            )
            continue
        chapter_entries.append({
            "chapter_name": chapter_name,
            "fenjing_prompts_path": fenjing_prompts_path,
            "chapter_dir": chapter_dir,
        })

    if not chapter_entries:
        emit_event(
            "ERROR",
            "video",
            "flow_error",
            "No chapters with fenjing_prompts.jsonl found",
            step="prepare",
            project=project_name,
        )
        return []

    emit_event(
        "INFO",
        "video",
        "phase_complete",
        "prepare completed",
        step="prepare",
        phase="prepare",
        project=project_name,
    )

    # Generate video prompts for each chapter
    interval = 1.0 / qps if qps > 0 else 0
    loop = asyncio.get_running_loop()

    async def build_video_prompts_for_chapter(ch_name: str, fp_path: Path, ch_dir: Path) -> Path:
        video_prompts_path = ch_dir / "shipin_prompts.jsonl"
        if video_prompts_path.exists():
            return video_prompts_path
        return await loop.run_in_executor(None, generate_video_prompts, fp_path, ch_dir, ch_name, project_name)

    prompt_jobs: List[asyncio.Task] = []
    for entry in chapter_entries:
        task = asyncio.create_task(build_video_prompts_for_chapter(
            entry["chapter_name"], entry["fenjing_prompts_path"], entry["chapter_dir"]
        ))
        prompt_jobs.append(task)
        if interval > 0:
            await asyncio.sleep(interval)

    prompt_results = await asyncio.gather(*prompt_jobs, return_exceptions=True)
    for entry, result in zip(chapter_entries, prompt_results):
        if isinstance(result, Exception):
            emit_event(
                "ERROR",
                "video",
                "log",
                f"[{entry['chapter_name']}] Video prompt generation failed: {result}",
                step="general",
                project=project_name,
            )
        else:
            entry["video_prompts_path"] = result

    emit_event(
        "INFO",
        "video",
        "phase_complete",
        "phase1_video_prompts completed",
        step="phase1_video_prompts",
        phase="phase1_video_prompts",
        project=project_name,
    )

    return chapter_entries


async def run_video_generate_only(
    output_dir: Path,
    project_name: Optional[str] = None,
) -> Tuple[int, int]:
    """Phase: generate_videos - scan for existing shipin_prompts.jsonl, generate videos, download to local (skip TOS upload).

    Returns (success_count, error_count).
    """
    if not project_name:
        if "storyboard_assets" in output_dir.parts:
            project_idx = output_dir.parts.index("storyboard_assets")
            if project_idx > 0:
                project_name = output_dir.parts[project_idx - 1]

    output_dir = normalize_output_dir(output_dir, project_name)
    storyboards_dir = output_dir / "storyboards"

    emit_event(
        "INFO",
        "video",
        "flow_start",
        "video workflow start (generate_videos)",
        step="start",
        project=project_name,
    )

    # Discover chapters that already have shipin_prompts.jsonl
    chapter_dirs = sorted(storyboards_dir.glob("storyboard_chapter_*"))
    chapter_entries: List[Dict[str, Any]] = []
    for ch_dir in chapter_dirs:
        if not ch_dir.is_dir():
            continue
        shipin_path = ch_dir / "shipin_prompts.jsonl"
        fenjing_path = ch_dir / "fenjing_prompts.jsonl"
        if not shipin_path.exists():
            continue
        chapter_entries.append({
            "chapter_name": ch_dir.name,
            "chapter_dir": ch_dir,
            "shipin_prompts_path": shipin_path,
            "fenjing_prompts_path": fenjing_path,
        })

    if not chapter_entries:
        emit_event(
            "ERROR",
            "video",
            "flow_error",
            "No chapters with shipin_prompts.jsonl found for generate_videos",
            step="phase2_video_generation",
            project=project_name,
        )
        return (0, 0)

    emit_event(
        "INFO",
        "video",
        "log",
        f"Found {len(chapter_entries)} chapters for video generation",
        step="general",
        project=project_name,
    )

    tos_client = TosClientWrapper()
    all_tasks: List[asyncio.Task] = []

    for entry in chapter_entries:
        chapter_name = entry["chapter_name"]
        shipin_path = entry["shipin_prompts_path"]
        fenjing_path = entry["fenjing_prompts_path"]
        video_dir = output_dir / "video" / chapter_name
        ensure_dir(video_dir)

        prompts = read_jsonl(str(shipin_path))
        # Build duration map from fenjing_prompts.jsonl
        fenjing_duration_map: Dict[str, float] = {}
        if fenjing_path.exists():
            fenjing_items = read_jsonl(str(fenjing_path))
            fenjing_duration_map = {str(item.get("fenjing_id", "")): item.get("duration", 5.0) for item in fenjing_items}

        interval = 1.0 / runtime_config.VIDEO_TASK_QPS if runtime_config.VIDEO_TASK_QPS > 0 else 0

        for item in prompts:
            fenjing_id = str(item.get("fenjing_id", ""))
            model_version = str(item.get("model", "1.5"))
            prompt = item.get("prompt", "")
            if not fenjing_id or not prompt:
                continue

            if "1.0" in model_version:
                model_ep = runtime_config.VIDEO_MODEL_1_0_EP
                min_duration = runtime_config.VIDEO_MIN_DURATION_1_0
            else:
                model_ep = runtime_config.VIDEO_MODEL_1_5_EP
                min_duration = runtime_config.VIDEO_MIN_DURATION_1_5

            project_prefixes = runtime_config.get_project_prefixes(project_name) if project_name else {}
            tos_fenjing_prefix = project_prefixes.get("TOS_FENJING_PREFIX", "")
            image_key = f"{tos_fenjing_prefix}/{chapter_name}/fenjing{fenjing_id}.png" if chapter_name else f"{tos_fenjing_prefix}/fenjing{fenjing_id}.png"
            image_url = tos_client.presign_get(runtime_config.TOS_BUCKET, image_key)
            if not image_url:
                continue

            audio_duration = fenjing_duration_map.get(fenjing_id, 5.0)

            task = asyncio.create_task(process_single_video_independent(
                fenjing_id=fenjing_id,
                model_ep=model_ep,
                prompt=prompt,
                image_url=image_url,
                audio_duration=audio_duration,
                min_duration=min_duration,
                video_dir=video_dir,
                chapter_name=chapter_name,
                project_name=project_name,
                skip_upload=True,
            ))
            all_tasks.append(task)
            if interval > 0:
                await asyncio.sleep(interval)

    if not all_tasks:
        emit_event(
            "WARN",
            "video",
            "log",
            "No video tasks created for generate_videos phase",
            step="phase2_video_generation",
            project=project_name,
        )
        return (0, 0)

    results = await asyncio.gather(*all_tasks, return_exceptions=True)
    success_count = sum(1 for r in results if r is True)
    error_count = sum(1 for r in results if isinstance(r, Exception) or r is False)

    emit_event(
        "INFO",
        "video",
        "phase_complete",
        "phase2_video_generation completed",
        step="phase2_video_generation",
        phase="phase2_video_generation",
        project=project_name,
        data={"success": success_count, "error": error_count, "total": len(results)},
    )

    return (success_count, error_count)


async def run_video_upload_only(
    output_dir: Path,
    project_name: Optional[str] = None,
) -> Tuple[int, int]:
    """Phase: upload_videos - scan local MP4 files and upload to TOS.

    Returns (success_count, error_count).
    """
    if not project_name:
        if "storyboard_assets" in output_dir.parts:
            project_idx = output_dir.parts.index("storyboard_assets")
            if project_idx > 0:
                project_name = output_dir.parts[project_idx - 1]

    output_dir = normalize_output_dir(output_dir, project_name)

    emit_event(
        "INFO",
        "video",
        "flow_start",
        "video workflow start (upload_videos)",
        step="start",
        project=project_name,
    )

    tos = TosClientWrapper()
    if not tos.available():
        emit_event(
            "ERROR",
            "video",
            "flow_error",
            "TOS client not available for upload",
            step="fenjing_video_upload",
            project=project_name,
        )
        return (0, 0)

    project_prefixes = runtime_config.get_project_prefixes(project_name) if project_name else {}
    tos_video_prefix = project_prefixes.get("TOS_VIDEO_PREFIX", "")

    video_base = output_dir / "video"
    if not video_base.exists():
        emit_event(
            "WARN",
            "video",
            "log",
            "No video directory found for upload",
            step="fenjing_video_upload",
            project=project_name,
        )
        return (0, 0)

    success_count = 0
    error_count = 0

    for chapter_dir in sorted(video_base.iterdir()):
        if not chapter_dir.is_dir():
            continue
        chapter_name = chapter_dir.name
        for mp4_file in sorted(chapter_dir.glob("fenjing_*_video.mp4")):
            tos_key = f"{tos_video_prefix}/{chapter_name}/{mp4_file.name}"
            emit_event(
                "INFO",
                "video",
                "fenjing_video_upload_start",
                f"Uploading {mp4_file.name} to TOS",
                step="fenjing_video_upload",
                project=project_name,
                chapter=chapter_name,
                data={"key": tos_key, "path": str(mp4_file)},
            )
            uploaded_url = tos.upload_file(runtime_config.TOS_BUCKET, tos_key, mp4_file)
            if uploaded_url:
                emit_event(
                    "INFO",
                    "video",
                    "fenjing_video_uploaded",
                    f"Uploaded {mp4_file.name} to TOS",
                    step="fenjing_video_upload",
                    project=project_name,
                    chapter=chapter_name,
                    data={"key": tos_key, "url": uploaded_url},
                )
                success_count += 1
            else:
                emit_event(
                    "ERROR",
                    "video",
                    "fenjing_video_upload_error",
                    f"Failed to upload {mp4_file.name} to TOS",
                    step="fenjing_video_upload",
                    project=project_name,
                    chapter=chapter_name,
                    data={"key": tos_key},
                )
                error_count += 1

    emit_event(
        "INFO",
        "video",
        "phase_complete",
        "fenjing_video_upload completed",
        step="fenjing_video_upload",
        phase="fenjing_video_upload",
        project=project_name,
        data={"success": success_count, "error": error_count},
    )

    return (success_count, error_count)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2:
        arg1 = sys.argv[1]
        arg2 = sys.argv[2]
        if isinstance(arg1, str) and arg1.startswith("tos://"):
            tos_info = parse_tos_uri(arg1)
            if tos_info:
                local_out = Path(runtime_config.OUTPUT_DIR) / runtime_config.PROJECT_NAME / "storyboard_assets"
                asyncio.run(run_video_workflow_multi(local_out, tos_assets_prefix=tos_info["prefix"], tos_bucket=tos_info["bucket"]))
            else:
                asyncio.run(run_video_workflow_multi(Path(arg2)))
        else:
            asyncio.run(run_video_workflow(Path(arg1), Path(arg2)))
    elif len(sys.argv) > 1:
        arg1 = sys.argv[1]
        if isinstance(arg1, str) and arg1.startswith("tos://"):
            tos_info = parse_tos_uri(arg1)
            if tos_info:
                local_out = Path(runtime_config.OUTPUT_DIR) / runtime_config.PROJECT_NAME / "storyboard_assets"
                asyncio.run(run_video_workflow_multi(local_out, tos_assets_prefix=tos_info["prefix"], tos_bucket=tos_info["bucket"]))
            else:
                asyncio.run(run_video_workflow_multi(Path(arg1)))
        else:
            asyncio.run(run_video_workflow_multi(Path(arg1)))
