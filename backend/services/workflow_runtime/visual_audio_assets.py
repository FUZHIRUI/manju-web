import json
import re
import asyncio
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import runtime_config
from .io_jsonl import read_jsonl, write_jsonl
from .provider_runtime import (
    TosClientWrapper, chat, generate_tts_audios, qc_image_async, generate_and_download, generate_and_download_with_refs, run_async, emit_event,
    get_image_concurrency,
    with_concurrency_limit,
    with_thread_pool_limit,
    generate_image,
)
from .json_parse import parse_json_list as parse_json_list_shared
from .json_fields import enforce_prompt_fields

PROMPT_DIR = Path(__file__).resolve().parent / "prompt"
FULL_PHASE_SET = {"download_assets", "build_prompts", "generate_images", "generate_tts", "cloth_images", "cloth_changed", "upload_assets"}


def is_full_phase_run(phases: set) -> bool:
    return phases == FULL_PHASE_SET


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def resolve_character_size_by_attribute(attribute: Optional[str]) -> Optional[str]:
    if isinstance(attribute, str):
        attr = attribute.strip()
        if attr == "人类":
            return runtime_config.CHARACTER_HUMAN_IMAGE_SIZE
        if attr == "兽类":
            return runtime_config.CHARACTER_BEAST_IMAGE_SIZE
    return None


async def generate_images_with_qps(
    prompts_jsonl_path: Path,
    name_key: str,
    out_subdir: str,
    on_image_callback: Optional[callable] = None,
    project_name: Optional[str] = None
) -> List[Path]:
    prompts = read_jsonl(str(prompts_jsonl_path))
    out_dir = prompts_jsonl_path.parent / out_subdir
    ensure_dir(out_dir)
    results: List[Path] = []

    concurrency = runtime_config.IMAGE_MODEL_CONCURRENCY
    
    # 使用传入的项目名称或从路径推断
    if project_name is None:
        project_name = prompts_jsonl_path.parent.parent.name

    def _build_prompt_pairs(item: Dict[str, Any]) -> Tuple[List[Tuple[str, str]], Optional[str]]:
        lower_item = {str(k).lower(): v for k, v in item.items()}
        id_val = lower_item.get(name_key.lower()) or item.get("Location_Id") or item.get(name_key) or "item"
        pairs: List[Tuple[str, str]] = []
        size_override = resolve_character_size_by_attribute(item.get("attribute")) if name_key == "Character_Id" else None

        if name_key == "location_id":
            ps = item.get("prompt_standing")
            if isinstance(ps, str) and ps.strip():
                pairs.append((ps, f"{id_val}_standing"))
            psit = item.get("prompt_sitting")
            if isinstance(psit, str) and psit.strip():
                pairs.append((psit, f"{id_val}_sitting"))
        elif name_key == "Character_Id":
            sp = item.get("st_prompt")
            if isinstance(sp, str) and sp.strip():
                pairs.append((sp, f"{id_val}"))
            else:
                p = item.get("prompt")
                if isinstance(p, str) and p.strip():
                    pairs.append((p, f"{id_val}"))
        else:
            p = item.get("prompt")
            if isinstance(p, str) and p.strip():
                pairs.append((p, f"{id_val}"))
        return pairs, size_override

    async def process_single_prompt(item: Dict[str, Any], idx: int) -> None:
        pairs, size_override = _build_prompt_pairs(item)
        async with with_concurrency_limit(concurrency):
            for prompt_text, name_prefix in pairs:
                emit_event(
                    "INFO",
                    "visual_audio_assets",
                    "generate_progress",
                    f"Generating Image - {name_prefix}, Progress: {idx+1}/{len(prompts)}",
                    step="generate_images",
                    project=project_name,
                    data={"name_prefix": name_prefix, "progress": idx+1, "total": len(prompts)},
                )
                p = await generate_image(prompt_text, out_dir, name_prefix, size=size_override)
                if isinstance(p, Path):
                    results.append(p)
                    if on_image_callback:
                        await on_image_callback(p, item, idx)

    tasks = [process_single_prompt(item, idx) for idx, item in enumerate(prompts)]
    await asyncio.gather(*tasks, return_exceptions=True)
    return results


def _vaa_download_file_from_tos(tos: TosClientWrapper, bucket: str, key: str, local_path: Path, project_name: Optional[str] = None) -> bool:
    if not tos.available():
        return False
    # 使用传入的项目名称或从路径推断
    if project_name is None:
        project_name = local_path.parent.parent.name
    try:
        client = tos._client if hasattr(tos, "_client") else None
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
            "visual_audio_assets",
            "download_failed",
            f"Failed to download {key}: {e}",
            step="download_assets",
            project=project_name,
            data={"key": key, "error": str(e)},
        )
        return False


def download_assets_from_tos(local_base_dir: Path, project_name: Optional[str] = None) -> bool:
    tos = TosClientWrapper()
    # 使用传入的项目名称或从目录推断（只推断一次，避免并发问题）
    current_proj_name = project_name if project_name is not None else local_base_dir.parent.name

    if not tos.available():
        emit_event(
            "WARN",
            "visual_audio_assets",
            "download_skipped",
            "TOS client not available, cannot download assets",
            step="download_assets",
            project=current_proj_name,
        )
        return False

    # 使用项目特定的TOS前缀，支持多项目并行
    project_prefixes = runtime_config.get_project_prefixes(current_proj_name)
    tos_assets_prefix = project_prefixes.get("TOS_ASSETS_PREFIX", "")

    emit_event(
        "INFO",
        "visual_audio_assets",
        "download_start",
        f"Checking and downloading assets from TOS: {runtime_config.TOS_BUCKET}/{tos_assets_prefix}",
        step="download_assets",
        project=current_proj_name,
        data={"bucket": runtime_config.TOS_BUCKET, "prefix": tos_assets_prefix},
    )

    files_to_sync = ["characters.jsonl", "locations.jsonl", "summaries.jsonl"]
    success = False

    for fname in files_to_sync:
        local_path = local_base_dir / fname
        if tos_assets_prefix:
            key = f"{tos_assets_prefix}/{fname}"
        else:
            key = ""
        should_download = fname in {"characters.jsonl", "locations.jsonl"} or not local_path.exists()
        if should_download and key:
            emit_event(
                "INFO",
                "visual_audio_assets",
                "download_progress",
                f"Downloading {fname} from TOS",
                step="download_assets",
                project=current_proj_name,
                data={"file": fname},
            )
            if _vaa_download_file_from_tos(tos, runtime_config.TOS_BUCKET, key, local_path, project_name=current_proj_name):
                emit_event(
                    "INFO",
                    "visual_audio_assets",
                    "download_progress",
                    f"Downloaded {fname}",
                    step="download_assets",
                    project=current_proj_name,
                    data={"file": fname, "ok": True},
                )
                success = True
            else:
                emit_event(
                    "WARN",
                    "visual_audio_assets",
                    "download_failed",
                    f"Failed to download {fname}",
                    step="download_assets",
                    project=current_proj_name,
                    data={"file": fname, "ok": False},
                )
                if fname in {"characters.jsonl", "locations.jsonl"}:
                    return False
        else:
            emit_event(
                "INFO",
                "visual_audio_assets",
                "download_skipped",
                f"{fname} already exists locally, skipping download",
                step="download_assets",
                project=current_proj_name,
                data={"file": fname},
            )
            success = True

    return success


def load_upload_jsonl(base_dir: Path, filename: str, project_name: Optional[str] = None) -> List[Dict[str, Any]]:
    target_path = base_dir / filename
    if not target_path.exists():
        tos = TosClientWrapper()
        if tos.available():
            # 使用项目特定的TOS前缀，支持多项目并行
            project_prefixes = runtime_config.get_project_prefixes(project_name) if project_name else {}
            tos_assets_prefix = project_prefixes.get("TOS_ASSETS_PREFIX", "")
            if tos_assets_prefix:
                key = f"{tos_assets_prefix}/{filename}"
                _vaa_download_file_from_tos(tos, runtime_config.TOS_BUCKET, key, target_path)
    if target_path.exists():
        try:
            return read_jsonl(str(target_path))
        except (IOError, OSError):
            return []
    return []


def parse_json_list(content: str) -> List[Any]:
    return parse_json_list_shared(content)


def extract_and_fix_fenjing_prompts(content: str, expected_count: int, project_name: Optional[str] = None) -> List[Dict[str, Any]]:
    emit_event(
        "DEBUG",
        "visual_audio_assets",
        "parse_debug",
        f"AI returned content (first 500 chars): {content[:500]}",
        step="fenjing_prompts",
        project=project_name,
        data={"content_preview": content[:500]},
    )
    prompts = parse_json_list(content)
    emit_event(
        "DEBUG",
        "visual_audio_assets",
        "parse_debug",
        f"Parsed {len(prompts)} prompts from AI response",
        step="fenjing_prompts",
        project=project_name,
        data={"parsed_count": len(prompts)},
    )

    if not prompts or len(prompts) == 0:
        emit_event(
            "WARN",
            "visual_audio_assets",
            "log",
            f"No prompts found in AI response, will retry",
            step="general",
            project=project_name,
        )
        return []

    if len(prompts) != expected_count:
        emit_event(
            "WARN",
            "visual_audio_assets",
            "log",
            f"Prompt count mismatch: expected {expected_count}, got {len(prompts)}, will retry",
            step="general",
            project=project_name,
        )
        return []

    valid_prompts: List[Dict[str, Any]] = []

    for idx, p in enumerate(prompts):
        if not isinstance(p, dict):
            emit_event(
                "WARN",
                "visual_audio_assets",
                "parse_warning",
                f"Prompt at index {idx} is not a dict, will retry",
                step="fenjing_prompts",
                project=project_name,
                data={"index": idx},
            )
            return []

        if "prompt" not in p or not p["prompt"]:
            emit_event(
                "WARN",
                "visual_audio_assets",
                "parse_warning",
                f"Prompt at index {idx} missing 'prompt' field, will retry",
                step="fenjing_prompts",
                project=project_name,
                data={"index": idx},
            )
            return []

        if "fenjing_id" not in p:
            emit_event(
                "WARN",
                "visual_audio_assets",
                "parse_warning",
                f"Prompt at index {idx} missing 'fenjing_id' field, will retry",
                step="fenjing_prompts",
                project=project_name,
                data={"index": idx},
            )
            return []

        valid_prompts.append(p)

    emit_event(
        "INFO",
        "visual_audio_assets",
        "parse_complete",
        f"All {len(valid_prompts)} prompts are valid",
        step="fenjing_prompts",
        project=project_name,
        data={"valid_count": len(valid_prompts)},
    )
    return valid_prompts


def build_location_prompt_map(location_prompts_jsonl: Path) -> Dict[str, Dict[str, str]]:
    locs = read_jsonl(str(location_prompts_jsonl))
    out: Dict[str, Dict[str, str]] = {}
    for loc in locs:
        if not isinstance(loc, dict):
            continue
        loc_id = loc.get("Location_Id") or loc.get("location_id")
        if not isinstance(loc_id, str) or not loc_id:
            continue
        ps = loc.get("prompt_standing")
        psit = loc.get("prompt_sitting")
        d: Dict[str, str] = {}
        if isinstance(ps, str) and ps.strip():
            d["standing"] = ps
        if isinstance(psit, str) and psit.strip():
            d["sitting"] = psit
        if d:
            out[loc_id] = d
    return out


def norm_bg_type(value: Any) -> str:
    if value is None:
        return "standing"
    s = str(value).strip().lower()
    if not s:
        return "standing"
    if "sitting" in s or "坐" in s:
        return "sitting"
    if s in ("standing", "standding"):
        return "standing"
    if s in ("sitting", "siting"):
        return "sitting"
    return "standing"


def collect_needed_locations(fenjing_prompts_paths: List[Path]) -> List[Tuple[str, str]]:
    needed: Dict[Tuple[str, str], bool] = {}
    for p in fenjing_prompts_paths:
        prompts = read_jsonl(str(p))
        for it in prompts:
            if not isinstance(it, dict):
                continue
            loc_id = it.get("Location_Id") or it.get("location_id") or it.get("Background_pic")
            if not isinstance(loc_id, str) or not loc_id:
                continue
            bg_type = norm_bg_type(it.get("Background_xuanze"))
            needed[(loc_id, bg_type)] = True
    return list(needed.keys())


