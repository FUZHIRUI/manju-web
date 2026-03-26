import json
import re
import asyncio
import time
import urllib.parse
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from concurrent.futures import as_completed
from .provider_runtime import (
    download, generate_image, generate_image_with_refs, run_async, size_for_2k_9x16, TosClientWrapper, emit_event, with_thread_pool_limit,
)
from .io_jsonl import write_jsonl, read_jsonl
from .json_fields import fix_fenjing_character_fields
from . import runtime_config

# 从visual_audio_assets导入的函数已内联，避免导入冲突导致的函数覆盖问题

# 内联 character_keys_sorted 函数
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

# 内联 prepare_character_map 函数
def prepare_character_map(char_dir: Path, project_name: Optional[str] = None) -> Dict[str, str]:
    tos = TosClientWrapper()
    char_map: Dict[str, str] = {}
    if not project_name:
        return char_map
    # 使用项目特定的TOS前缀，支持多项目并行
    project_prefixes = runtime_config.get_project_prefixes(project_name)
    tos_character_prefix = project_prefixes.get("TOS_CHARACTER_PREFIX", "")
    if not tos_character_prefix:
        return char_map
    if char_dir.exists():
        for f in char_dir.glob("*.png"):
            name = f.name
            base = name[:-4]
            if base.endswith("st"):
                char_id = base[:-2]
            else:
                char_id = base
            key = f"{tos_character_prefix}/{name}"
            presigned = tos.presign_get(runtime_config.TOS_BUCKET, key) if tos.available() else None
            if presigned:
                char_map[char_id] = presigned
    return char_map

# 内联 build_character_presigned_map 函数
def build_character_presigned_map(chars_jsonl_path: Path, project_name: Optional[str] = None) -> Dict[str, str]:
    items = read_jsonl(str(chars_jsonl_path))
    tos = TosClientWrapper()
    m: Dict[str, str] = {}
    if not tos.available():
        return m
    if not project_name:
        return m
    # 使用项目特定的TOS前缀，支持多项目并行
    project_prefixes = runtime_config.get_project_prefixes(project_name)
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

# 内联 load_char_defaults 函数
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

# 内联 load_char_plot_outfits 函数
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

# 内联 download_file_from_tos 函数，避免导入冲突
def _download_file_from_tos(tos: TosClientWrapper, bucket: str, key: str, local_path: Path, project_name: Optional[str] = None) -> bool:
    """Download a file from TOS to local path."""
    if not tos.available():
        return False
    actual_project_name = project_name
    try:
        client = tos._client if hasattr(tos, "_client") else None
        if not client:
            return False
        resp = client.get_object(bucket, key)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with open(local_path, "wb") as f:
            f.write(resp.read())
        return True
    except Exception as e:
        # 捕获所有异常，包括 TosServerError
        emit_event(
            "WARN",
            "fenjing",
            "download_failed",
            f"Failed to download {key}: {e}",
            step="step_download",
            project=actual_project_name,
            data={"key": key, "error": str(e)},
        )
        return False

# 内联 load_upload_jsonl 函数
def load_upload_jsonl(base_dir: Path, filename: str, project_name: Optional[str] = None, optional: bool = False) -> List[Dict[str, Any]]:
    target_path = base_dir / filename
    if not target_path.exists():
        tos = TosClientWrapper()
        if tos.available() and project_name:
            project_prefixes = runtime_config.get_project_prefixes(project_name)
            tos_assets_prefix = project_prefixes.get("TOS_ASSETS_PREFIX", "")
            if tos_assets_prefix:
                key = f"{tos_assets_prefix}/{filename}"
                _download_file_from_tos_optional(tos, runtime_config.TOS_BUCKET, key, target_path, project_name=project_name, optional=optional)
    if target_path.exists():
        try:
            return read_jsonl(str(target_path))
        except (IOError, OSError):
            return []
    return []

def _download_file_from_tos_optional(tos: TosClientWrapper, bucket: str, key: str, local_path: Path, project_name: Optional[str] = None, optional: bool = False) -> bool:
    if not tos.available():
        return False
    actual_project_name = project_name
    try:
        client = tos._client if hasattr(tos, "_client") else None
        if not client:
            return False
        resp = client.get_object(bucket, key)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with open(local_path, "wb") as f:
            f.write(resp.read())
        return True
    except Exception as e:
        level = "DEBUG" if optional else "WARN"
        emit_event(
            level,
            "fenjing",
            "download_failed",
            f"Failed to download {key}: {e}",
            step="step_download",
            project=actual_project_name,
            data={"key": key, "error": str(e), "optional": optional},
        )
        return False

def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)



def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def list_tos_keys(tos: TosClientWrapper, bucket: str, prefix: str, log_prefix: str = "", project_name: Optional[str] = None) -> List[str]:
    if not tos.available():
        return []
    client = tos._client if hasattr(tos, "_client") else None
    if not client:
        return []
    keys: List[str] = []
    actual_project_name = project_name
    try:
        resp = None
        if hasattr(client, "list_objects_type2"):
            resp = client.list_objects_type2(bucket, prefix=prefix)
        elif hasattr(client, "list_objects"):
            resp = client.list_objects(bucket, prefix=prefix)
        if resp is None:
            return []
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
    except (IOError, OSError) as e:
        emit_event(
            "WARN",
            "fenjing",
            "log",
            f"{log_prefix}Failed to list TOS keys for prefix : {e}",
            step="step_download",
            project=actual_project_name,
        )
        return []
    return keys


def download_storyboards_from_tos(base_dir: Path, prefix: str = "", project_name: Optional[str] = None) -> List[Path]:
    tos = TosClientWrapper()
    actual_project_name = project_name
    if not tos.available():
        emit_event(
            "WARN",
            "fenjing",
            "log",
            f"TOS client not available, cannot download storyboards.",
            step="step_download",
            project=actual_project_name,
        )
        return []
    if not actual_project_name:
        return []
    # 使用项目特定的TOS前缀，支持多项目并行
    project_prefixes = runtime_config.get_project_prefixes(actual_project_name)
    tos_assets_prefix = project_prefixes.get("TOS_ASSETS_PREFIX", "")
    if not tos_assets_prefix:
        return []
    tos_prefix = f"{tos_assets_prefix}/storyboards/"
    keys = list_tos_keys(tos, runtime_config.TOS_BUCKET, tos_prefix, log_prefix=prefix, project_name=actual_project_name)
    if not keys:
        emit_event(
            "WARN",
            "fenjing",
            "log",
            f"No storyboard files found in TOS, falling back to local directory.",
            step="step_download",
            project=actual_project_name,
        )
        local_dir = base_dir / "storyboards"
        if local_dir.exists():
            return list(local_dir.rglob("storyboard_chapter_*.jsonl"))
        return []
    local_dir = base_dir / "storyboards"
    local_dir.mkdir(parents=True, exist_ok=True)
    local_files: List[Path] = []
    for key in keys:
        if not key.endswith(".jsonl"):
            continue
        fname = key.split("/")[-1]
        if not re.match(r"^storyboard_chapter_\d+\.jsonl$", fname):
            continue
        local_path = local_dir / fname
        if _download_file_from_tos(tos, runtime_config.TOS_BUCKET, key, local_path, project_name=actual_project_name):
            local_files.append(local_path)
    return local_files


def prepare_location_map(input_dir: Path, project_name: Optional[str] = None) -> Dict[str, Dict[str, str]]:
    tos = TosClientWrapper()
    loc_map: Dict[str, Dict[str, str]] = {}
    if not project_name:
        return loc_map
    # 使用项目特定的TOS前缀，支持多项目并行
    project_prefixes = runtime_config.get_project_prefixes(project_name)
    tos_location_prefix = project_prefixes.get("TOS_LOCATION_PREFIX", "")
    if not tos_location_prefix:
        return loc_map
    loc_dir = input_dir / "location_images"
    if loc_dir.exists():
        for f in loc_dir.glob("*.png"):
            name = f.name
            base = name[:-4]
            if base.endswith("_standing"):
                loc_id = base[:-9]
                typ = "standing"
            elif base.endswith("_sitting"):
                loc_id = base[:-8]
                typ = "sitting"
            else:
                loc_id = base
                typ = "standing"
            key = f"{tos_location_prefix}/{name}"
            presigned = tos.presign_get(runtime_config.TOS_BUCKET, key) if tos.available() else None
            d = loc_map.get(loc_id) or {}
            if presigned:
                d[typ] = presigned
                loc_map[loc_id] = d
    return loc_map