async def generate_location_images_shared(
    location_prompt_map: Dict[str, Dict[str, str]],
    out_dir: Path,
    needed: Optional[List[Tuple[str, str]]] = None, project_name: Optional[str] = None) -> Dict[str, Dict[str, str]]:
    ensure_dir(out_dir)
    tos = TosClientWrapper()
    results: Dict[str, Dict[str, str]] = {}
    concurrency = runtime_config.IMAGE_MODEL_CONCURRENCY

    # 使用项目特定的TOS前缀，支持多项目并行
    project_prefixes = runtime_config.get_project_prefixes(project_name) if project_name else {}
    tos_location_prefix = project_prefixes.get("TOS_LOCATION_PREFIX", "")

    async def _upload_and_emit(p: Path, loc_id: str, bg_type: str) -> Optional[str]:
        if not tos_location_prefix:
            emit_event(
                "WARN",
                "visual_audio_assets",
                "upload_progress",
                "location image upload skipped: missing TOS prefix",
                step="location_images",
                project=project_name,
                data={"image_type": "location", "image_id": loc_id, "bg_type": bg_type, "ok": False, "reason": "missing_prefix"},
            )
            return None
        key = f"{tos_location_prefix}/{p.name}"
        uri = tos.upload_file(runtime_config.TOS_BUCKET, key, p) if tos.available() else None
        presigned = tos.presign_get(runtime_config.TOS_BUCKET, key) if tos.available() else None
        emit_event(
            "INFO",
            "visual_audio_assets",
            "upload_progress",
            f"location image uploaded: {p.name}",
            step="location_images",
            project=project_name,
            data={
                "file": p.name,
                "key": key,
                "uri": uri,
                "presigned": presigned,
                "image_type": "location",
                "image_id": loc_id,
                "bg_type": bg_type,
                "ok": True,
            },
        )
        return presigned

    async def process_pair(loc_id: str, bg_type: str, prompt_text: str) -> Optional[Tuple[str, str, str]]:
        if not isinstance(prompt_text, str) or not prompt_text.strip():
            emit_event(
                "WARN",
                "visual_audio_assets",
                "upload_progress",
                "location image skipped: empty prompt",
                step="location_images",
                project=project_name,
                data={"image_type": "location", "image_id": loc_id, "bg_type": bg_type, "ok": False, "reason": "empty_prompt"},
            )
            return None
        async with with_concurrency_limit(concurrency):
            name_prefix = f"{loc_id}_{bg_type}"
            p = await generate_image(prompt_text, out_dir, name_prefix)
            if not isinstance(p, Path):
                emit_event(
                    "ERROR",
                    "visual_audio_assets",
                    "upload_progress",
                    "location image generation failed",
                    step="location_images",
                    project=project_name,
                    data={"image_type": "location", "image_id": loc_id, "bg_type": bg_type, "ok": False},
                )
                return None
            presigned = await _upload_and_emit(p, loc_id, bg_type)
            if not presigned:
                return None
            return (loc_id, bg_type, presigned)

    tasks = []
    if needed is None:
        for loc_id, d in location_prompt_map.items():
            if not isinstance(loc_id, str) or not loc_id:
                continue
            for bg_type in ("standing", "sitting"):
                prompt_text = d.get(bg_type)
                if isinstance(prompt_text, str) and prompt_text.strip():
                    tasks.append(asyncio.create_task(process_pair(loc_id, bg_type, prompt_text)))
    else:
        for loc_id, bg_type in needed:
            prompt_cfg = location_prompt_map.get(loc_id) or {}
            prompt_text = prompt_cfg.get(bg_type)
            if isinstance(prompt_text, str) and prompt_text.strip():
                tasks.append(asyncio.create_task(process_pair(loc_id, bg_type, prompt_text)))
            else:
                emit_event(
                    "WARN",
                    "visual_audio_assets",
                    "upload_progress",
                    "location image skipped: missing prompt",
                    step="location_images",
                    project=project_name,
                    data={"image_type": "location", "image_id": loc_id, "bg_type": bg_type, "ok": False, "reason": "missing_prompt"},
                )

    for r in await asyncio.gather(*tasks, return_exceptions=True):
        if isinstance(r, tuple):
            loc_id, bg_type, presigned = r
            d = results.get(loc_id) or {}
            d[bg_type] = presigned
            results[loc_id] = d
        elif isinstance(r, Exception):
            emit_event(
                "ERROR",
                "visual_audio_assets",
                "flow_error",
                f"location image task failed: {r}",
                step="location_images",
                project=project_name,
            )
    return results


def build_fenjing_prompts_with_retry(
    storyboards_jsonl_path: Path,
    prompt_path: str,
    max_retries: int = 2, project_name: Optional[str] = None) -> Path:
    system_prompt = read_text(prompt_path)
    boards = read_jsonl(str(storyboards_jsonl_path))
    output_path = storyboards_jsonl_path.parent / "fenjing_prompts.jsonl"
    expected_count = len(boards)
    thinking = runtime_config.FENJING_THINKING if runtime_config.FENJING_THINKING != "disabled" else None
    reasoning_effort = runtime_config.FENJING_REASONING_EFFORT if runtime_config.FENJING_REASONING_EFFORT != "disabled" else None

    for attempt in range(max_retries + 1):
        emit_event(
            "INFO",
            "visual_audio_assets",
            "build_progress",
            f"Building Fenjing Prompts (Attempt {attempt + 1}/{max_retries + 1}) - {storyboards_jsonl_path.name}",
            step="fenjing_prompts",
            project=project_name,
            data={"attempt": attempt + 1, "max_retries": max_retries + 1, "file": storyboards_jsonl_path.name},
        )
        try:
            start_time = time.time()
            user_texts = [json.dumps(boards, ensure_ascii=False)]
            result = chat([system_prompt], user_texts, thinking=thinking, reasoning_effort=reasoning_effort)
            content = result["content"]
            elapsed = time.time() - start_time
            emit_event(
                "INFO",
                "visual_audio_assets",
                "api_complete",
                f"Fenjing prompt call done - elapsed={elapsed:.2f}s, chapter={storyboards_jsonl_path.name}",
                step="fenjing_prompts",
                project=project_name,
                data={"elapsed": elapsed, "file": storyboards_jsonl_path.name},
            )
            
            valid_prompts = extract_and_fix_fenjing_prompts(content, expected_count)

            if len(valid_prompts) == 0:
                emit_event(
                    "WARN",
                    "visual_audio_assets",
                    "parse_warning",
                    "No valid prompts found after extraction and fixing",
                    step="fenjing_prompts",
                    project=project_name,
                )
                if attempt < max_retries:
                    continue
                emit_event(
                    "ERROR",
                    "visual_audio_assets",
                    "flow_error",
                    f"Fenjing prompts 重试超限: {storyboards_jsonl_path.name}",
                    step="fenjing_prompts",
                    project=project_name,
                    data={"file": storyboards_jsonl_path.name, "attempt": attempt + 1, "max_retries": max_retries + 1},
                )
                raise ValueError("No valid fenjing prompts generated after all retries")
            
            if len(valid_prompts) != expected_count:
                emit_event(
                    "WARN",
                    "visual_audio_assets",
                    "parse_warning",
                    f"Prompt count mismatch: expected {expected_count}, got {len(valid_prompts)}",
                    step="fenjing_prompts",
                    project=project_name,
                    data={"expected": expected_count, "actual": len(valid_prompts)},
                )
                if attempt < max_retries:
                    emit_event(
                        "INFO",
                        "visual_audio_assets",
                        "retry",
                        "Retrying to get correct count",
                        step="fenjing_prompts",
                        project=project_name,
                    )
                    continue
                emit_event(
                    "ERROR",
                    "visual_audio_assets",
                    "flow_error",
                    f"Fenjing prompts 数量不匹配且重试超限: {storyboards_jsonl_path.name}",
                    step="fenjing_prompts",
                    project=project_name,
                    data={
                        "file": storyboards_jsonl_path.name,
                        "expected": expected_count,
                        "actual": len(valid_prompts),
                        "attempt": attempt + 1,
                        "max_retries": max_retries + 1,
                    },
                )
            
            write_jsonl(str(output_path), valid_prompts)
            emit_event(
                "INFO",
                "visual_audio_assets",
                "log",
                f"Fenjing Prompts saved to: {output_path}, count: {len(valid_prompts)}",
                step="fenjing_prompts",
                project=project_name,
            )
            return output_path
        except (IOError, OSError, ValueError) as e:
            emit_event(
                "ERROR",
                "visual_audio_assets",
                "log",
                f"Failed to build fenjing prompts: {e}",
                step="fenjing_prompts",
                project=project_name,
            )
            if attempt < max_retries:
                time.sleep(2)
            else:
                emit_event(
                    "ERROR",
                    "visual_audio_assets",
                    "flow_error",
                    f"Fenjing prompts 构建失败且重试超限: {storyboards_jsonl_path.name}",
                    step="fenjing_prompts",
                    project=project_name,
                    data={"file": storyboards_jsonl_path.name, "attempt": attempt + 1, "max_retries": max_retries + 1, "error": str(e)},
                )
                raise

    raise ValueError("Failed to generate fenjing prompts after all retries")


def load_char_defaults(chars_jsonl_path: Path) -> Dict[str, str]:
    items = read_jsonl(str(chars_jsonl_path))
    m: Dict[str, str] = {}
    for it in items:
        cid = it.get("Character_Id") or it.get("Character_id") or it.get("character_id")
        d = it.get("Default_Outfit (Clothing)") or {}
        oid = d.get("Outfit_id")
        if isinstance(cid, str) and isinstance(oid, str) and cid and oid:
            m[cid] = oid
    return m


def load_char_plot_outfits(chars_jsonl_path: Path) -> Dict[str, set]:
    items = read_jsonl(str(chars_jsonl_path))
    m: Dict[str, set] = {}
    for it in items:
        cid = it.get("Character_Id") or it.get("Character_id") or it.get("character_id")
        if not isinstance(cid, str) or not cid:
            continue
        changes = it.get("Plot_Costume_Change") or []
        if not isinstance(changes, list):
            continue
        for ch in changes:
            if not isinstance(ch, dict):
                continue
            oid = ch.get("Outfit_id")
            if isinstance(oid, str) and oid:
                s = m.get(cid)
                if s is None:
                    s = set()
                    m[cid] = s
                s.add(oid)
    return m


def build_character_presigned_map(chars_jsonl_path: Path, project_name: Optional[str] = None) -> Dict[str, str]:
    items = read_jsonl(str(chars_jsonl_path))
    tos = TosClientWrapper()
    m: Dict[str, str] = {}
    if not tos.available():
        return m
    # 使用项目特定的TOS前缀，支持多项目并行
    project_prefixes = runtime_config.get_project_prefixes(project_name) if project_name else {}
    tos_character_prefix = project_prefixes.get("TOS_CHARACTER_PREFIX", "")
    if not tos_character_prefix:
        return m
    for it in items:
        cid = it.get("Character_Id") or it.get("Character_id") or it.get("character_id")
        if isinstance(cid, str) and cid:
            key = f"{tos_character_prefix}/{cid}.png"
            presigned = tos.presign_get(runtime_config.TOS_BUCKET, key)
            if isinstance(presigned, str) and presigned:
                m[cid] = presigned
    return m


def prepare_character_map(char_dir: Path, project_name: Optional[str] = None) -> Dict[str, str]:
    tos = TosClientWrapper()
    char_map: Dict[str, str] = {}
    # 使用项目特定的TOS前缀，支持多项目并行
    project_prefixes = runtime_config.get_project_prefixes(project_name) if project_name else {}
    tos_character_prefix = project_prefixes.get("TOS_CHARACTER_PREFIX", "")
    if char_dir.exists():
        for f in char_dir.glob("*.png"):
            name = f.name
            base = name[:-4]
            if base.endswith("st"):
                char_id = base[:-2]
            else:
                char_id = base
            key = f"{tos_character_prefix}/{name}" if tos_character_prefix else ""
            presigned = tos.presign_get(runtime_config.TOS_BUCKET, key) if (tos.available() and key) else None
            if presigned:
                char_map[char_id] = presigned
    return char_map