def norm_bg_type(x: Optional[str]) -> str:
    if not isinstance(x, str):
        return "standing"
    s = x.strip().lower()
    if s.endswith("图"):
        s = s[:-1]
    if s in ("standing", "standding"):
        return "standing"
    if s in ("sitting", "siting"):
        return "sitting"
    return "standing"


#核心step
def generate_fenjing_images(
    fenjing_prompts_jsonl: Path,
    storyboards_jsonl: Path,
    input_dir: Path,
    cloth_changed_upload: List[Dict[str, Any]],
    chars_jsonl: Path,
    loc_map_override: Optional[Dict[str, Dict[str, str]]] = None,
    char_map_override: Optional[Dict[str, str]] = None,
    chapter_name: Optional[str] = None,
    project_name: Optional[str] = None
) -> Tuple[List[Path], List[Dict[str, Any]]]:
    project_info = f"[{project_name}] " if project_name else ""
    chapter_info = f"[{chapter_name}] " if isinstance(chapter_name, str) and chapter_name else ""
    chapter_label = f"{project_info}{chapter_info}"
    
    loc_map = loc_map_override if isinstance(loc_map_override, dict) else prepare_location_map(input_dir, project_name)
    char_map = char_map_override if isinstance(char_map_override, dict) else prepare_character_map(input_dir / "character_images", project_name)
    cloth_changed_map: Dict[str, str] = {}
    for it in cloth_changed_upload or []:
        cid = it.get("character_id")
        oid = it.get("outfit_id")
        presigned = it.get("presigned")
        if isinstance(cid, str) and isinstance(oid, str) and isinstance(presigned, str) and cid and oid:
            cloth_changed_map[f"{cid}_{oid}"] = presigned
    defaults = load_char_defaults(chars_jsonl)
    plot_outfits = load_char_plot_outfits(chars_jsonl)
    storyboards = read_jsonl(str(storyboards_jsonl))
    prompts = read_jsonl(str(fenjing_prompts_jsonl))
    out_dir = input_dir / "fenjing_images"
    ensure_dir(out_dir)
    tos = TosClientWrapper()
    size_default = size_for_2k_9x16()
    
    debug_log_path = out_dir / "fenjing_generation_debug.log"
    debug_log_file = open(debug_log_path, "w", encoding="utf-8") if out_dir.exists() else None
    if debug_log_file:
        debug_log_file.write(f"=== Fenjing Generation Debug Log ===\n")
        debug_log_file.write(f"Chapter: {chapter_name or 'unknown'}\n")
        debug_log_file.write(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        debug_log_file.write(f"{'='*50}\n\n")
        debug_log_file.flush()
    
    def log_debug(message: str) -> None:
        emit_event(
            "DEBUG",
            "fenjing",
            "log",
            message,
            step="step_generate",
            project=project_name,
        )
        if debug_log_file:
            debug_log_file.write(f"{message}\n")
            debug_log_file.flush()

    def build_image_payload(prompt_text_val: str, ref_urls_val: List[str]) -> Dict[str, Any]:
        payload = {
            "model": runtime_config.SEEDREAM_MODEL,
            "prompt": prompt_text_val,
            "size": size_default,
            "watermark": False,
            "sequential_image_generation": "disabled"
        }
        if ref_urls_val:
            payload["image"] = ref_urls_val[0] if len(ref_urls_val) == 1 else ref_urls_val
        return payload
    
    results: List[Path] = []
    uploads: List[Dict[str, Any]] = []
    
    def presigned_to_tos_uri(url: str) -> str:
        if not isinstance(url, str) or not url:
            return ""
        try:
            parsed = urllib.parse.urlparse(url)
        except ValueError:
            return ""
        if not parsed.netloc or not parsed.path:
            return ""
        host = parsed.netloc
        path = parsed.path
        bucket = runtime_config.TOS_BUCKET
        if host.startswith(f"{bucket}."):
            key = path.lstrip("/")
            return f"tos://{bucket}/{key}" if key else ""
        bucket_prefix = f"/{bucket}/"
        if path.startswith(bucket_prefix):
            key = path[len(bucket_prefix):]
            return f"tos://{bucket}/{key}" if key else ""
        return ""

    async def process_single_fenjing(idx: int, item: Dict[str, Any], fen_id: int, refs: List[str], prompt_text: str) -> Optional[Dict[str, Any]]:
        fenjing_info = f"[fenjing{fen_id}] "
        fenjing_label = f"{chapter_label}{fenjing_info}"
        
        name_prefix = f"fenjing{fen_id}"
        retry = 1
        attempts = 0
        attempt_records: List[Dict[str, Any]] = []

        # Phase: download_assets，获取分镜生成依赖的基础素材
        emit_event(
            "INFO",
            "fenjing",
            "fenjing_image_start",
            f"Fenjing {fen_id} image generation start",
            step="step_generate",
            project=project_name,
            chapter=chapter_name,
            fenjing_id=str(fen_id),
            data={"attempts": retry + 1, "image_type": "fenjing", "image_id": str(fen_id)},
        )
        
        def add_attempt_record(
            attempt_status: str,
            file_path: Optional[Path] = None,
            uri_val: Optional[str] = None,
            presigned_val: Optional[str] = None,
            recheck_result: Optional[Dict[str, Any]] = None,
            ref_urls: Optional[List[str]] = None,
            origin_image_url: str = ""
        ) -> None:
            refs_list = ref_urls if isinstance(ref_urls, list) else []
            tos_uris = [presigned_to_tos_uri(r) for r in refs_list]
            tos_uris = [u for u in tos_uris if u]
            payload = build_image_payload(prompt_text, refs_list)
            attempt_records.append({
                "fenjing_id": fen_id,
                "prompt_text": prompt_text,
                "attempt": attempts,
                "attempt_status": attempt_status,
                "file": file_path.name if isinstance(file_path, Path) else None,
                "uri": uri_val,
                "presigned": presigned_val,
                "recheck_result": recheck_result,
                "ref_urls": ";".join(refs_list),
                "ref_tos_uris": ";".join(tos_uris),
                "image_payload": json.dumps(payload, ensure_ascii=False),
                "origin_image_url": origin_image_url
            })
        
        while attempts <= retry:
            attempts += 1
            log_debug(f"[INFO] {fenjing_label}Generating Fenjing Image - fenjing_id: {fen_id}, Attempt: {attempts}/{retry+1}")
            emit_event(
                "INFO",
                "fenjing",
                "fenjing_image_attempt",
                f"Fenjing {fen_id} generating (attempt {attempts}/{retry + 1})",
                step="step_generate",
                project=project_name,
                chapter=chapter_name,
                fenjing_id=str(fen_id),
                data={"attempt": attempts, "max_attempts": retry + 1, "image_type": "fenjing", "image_id": str(fen_id)},
            )
            
            origin_image_url = ""
            result = await generate_image_with_refs(prompt_text, refs, fenjing_id=fen_id)
            if not result or "data" not in result or not result["data"]:
                p = await generate_image(prompt_text, out_dir, f"fenjing{fen_id}")
                if isinstance(p, Path):
                    project_prefixes = runtime_config.get_project_prefixes(project_name) if project_name else {}
                    tos_fenjing_prefix = project_prefixes.get("TOS_FENJING_PREFIX", "")
                    if not tos_fenjing_prefix:
                        emit_event(
                            "WARN",
                            "fenjing",
                            "upload_progress",
                            f"fenjing image upload skipped: missing TOS prefix",
                            step="step_upload",
                            project=project_name,
                            chapter=chapter_name,
                            fenjing_id=str(fen_id),
                            data={"image_type": "fenjing", "image_id": str(fen_id), "ok": False, "reason": "missing_prefix"},
                        )
                        return {"fenjing_id": fen_id, "prompt_text": prompt_text, "file": p.name, "uri": None, "presigned": None, "attempt_records": attempt_records, "origin_image_url": ""}
                    key = f"{tos_fenjing_prefix}/{chapter_name}/{p.name}" if chapter_name else f"{tos_fenjing_prefix}/{p.name}"
                    uri = tos.upload_file(runtime_config.TOS_BUCKET, key, p) if tos.available() else None
                    presigned = tos.presign_get(runtime_config.TOS_BUCKET, key) if tos.available() else None
                    add_attempt_record("generated", file_path=p, uri_val=uri, presigned_val=presigned, ref_urls=refs, origin_image_url="")
                    emit_event(
                        "INFO",
                        "fenjing",
                        "fenjing_image_generated",
                        f"Fenjing {fen_id} image generated",
                        step="step_generate",
                        project=project_name,
                        chapter=chapter_name,
                        fenjing_id=str(fen_id),
                        data={
                            "file": p.name,
                            "key": key,
                            "uri": uri,
                            "presigned": presigned,
                            "image_type": "fenjing",
                            "image_id": str(fen_id),
                        },
                    )
                    emit_event(
                        "INFO",
                        "fenjing",
                        "upload_progress",
                        f"fenjing image uploaded: {p.name}",
                        step="step_upload",
                        project=project_name,
                        chapter=chapter_name,
                        fenjing_id=str(fen_id),
                        data={
                            "file": p.name,
                            "key": key,
                            "uri": uri,
                            "presigned": presigned,
                            "image_type": "fenjing",
                            "image_id": str(fen_id),
                        },
                    )
                    return {"fenjing_id": fen_id, "prompt_text": prompt_text, "file": p.name, "uri": uri, "presigned": presigned, "attempt_records": attempt_records, "origin_image_url": ""}
            if not result or "data" not in result or not result["data"]:
                log_debug(f"[ERROR] {fenjing_label}Generation Failed - fenjing_id: {fen_id}, Attempt: {attempts}")
                add_attempt_record("generation_failed", ref_urls=refs, origin_image_url=origin_image_url)
                if attempts <= retry:
                    continue
                emit_event(
                    "ERROR",
                    "fenjing",
                    "fenjing_image_failed",
                    f"Fenjing {fen_id} generation failed",
                    step="step_generate",
                    project=project_name,
                    chapter=chapter_name,
                    fenjing_id=str(fen_id),
                    data={"attempt": attempts, "image_type": "fenjing", "image_id": str(fen_id)},
                )
                emit_event(
                    "ERROR",
                    "fenjing",
                    "flow_error",
                    f"Fenjing {fen_id} 生成重试超限",
                    step="step_generate",
                    project=project_name,
                    chapter=chapter_name,
                    fenjing_id=str(fen_id),
                    data={"attempt": attempts, "max_attempts": retry + 1, "reason": "generation_failed"},
                )
                return {"fenjing_id": fen_id, "prompt_text": prompt_text, "file": None, "uri": None, "presigned": None, "attempt_records": attempt_records, "origin_image_url": origin_image_url}
            image_url = result["data"][0].get("url") if isinstance(result["data"][0], dict) else None
            if not isinstance(image_url, str) or not image_url:
                log_debug(f"[ERROR] {fenjing_label}Generation Failed - fenjing_id: {fen_id}, Attempt: {attempts}")
                add_attempt_record("generation_failed", ref_urls=refs, origin_image_url=origin_image_url)
                if attempts <= retry:
                    continue
                emit_event(
                    "ERROR",
                    "fenjing",
                    "fenjing_image_failed",
                    f"Fenjing {fen_id} generation failed (empty url)",
                    step="step_generate",
                    project=project_name,
                    chapter=chapter_name,
                    fenjing_id=str(fen_id),
                    data={"attempt": attempts, "image_type": "fenjing", "image_id": str(fen_id)},
                )
                emit_event(
                    "ERROR",
                    "fenjing",
                    "flow_error",
                    f"Fenjing {fen_id} 生成重试超限",
                    step="step_generate",
                    project=project_name,
                    chapter=chapter_name,
                    fenjing_id=str(fen_id),
                    data={"attempt": attempts, "max_attempts": retry + 1, "reason": "empty_url"},
                )
                return {"fenjing_id": fen_id, "prompt_text": prompt_text, "file": None, "uri": None, "presigned": None, "attempt_records": attempt_records, "origin_image_url": origin_image_url}
            origin_image_url = image_url
            save_path = out_dir / f"{name_prefix}.png"
            ok = await download(image_url, save_path)
            p = save_path if ok else None
            if not isinstance(p, Path):
                log_debug(f"[ERROR] {fenjing_label}Generation Failed - fenjing_id: {fen_id}, Attempt: {attempts}")
                add_attempt_record("generation_failed", ref_urls=refs, origin_image_url=origin_image_url)
                if attempts <= retry:
                    continue
                emit_event(
                    "ERROR",
                    "fenjing",
                    "fenjing_image_failed",
                    f"Fenjing {fen_id} download failed",
                    step="step_generate",
                    project=project_name,
                    chapter=chapter_name,
                    fenjing_id=str(fen_id),
                    data={"attempt": attempts, "image_type": "fenjing", "image_id": str(fen_id)},
                )
                emit_event(
                    "ERROR",
                    "fenjing",
                    "flow_error",
                    f"Fenjing {fen_id} 生成重试超限",
                    step="step_generate",
                    project=project_name,
                    chapter=chapter_name,
                    fenjing_id=str(fen_id),
                    data={"attempt": attempts, "max_attempts": retry + 1, "reason": "download_failed"},
                )
                return {"fenjing_id": fen_id, "prompt_text": prompt_text, "file": None, "uri": None, "presigned": None, "attempt_records": attempt_records, "origin_image_url": origin_image_url}
            
            # 使用项目特定的TOS前缀，支持多项目并行
            project_prefixes = runtime_config.get_project_prefixes(project_name) if project_name else {}
            tos_fenjing_prefix = project_prefixes.get("TOS_FENJING_PREFIX", "")
            if not tos_fenjing_prefix:
                emit_event(
                    "WARN",
                    "fenjing",
                    "upload_progress",
                    f"fenjing image upload skipped: missing TOS prefix",
                    step="step_upload",
                    project=project_name,
                    chapter=chapter_name,
                    fenjing_id=str(fen_id),
                    data={"image_type": "fenjing", "image_id": str(fen_id), "ok": False, "reason": "missing_prefix"},
                )
                return {"fenjing_id": fen_id, "prompt_text": prompt_text, "file": p.name, "uri": None, "presigned": None, "attempt_records": attempt_records, "origin_image_url": origin_image_url}
            key = f"{tos_fenjing_prefix}/{chapter_name}/{p.name}" if chapter_name else f"{tos_fenjing_prefix}/{p.name}"
            uri = tos.upload_file(runtime_config.TOS_BUCKET, key, p) if tos.available() else None
            presigned = tos.presign_get(runtime_config.TOS_BUCKET, key) if tos.available() else None
            
            add_attempt_record("generated", file_path=p, uri_val=uri, presigned_val=presigned, ref_urls=refs, origin_image_url=origin_image_url)
            emit_event(
                "INFO",
                "fenjing",
                "fenjing_image_generated",
                f"Fenjing {fen_id} image generated",
                step="step_generate",
                project=project_name,
                chapter=chapter_name,
                fenjing_id=str(fen_id),
                data={
                    "file": p.name,
                    "key": key,
                    "uri": uri,
                    "presigned": presigned,
                    "image_type": "fenjing",
                    "image_id": str(fen_id),
                },
            )
            emit_event(
                "INFO",
                "fenjing",
                "upload_progress",
                f"fenjing image uploaded: {p.name}",
                step="step_upload",
                project=project_name,
                chapter=chapter_name,
                fenjing_id=str(fen_id),
                data={
                    "file": p.name,
                    "key": key,
                    "uri": uri,
                    "presigned": presigned,
                    "image_type": "fenjing",
                    "image_id": str(fen_id),
                },
            )
            return {"fenjing_id": fen_id, "prompt_text": prompt_text, "file": p.name, "uri": uri, "presigned": presigned, "attempt_records": attempt_records, "origin_image_url": origin_image_url}
    
    with with_thread_pool_limit() as pool:
        futures = []
        skipped_items = 0
        for idx, item in enumerate(prompts):
            if not isinstance(item, dict):
                continue
            fen_id = item.get("fenjing_id")
            try:
                fen_id = int(fen_id)
            except (ValueError, TypeError):
                fen_id = idx + 1
            fenjing_info = f"[fenjing{fen_id}] "
            fenjing_label = f"{chapter_label}{fenjing_info}"
            loc_id = item.get("Location_Id") or item.get("location_id") or item.get("Background_pic")
            bg_type = norm_bg_type(item.get("Background_xuanze"))
            refs: List[str] = []
            sb = storyboards[idx] if idx < len(storyboards) else {}
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
            missing_chars: List[str] = []
            for pk in character_keys_sorted(item):
                cid = item.get(pk)
                if not isinstance(cid, str):
                    continue
                if cid in char_map:
                    num = pk.split("_")[1] if "_" in pk else ""
                    prefix = "Character" if pk.startswith("Character_") else "person"
                    current_outfit = item.get(f"{prefix}_{num}_outfit") or outfit_map.get(cid)
                    default_outfit = defaults.get(cid)
                    ref_url = None
                    if isinstance(current_outfit, str) and current_outfit and current_outfit != default_outfit:
                        changed_key = f"{cid}_{current_outfit}"
                        changed_presigned = cloth_changed_map.get(changed_key)
                        if isinstance(changed_presigned, str):
                            ref_url = changed_presigned
                            log_debug(f"[DEBUG] {fenjing_label}Using outfit-changed image (from upload list) - fenjing_id: {fen_id}, character_id: {cid}, outfit_id: {current_outfit}, ref_url: {ref_url[:100]}...")
                        else:
                            project_prefixes = runtime_config.get_project_prefixes(project_name) if project_name else {}
                            tos_cloth_prefix = project_prefixes.get("TOS_CLOTH_PREFIX", "")
                            remote_presigned = None
                            if tos_cloth_prefix:
                                remote_key = f"{tos_cloth_prefix}/{changed_key}.png"
                                remote_presigned = tos.presign_get(runtime_config.TOS_BUCKET, remote_key) if tos.available() else None
                            if isinstance(remote_presigned, str) and remote_presigned:
                                ref_url = remote_presigned
                                log_debug(f"[DEBUG] {fenjing_label}Using outfit-changed image (presigned) - fenjing_id: {fen_id}, character_id: {cid}, outfit_id: {current_outfit}, ref_url: {ref_url[:100]}...")
                            else:
                                ref_url = char_map[cid]
                                log_debug(f"[DEBUG] {fenjing_label}Outfit-changed image not found, using default - fenjing_id: {fen_id}, character_id: {cid}, outfit_id: {current_outfit}, ref_url: {ref_url[:100]}...")
                    else:
                        ref_url = char_map[cid]
                        log_debug(f"[DEBUG] {fenjing_label}Using default character image - fenjing_id: {fen_id}, character_id: {cid}, ref_url: {ref_url[:100]}...")
                    refs.append(ref_url)
                else:
                    missing_chars.append(cid)
            missing_loc = False
            if isinstance(loc_id, str) and loc_id:
                # 使用项目特定的TOS前缀，支持多项目并行
                project_prefixes = runtime_config.get_project_prefixes(project_name) if project_name else {}
                tos_location_prefix = project_prefixes.get("TOS_LOCATION_PREFIX", "")
                if tos_location_prefix:
                    remote_key = f"{tos_location_prefix}/{loc_id}_{bg_type}.png"
                    remote_presigned = tos.presign_get(runtime_config.TOS_BUCKET, remote_key) if tos.available() else None
                else:
                    remote_presigned = None
                if isinstance(remote_presigned, str) and remote_presigned:
                    refs.append(remote_presigned)
                elif loc_id in loc_map and bg_type in loc_map[loc_id]:
                    refs.append(loc_map[loc_id][bg_type])
                else:
                    missing_loc = True
            prompt_text = item.get("prompt") or ""
            if isinstance(prompt_text, str) and prompt_text.strip():
                if missing_chars or missing_loc or not refs:
                    if missing_chars:
                        log_debug(f"[WARN] {fenjing_label}Missing character refs - fenjing_id: {fen_id}, missing: {missing_chars}")
                    if missing_loc:
                        log_debug(f"[WARN] {fenjing_label}Missing location ref - fenjing_id: {fen_id}, Location_Id: {loc_id}, type: {bg_type}")
                    if not refs:
                        log_debug(f"[WARN] {fenjing_label}No refs for fenjing - fenjing_id: {fen_id}, skipping")
                    skipped_items += 1
                else:
                    char_keys = character_keys_sorted(item)
                    ref_mapping = []
                    char_idx = 0
                    for pk in char_keys:
                        cid = item.get(pk)
                        if isinstance(cid, str) and cid in char_map:
                            ref_mapping.append(f"ref[{char_idx}]={cid}")
                            char_idx += 1
                    if loc_id:
                        ref_mapping.append(f"ref[{char_idx}]=location_{loc_id}")
                    log_debug(f"[INFO] {fenjing_label}Fenjing refs summary - fenjing_id: {fen_id}, total_refs: {len(refs)}, mapping: {', '.join(ref_mapping)}")
                    # 额外打印将要发送给模型的 image 数组，便于比对是否使用了换装图
                    payload_preview = build_image_payload(prompt_text, refs)
                    log_debug(f"[INFO] {fenjing_label}Image payload preview - fenjing_id: {fen_id}, image: {json.dumps(payload_preview.get('image', []), ensure_ascii=False)[:200]}...")
                    log_debug(f"[INFO] {fenjing_label}Fenjing Character mapping - fenjing_id: {fen_id}, characters: {[pk + '=' + item.get(pk) for pk in char_keys]}")
                    futures.append(pool.submit(lambda: run_async(process_single_fenjing(idx, item, fen_id, refs, prompt_text))))
        
        for fut in as_completed(futures):
            r = fut.result()
            if r:
                file_name = r.get("file")
                if isinstance(file_name, str) and file_name:
                    results.append(Path(out_dir / file_name))
                attempt_records = r.get("attempt_records")
                if isinstance(attempt_records, list) and attempt_records:
                    uploads.append({
                        "fenjing_id": r.get("fenjing_id"),
                        "prompt_text": r.get("prompt_text"),
                        "ref_urls": r.get("ref_urls"),
                        "ref_tos_uris": r.get("ref_tos_uris"),
                        "image_payload": r.get("image_payload"),
                        "origin_image_url": r.get("origin_image_url"),
                        "attempt_records": attempt_records
                    })
                else:
                    uploads.append({
                        "fenjing_id": r.get("fenjing_id"),
                        "prompt_text": r.get("prompt_text"),
                        "ref_urls": r.get("ref_urls"),
                        "ref_tos_uris": r.get("ref_tos_uris"),
                        "image_payload": r.get("image_payload"),
                        "origin_image_url": r.get("origin_image_url"),
                        "attempt_records": []
                    })
        if skipped_items:
            log_debug(f"[WARN] {fenjing_label}Skipped fenjing items due to missing refs: {skipped_items}")
    
    if debug_log_file:
        debug_log_file.write(f"\n{'='*50}\n")
        debug_log_file.write(f"Generation completed at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        debug_log_file.write(f"Total fenjing items: {len(prompts)}\n")
        debug_log_file.write(f"Successfully generated: {len(results)}\n")
        debug_log_file.write(f"Skipped items: {skipped_items}\n")
        debug_log_file.close()
    
    return results, uploads


def run_fenjing_workflow_multi(project_name: Optional[str] = None) -> Dict[str, Any]:
    project_info = f"[{project_name}] " if project_name else ""
    prefix = project_info
    # 使用传入的project_name或runtime_config中的值
    actual_project_name = project_name

    if not actual_project_name:
        emit_event(
            "ERROR",
            "fenjing",
            "flow_error",
            "project_name is required for fenjing workflow",
            step="step_download",
            project=actual_project_name,
        )
        return {"chapters": [], "cloth_changed_upload": [],}

    # 获取项目特定的TOS前缀
    project_prefixes = runtime_config.get_project_prefixes(actual_project_name)
    tos_assets_prefix = project_prefixes.get("TOS_ASSETS_PREFIX", "")
    if not tos_assets_prefix:
        emit_event(
            "ERROR",
            "fenjing",
            "flow_error",
            "TOS_ASSETS_PREFIX is not configured",
            step="step_download",
            project=actual_project_name,
        )
        return {"chapters": [], "cloth_changed_upload": [],}
    
    try:
        # Phase: generate_images，生成分镜图像并进入上传流程
        emit_event(
            "INFO",
            "fenjing",
            "flow_start",
            "fenjing workflow start",
            step="step_download",
            project=actual_project_name,
        )

        base_dir = Path(runtime_config.OUTPUT_DIR) / actual_project_name / "storyboard_assets"
        ensure_dir(base_dir)
        tos = TosClientWrapper()

        chars_jsonl = base_dir / "characters.jsonl"

        emit_event(
            "INFO",
            "fenjing",
            "phase_start",
            "phase_download_assets",
            step="step_download",
            phase="step_download",
            project=actual_project_name,
        )
        if tos.available():
            emit_event(
                "INFO",
                "fenjing",
                "step_progress",
                "download_assets",
                step="step_download",
                project=actual_project_name,
            )
            _download_file_from_tos(tos, runtime_config.TOS_BUCKET, f"{tos_assets_prefix}/characters.jsonl", chars_jsonl)

        if not chars_jsonl.exists():
            raise FileNotFoundError(f"characters.jsonl not found at {chars_jsonl}")
        emit_event(
            "INFO",
            "fenjing",
            "phase_complete",
            "phase_download_assets completed",
            step="step_download",
            phase="step_download",
            project=actual_project_name,
        )

        storyboards = download_storyboards_from_tos(base_dir, prefix, actual_project_name)
        if not storyboards:
            raise FileNotFoundError("No storyboards jsonl files found")

        if (base_dir / "character_images").exists():
            char_map = prepare_character_map(base_dir / "character_images", actual_project_name)
        else:
            char_map = build_character_presigned_map(chars_jsonl, actual_project_name)

        loc_map = prepare_location_map(base_dir, actual_project_name)

        emit_event(
            "INFO",
            "fenjing",
            "phase_start",
            "phase_generate_images",
            step="step_generate",
            phase="step_generate",
            project=actual_project_name,
        )
        emit_event(
            "INFO",
            "fenjing",
            "upload_start",
            "upload_assets start",
            step="step_upload",
            project=actual_project_name,
        )
        cloth_changed_upload = load_upload_jsonl(base_dir, "cloth_changed_upload.jsonl", actual_project_name, optional=True)

        async def prepare_chapter_inputs(chapter_path: Path) -> Dict[str, Any]:
            chapter_name = chapter_path.stem
            chapter_dir = base_dir / "storyboards" / chapter_name
            ensure_dir(chapter_dir)
            chapter_storyboards = chapter_dir / chapter_path.name
            write_jsonl(str(chapter_storyboards), read_jsonl(str(chapter_path)))
            fen_prompts = chapter_dir / "fenjing_prompts.jsonl"
            if not fen_prompts.exists() and tos.available():
                key = f"{tos_assets_prefix}/storyboards/{chapter_name}/fenjing_prompts.jsonl"
                await asyncio.to_thread(_download_file_from_tos, tos, runtime_config.TOS_BUCKET, key, fen_prompts)
            if not fen_prompts.exists():
                raise FileNotFoundError(f"fenjing_prompts.jsonl not found for {chapter_name}")

            storyboards_list = read_jsonl(str(chapter_storyboards))
            prompts_list = read_jsonl(str(fen_prompts))
            updated_prompts, stats = fix_fenjing_character_fields(storyboards_list, prompts_list)
            if stats.get("fixed_count"):
                write_jsonl(str(fen_prompts), updated_prompts)
                emit_event(
                    "INFO",
                    "fenjing",
                    "fenjing_character_fields_fixed",
                    "fenjing prompts character fields fixed",
                    step="step_generate",
                    project=actual_project_name,
                    chapter=str(chapter_name),
                    data=stats,
                )

            return {
                "chapter": chapter_name,
                "chapter_dir": str(chapter_dir),
                "storyboards_jsonl": str(chapter_storyboards),
                "fenjing_prompts_jsonl": str(fen_prompts)
            }

        async def process_chapter_images(chapter_info: Dict[str, Any]) -> Dict[str, Any]:
            chapter_dir = Path(chapter_info["chapter_dir"])
            fen_prompts = Path(chapter_info["fenjing_prompts_jsonl"])
            chapter_storyboards = Path(chapter_info["storyboards_jsonl"])
            chapter_name = chapter_info["chapter"]
            fen_images, fen_upload = await asyncio.to_thread(
                generate_fenjing_images,
                fen_prompts,
                chapter_storyboards,
                chapter_dir,
                cloth_changed_upload,
                chars_jsonl,
                None,
                char_map,
                chapter_name,
                project_name
            )
            return {
                "chapter": chapter_info["chapter"],
                "fenjing_prompts_jsonl": str(fen_prompts),
                "fenjing_images": [str(p) for p in fen_images],
                "fenjing_upload": fen_upload
            }

        async def run_all() -> List[Dict[str, Any]]:
            prompt_tasks: List[Tuple[str, asyncio.Task]] = []
            for ch in storyboards:
                chapter_name = ch.stem if isinstance(ch, Path) else str(ch)
                prompt_tasks.append((chapter_name, asyncio.create_task(prepare_chapter_inputs(ch))))
            prompt_results = await asyncio.gather(*[t for _, t in prompt_tasks], return_exceptions=True)
            prompt_infos: List[Dict[str, Any]] = []
            out: List[Dict[str, Any]] = []
            for (chapter_name, _), r in zip(prompt_tasks, prompt_results):
                if isinstance(r, dict):
                    prompt_infos.append(r)
                else:
                    emit_event(
                        "ERROR",
                        "fenjing",
                        "log",
                        f"Chapter prompt task failed: {r}",
                        step="step_generate",
                        project=actual_project_name,
                    )
                    out.append({
                        "chapter": chapter_name,
                        "fenjing_upload": [],
                        "error": str(r),
                        "stage": "prompt"
                    })
            image_tasks: List[Tuple[str, asyncio.Task]] = []
            for info in prompt_infos:
                chapter_name = info.get("chapter") if isinstance(info, dict) else "unknown"
                image_tasks.append((str(chapter_name), asyncio.create_task(process_chapter_images(info))))
            image_results = await asyncio.gather(*[t for _, t in image_tasks], return_exceptions=True)
            for (chapter_name, _), r in zip(image_tasks, image_results):
                if isinstance(r, dict):
                    emit_event(
                        "INFO",
                        "fenjing",
                        "step_progress",
                        f"chapter_completed: {chapter_name}",
                        step="step_generate",
                        project=actual_project_name,
                        chapter=str(chapter_name),
                    )
                    out.append(r)
                else:
                    emit_event(
                        "ERROR",
                        "fenjing",
                        "log",
                        f"Chapter image task failed: {r}",
                        step="step_generate",
                        project=actual_project_name,
                    )
                    out.append({
                        "chapter": chapter_name,
                        "fenjing_upload": [],
                        "error": str(r),
                        "stage": "image"
                    })
            return out

        chapters_result = asyncio.run(run_all())
        emit_event(
            "INFO",
            "fenjing",
            "phase_complete",
            "phase_generate_images completed",
            step="step_generate",
            phase="step_generate",
            project=actual_project_name,
        )
        emit_event(
            "INFO",
            "fenjing",
            "upload_complete",
            "upload_assets completed",
            step="step_upload",
            project=actual_project_name,
        )
        emit_event(
            "INFO",
            "fenjing",
            "flow_complete",
            "fenjing workflow complete",
            step="step_upload",
            project=actual_project_name,
        )
        return {
            "chapters": chapters_result,
            "cloth_changed_upload": cloth_changed_upload,
        }
    except (IOError, OSError, ValueError) as e:
        emit_event(
            "ERROR",
            "fenjing",
            "flow_error",
            f"fenjing workflow error: {e}",
            step="step_generate",
            project=actual_project_name,
        )
        raise


def run_fenjing_generate_workflow(project_name: Optional[str] = None) -> Dict[str, Any]:
    """分镜图生成工作流：下载资产 + 生成分镜图到本地（不上传）"""
    project_info = f"[{project_name}] " if project_name else ""
    prefix = project_info
    actual_project_name = project_name

    if not actual_project_name:
        emit_event(
            "ERROR",
            "fenjing_generate",
            "flow_error",
            "project_name is required for fenjing_generate workflow",
            step="step_download",
            project=actual_project_name,
        )
        return {"chapters": [],}

    project_prefixes = runtime_config.get_project_prefixes(actual_project_name)
    tos_assets_prefix = project_prefixes.get("TOS_ASSETS_PREFIX", "")
    if not tos_assets_prefix:
        emit_event(
            "ERROR",
            "fenjing_generate",
            "flow_error",
            "TOS_ASSETS_PREFIX is not configured",
            step="step_download",
            project=actual_project_name,
        )
        return {"chapters": [],}

    try:
        emit_event(
            "INFO",
            "fenjing_generate",
            "fenjing_generate_start",
            "fenjing_generate workflow start",
            step="step_download",
            project=actual_project_name,
        )

        base_dir = Path(runtime_config.OUTPUT_DIR) / actual_project_name / "storyboard_assets"
        ensure_dir(base_dir)
        tos = TosClientWrapper()

        chars_jsonl = base_dir / "characters.jsonl"

        emit_event(
            "INFO",
            "fenjing_generate",
            "phase_start",
            "phase_download_assets",
            step="step_download",
            phase="step_download",
            project=actual_project_name,
        )
        if tos.available():
            emit_event(
                "INFO",
                "fenjing_generate",
                "step_progress",
                "download_assets",
                step="step_download",
                project=actual_project_name,
            )
            _download_file_from_tos(tos, runtime_config.TOS_BUCKET, f"{tos_assets_prefix}/characters.jsonl", chars_jsonl)

        if not chars_jsonl.exists():
            raise FileNotFoundError(f"characters.jsonl not found at {chars_jsonl}")
        emit_event(
            "INFO",
            "fenjing_generate",
            "phase_complete",
            "phase_download_assets completed",
            step="step_download",
            phase="step_download",
            project=actual_project_name,
        )

        storyboards = download_storyboards_from_tos(base_dir, prefix, actual_project_name)
        if not storyboards:
            raise FileNotFoundError("No storyboards jsonl files found")

        if (base_dir / "character_images").exists():
            char_map = prepare_character_map(base_dir / "character_images", actual_project_name)
        else:
            char_map = build_character_presigned_map(chars_jsonl, actual_project_name)

        loc_map = prepare_location_map(base_dir, actual_project_name)

        emit_event(
            "INFO",
            "fenjing_generate",
            "phase_start",
            "phase_generate_images",
            step="step_generate",
            phase="step_generate",
            project=actual_project_name,
        )

        cloth_changed_upload = load_upload_jsonl(base_dir, "cloth_changed_upload.jsonl", actual_project_name, optional=True)

        async def prepare_chapter_inputs(chapter_path: Path) -> Dict[str, Any]:
            chapter_name = chapter_path.stem
            chapter_dir = base_dir / "storyboards" / chapter_name
            ensure_dir(chapter_dir)
            chapter_storyboards = chapter_dir / chapter_path.name
            write_jsonl(str(chapter_storyboards), read_jsonl(str(chapter_path)))
            fen_prompts = chapter_dir / "fenjing_prompts.jsonl"
            if not fen_prompts.exists() and tos.available():
                key = f"{tos_assets_prefix}/storyboards/{chapter_name}/fenjing_prompts.jsonl"
                await asyncio.to_thread(_download_file_from_tos, tos, runtime_config.TOS_BUCKET, key, fen_prompts)
            if not fen_prompts.exists():
                raise FileNotFoundError(f"fenjing_prompts.jsonl not found for {chapter_name}")

            storyboards_list = read_jsonl(str(chapter_storyboards))
            prompts_list = read_jsonl(str(fen_prompts))
            updated_prompts, stats = fix_fenjing_character_fields(storyboards_list, prompts_list)
            if stats.get("fixed_count"):
                write_jsonl(str(fen_prompts), updated_prompts)
                emit_event(
                    "INFO",
                    "fenjing_generate",
                    "fenjing_character_fields_fixed",
                    "fenjing prompts character fields fixed",
                    step="step_generate",
                    project=actual_project_name,
                    chapter=str(chapter_name),
                    data=stats,
                )

            return {
                "chapter": chapter_name,
                "chapter_dir": str(chapter_dir),
                "storyboards_jsonl": str(chapter_storyboards),
                "fenjing_prompts_jsonl": str(fen_prompts)
            }

        async def process_chapter_images(chapter_info: Dict[str, Any]) -> Dict[str, Any]:
            chapter_dir = Path(chapter_info["chapter_dir"])
            fen_prompts = Path(chapter_info["fenjing_prompts_jsonl"])
            chapter_storyboards = Path(chapter_info["storyboards_jsonl"])
            chapter_name = chapter_info["chapter"]
            fen_images, fen_upload = await asyncio.to_thread(
                generate_fenjing_images_local,
                fen_prompts,
                chapter_storyboards,
                chapter_dir,
                cloth_changed_upload,
                chars_jsonl,
                loc_map,
                char_map,
                chapter_name,
                project_name
            )
            return {
                "chapter": chapter_info["chapter"],
                "fenjing_prompts_jsonl": str(fen_prompts),
                "fenjing_images": [str(p) for p in fen_images],
                "fenjing_upload": fen_upload
            }

        async def run_all() -> List[Dict[str, Any]]:
            prompt_tasks: List[Tuple[str, asyncio.Task]] = []
            for ch in storyboards:
                chapter_name = ch.stem if isinstance(ch, Path) else str(ch)
                prompt_tasks.append((chapter_name, asyncio.create_task(prepare_chapter_inputs(ch))))
            prompt_results = await asyncio.gather(*[t for _, t in prompt_tasks], return_exceptions=True)
            prompt_infos: List[Dict[str, Any]] = []
            out: List[Dict[str, Any]] = []
            for (chapter_name, _), r in zip(prompt_tasks, prompt_results):
                if isinstance(r, dict):
                    prompt_infos.append(r)
                else:
                    emit_event(
                        "ERROR",
                        "fenjing_generate",
                        "log",
                        f"Chapter prompt task failed: {r}",
                        step="step_generate",
                        project=actual_project_name,
                    )
                    out.append({
                        "chapter": chapter_name,
                        "fenjing_upload": [],
                        "error": str(r),
                        "stage": "prompt"
                    })
            image_tasks: List[Tuple[str, asyncio.Task]] = []
            for info in prompt_infos:
                chapter_name = info.get("chapter") if isinstance(info, dict) else "unknown"
                image_tasks.append((str(chapter_name), asyncio.create_task(process_chapter_images(info))))
            image_results = await asyncio.gather(*[t for _, t in image_tasks], return_exceptions=True)
            for (chapter_name, _), r in zip(image_tasks, image_results):
                if isinstance(r, dict):
                    emit_event(
                        "INFO",
                        "fenjing_generate",
                        "step_progress",
                        f"chapter_completed: {chapter_name}",
                        step="step_generate",
                        project=actual_project_name,
                        chapter=str(chapter_name),
                    )
                    out.append(r)
                else:
                    emit_event(
                        "ERROR",
                        "fenjing_generate",
                        "log",
                        f"Chapter image task failed: {r}",
                        step="step_generate",
                        project=actual_project_name,
                    )
                    out.append({
                        "chapter": chapter_name,
                        "fenjing_upload": [],
                        "error": str(r),
                        "stage": "image"
                    })
            return out

        chapters_result = asyncio.run(run_all())
        emit_event(
            "INFO",
            "fenjing_generate",
            "phase_complete",
            "phase_generate_images completed",
            step="step_generate",
            phase="step_generate",
            project=actual_project_name,
        )
        emit_event(
            "INFO",
            "fenjing_generate",
            "fenjing_generate_complete",
            "fenjing_generate workflow complete",
            step="step_generate",
            project=actual_project_name,
        )
        return {
            "chapters": chapters_result,
        }
    except (IOError, OSError, ValueError) as e:
        emit_event(
            "ERROR",
            "fenjing_generate",
            "flow_error",
            f"fenjing_generate workflow error: {e}",
            step="step_generate",
            project=actual_project_name,
        )
        raise


def generate_fenjing_images_local(
    fenjing_prompts_jsonl: Path,
    storyboards_jsonl: Path,
    input_dir: Path,
    cloth_changed_upload: List[Dict[str, Any]],
    chars_jsonl: Path,
    loc_map_override: Optional[Dict[str, Dict[str, str]]] = None,
    char_map_override: Optional[Dict[str, str]] = None,
    chapter_name: Optional[str] = None,
    project_name: Optional[str] = None
) -> Tuple[List[Path], List[Dict[str, Any]]]:
    """生成分镜图到本地目录（不上传到 TOS）"""
    project_info = f"[{project_name}] " if project_name else ""
    chapter_info = f"[{chapter_name}] " if isinstance(chapter_name, str) and chapter_name else ""
    chapter_label = f"{project_info}{chapter_info}"

    loc_map = loc_map_override if isinstance(loc_map_override, dict) else prepare_location_map(input_dir, project_name)
    char_map = char_map_override if isinstance(char_map_override, dict) else prepare_character_map(input_dir / "character_images", project_name)
    cloth_changed_map: Dict[str, str] = {}
    for it in cloth_changed_upload or []:
        cid = it.get("character_id")
        oid = it.get("outfit_id")
        presigned = it.get("presigned")
        if isinstance(cid, str) and isinstance(oid, str) and isinstance(presigned, str) and cid and oid:
            cloth_changed_map[f"{cid}_{oid}"] = presigned
    defaults = load_char_defaults(chars_jsonl)
    plot_outfits = load_char_plot_outfits(chars_jsonl)
    storyboards = read_jsonl(str(storyboards_jsonl))
    prompts = read_jsonl(str(fenjing_prompts_jsonl))
    out_dir = input_dir / "fenjing_images"
    ensure_dir(out_dir)
    tos = TosClientWrapper()
    size_default = size_for_2k_9x16()

    results: List[Path] = []
    uploads: List[Dict[str, Any]] = []

    async def process_single_fenjing_local(idx: int, item: Dict[str, Any], fen_id: int, refs: List[str], prompt_text: str) -> Optional[Dict[str, Any]]:
        fenjing_info = f"[fenjing{fen_id}] "
        fenjing_label = f"{chapter_label}{fenjing_info}"

        name_prefix = f"fenjing{fen_id}"
        retry = 1
        attempts = 0

        emit_event(
            "INFO",
            "fenjing_generate",
            "fenjing_image_start",
            f"Fenjing {fen_id} image generation start",
            step="step_generate",
            project=project_name,
            chapter=chapter_name,
            fenjing_id=str(fen_id),
            data={"attempts": retry + 1, "image_type": "fenjing", "image_id": str(fen_id)},
        )

        while attempts <= retry:
            attempts += 1
            emit_event(
                "INFO",
                "fenjing_generate",
                "fenjing_image_attempt",
                f"Fenjing {fen_id} generating (attempt {attempts}/{retry + 1})",
                step="step_generate",
                project=project_name,
                chapter=chapter_name,
                fenjing_id=str(fen_id),
                data={"attempt": attempts, "max_attempts": retry + 1, "image_type": "fenjing", "image_id": str(fen_id)},
            )

            payload_preview = {
                "model": runtime_config.SEEDREAM_MODEL,
                "prompt": prompt_text,
                "size": size_default,
                "watermark": False,
                "sequential_image_generation": "disabled",
                "image": refs[0] if len(refs) == 1 else refs,
            }
            emit_event(
                "INFO",
                "fenjing_generate",
                "image_payload_preview",
                "Image payload preview",
                step="step_generate",
                project=project_name,
                chapter=chapter_name,
                fenjing_id=str(fen_id),
                data={"image": payload_preview.get("image", [])},
            )
            result = await generate_image_with_refs(prompt_text, refs, fenjing_id=fen_id)
            if not result or "data" not in result or not result["data"]:
                p = await generate_image(prompt_text, out_dir, f"fenjing{fen_id}")
                if isinstance(p, Path):
                    emit_event(
                        "INFO",
                        "fenjing_generate",
                        "fenjing_image_generated",
                        f"Fenjing {fen_id} image generated locally",
                        step="step_generate",
                        project=project_name,
                        chapter=chapter_name,
                        fenjing_id=str(fen_id),
                        data={"file": p.name, "image_type": "fenjing", "image_id": str(fen_id)},
                    )
                    return {"fenjing_id": fen_id, "prompt_text": prompt_text, "file": p.name, "uri": None, "presigned": None}

            if not result or "data" not in result or not result["data"]:
                if attempts <= retry:
                    continue
                emit_event(
                    "ERROR",
                    "fenjing_generate",
                    "fenjing_image_failed",
                    f"Fenjing {fen_id} generation failed",
                    step="step_generate",
                    project=project_name,
                    chapter=chapter_name,
                    fenjing_id=str(fen_id),
                    data={"attempt": attempts, "image_type": "fenjing", "image_id": str(fen_id)},
                )
                return {"fenjing_id": fen_id, "prompt_text": prompt_text, "file": None, "uri": None, "presigned": None}

            image_url = result["data"][0].get("url") if isinstance(result["data"][0], dict) else None
            if not isinstance(image_url, str) or not image_url:
                if attempts <= retry:
                    continue
                emit_event(
                    "ERROR",
                    "fenjing_generate",
                    "fenjing_image_failed",
                    f"Fenjing {fen_id} generation failed (empty url)",
                    step="step_generate",
                    project=project_name,
                    chapter=chapter_name,
                    fenjing_id=str(fen_id),
                    data={"attempt": attempts, "image_type": "fenjing", "image_id": str(fen_id)},
                )
                return {"fenjing_id": fen_id, "prompt_text": prompt_text, "file": None, "uri": None, "presigned": None}

            save_path = out_dir / f"{name_prefix}.png"
            ok = await download(image_url, save_path)
            p = save_path if ok else None
            if not isinstance(p, Path):
                if attempts <= retry:
                    continue
                emit_event(
                    "ERROR",
                    "fenjing_generate",
                    "fenjing_image_failed",
                    f"Fenjing {fen_id} download failed",
                    step="step_generate",
                    project=project_name,
                    chapter=chapter_name,
                    fenjing_id=str(fen_id),
                    data={"attempt": attempts, "image_type": "fenjing", "image_id": str(fen_id)},
                )
                return {"fenjing_id": fen_id, "prompt_text": prompt_text, "file": None, "uri": None, "presigned": None}

            emit_event(
                "INFO",
                "fenjing_generate",
                "fenjing_image_generated",
                f"Fenjing {fen_id} image generated locally",
                step="step_generate",
                project=project_name,
                chapter=chapter_name,
                fenjing_id=str(fen_id),
                data={"file": p.name, "image_type": "fenjing", "image_id": str(fen_id)},
            )
            return {"fenjing_id": fen_id, "prompt_text": prompt_text, "file": p.name, "uri": None, "presigned": None}

        return {"fenjing_id": fen_id, "prompt_text": prompt_text, "file": None, "uri": None, "presigned": None}

    with with_thread_pool_limit() as pool:
        futures = []
        for idx, item in enumerate(prompts):
            if not isinstance(item, dict):
                continue
            fen_id = item.get("fenjing_id")
            try:
                fen_id = int(fen_id)
            except (ValueError, TypeError):
                fen_id = idx + 1
            loc_id = item.get("Location_Id") or item.get("location_id") or item.get("Background_pic")
            bg_type = norm_bg_type(item.get("Background_xuanze"))
            refs: List[str] = []
            sb = storyboards[idx] if idx < len(storyboards) else {}
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
            for i in range(1, 6):
                char_key = f"Character_{i}"
                outfit_key = f"Character_{i}_outfit"
                cid = item.get(char_key)
                oid = item.get(outfit_key)
                cid = cid if isinstance(cid, str) else None
                oid = oid if isinstance(oid, str) else None
                if not cid:
                    continue
                if not oid:
                    oid = outfit_map.get(cid)
                default_outfit = defaults.get(cid)
                if oid and oid != default_outfit:
                    changed_key = f"{cid}_{oid}"
                    if changed_key in cloth_changed_map:
                        refs.append(cloth_changed_map[changed_key])
                    else:
                        project_prefixes = runtime_config.get_project_prefixes(project_name) if project_name else {}
                        tos_cloth_prefix = project_prefixes.get("TOS_CLOTH_PREFIX", "")
                        remote_presigned = None
                        if tos_cloth_prefix:
                            remote_key = f"{tos_cloth_prefix}/{changed_key}.png"
                            remote_presigned = tos.presign_get(runtime_config.TOS_BUCKET, remote_key) if tos.available() else None
                        if isinstance(remote_presigned, str) and remote_presigned:
                            refs.append(remote_presigned)
                        elif cid in char_map:
                            refs.append(char_map[cid])
                else:
                    if cid in char_map:
                        refs.append(char_map[cid])
            if isinstance(loc_id, str) and loc_id:
                project_prefixes = runtime_config.get_project_prefixes(project_name) if project_name else {}
                tos_location_prefix = project_prefixes.get("TOS_LOCATION_PREFIX", "")
                if tos_location_prefix:
                    remote_key = f"{tos_location_prefix}/{loc_id}_{bg_type}.png"
                    remote_presigned = tos.presign_get(runtime_config.TOS_BUCKET, remote_key) if tos.available() else None
                else:
                    remote_presigned = None
                if isinstance(remote_presigned, str) and remote_presigned:
                    refs.append(remote_presigned)
                elif loc_id in loc_map and bg_type in loc_map[loc_id]:
                    refs.append(loc_map[loc_id][bg_type])
            prompt_text = item.get("prompt") or item.get("Prompt") or ""
            if not isinstance(prompt_text, str):
                prompt_text = str(prompt_text) if prompt_text else ""
            futures.append(pool.submit(lambda i=idx, it=item, f=fen_id, r=refs, p=prompt_text: run_async(process_single_fenjing_local(i, it, f, r, p))))

        for future in as_completed(futures):
            try:
                result = future.result()
                if isinstance(result, dict) and result.get("file"):
                    results.append(out_dir / result["file"])
                    uploads.append(result)
            except Exception as e:
                emit_event(
                    "ERROR",
                    "fenjing_generate",
                    "log",
                    f"Error processing fenjing image: {e}",
                    step="step_generate",
                    project=project_name,
                    chapter=chapter_name,
                )

    return results, uploads


def run_fenjing_upload_workflow(project_name: Optional[str] = None) -> Dict[str, Any]:
    """上传分镜图工作流：读取本地分镜图，上传到 TOS"""

    project_info = f"[{project_name}] " if project_name else ""
    prefix = project_info
    actual_project_name = project_name

    if not actual_project_name:
        emit_event(
            "ERROR",
            "fenjing_upload",
            "flow_error",
            "project_name is required for fenjing_upload workflow",
            step="step_upload",
            project=actual_project_name,
        )
        return {"chapters": [], "uploaded_count": 0}

    project_prefixes = runtime_config.get_project_prefixes(actual_project_name)
    tos_fenjing_prefix = project_prefixes.get("TOS_FENJING_PREFIX", "")
    if not tos_fenjing_prefix:
        emit_event(
            "ERROR",
            "fenjing_upload",
            "flow_error",
            "TOS_FENJING_PREFIX is not configured",
            step="step_upload",
            project=actual_project_name,
        )
        return {"chapters": [], "uploaded_count": 0}

    try:
        emit_event(
            "INFO",
            "fenjing_upload",
            "fenjing_upload_start",
            "fenjing_upload workflow start",
            step="step_upload",
            project=actual_project_name,
        )

        base_dir = Path(runtime_config.OUTPUT_DIR) / actual_project_name / "storyboard_assets"
        tos = TosClientWrapper()

        if not tos.available():
            emit_event(
                "ERROR",
                "fenjing_upload",
                "flow_error",
                "TOS is not available",
                step="step_upload",
                project=actual_project_name,
            )
            return {"chapters": [], "uploaded_count": 0}

        storyboards_dir = base_dir / "storyboards"
        if not storyboards_dir.exists():
            emit_event(
                "WARN",
                "fenjing_upload",
                "log",
                "No storyboards directory found",
                step="step_upload",
                project=actual_project_name,
            )
            return {"chapters": [], "uploaded_count": 0}

        uploaded_count = 0
        chapters_result = []

        for chapter_dir in storyboards_dir.iterdir():
            if not chapter_dir.is_dir():
                continue
            chapter_name = chapter_dir.name
            fenjing_dir = chapter_dir / "fenjing_images"
            if not fenjing_dir.exists():
                continue

            chapter_uploads = []
            for img_path in fenjing_dir.glob("*.png"):
                key = f"{tos_fenjing_prefix}/{chapter_name}/{img_path.name}"
                uri = tos.upload_file(runtime_config.TOS_BUCKET, key, img_path)
                presigned = tos.presign_get(runtime_config.TOS_BUCKET, key) if uri else None

                emit_event(
                    "INFO",
                    "fenjing_upload",
                    "fenjing_upload_progress",
                    f"fenjing image uploaded: {img_path.name}",
                    step="step_upload",
                    project=actual_project_name,
                    chapter=chapter_name,
                    data={
                        "file": img_path.name,
                        "key": key,
                        "uri": uri,
                        "presigned": presigned,
                        "image_type": "fenjing",
                    },
                )

                if uri:
                    uploaded_count += 1
                    chapter_uploads.append({
                        "file": img_path.name,
                        "key": key,
                        "uri": uri,
                        "presigned": presigned
                    })

            if chapter_uploads:
                chapters_result.append({
                    "chapter": chapter_name,
                    "uploads": chapter_uploads
                })
                emit_event(
                    "INFO",
                    "fenjing_upload",
                    "chapter_completed",
                    f"chapter {chapter_name} upload completed",
                    step="step_upload",
                    project=actual_project_name,
                    chapter=chapter_name,
                    data={"upload_count": len(chapter_uploads)},
                )

        emit_event(
            "INFO",
            "fenjing_upload",
            "fenjing_upload_complete",
            f"fenjing_upload workflow complete, uploaded {uploaded_count} images",
            step="step_upload",
            project=actual_project_name,
            data={"uploaded_count": uploaded_count},
        )

        return {
            "chapters": chapters_result,
            "uploaded_count": uploaded_count
        }
    except (IOError, OSError, ValueError) as e:
        emit_event(
            "ERROR",
            "fenjing_upload",
            "flow_error",
            f"fenjing_upload workflow error: {e}",
            step="step_upload",
            project=actual_project_name,
        )
        raise