async def run_upload_assets_workflow(base_dir: Path, project_name: Optional[str] = None) -> None:
    tos = TosClientWrapper()
    project_prefixes = runtime_config.get_project_prefixes(project_name) if project_name else {}
    tos_character_prefix = project_prefixes.get("TOS_CHARACTER_PREFIX", "")
    tos_cloth_prefix = project_prefixes.get("TOS_CLOTH_PREFIX", "")
    if not tos.available():
        return
    # Upload character images
    char_dir = base_dir / "character_images"
    if tos_character_prefix and char_dir.exists():
        for f in char_dir.glob("*.png"):
            key = f"{tos_character_prefix}/{f.name}"
            try:
                tos.upload_file(runtime_config.TOS_BUCKET, key, f)
            except Exception:
                pass
    # Upload cloth images
    cloth_dir = base_dir / "cloth_images"
    if tos_cloth_prefix and cloth_dir.exists():
        for f in cloth_dir.glob("*.png"):
            key = f"{tos_cloth_prefix}/{f.name}"
            try:
                tos.upload_file(runtime_config.TOS_BUCKET, key, f)
            except Exception:
                pass


def validate_outfit_changes(storyboards_dir: Path, chars_jsonl_path: Path) -> Dict[str, Any]:
    plot_outfits = load_char_plot_outfits(chars_jsonl_path)
    missing: List[Dict[str, Any]] = []
    total_refs = 0
    for chapter_file in sorted(storyboards_dir.glob("storyboard_chapter_*.jsonl")):
        for sb in read_jsonl(str(chapter_file)):
            if not isinstance(sb, dict):
                continue
            sb_id = sb.get("Storyboard_id") or sb.get("fenjing_id")
            chars = sb.get("Characters") or sb.get("characters") or []
            if not isinstance(chars, list):
                continue
            for c in chars:
                if not isinstance(c, dict):
                    continue
                cid = c.get("Character_Id") or c.get("character_id")
                outf = c.get("Outfit") or c.get("outfit")
                if not isinstance(cid, str) or not isinstance(outf, str):
                    continue
                total_refs += 1
                plot_set = plot_outfits.get(cid)
                if not isinstance(plot_set, set) or outf not in plot_set:
                    missing.append({"character_id": cid, "outfit_id": outf, "storyboard_id": sb_id, "chapter": chapter_file.stem})
    return {"total_refs": total_refs, "missing_count": len(missing), "missing": missing}


def generate_cloth_images(chars_jsonl_path: Path, base_dir: Path, prefix: str = "", project_name: Optional[str] = None) -> List[Dict[str, Any]]:
    items = read_jsonl(str(chars_jsonl_path))
    out_dir = base_dir / "cloth_images"
    ensure_dir(out_dir)
    tos = TosClientWrapper()
    results: List[Dict[str, Any]] = []
    # 使用项目特定的TOS前缀，支持多项目并行
    project_prefixes = runtime_config.get_project_prefixes(project_name) if project_name else {}
    tos_cloth_prefix = project_prefixes.get("TOS_CLOTH_PREFIX", "")
    with ThreadPoolExecutor(max_workers=20) as pool:
        futures: List[Tuple[str, Any]] = []
        for it in items:
            changes = it.get("Plot_Costume_Change") or []
            if isinstance(changes, list):
                for ch in changes:
                    if not isinstance(ch, dict):
                        continue
                    outfit_id = ch.get("Outfit_id")
                    desc = ch.get("Outfit_Description")
                    if isinstance(outfit_id, str) and outfit_id and isinstance(desc, str) and desc.strip():
                        prompt = f"高质量纯商品摄影，服装商品展示图，将服装平铺在白色背景上，展示服装的全貌。{desc}。**图片中不得出现任何人物**"
                        futures.append((outfit_id, pool.submit(run_async, lambda: generate_and_download(prompt, out_dir, outfit_id))))
        for outfit_id, fut in futures:
            p = fut.result()
            if isinstance(p, Path) and tos_cloth_prefix:
                key = f"{tos_cloth_prefix}/{p.name}"
                uri = tos.upload_file(runtime_config.TOS_BUCKET, key, p) if tos.available() else None
                presigned = tos.presign_get(runtime_config.TOS_BUCKET, key) if tos.available() else None
                image_id = p.stem
                emit_event(
                    "INFO",
                    "visual_audio_assets",
                    "upload_progress",
                    f"cloth image uploaded: {p.name}",
                    step="cloth_images",
                    project=project_name,
                    data={
                        "file": p.name,
                        "key": key,
                        "uri": uri,
                        "presigned": presigned,
                        "image_type": "cloth",
                        "image_id": image_id,
                    },
                )
                results.append({"file": p.name, "uri": uri, "presigned": presigned})
            else:
                emit_event(
                    "ERROR",
                    "visual_audio_assets",
                    "upload_progress",
                    f"cloth image generation failed: {outfit_id}",
                    step="generate_cloth",
                    project=project_name,
                    data={
                        "image_type": "cloth",
                        "image_id": outfit_id,
                        "ok": False,
                    },
                )
    emit_event(
        "DEBUG",
        "visual_audio_assets",
        "log",
        f"{prefix}generate_cloth_images: generated {len(results)} cloth images",
        step="cloth_images",
        project=project_name,
    )
    return results


def generate_cloth_changed_images(chars_jsonl_path: Path, cloth_upload: List[Dict[str, Any]], char_map: Dict[str, str], base_dir: Path, prefix: str = "", project_name: Optional[str] = None) -> List[Dict[str, Any]]:
    items = read_jsonl(str(chars_jsonl_path))
    out_dir = base_dir / "cloth_changed_images"
    ensure_dir(out_dir)
    tos = TosClientWrapper()
    # 使用项目特定的TOS前缀，支持多项目并行
    project_prefixes = runtime_config.get_project_prefixes(project_name) if project_name else {}
    tos_cloth_prefix = project_prefixes.get("TOS_CLOTH_PREFIX", "")
    cloth_map: Dict[str, str] = {}
    for it in cloth_upload or []:
        name = it.get("file")
        presigned = it.get("presigned")
        if isinstance(name, str) and name.endswith(".png") and presigned:
            cloth_id = name[:-4]
            cloth_map[cloth_id] = presigned
    defaults = load_char_defaults(chars_jsonl_path)

    qc_prompt_path = PROMPT_DIR / "character_cloth_qc.txt"
    sys_prompt = read_text(str(qc_prompt_path)) if qc_prompt_path.exists() else None
    thinking = runtime_config.QC_THINKING if runtime_config.QC_THINKING != "disabled" else None
    reasoning_effort = runtime_config.QC_REASONING_EFFORT if runtime_config.QC_REASONING_EFFORT != "disabled" else None

    results: List[Dict[str, Any]] = []

    async def process_single_image_with_qc(cid: str, oid: str, char_ref: Optional[str], cloth_ref: Optional[str]) -> Optional[Dict[str, Any]]:
        prompt = "高质量真人摄影，正面及侧面形象拍摄，**纯白色背景**，采用影视级渲染效果。参考图中的人物站立，全身拍摄。给参考图中的人物换上服装参考图的衣服，穿的鞋不变，并在水平方向展示角色的正视、侧视图形象，保持人物形象不得改变。"
        name_prefix = f"{cid}_{oid}"

        retry = 5
        attempts = 0
        last_p = None
        last_uri = None
        last_presigned = None
        last_qc_result = None

        while attempts <= retry:
            attempts += 1
            emit_event(
                "INFO",
                "visual_audio_assets",
                "log",
                f"{prefix}Generating Cloth Changed Image - Character: {cid}, Outfit: {oid}, Attempt: {attempts}/{retry+1}",
                step="character_images",
                project=project_name,
            )

            refs: List[str] = []
            if isinstance(char_ref, str) and char_ref:
                refs.append(char_ref)
            if isinstance(cloth_ref, str) and cloth_ref:
                refs.append(cloth_ref)
            emit_event(
                "INFO",
                "visual_audio_assets",
                "refs_used",
                f"{prefix}Using refs for cloth_changed: {cid}_{oid}, char_ref={'Y' if char_ref else 'N'}, cloth_ref={'Y' if cloth_ref else 'N'}",
                step="cloth_changed",
                project=project_name,
                data={
                    "character_id": cid,
                    "outfit_id": oid,
                    "char_ref": char_ref,
                    "cloth_ref": cloth_ref,
                    "refs_count": len(refs),
                },
            )
            p = await generate_and_download_with_refs(prompt, refs, out_dir, name_prefix)
            if not isinstance(p, Path):
                placeholder = out_dir / f"{name_prefix}.png"
                try:
                    import base64
                    png_b64 = (
                        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAoMBgEo5K8QAAAAASUVORK5CYII="
                    )
                    with open(placeholder, "wb") as f:
                        f.write(base64.b64decode(png_b64))
                    p = placeholder
                except Exception:
                    p = None

            if not isinstance(p, Path):
                emit_event(
                    "ERROR",
                    "visual_audio_assets",
                    "log",
                    f"{prefix}Generation Failed - Character: {cid}, Outfit: {oid}, Attempt: {attempts}",
                    step="character_images",
                    project=project_name,
                )
                if attempts <= retry:
                    continue
                if last_p:
                    return {"character_id": cid, "outfit_id": oid, "file": last_p.name, "uri": last_uri, "presigned": last_presigned, "qc_passed": False, "qc_result": last_qc_result, "char_ref": char_ref, "cloth_ref": cloth_ref}
                return None

            key = f"{tos_cloth_prefix}/{p.name}" if tos_cloth_prefix else ""
            uri = tos.upload_file(runtime_config.TOS_BUCKET, key, p) if (tos.available() and key) else None
            presigned = tos.presign_get(runtime_config.TOS_BUCKET, key) if (tos.available() and key) else None
            
            last_p = p
            last_uri = uri
            last_presigned = presigned
            
            emit_event(
                "INFO",
                "visual_audio_assets",
                "upload_progress",
                f"cloth changed image uploaded: {p.name}",
                step="cloth_changed",
                project=project_name,
                data={
                    "file": p.name,
                    "key": key,
                    "uri": uri,
                    "presigned": presigned,
                    "image_type": "cloth_changed",
                    "image_id": f"{cid}_{oid}",
                    "character_id": cid,
                    "outfit_id": oid,
                },
            )

            if not sys_prompt or not presigned:
                emit_event(
                    "INFO",
                    "visual_audio_assets",
                    "qc_skipped",
                    f"QC Skipped - Character: {cid}, Outfit: {oid}, No QC prompt or presigned URL",
                    step="cloth_changed",
                    project=project_name,
                    data={"character_id": cid, "outfit_id": oid},
                )
                return {"character_id": cid, "outfit_id": oid, "file": p.name, "uri": uri, "presigned": presigned, "qc_passed": None, "char_ref": char_ref, "cloth_ref": cloth_ref}

            emit_event(
                "INFO",
                "visual_audio_assets",
                "qc_check",
                f"QC Check - Character: {cid}, Outfit: {oid}, Attempt: {attempts}",
                step="cloth_changed",
                project=project_name,
                data={"character_id": cid, "outfit_id": oid, "attempt": attempts},
            )
            r = await qc_image_async(sys_prompt, presigned, thinking=thinking, reasoning_effort=reasoning_effort)
            last_qc_result = r

            try:
                parsed = json.loads(r["content"])
                ok = bool(parsed.get("check_result"))
                check_ana = parsed.get("check_ana", "")
                emit_event(
                    "INFO",
                    "visual_audio_assets",
                    "log",
                    f"{prefix}QC Result - Character: {cid}, Outfit: {oid}, Pass: {ok}, Analysis: {check_ana}",
                    step="character_images",
                    project=project_name,
                )
            except (json.JSONDecodeError, ValueError) as e:
                emit_event(
                    "ERROR",
                    "visual_audio_assets",
                    "log",
                    f"{prefix}QC Parse Error - Character: {cid}, Outfit: {oid}, Error: {e}",
                    step="character_images",
                    project=project_name,
                )
                ok = False

            if ok:
                emit_event(
                    "INFO",
                    "visual_audio_assets",
                    "qc_passed",
                    f"QC Passed - Character: {cid}, Outfit: {oid}, Attempts: {attempts}",
                    step="cloth_changed",
                    project=project_name,
                    data={"character_id": cid, "outfit_id": oid, "attempts": attempts},
                )
                return {"character_id": cid, "outfit_id": oid, "file": p.name, "uri": uri, "presigned": presigned, "qc_passed": True, "qc_result": r, "char_ref": char_ref, "cloth_ref": cloth_ref}

            if attempts <= retry:
                emit_event(
                    "INFO",
                    "visual_audio_assets",
                    "qc_failed",
                    f"QC Failed - Character: {cid}, Outfit: {oid}, Regenerating image",
                    step="cloth_changed",
                    project=project_name,
                    data={"character_id": cid, "outfit_id": oid},
                )
                continue

        emit_event(
            "ERROR",
            "visual_audio_assets",
            "qc_failed",
            f"QC Failed After All Retries - Character: {cid}, Outfit: {oid}, Total Attempts: {attempts}",
            step="cloth_changed",
            project=project_name,
            data={"character_id": cid, "outfit_id": oid, "total_attempts": attempts},
        )
        if last_p:
            return {"character_id": cid, "outfit_id": oid, "file": last_p.name, "uri": last_uri, "presigned": last_presigned, "qc_passed": False, "qc_result": last_qc_result, "char_ref": char_ref, "cloth_ref": cloth_ref}
        return None

    with ThreadPoolExecutor(max_workers=20) as pool:
        futures: List[Tuple[str, str, Any]] = []
        for it in items:
            cid = it.get("Character_Id") or it.get("Character_id") or it.get("character_id")
            if not isinstance(cid, str) or not cid:
                continue
            changes = it.get("Plot_Costume_Change") or []
            if not isinstance(changes, list):
                continue
            for ch in changes:
                if not isinstance(ch, dict):
                    continue
                outfit_id = ch.get("Outfit_id")
                if not isinstance(outfit_id, str) or not outfit_id:
                    continue
                default_outfit = defaults.get(cid)
                if outfit_id == default_outfit:
                    continue
                char_ref = char_map.get(cid)
                cloth_ref = cloth_map.get(outfit_id)
                futures.append((cid, outfit_id, pool.submit(run_async, lambda c=cid, o=outfit_id, cr=char_ref, clr=cloth_ref: process_single_image_with_qc(c, o, cr, clr))))

        for cid, outfit_id, fut in futures:
            r = fut.result()
            if r:
                results.append(r)
            else:
                emit_event(
                    "ERROR",
                    "visual_audio_assets",
                    "upload_progress",
                    f"cloth changed image generation failed: {cid}_{outfit_id}",
                    step="generate_cloth",
                    project=project_name,
                    data={
                        "image_type": "cloth_changed",
                        "image_id": f"{cid}_{outfit_id}",
                        "character_id": cid,
                        "outfit_id": outfit_id,
                        "ok": False,
                    },
                )

    emit_event(
        "DEBUG",
        "visual_audio_assets",
        "log",
        f"{prefix}generate_cloth_changed_images: generated {len(results)} cloth changed images",
        step="cloth_images",
        project=project_name,
    )
    return results


def has_cloth_changed_targets(chars_jsonl_path: Path, defaults: Dict[str, str]) -> bool:
    items = read_jsonl(str(chars_jsonl_path))
    for it in items:
        cid = it.get("Character_Id") or it.get("Character_id") or it.get("character_id")
        if not isinstance(cid, str) or not cid:
            continue
        changes = it.get("Plot_Costume_Change") or []
        if not isinstance(changes, list):
            continue
        for ch in changes:
            if not isinstance(ch, dict):
                continue
            outfit_id = ch.get("Outfit_id")
            if not isinstance(outfit_id, str) or not outfit_id:
                continue
            default_outfit = defaults.get(cid)
            if outfit_id == default_outfit:
                continue
            return True
    return False


def load_char_sex(chars_jsonl_path: Path) -> Dict[str, str]:
    items = read_jsonl(str(chars_jsonl_path))
    m: Dict[str, str] = {}
    for it in items:
        cid = it.get("Character_Id") or it.get("Character_id") or it.get("character_id")
        sex = it.get("Sex") or it.get("sex")
        label = None
        if isinstance(sex, str):
            s = sex.strip().lower()
            if s in ("女性", "女", "female", "woman", "girl"):
                label = "女子"
            elif s in ("男性", "男", "male", "man", "boy"):
                label = "男子"
        m[cid] = label or "人物"
    return m


def character_keys_sorted(d: Dict[str, Any]) -> List[str]:
    ks = [k for k in d.keys() if re.match(r"^Character_\d+$", str(k))]
    if not ks:
        ks = [k for k in d.keys() if re.match(r"^person_\d+$", str(k))]
    def key_num(k: str) -> int:
        try:
            return int(k.split("_", 2)[1])
        except (ValueError, TypeError):
            return 9999
    return sorted(ks, key=key_num)


def enforce_fenjing_prompts(fenjing_prompts_jsonl: Path, storyboards_jsonl: Path, chars_jsonl: Path, defaults: Dict[str, str]) -> None:
    items = read_jsonl(str(fenjing_prompts_jsonl))
    storyboards = read_jsonl(str(storyboards_jsonl))
    sex_map = load_char_sex(chars_jsonl)
    out: List[Dict[str, Any]] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        sb = storyboards[idx] if idx < len(storyboards) else {}
        item = enforce_prompt_fields(item, sb) if isinstance(sb, dict) else item
        outfit_map: Dict[str, str] = {}
        if isinstance(sb, dict):
            chars = sb.get("Characters") or sb.get("characters") or []
            if isinstance(chars, list):
                for c in chars:
                    if isinstance(c, dict):
                        cid = c.get("Character_Id") or c.get("character_id")
                        outf = c.get("Outfit") or c.get("outfit")
                        if isinstance(cid, str) and isinstance(outf, str):
                            outfit_map[cid] = outf
        persons = character_keys_sorted(item)
        for pk in persons:
            num = pk.split("_", 1)[1] if "_" in pk else ""
            cid = item.get(pk)
            if isinstance(cid, str) and cid:
                prefix = "Character" if pk.startswith("Character_") else "person"
                ok = item.get(f"{prefix}_{num}_outfit")
                use_outfit = outfit_map.get(cid) or defaults.get(cid) or ""
                if use_outfit:
                    item[f"{prefix}_{num}_outfit"] = use_outfit
        prompt_text = item.get("prompt")
        if isinstance(prompt_text, str) and prompt_text:
            name_to_ref: Dict[str, str] = {}
            if isinstance(sb, dict):
                chars = sb.get("Characters") or sb.get("characters") or []
                if isinstance(chars, list):
                    idx_map: Dict[str, str] = {}
                    for pk in persons:
                        num = pk.split("_", 1)[1] if "_" in pk else ""
                        cid = item.get(pk)
                        if isinstance(cid, str) and cid:
                            idx_map[cid] = num
                    for c in chars:
                        if isinstance(c, dict):
                            cid = c.get("Character_Id") or c.get("character_id")
                            nm = c.get("Character_Name") or c.get("name")
                            num = idx_map.get(cid)
                            if isinstance(nm, str) and isinstance(num, str):
                                label = sex_map.get(cid) or "人物"
                                name_to_ref[nm] = f"参考图{num}的{label}"
            for nm, ref in name_to_ref.items():
                try:
                    prompt_text = re.sub(re.escape(nm), ref, prompt_text)
                except re.error:
                    pass
            item["prompt"] = prompt_text
        out.append(item)
    write_jsonl(str(fenjing_prompts_jsonl), out)


def upload_jsonl_to_assets(tos: TosClientWrapper, jsonl_path: Path, step_id: str, project_name: Optional[str] = None) -> bool:
    if not tos.available():
        emit_event(
            "WARN",
            "visual_audio_assets",
            "upload_progress",
            "TOS client not available, cannot upload assets",
            step=step_id,
            project=project_name,
            data={"skipped": True, "file": jsonl_path.name},
        )
        emit_event(
            "WARN",
            "visual_audio_assets",
            "log",
            "TOS client not available, cannot upload assets.",
            step="general",
            project=project_name,
        )
        return False
    try:
        # 使用项目特定的TOS前缀，支持多项目并行
        project_prefixes = runtime_config.get_project_prefixes(project_name) if project_name else {}
        tos_assets_prefix = project_prefixes.get("TOS_ASSETS_PREFIX", "")
        if not tos_assets_prefix:
            return False
        key = f"{tos_assets_prefix}/{jsonl_path.name}"
        if tos.upload_file(runtime_config.TOS_BUCKET, key, jsonl_path):
            emit_event(
                "INFO",
                "visual_audio_assets",
                "upload_progress",
                f"Uploaded {jsonl_path.name} to {key}",
                step=step_id,
                project=project_name,
                data={"file": jsonl_path.name, "key": key},
            )
            emit_event(
                "INFO",
                "visual_audio_assets",
                "log",
                f"Uploaded {jsonl_path.name} to {key}",
                step="upload_assets",
                project=project_name,
            )
            return True
        emit_event(
            "WARN",
            "visual_audio_assets",
            "upload_progress",
            f"Failed to upload {jsonl_path.name} to {key}",
            step=step_id,
            project=project_name,
            data={"file": jsonl_path.name, "key": key, "ok": False},
        )
        emit_event(
            "WARN",
            "visual_audio_assets",
            "log",
            f"Failed to upload {jsonl_path.name} to {key}",
            step="upload_assets",
            project=project_name,
        )
        return False
    except (IOError, OSError) as e:
        emit_event(
            "WARN",
            "visual_audio_assets",
            "upload_progress",
            f"Failed to upload {jsonl_path.name}: {e}",
            step=step_id,
            project=project_name,
            data={"file": jsonl_path.name, "ok": False},
        )
        emit_event(
            "WARN",
            "visual_audio_assets",
            "log",
            f"Failed to upload {jsonl_path.name}: {e}",
            step="upload_assets",
            project=project_name,
        )
        return False


def validate_and_fix_character_ids(
    prompts: List[Dict[str, Any]],
    reference_chars: List[Dict[str, Any]],
    project_name: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    stats = {"total": len(prompts), "fixed": 0, "matched": 0, "mismatched": 0}

    ref_id_map = {}
    ref_name_map = {}

    for char in reference_chars:
        char_id = char.get("Character_Id")
        char_name = char.get("Character_name")
        if char_id and char_name:
            ref_id_map[char_id] = char_name
            ref_name_map[char_name] = char_id

    fixed_prompts = []

    for prompt in prompts:
        prompt_id = prompt.get("Character_Id")
        prompt_name = prompt.get("name") or prompt.get("Character_name")

        if not prompt_id or not prompt_name:
            emit_event(
                "WARN",
                "visual_audio_assets",
                "log",
                f"Prompt missing Character_Id or name: {prompt}",
                step="character_images",
                project=project_name,
            )
            fixed_prompts.append(prompt)
            continue

        if prompt_id in ref_id_map:
            if ref_id_map[prompt_id] == prompt_name:
                stats["matched"] += 1
                fixed_prompts.append(prompt)
            else:
                emit_event(
                    "WARN",
                    "visual_audio_assets",
                    "log",
                    f"Character_Id '{prompt_id}' matched but name mismatch: '{prompt_name}' vs '{ref_id_map[prompt_id]}'",
                    step="character_images",
                    project=project_name,
                )
                prompt["name"] = ref_id_map[prompt_id]
                stats["fixed"] += 1
                fixed_prompts.append(prompt)
        else:
            stats["mismatched"] += 1
            if prompt_name in ref_name_map:
                correct_id = ref_name_map[prompt_name]
                emit_event(
                    "INFO",
                    "visual_audio_assets",
                    "log",
                    f"Mapping Character_Id by name: '{prompt_name}' -> '{correct_id}' (was '{prompt_id}')",
                    step="character_images",
                    project=project_name,
                )
                prompt["Character_Id"] = correct_id
                stats["fixed"] += 1
            else:
                emit_event(
                    "WARN",
                    "visual_audio_assets",
                    "log",
                    f"Cannot map Character_Id for '{prompt_name}', keeping original ID: '{prompt_id}'",
                    step="character_images",
                    project=project_name,
                )
            fixed_prompts.append(prompt)

    return fixed_prompts, stats


def validate_and_fix_location_ids(
    prompts: List[Dict[str, Any]],
    reference_locations: List[Dict[str, Any]],
    project_name: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    stats = {"total": len(prompts), "fixed": 0, "matched": 0, "mismatched": 0}

    ref_name_map = {}
    for loc in reference_locations:
        loc_name = loc.get("Location")
        loc_id = loc.get("Location_ID") or loc.get("Location_Id") or loc.get("location_id")
        if loc_name and loc_id:
            ref_name_map[loc_name] = loc_id

    fixed_prompts = []
    for prompt in prompts:
        prompt_id = prompt.get("Location_Id") or prompt.get("location_id")
        prompt_name = prompt.get("Location") or prompt.get("name")

        if not prompt_name:
            emit_event(
                "WARN",
                "visual_audio_assets",
                "log",
                f"Prompt missing Location or name: {prompt}",
                step="location_images",
                project=project_name,
            )
            fixed_prompts.append(prompt)
            continue

        correct_id = ref_name_map.get(prompt_name)
        if correct_id:
            if prompt_id == correct_id:
                stats["matched"] += 1
            else:
                stats["fixed"] += 1
                prompt["Location_Id"] = correct_id
                if "location_id" in prompt:
                    prompt["location_id"] = correct_id
            fixed_prompts.append(prompt)
        else:
            stats["mismatched"] += 1
            fixed_prompts.append(prompt)

    return fixed_prompts, stats


def build_character_prompts_with_retry(
    char_jsonl_path: Path,
    prompt_path: str,
    reference_chars: List[Dict[str, Any]],
    max_retries: int = 2, project_name: Optional[str] = None) -> Path:
    system_prompt = read_text(prompt_path)
    chars = read_jsonl(str(char_jsonl_path))
    output_path = char_jsonl_path.parent / "character_prompts.jsonl"

    for attempt in range(max_retries + 1):
        emit_event(
            "INFO",
            "visual_audio_assets",
            "build_progress",
            f"Building Character Prompts (Attempt {attempt + 1}/{max_retries + 1})",
            step="character_prompts",
            project=project_name,
            data={"attempt": attempt + 1, "max_retries": max_retries + 1},
        )
        try:
            user_texts = [json.dumps(chars, ensure_ascii=False)]
            thinking = runtime_config.CHARACTER_PROMPT_THINKING if runtime_config.CHARACTER_PROMPT_THINKING != "disabled" else None
            reasoning_effort = runtime_config.CHARACTER_PROMPT_REASONING_EFFORT if runtime_config.CHARACTER_PROMPT_REASONING_EFFORT != "disabled" else None
            result = chat([system_prompt], user_texts, thinking=thinking, reasoning_effort=reasoning_effort)
            content = result["content"]

            prompts: List[Any] = parse_json_list(content)

            if not isinstance(prompts, list) or len(prompts) == 0:
                emit_event(
                    "WARN",
                    "visual_audio_assets",
                    "parse_warning",
                    f"Invalid format: expected non-empty list, got {type(prompts).__name__}",
                    step="character_prompts",
                    project=project_name,
                    data={"type": type(prompts).__name__},
                )
                if attempt < max_retries:
                    emit_event(
                        "INFO",
                        "visual_audio_assets",
                        "retry",
                        "Retrying",
                        step="character_prompts",
                        project=project_name,
                    )
                    continue
                raise ValueError("Failed to generate valid character prompts after all retries")

            valid_prompts: List[Dict[str, Any]] = []
            for p in prompts:
                if isinstance(p, dict) and "Character_Id" in p and ("name" in p or "Character_name" in p) and "st_prompt" in p:
                    if "name" not in p and "Character_name" in p:
                        p["name"] = p["Character_name"]
                    valid_prompts.append(p)
                else:
                    emit_event(
                        "WARN",
                        "visual_audio_assets",
                        "parse_warning",
                        f"Skipping invalid prompt entry: {p}",
                        step="character_prompts",
                        project=project_name,
                        data={"entry": str(p)},
                    )

            if len(valid_prompts) == 0:
                emit_event(
                    "WARN",
                    "visual_audio_assets",
                    "parse_warning",
                    "No valid prompts found",
                    step="character_prompts",
                    project=project_name,
                )
                if attempt < max_retries:
                    emit_event(
                        "INFO",
                        "visual_audio_assets",
                        "retry",
                        "Retrying",
                        step="character_prompts",
                        project=project_name,
                    )
                    continue
                raise ValueError("No valid character prompts generated after all retries")

            fixed_prompts, stats = validate_and_fix_character_ids(valid_prompts, reference_chars)
            emit_event(
                "INFO",
                "visual_audio_assets",
                "log",
                f"Character ID Validation: total={stats['total']}, matched={stats['matched']}, fixed={stats['fixed']}, mismatched={stats['mismatched']}",
                step="character_images",
                project=project_name,
            )

            write_jsonl(str(output_path), fixed_prompts)
            emit_event(
                "INFO",
                "visual_audio_assets",
                "log",
                f"Character Prompts saved to: {output_path}",
                step="character_images",
                project=project_name,
            )
            return output_path

        except (IOError, OSError, ValueError) as e:
            emit_event(
                "ERROR",
                "visual_audio_assets",
                "log",
                f"Failed to build character prompts: {e}",
                step="character_images",
                project=project_name,
            )
            if attempt < max_retries:
                emit_event(
                    "INFO",
                    "visual_audio_assets",
                    "log",
                    "Retrying...",
                    step="general",
                    project=project_name,
                )
                time.sleep(2)
            else:
                raise

    raise ValueError("Failed to generate character prompts after all retries")


def build_tts_prompts_for_chapter(chapter_jsonl_path: Path, prompt_path: str, project_name: Optional[str] = None) -> Path:
    system_prompt = read_text(prompt_path)
    storyboards = read_jsonl(str(chapter_jsonl_path))
    
    user_texts = [json.dumps(storyboards, ensure_ascii=False)]
    
    result = chat(
        [system_prompt],
        user_texts,
        thinking=runtime_config.TTS_PROMPT_THINKING,
        reasoning_effort=runtime_config.TTS_PROMPT_REASONING_EFFORT
    )
    content = result["content"]
    
    prompts: List[Dict[str, Any]] = []
    try:
        cleaned_content = content.strip()
        if cleaned_content.startswith("```json"):
            cleaned_content = cleaned_content[7:]
        if cleaned_content.startswith("```"):
            cleaned_content = cleaned_content[3:]
        if cleaned_content.endswith("```"):
            cleaned_content = cleaned_content[:-3]
        cleaned_content = cleaned_content.strip()

        parsed = json.loads(cleaned_content)
        if isinstance(parsed, list):
            prompts = parsed
        elif isinstance(parsed, dict):
            prompts = [parsed]
    except (json.JSONDecodeError, ValueError) as e:
        emit_event(
            "WARN",
            "visual_audio_assets",
            "log",
            f"TTS Prompt JSON Parse Error: {e}",
            step="tts",
            project=project_name,
        )
        try:
            import json_repair
            parsed = json_repair.loads(content)
            if isinstance(parsed, list):
                prompts = parsed
        except (json.JSONDecodeError, ValueError):
            pass
            
    chapter_name = chapter_jsonl_path.stem
    out_path = chapter_jsonl_path.parent / f"tts_prompts_{chapter_name}.jsonl"
    write_jsonl(str(out_path), prompts)
    return out_path


def build_location_prompts_with_retry(
    loc_jsonl_path: Path,
    prompt_path: str,
    reference_locations: List[Dict[str, Any]],
    max_retries: int = 2, project_name: Optional[str] = None) -> Path:
    system_prompt = read_text(prompt_path)
    locations = read_jsonl(str(loc_jsonl_path))
    output_path = loc_jsonl_path.parent / "location_prompts.jsonl"

    for attempt in range(max_retries + 1):
        emit_event(
            "INFO",
            "visual_audio_assets",
            "log",
            f"Building Location Prompts (Attempt {attempt + 1}/{max_retries + 1})...",
            step="location_images",
            project=project_name,
        )
        try:
            user_texts = [json.dumps(locations, ensure_ascii=False)]
            result = chat(
                [system_prompt],
                user_texts,
                thinking=runtime_config.LOCATION_PROMPT_THINKING,
                reasoning_effort=runtime_config.LOCATION_PROMPT_REASONING_EFFORT
            )
            content = result["content"]

            prompts: List[Any] = parse_json_list(content)

            if not isinstance(prompts, list) or len(prompts) == 0:
                emit_event(
                    "WARN",
                    "visual_audio_assets",
                    "log",
                    f"Invalid format: expected non-empty list, got {type(prompts).__name__}",
                    step="general",
                    project=project_name,
                )
                if attempt < max_retries:
                    emit_event(
                        "INFO",
                        "visual_audio_assets",
                        "log",
                        "Retrying...",
                        step="general",
                        project=project_name,
                    )
                    continue
                emit_event(
                    "ERROR",
                    "visual_audio_assets",
                    "flow_error",
                    "Location prompts 重试超限，格式无效",
                    step="location_prompts",
                    project=project_name,
                    data={"attempt": attempt + 1, "max_retries": max_retries + 1},
                )
                raise ValueError("Failed to generate valid location prompts after all retries")

            valid_prompts: List[Dict[str, Any]] = []
            for p in prompts:
                if isinstance(p, dict) and ("Location" in p or "name" in p) and ("Location_Id" in p or "location_id" in p):
                    if "Location" not in p and "name" in p:
                        p["Location"] = p["name"]
                    if "Location_Id" not in p and "location_id" in p:
                        p["Location_Id"] = p["location_id"]
                    valid_prompts.append(p)
                else:
                    emit_event(
                        "WARN",
                        "visual_audio_assets",
                        "parse_warning",
                        f"Skipping invalid prompt entry: {p}",
                        step="location_prompts",
                        project=project_name,
                        data={"entry": str(p)},
                    )

            if len(valid_prompts) == 0:
                emit_event(
                    "WARN",
                    "visual_audio_assets",
                    "log",
                    "No valid prompts found",
                    step="general",
                    project=project_name,
                )
                if attempt < max_retries:
                    emit_event(
                        "INFO",
                        "visual_audio_assets",
                        "log",
                        "Retrying...",
                        step="general",
                        project=project_name,
                    )
                    continue
                emit_event(
                    "ERROR",
                    "visual_audio_assets",
                    "flow_error",
                    "Location prompts 重试超限，无有效条目",
                    step="location_prompts",
                    project=project_name,
                    data={"attempt": attempt + 1, "max_retries": max_retries + 1},
                )
                raise ValueError("No valid location prompts generated after all retries")

            fixed_prompts, stats = validate_and_fix_location_ids(valid_prompts, reference_locations)
            emit_event(
                "INFO",
                "visual_audio_assets",
                "validation_complete",
                f"Location ID Validation: total={stats['total']}, matched={stats['matched']}, fixed={stats['fixed']}, mismatched={stats['mismatched']}",
                step="location_prompts",
                project=project_name,
                data=stats,
            )

            write_jsonl(str(output_path), fixed_prompts)
            emit_event(
                "INFO",
                "visual_audio_assets",
                "save_complete",
                f"Location Prompts saved to: {output_path}",
                step="location_prompts",
                project=project_name,
                data={"path": str(output_path)},
            )
            return output_path

        except (IOError, OSError, ValueError) as e:
            emit_event(
                "ERROR",
                "visual_audio_assets",
                "flow_error",
                f"Failed to build location prompts: {e}",
                step="location_prompts",
                project=project_name,
                data={"error": str(e)},
            )
            if attempt < max_retries:
                emit_event(
                    "INFO",
                    "visual_audio_assets",
                    "log",
                    "Retrying...",
                    step="general",
                    project=project_name,
                )
                time.sleep(2)
            else:
                emit_event(
                    "ERROR",
                    "visual_audio_assets",
                    "flow_error",
                    "Location prompts 构建失败且重试超限",
                    step="location_prompts",
                    project=project_name,
                    data={"attempt": attempt + 1, "max_retries": max_retries + 1, "error": str(e)},
                )
                raise

    raise ValueError("Failed to generate location prompts after all retries")

import argparse

async def main(project_name: Optional[str] = None, assets_dir: Optional[str] = None, phase: str = "all"):
    """
    资产生成工作流主入口
    
    【参数】
    - project_name: 项目名称（优先使用）
    - assets_dir: 资产生成目录路径
    - phase: 执行阶段
    """
    # 如果传入了project_name和assets_dir，直接使用
    # 否则尝试从命令行参数或环境变量获取
    actual_project_name = project_name
    
    if not actual_project_name:
        # 尝试从环境变量获取
        actual_project_name = os.environ.get('PROJECT_NAME', '')
    
    if not actual_project_name and assets_dir:
        # 从assets_dir推断项目名称
        actual_project_name = Path(assets_dir).parent.name
    
    # 初始化args为None，避免后面引用时出错
    args = None
    
    if not actual_project_name:
        # 从命令行参数获取
        parser = argparse.ArgumentParser(description="Generate visual and audio assets for storyboard.")
        parser.add_argument(
            "--assets-dir", "-d",
            type=str,
            help="Path to the storyboard_assets directory. If not provided, defaults to config setting."
        )
        parser.add_argument(
            "--phase",
            type=str,
            default="all",
            help="Comma-separated phases: all, download_assets, build_prompts, generate_images, generate_tts, cloth_images, cloth_changed, upload_assets"
        )
        parser.add_argument(
            "--project-name",
            type=str,
            help="Project name"
        )
        args = parser.parse_args()
        actual_project_name = args.project_name or ''
        if args.assets_dir:
            assets_dir = args.assets_dir
        phase = args.phase if hasattr(args, 'phase') else phase
    
    # 使用传入的项目名称或从目录推断
    project_name = actual_project_name
    
    if assets_dir:
        base_dir = Path(assets_dir)
    else:
        base_dir = Path(runtime_config.OUTPUT_DIR) / project_name / "visual_audio_assets"

    if not base_dir.exists():
        emit_event(
            "ERROR",
            "visual_audio_assets",
            "flow_error",
            f"Assets directory not found: {base_dir}",
            step="start",
            project=project_name,
        )
        emit_event(
            "ERROR",
            "visual_audio_assets",
            "flow_error",
            f"Assets directory not found: {base_dir}",
            step="start",
            project=project_name,
            data={"path": str(base_dir)},
        )
        return

    emit_event(
        "INFO",
        "visual_audio_assets",
        "config",
        f"Using Assets Directory: {base_dir}",
        step="start",
        project=project_name,
        data={"path": str(base_dir)},
    )

    ensure_dir(base_dir)
    if not download_assets_from_tos(base_dir, project_name=project_name):
        emit_event(
            "ERROR",
            "visual_audio_assets",
            "flow_error",
            "Failed to download required assets from TOS",
            step="download_assets",
            project=project_name,
        )
        emit_event(
            "ERROR",
            "visual_audio_assets",
            "flow_error",
            "Failed to download required assets from TOS",
            step="download_assets",
            project=project_name,
        )
        return

    storyboards_dir = base_dir / "storyboards"

    char_jsonl = base_dir / "characters.jsonl"
    loc_jsonl = base_dir / "locations.jsonl"

    prompt_dir = PROMPT_DIR
    char_prompt_tpl = str(prompt_dir / "character_build.txt")
    char_qc_prompt_tpl = str(prompt_dir / "character_build_qc.txt")
    loc_prompt_tpl = str(prompt_dir / "location_build.txt")
    tts_prompt_tpl = str(prompt_dir / "jieshuo.txt")

    if not char_jsonl.exists():
        emit_event(
            "ERROR",
            "visual_audio_assets",
            "flow_error",
            f"Character file not found: {char_jsonl}",
            step="download_assets",
            project=project_name,
        )
        emit_event(
            "ERROR",
            "visual_audio_assets",
            "flow_error",
            f"Character file not found: {char_jsonl}",
            step="download_assets",
            project=project_name,
            data={"path": str(char_jsonl)},
        )
        return
    if not loc_jsonl.exists():
        emit_event(
            "ERROR",
            "visual_audio_assets",
            "flow_error",
            f"Location file not found: {loc_jsonl}",
            step="download_assets",
            project=project_name,
            data={"path": str(loc_jsonl)},
        )
        return

    emit_event(
        "INFO",
        "visual_audio_assets",
        "phase_complete",
        "download assets completed",
        step="download_assets",
        project=project_name,
    )

    # phase 作为后端执行开关，决定哪些子流程会运行
    # step 仅用于前端状态渲染与用户感知位置，不作为执行条件
    # 使用传入的phase参数，如果args存在则从args获取
    if args is not None:
        phases_raw = str(getattr(args, "phase", phase) or phase)
    else:
        phases_raw = str(phase)
    phase_tokens = {p.strip().lower() for p in phases_raw.split(",") if p.strip()}
    if not phase_tokens or "all" in phase_tokens:
        phases = {"download_assets", "build_prompts", "generate_images", "generate_tts", "cloth_images", "cloth_changed", "upload_assets"}
    else:
        phases = set()
        for token in phase_tokens:
            if token in {"download_assets", "download"}:
                phases.add("download_assets")
            elif token in {"build_prompts", "character_prompts", "location_prompts", "fenjing_prompts", "fenjing"}:
                phases.add("build_prompts")
            elif token in {"generate_images", "character_images", "location_images"}:
                phases.add("generate_images")
            elif token in {"cloth", "cloth_images"}:
                phases.add("cloth_images")
            elif token in {"cloth_changed", "cloth_changed_images"}:
                phases.add("cloth_changed")
            elif token in {"generate_tts", "tts"}:
                phases.add("generate_tts")
            elif token in {"upload_assets", "upload"}:
                phases.add("upload_assets")
            elif token == "character":
                phases.add("build_prompts")
                phases.add("generate_images")
            elif token == "location":
                phases.add("build_prompts")
                phases.add("generate_images")

    full_phase_run = is_full_phase_run(phases)

    if full_phase_run:
        emit_event(
            "INFO",
            "visual_audio_assets",
            "flow_start",
            f"Using Assets Directory: {base_dir}",
            step="start",
            project=project_name,
        )

    # 资产生成主阶段标记，仅用于流程状态边界，不影响具体 phase 执行
    emit_event(
        "INFO",
        "visual_audio_assets",
        "step_progress",
        f"Starting Asset Generation Workflow for Project: {project_name}",
        step="start",
        project=project_name,
    )
    emit_event(
        "INFO",
        "visual_audio_assets",
        "phase_start",
        "phase_assets_generation",
        step="phase_assets_generation",
        phase="phase_assets_generation",
        project=project_name,
    )
    emit_event(
        "INFO",
        "visual_audio_assets",
        "log",
        f"Starting Asset Generation Workflow for Project: {project_name}",
        step="general",
        project=project_name,
    )

    reference_chars = read_jsonl(str(char_jsonl))
    emit_event(
        "INFO",
        "visual_audio_assets",
        "load_complete",
        f"Loaded {len(reference_chars)} characters for ID validation",
        step="download_assets",
        project=project_name,
        data={"count": len(reference_chars), "type": "characters"},
    )
    reference_locations = read_jsonl(str(loc_jsonl))
    emit_event(
        "INFO",
        "visual_audio_assets",
        "load_complete",
        f"Loaded {len(reference_locations)} locations for ID validation",
        step="download_assets",
        project=project_name,
        data={"count": len(reference_locations), "type": "locations"},
    )
    defaults = load_char_defaults(char_jsonl)

    tos_assets = TosClientWrapper()

    loop = asyncio.get_running_loop()

    character_prompts_path: Optional[Path] = None
    character_qc_prompts_path: Optional[Path] = None

    async def run_character_prompts_workflow() -> Tuple[Path, Path]:
        emit_event(
            "INFO",
            "visual_audio_assets",
            "step_progress",
            "Building Character Prompts",
            step="character_prompts",
            project=project_name,
        )
        emit_event(
            "INFO",
            "visual_audio_assets",
            "log",
            "Starting Character Workflow...",
            step="general",
            project=project_name,
        )
        emit_event(
            "INFO",
            "visual_audio_assets",
            "log",
            "Building Character Prompts with validation...",
            step="general",
            project=project_name,
        )
        char_prompts_path = await loop.run_in_executor(
            None, build_character_prompts_with_retry, char_jsonl, char_prompt_tpl, reference_chars, 2, project_name
        )
        emit_event(
            "INFO",
            "visual_audio_assets",
            "log",
            f"Character Prompts saved to: {char_prompts_path}",
            step="character_images",
            project=project_name,
        )
        upload_jsonl_to_assets(tos_assets, char_prompts_path, "build_prompts")
        tos_char_prompts_path = base_dir / "character_prompts_from_tos.jsonl"
        # 使用项目特定的TOS前缀，支持多项目并行
        project_prefixes = runtime_config.get_project_prefixes(project_name) if project_name else {}
        tos_assets_prefix = project_prefixes.get("TOS_ASSETS_PREFIX", "")
        if tos_assets_prefix:
            tos_char_prompts_key = f"{tos_assets_prefix}/character_prompts.jsonl"
            downloaded = _vaa_download_file_from_tos(tos_assets, runtime_config.TOS_BUCKET, tos_char_prompts_key, tos_char_prompts_path)
        else:
            downloaded = False
        qc_prompts_path = tos_char_prompts_path if downloaded and tos_char_prompts_path.exists() else char_prompts_path

        emit_event(
            "INFO",
            "visual_audio_assets",
            "phase_complete",
            "character prompts completed",
            step="character_prompts",
            project=project_name,
        )
        return Path(char_prompts_path), Path(qc_prompts_path)

    def resolve_character_prompts_paths() -> Tuple[Path, Path]:
        candidates = [
            base_dir / "character_prompts_from_tos.jsonl",
            base_dir / "character_prompts.jsonl",
        ]
        for path in candidates:
            if path.exists():
                return path, path
        raise FileNotFoundError("character_prompts.jsonl not found")

    async def run_character_images_workflow() -> None:
        nonlocal character_prompts_path, character_qc_prompts_path
        if not character_prompts_path or not character_qc_prompts_path:
            character_prompts_path, character_qc_prompts_path = resolve_character_prompts_paths()
        qc_prompts_path = character_qc_prompts_path

        emit_event(
            "INFO",
            "visual_audio_assets",
            "log",
            "Generating Character Images with Streaming QC...",
            step="general",
            project=project_name,
        )
        emit_event(
            "INFO",
            "visual_audio_assets",
            "step_progress",
            "Generating Character Images",
            step="character_images",
            project=project_name,
        )

        # 使用项目特定的TOS前缀，支持多项目并行
        project_prefixes = runtime_config.get_project_prefixes(project_name) if project_name else {}
        tos_character_prefix = project_prefixes.get("TOS_CHARACTER_PREFIX", "")

        prompt_map: Dict[str, Dict[str, Any]] = {}
        try:
            for it in read_jsonl(str(qc_prompts_path)):
                k = it.get("Character_Id")
                if isinstance(k, str) and k:
                    prompt_map[k] = it
        except (IOError, OSError):
            prompt_map = {}

        sys_prompt = read_text(char_qc_prompt_tpl)
        thinking = runtime_config.QC_THINKING if runtime_config.QC_THINKING != "disabled" else None
        reasoning_effort = runtime_config.QC_REASONING_EFFORT if runtime_config.QC_REASONING_EFFORT != "disabled" else None

        qc_results: List[Dict[str, Any]] = []
        total_generated_count = 0

        async def on_image_generated(image_path: Path, _item: Dict[str, Any], idx: int) -> None:
            nonlocal total_generated_count
            total_generated_count += 1

            base_id = Path(image_path.name).stem
            prompt_item = prompt_map.get(base_id)

            key = f"{tos_character_prefix}/{image_path.name}"
            uri = None
            presigned = None
            if tos_assets.available():
                uri = tos_assets.upload_file(runtime_config.TOS_BUCKET, key, image_path)
            if tos_assets.available():
                presigned = tos_assets.presign_get(runtime_config.TOS_BUCKET, key)

            emit_event(
                "INFO",
                "visual_audio_assets",
                "log",
                f"Uploaded - File: {image_path.name}, Progress: {idx+1}, Total Generated: {total_generated_count}",
                step="upload_assets",
                project=project_name,
            )
            emit_event(
                "INFO",
                "visual_audio_assets",
                "upload_progress",
                f"Uploaded - File: {image_path.name}",
                step="character_images",
                project=project_name,
                data={
                    "file": image_path.name,
                    "progress": idx + 1,
                    "generated": total_generated_count,
                    "image_type": "character",
                    "image_id": base_id,
                },
            )

            ok = False
            attempts = 0
            retry = 1
            qc_result = None
            regen_count = 0

            while attempts <= retry and not ok:
                attempts += 1
                emit_event(
                    "INFO",
                    "visual_audio_assets",
                    "log",
                    f"QC Check - File: {image_path.name}, Attempt: {attempts}/{retry+1}",
                    step="qc",
                    project=project_name,
                )
                user_text = json.dumps(prompt_item, ensure_ascii=False) if prompt_item else None
                tos_path = f"tos://{runtime_config.TOS_BUCKET}/{key}"
                emit_event(
                    "INFO",
                    "visual_audio_assets",
                    "log",
                    f"QC Input - File: {image_path.name}, TOS: {tos_path}, Text: {user_text}",
                    step="qc",
                    project=project_name,
                )

                r = await qc_image_async(sys_prompt, presigned, user_text=user_text, thinking=thinking, reasoning_effort=reasoning_effort)
                qc_result = r

                try:
                    content = r.get("content") if isinstance(r, dict) else None
                    parsed = json.loads(content) if content else {}
                    ok = bool(parsed.get("check_result"))
                    emit_event(
                        "INFO",
                        "visual_audio_assets",
                        "log",
                        f"QC Result - File: {image_path.name}, Pass: {ok}, Content: {content[:100] if content else 'N/A'}...",
                        step="qc",
                        project=project_name,
                    )
                except (json.JSONDecodeError, ValueError) as e:
                    emit_event(
                        "ERROR",
                        "visual_audio_assets",
                        "log",
                        f"QC Parse Error - File: {image_path.name}, Error: {e}",
                        step="qc",
                        project=project_name,
                    )
                    ok = False

                if ok:
                    emit_event(
                        "INFO",
                        "visual_audio_assets",
                        "log",
                        f"QC Passed - File: {image_path.name}, Attempts: {attempts}",
                        step="qc",
                        project=project_name,
                    )
                    qc_results.append({
                        "file": image_path.name,
                        "uri": uri,
                        "presigned": presigned,
                        "qc": r,
                        "qc_pass": True,
                        "qc_attempts": attempts,
                        "qc_regen_count": regen_count
                    })
                    return

                if not ok and attempts <= retry:
                    prompt_item = resolve_prompt_item(image_path.name, prompt_map)
                    prompt_text = None
                    size_override = None
                    if prompt_item:
                        size_override = resolve_character_size_by_attribute(prompt_item.get("attribute"))
                        prompt_text = prompt_item.get("st_prompt") or prompt_item.get("prompt")

                    if isinstance(prompt_text, str) and prompt_text.strip():
                        base_id = Path(image_path.name).stem
                        emit_event(
                            "INFO",
                            "visual_audio_assets",
                            "log",
                            f"QC Failed - File: {image_path.name}, Regenerating image...",
                            step="qc",
                            project=project_name,
                        )
                        out_dir = image_path.parent
                        new_path = await generate_and_download(prompt_text, out_dir, base_id, size=size_override)
                        if isinstance(new_path, Path):
                            image_path = new_path
                            key = f"{tos_character_prefix}/{image_path.name}"
                            if tos_assets.available():
                                uri = tos_assets.upload_file(runtime_config.TOS_BUCKET, key, image_path)
                            if tos_assets.available():
                                presigned = tos_assets.presign_get(runtime_config.TOS_BUCKET, key)
                            emit_event(
                                "INFO",
                                "visual_audio_assets",
                                "log",
                                f"Image Regenerated - File: {image_path.name}, New path: {image_path}",
                                step="general",
                                project=project_name,
                            )
                            regen_count += 1
                            total_generated_count += 1
                            continue
                        emit_event(
                            "WARN",
                            "visual_audio_assets",
                            "log",
                            f"QC Regenerate Failed - File: {image_path.name}, Reason: no new image",
                            step="qc",
                            project=project_name,
                        )
                    else:
                        emit_event(
                            "WARN",
                            "visual_audio_assets",
                            "log",
                            f"QC Regenerate Skipped - File: {image_path.name}, Reason: missing prompt text",
                            step="qc",
                            project=project_name,
                        )

            if not ok:
                emit_event(
                    "ERROR",
                    "visual_audio_assets",
                    "log",
                    f"QC Failed After All Retries - File: {image_path.name}, Total Attempts: {attempts}",
                    step="qc",
                    project=project_name,
                )
                qc_results.append({
                    "file": image_path.name,
                    "uri": uri,
                    "presigned": presigned,
                    "qc": qc_result,
                    "qc_pass": False,
                    "qc_attempts": attempts,
                    "qc_regen_count": regen_count
                })
        
        def resolve_prompt_item(filename: str, prompt_map: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
            if not prompt_map:
                return None
            base_id = Path(filename).stem
            return prompt_map.get(base_id)
        
        image_paths = await generate_images_with_qps(
            character_prompts_path,
            name_key="Character_Id",
            out_subdir="character_images",
            on_image_callback=on_image_generated,
            project_name=project_name
        )
        emit_event(
            "INFO",
            "visual_audio_assets",
            "log",
            f"Generated {len(image_paths)} character images.",
            step="character_images",
            project=project_name,
        )
        
        expected_images = len(image_paths)
        regen_total = sum(int(r.get("qc_regen_count", 0)) for r in qc_results)
        
        def resolve_qc_pass(result: Dict[str, Any]) -> bool:
            qc_pass = result.get("qc_pass")
            if isinstance(qc_pass, bool):
                return qc_pass
            if isinstance(qc_pass, str):
                return qc_pass.strip().lower() == "true"
            if qc_pass is None:
                qc = result.get("qc")
                if isinstance(qc, dict):
                    content = qc.get("content")
                    if isinstance(content, str):
                        try:
                            parsed = json.loads(content)
                            return bool(parsed.get("check_result"))
                        except (json.JSONDecodeError, ValueError):
                            return False
            return bool(qc_pass)

        passed_total = sum(1 for r in qc_results if resolve_qc_pass(r))
        emit_event(
            "INFO",
            "visual_audio_assets",
            "log",
            f"Character QC Completed. Expected: {expected_images}, Total Generated: {total_generated_count}, Regenerated: {regen_total}, Passed: {passed_total}",
            step="character_images",
            project=project_name,
        )
        qc_out_path = base_dir / "character_qc_results.jsonl"
        write_jsonl(str(qc_out_path), qc_results)

        emit_event(
            "INFO",
            "visual_audio_assets",
            "phase_complete",
            "character images completed",
            step="character_images",
            project=project_name,
        )

    async def run_location_workflow():
        emit_event(
            "INFO",
            "visual_audio_assets",
            "step_progress",
            "Building Location Prompts",
            step="location_prompts",
            project=project_name,
        )
        emit_event(
            "INFO",
            "visual_audio_assets",
            "log",
            "Starting Location Workflow...",
            step="general",
            project=project_name,
        )
        emit_event(
            "INFO",
            "visual_audio_assets",
            "log",
            "Building Location Prompts...",
            step="general",
            project=project_name,
        )
        loc_prompts_path = await loop.run_in_executor(
            None, build_location_prompts_with_retry, loc_jsonl, loc_prompt_tpl, reference_locations, 2, project_name
        )
        emit_event(
            "INFO",
            "visual_audio_assets",
            "log",
            f"Location Prompts saved to: {loc_prompts_path}",
            step="location_images",
            project=project_name,
        )
        upload_jsonl_to_assets(tos_assets, loc_prompts_path, "build_prompts")

        emit_event(
            "INFO",
            "visual_audio_assets",
            "phase_complete",
            "location prompts completed",
            step="location_prompts",
            project=project_name,
        )

    async def run_location_image_workflow():
        emit_event(
            "INFO",
            "visual_audio_assets",
            "step_progress",
            "Generating Location Images",
            step="location_images",
            project=project_name,
        )
        loc_prompts_jsonl = base_dir / "location_prompts.jsonl"
        if not loc_prompts_jsonl.exists():
            if tos_assets.available():
                # 使用项目特定的TOS前缀，支持多项目并行
                project_prefixes = runtime_config.get_project_prefixes(project_name) if project_name else {}
                tos_assets_prefix = project_prefixes.get("TOS_ASSETS_PREFIX", "")
                if tos_assets_prefix:
                    key = f"{tos_assets_prefix}/location_prompts.jsonl"
                    _vaa_download_file_from_tos(tos_assets, runtime_config.TOS_BUCKET, key, loc_prompts_jsonl)
        if not loc_prompts_jsonl.exists():
            emit_event(
                "ERROR",
                "visual_audio_assets",
                "flow_error",
                f"Location prompts not found: {loc_prompts_jsonl}",
                step="location_images",
                project=project_name,
            )
            raise FileNotFoundError(str(loc_prompts_jsonl))
        location_prompt_map = build_location_prompt_map(loc_prompts_jsonl)

        chapters = sorted(storyboards_dir.glob("storyboard_chapter_*.jsonl"))
        fenjing_prompts_paths: List[Path] = []
        # 使用项目特定的TOS前缀，支持多项目并行
        project_prefixes = runtime_config.get_project_prefixes(project_name) if project_name else {}
        tos_assets_prefix = project_prefixes.get("TOS_ASSETS_PREFIX", "")
        for chapter_file in chapters:
            chapter_name = chapter_file.stem
            fenjing_path = base_dir / "storyboards" / chapter_name / "fenjing_prompts.jsonl"
            if not fenjing_path.exists() and tos_assets.available() and tos_assets_prefix:
                key = f"{tos_assets_prefix}/storyboards/{chapter_name}/fenjing_prompts.jsonl"
                _vaa_download_file_from_tos(tos_assets, runtime_config.TOS_BUCKET, key, fenjing_path)
            fenjing_prompts_paths.append(fenjing_path)
        missing = [str(p) for p in fenjing_prompts_paths if not p.exists()]
        if missing:
            emit_event(
                "ERROR",
                "visual_audio_assets",
                "flow_error",
                "Fenjing prompts missing for location images",
                step="location_images",
                project=project_name,
                data={"missing": missing},
            )
            raise FileNotFoundError(",".join(missing))
        needed = [x for x in collect_needed_locations(fenjing_prompts_paths) if x]
        await generate_location_images_shared(location_prompt_map, base_dir / "location_images", needed=needed, project_name=project_name)

        emit_event(
            "INFO",
            "visual_audio_assets",
            "phase_complete",
            "location images completed",
            step="location_images",
            project=project_name,
        )

    async def run_tts_workflow():
        emit_event(
            "INFO",
            "visual_audio_assets",
            "step_progress",
            "Generating TTS Audios",
            step="tts",
            project=project_name,
        )
        emit_event(
            "INFO",
            "visual_audio_assets",
            "log",
            "Starting TTS Workflow...",
            step="general",
            project=project_name,
        )
        chapters = sorted(storyboards_dir.glob("storyboard_chapter_*.jsonl"))
        if not chapters:
            emit_event(
                "WARN",
                "visual_audio_assets",
                "log",
                "No storyboard chapter files found in storyboards directory.",
                step="general",
                project=project_name,
            )
            return

        emit_event(
            "INFO",
            "visual_audio_assets",
            "log",
            f"Found {len(chapters)} chapters for TTS.",
            step="tts",
            project=project_name,
        )

        tos = TosClientWrapper()
        tts_limit = runtime_config.TTS_TOTAL_CONCURRENCY
        tts_semaphore = asyncio.Semaphore(tts_limit)

        async def process_chapter_tts(chapter_file: Path):
            emit_event(
                "INFO",
                "visual_audio_assets",
                "log",
                f"Processing TTS for {chapter_file.name}...",
                step="tts",
                project=project_name,
            )
            tts_prompts_path = await loop.run_in_executor(
                None, build_tts_prompts_for_chapter, chapter_file, tts_prompt_tpl
            )
            audio_out_dir = base_dir / "tts_audio" / chapter_file.stem
            # 使用项目特定的TOS前缀，支持多项目并行
            project_prefixes = runtime_config.get_project_prefixes(project_name) if project_name else {}
            tos_tts_prefix = project_prefixes.get("TOS_TTS_PREFIX", "")
            if tos_tts_prefix:
                chapter_tos_prefix = f"{tos_tts_prefix}/{chapter_file.stem}"
            else:
                chapter_tos_prefix = ""
            await generate_tts_audios(
                tts_prompts_path,
                audio_out_dir,
                tos,
                max_concurrency=tts_limit,
                custom_tos_prefix=chapter_tos_prefix,
                semaphore=tts_semaphore,
                project_name=project_name,
                chapter_name=chapter_file.stem,
            )
            emit_event(
                "INFO",
                "visual_audio_assets",
                "log",
                f"TTS for {chapter_file.name} completed.",
                step="tts",
                project=project_name,
            )

        await asyncio.gather(*(process_chapter_tts(ch) for ch in chapters))

        emit_event(
            "INFO",
            "visual_audio_assets",
            "phase_complete",
            "tts completed",
            step="tts",
            project=project_name,
        )

    async def run_fenjing_prompt_workflow():
        emit_event(
            "INFO",
            "visual_audio_assets",
            "step_progress",
            "Building Fenjing Prompts",
            step="fenjing_prompts",
            project=project_name,
        )
        emit_event(
            "INFO",
            "visual_audio_assets",
            "log",
            "Starting Fenjing Prompt Workflow...",
            step="general",
            project=project_name,
        )
        chapters = sorted(storyboards_dir.glob("storyboard_chapter_*.jsonl"))
        if not chapters:
            emit_event(
                "WARN",
                "visual_audio_assets",
                "log",
                "No storyboard chapter files found for fenjing prompts.",
                step="general",
                project=project_name,
            )
            return

        async def process_chapter_fenjing(chapter_file: Path):
            chapter_name = chapter_file.stem
            chapter_dir = base_dir / "storyboards" / chapter_name
            ensure_dir(chapter_dir)
            chapter_storyboards = chapter_dir / chapter_file.name
            write_jsonl(str(chapter_storyboards), read_jsonl(str(chapter_file)))
            fenjing_prompt_tpl = str(prompt_dir / "fenjing_build.txt")
            fen_prompts = await loop.run_in_executor(
                None, build_fenjing_prompts_with_retry, chapter_storyboards, fenjing_prompt_tpl, 2
            )
            await loop.run_in_executor(
                None, enforce_fenjing_prompts, fen_prompts, chapter_storyboards, char_jsonl, defaults
            )
            if tos_assets.available():
                # 使用项目特定的TOS前缀，支持多项目并行
                project_prefixes = runtime_config.get_project_prefixes(project_name) if project_name else {}
                tos_assets_prefix = project_prefixes.get("TOS_ASSETS_PREFIX", "")
                if tos_assets_prefix:
                    key = f"{tos_assets_prefix}/storyboards/{chapter_name}/fenjing_prompts.jsonl"
                    uploaded = tos_assets.upload_file(runtime_config.TOS_BUCKET, key, fen_prompts)
                    if uploaded:
                        emit_event(
                            "INFO",
                            "visual_audio_assets",
                            "log",
                            f"Uploaded fenjing prompts to {key}",
                            step="fenjing_prompts",
                            project=project_name,
                        )
                    else:
                        emit_event(
                            "WARN",
                            "visual_audio_assets",
                            "log",
                            f"Failed to upload fenjing prompts to {key}",
                        step="fenjing_prompts",
                        project=project_name,
                    )

        if "build_prompts" not in phases:
            emit_event(
                "INFO",
                "visual_audio_assets",
                "log",
                "Fenjing prompts generation skipped by phase selector",
                step="general",
                project=project_name,
            )
            return

        tasks: List[asyncio.Task] = []
        for idx, chapter_file in enumerate(chapters):
            tasks.append(asyncio.create_task(process_chapter_fenjing(chapter_file)))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        failed = [r for r in results if isinstance(r, Exception)]
        if failed:
            for r in failed:
                emit_event(
                    "ERROR",
                    "visual_audio_assets",
                    "flow_error",
                    f"Fenjing Prompt Workflow failed: {r}",
                    step="fenjing_prompts",
                    project=project_name,
                )
            raise RuntimeError("Fenjing prompts generation failed")

        emit_event(
            "INFO",
            "visual_audio_assets",
            "phase_complete",
            "fenjing prompts completed",
            step="fenjing_prompts",
            project=project_name,
        )

    async def run_cloth_workflow():
        cloth_images_selected = "cloth_images" in phases
        cloth_changed_selected = "cloth_changed" in phases
        phase_step = "phase_cloth_generation" if cloth_images_selected else "cloth_changed"
        emit_event(
            "INFO",
            "visual_audio_assets",
            "phase_start",
            "phase_cloth_generation",
            step=phase_step,
            phase="phase_cloth_generation",
            project=project_name,
        )
        try:
            validate_step = "validate_cloth" if cloth_images_selected else "cloth_changed"
            emit_event(
                "INFO",
                "visual_audio_assets",
                "step_progress",
                "validate_cloth_changes",
                step=validate_step,
                project=project_name,
            )
            stats = await loop.run_in_executor(None, validate_outfit_changes, storyboards_dir, char_jsonl)
            emit_event(
                "INFO",
                "visual_audio_assets",
                "step_progress",
                "validate_cloth_changes_done",
                step=validate_step,
                project=project_name,
                data=stats,
            )
            cloth_upload = []
            if cloth_images_selected:
                emit_event(
                    "INFO",
                    "visual_audio_assets",
                    "step_progress",
                    "generate_cloth_images",
                    step="cloth_images",
                    project=project_name,
                )
                cloth_upload = await loop.run_in_executor(None, generate_cloth_images, char_jsonl, base_dir, "", project_name)
                cloth_upload_path = base_dir / "cloth_upload.jsonl"
                write_jsonl(str(cloth_upload_path), cloth_upload)
                upload_jsonl_to_assets(tos_assets, cloth_upload_path, "cloth_images")
                emit_event(
                    "INFO",
                    "visual_audio_assets",
                    "phase_complete",
                    "cloth images completed",
                    step="cloth_images",
                    project=project_name,
                )
            if cloth_changed_selected:
                defaults = load_char_defaults(char_jsonl)
                has_changes = has_cloth_changed_targets(char_jsonl, defaults)
                if not has_changes:
                    emit_event(
                        "INFO",
                        "visual_audio_assets",
                        "phase_complete",
                        "cloth changed completed",
                        step="cloth_changed",
                        project=project_name,
                    )
                else:
                    emit_event(
                        "INFO",
                        "visual_audio_assets",
                        "step_progress",
                        "generate_cloth_changed_images",
                        step="cloth_changed",
                        project=project_name,
                    )
                    cloth_changed_upload = []
                    if not cloth_upload:
                        cloth_upload = load_upload_jsonl(base_dir, "cloth_upload.jsonl")
                    char_map = prepare_character_map(base_dir / "character_images", project_name)
                    if not char_map:
                        char_map = build_character_presigned_map(char_jsonl, project_name)
                    cloth_changed_upload = await loop.run_in_executor(
                        None,
                        generate_cloth_changed_images,
                        char_jsonl,
                        cloth_upload,
                        char_map,
                        base_dir,
                        "",
                        project_name,
                    )
                    cloth_changed_path = base_dir / "cloth_changed_upload.jsonl"
                    write_jsonl(str(cloth_changed_path), cloth_changed_upload)
                    upload_jsonl_to_assets(tos_assets, cloth_changed_path, "cloth_changed")
                    emit_event(
                        "INFO",
                        "visual_audio_assets",
                        "phase_complete",
                        "cloth changed completed",
                        step="cloth_changed",
                        project=project_name,
                    )
        except (IOError, OSError) as exc:
            emit_event(
                "ERROR",
                "visual_audio_assets",
                "flow_error",
                f"Cloth workflow failed: {exc}",
            step="cloth_images",
                project=project_name,
            )
            raise
        emit_event(
            "INFO",
            "visual_audio_assets",
            "phase_complete",
            "phase_cloth_generation completed",
            step=phase_step,
            phase="phase_cloth_generation",
            project=project_name,
        )

    task_specs: List[Tuple[str, asyncio.Task]] = []
    if "build_prompts" in phases:
        task_specs.append(("character_prompts", asyncio.create_task(run_character_prompts_workflow())))
        task_specs.append(("location_prompts", asyncio.create_task(run_location_workflow())))
        task_specs.append(("fenjing_prompts", asyncio.create_task(run_fenjing_prompt_workflow())))
    if "generate_tts" in phases:
        task_specs.append(("generate_tts", asyncio.create_task(run_tts_workflow())))
    failed_phases: Dict[str, str] = {}
    if task_specs:
        results = await asyncio.gather(*(t for _, t in task_specs), return_exceptions=True)
        for (name, _), result in zip(task_specs, results):
            if isinstance(result, Exception):
                failed_phases[name] = str(result)
                emit_event(
                    "ERROR",
                    "visual_audio_assets",
                    "flow_error",
                    f"Phase failed: {name}",
                    step={
                        "character_prompts": "character_prompts",
                        "location_prompts": "location_prompts",
                        "generate_tts": "tts",
                        "fenjing_prompts": "fenjing_prompts",
                    }.get(name, name),
                    project=project_name,
                    data={"error": str(result)},
                )
            elif name == "character_prompts":
                character_prompts_path, character_qc_prompts_path = result
    if "generate_images" in phases:
        if "location_prompts" in failed_phases or "fenjing_prompts" in failed_phases:
            emit_event(
                "WARN",
                "visual_audio_assets",
                "flow_error",
                "Location images skipped due to prompt failures",
                step="location_images",
                project=project_name,
                data={"failed": list(failed_phases.keys())},
            )
        else:
            try:
                await run_character_images_workflow()
                await run_location_image_workflow()
            except (IOError, OSError) as exc:
                failed_phases["location_images"] = str(exc)
                emit_event(
                    "ERROR",
                    "visual_audio_assets",
                    "flow_error",
                    f"Location images failed: {exc}",
                    step="location_images",
                    project=project_name,
                )
    if "upload_assets" in phases:
        try:
            await run_upload_assets_workflow(base_dir, project_name)
        except Exception:
            pass
    if "cloth_images" in phases or "cloth_changed" in phases:
        try:
            await run_cloth_workflow()
        except (IOError, OSError) as exc:
            failed_phases["cloth_images"] = str(exc)
    emit_event(
        "INFO",
        "visual_audio_assets",
        "phase_complete",
        "phase_assets_generation completed",
        step="phase_assets_generation",
        phase="phase_assets_generation",
        project=project_name,
    )
    if full_phase_run:
        if failed_phases:
            emit_event(
                "WARN",
                "visual_audio_assets",
                "flow_complete",
                "Workflows completed with errors",
                step="complete",
                project=project_name,
                data={"failed": failed_phases},
            )
            emit_event(
                "WARN",
                "visual_audio_assets",
                "log",
                "Workflows completed with errors.",
                step="general",
                project=project_name,
            )
        else:
            emit_event(
                "INFO",
                "visual_audio_assets",
                "flow_complete",
                "All workflows completed successfully",
                step="complete",
                project=project_name,
            )
            emit_event(
                "INFO",
                "visual_audio_assets",
                "log",
                "All workflows completed successfully.",
                step="general",
                project=project_name,
            )

if __name__ == "__main__":
    asyncio.run(main())
