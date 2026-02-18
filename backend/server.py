import asyncio
import json
import os
import queue
import re
import subprocess
import shutil
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qs, unquote, urlparse
from contextlib import redirect_stderr, redirect_stdout

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))
MANJU_WEB_DIR = ROOT_DIR / "manju_web"
sys.path.insert(0, str(MANJU_WEB_DIR))

# ========== 线程安全日志系统 ==========
# 解决多线程环境下 redirect_stdout 导致的 "I/O operation on closed file" 错误

from backend.services.workflow_runtime.thread_safe_logging import (
    ThreadLogRedirector,
    install_thread_aware_stdout,
    _log_manager,
)

# 安装线程感知的 stdout（只执行一次）
install_thread_aware_stdout()

from backend.handlers import config_handler, job_handler, media_handler, project_handler
from backend.repositories import job_repo, project_repo
from backend.repositories.project_repo import visual_audio_assets_dir
from backend.services import config_service, status_service
from backend.services.workflow_runtime import runtime_config
from backend.services.workflow_runtime.fenjing import load_char_plot_outfits
from backend.services.workflow_runtime.io_jsonl import read_jsonl, write_jsonl
from backend.services.workflow_runtime.provider_runtime import (
    TosClientWrapper,
    generate_and_download,
    generate_and_download_with_refs,
)
from backend.services.workflow_runtime.video import process_single_video_independent
from backend.services.workflow_runtime.visual_audio_assets import character_keys_sorted, load_char_defaults


OUTPUT_DIR = Path(os.environ.get("MANJU_OUTPUT_DIR", str(runtime_config.OUTPUT_DIR)))
LOG_DIR = ROOT_DIR / "manju_web" / "backend" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

PROJECT_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
CHAPTER_PATTERN = re.compile(r"^storyboard_chapter_\d+$")


def log_event(level: str, message: str, **fields: Any) -> None:
    payload = {
        "ts": time.time(),
        "level": level,
        "message": message,
        "trace_id": fields.pop("trace_id", ""),
        **fields,
    }
    try:
        print(json.dumps(payload, ensure_ascii=False))
    except (IOError, OSError, ValueError):
        pass


def jobs_index_path(project: str) -> Path:
    return project_base_dir(project) / "jobs.jsonl"


def load_jobs_from_disk(project: str) -> List[Dict[str, Any]]:
    path = jobs_index_path(project)
    if not path.exists():
        return []
    return safe_read_jsonl(path)


def write_jobs_to_disk(project: str, jobs: List[Dict[str, Any]]) -> None:
    path = jobs_index_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        write_jsonl(str(path), jobs)
    except Exception as exc:
        log_event("ERROR", "job_persist_failed", project=project, error=str(exc))


def persist_job_snapshot(job: Dict[str, Any]) -> None:
    project = job.get("project")
    if not project:
        return
    jobs = load_jobs_from_disk(project)
    updated = False
    for idx, existing in enumerate(jobs):
        if existing.get("id") == job.get("id"):
            jobs[idx] = job
            updated = True
            break
    if not updated:
        jobs.append(job)
    write_jobs_to_disk(project, jobs)


def find_job_on_disk(job_id: str) -> Optional[Dict[str, Any]]:
    for project in list_projects():
        jobs = load_jobs_from_disk(project)
        for job in jobs:
            if job.get("id") == job_id:
                return job
    return None


def read_json_body(handler: BaseHTTPRequestHandler) -> Dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}


def send_json(handler: BaseHTTPRequestHandler, status: int, payload: Dict[str, Any]) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET,POST,PATCH,OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.end_headers()
    handler.wfile.write(data)


def send_file(handler: BaseHTTPRequestHandler, file_path: Path, content_type: str) -> None:
    if not file_path.exists() or not file_path.is_file():
        send_json(handler, HTTPStatus.NOT_FOUND, {"error": "file_not_found"})
        return
    file_size = file_path.stat().st_size
    range_header = handler.headers.get("Range")
    if range_header:
        match = re.match(r"bytes=(\d*)-(\d*)", range_header)
        if match:
            start_text, end_text = match.groups()
            if start_text or end_text:
                if not start_text:
                    length = int(end_text)
                    length = min(length, file_size)
                    start = max(file_size - length, 0)
                    end = file_size - 1
                else:
                    start = int(start_text)
                    end = int(end_text) if end_text else file_size - 1
                if start >= file_size or end < start:
                    handler.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    handler.send_header("Content-Range", f"bytes */{file_size}")
                    handler.send_header("Access-Control-Allow-Origin", "*")
                    handler.end_headers()
                    return
                end = min(end, file_size - 1)
                length = end - start + 1
                handler.send_response(HTTPStatus.PARTIAL_CONTENT)
                handler.send_header("Content-Type", content_type)
                handler.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                handler.send_header("Accept-Ranges", "bytes")
                handler.send_header("Content-Length", str(length))
                handler.send_header("Access-Control-Allow-Origin", "*")
                handler.end_headers()
                with file_path.open("rb") as f:
                    f.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk = f.read(min(64 * 1024, remaining))
                        if not chunk:
                            break
                        handler.wfile.write(chunk)
                        remaining -= len(chunk)
                return
    data = file_path.read_bytes()
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Accept-Ranges", "bytes")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(data)


def safe_project_name(name: str) -> Optional[str]:
    if not isinstance(name, str):
        return None
    name = name.strip()
    if not name or not PROJECT_NAME_PATTERN.match(name):
        return None
    return name


def project_base_dir(project: str) -> Path:
    return OUTPUT_DIR / project


def storyboard_assets_dir(project: str) -> Path:
    return project_base_dir(project) / "storyboard_assets"


def list_projects() -> List[str]:
    if not OUTPUT_DIR.exists():
        return []
    return sorted([p.name for p in OUTPUT_DIR.iterdir() if p.is_dir()])


def ensure_project_dirs(project: str) -> Dict[str, Any]:
    base = project_base_dir(project)
    assets = storyboard_assets_dir(project)
    storyboards = assets / "storyboards"
    base.mkdir(parents=True, exist_ok=True)
    assets.mkdir(parents=True, exist_ok=True)
    storyboards.mkdir(parents=True, exist_ok=True)
    return {"base": str(base), "assets": str(assets), "storyboards": str(storyboards)}


def list_files(rel_dir: Path, exts: Optional[Tuple[str, ...]] = None) -> List[str]:
    abs_dir = rel_dir
    if not abs_dir.exists():
        return []
    files: List[str] = []
    for p in sorted(abs_dir.iterdir()):
        if not p.is_file():
            continue
        if exts and p.suffix.lower() not in exts:
            continue
        files.append(str(p))
    return files


def to_project_relative(project: str, path: Path) -> str:
    base = project_base_dir(project)
    try:
        return str(path.relative_to(base))
    except Exception:
        return ""


def safe_read_jsonl(path: Path) -> List[Dict[str, Any]]:
    try:
        data = read_jsonl(str(path))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def build_character_table(assets: Path) -> List[Dict[str, Any]]:
    path = assets / "characters.jsonl"
    rows: List[Dict[str, Any]] = []
    for item in safe_read_jsonl(path):
        if not isinstance(item, dict):
            continue
        outfit = item.get("Default_Outfit (Clothing)") or {}
        if not isinstance(outfit, dict):
            outfit = {}
        rows.append(
            {
                "Character_Id": item.get("Character_Id", ""),
                "Character_name": item.get("Character_name", ""),
                "Alias": item.get("Alias", ""),
                "attribute": item.get("attribute", ""),
                "Age_group": item.get("Age_group", ""),
                "Sex": item.get("Sex", ""),
                "Appearance": item.get("Appearance Description", ""),
                "Default_Outfit_id": outfit.get("Outfit_id", ""),
                "Default_Outfit_Description": outfit.get("Outfit_Description", ""),
                "Default_Shoes": item.get("Default_Shoes", ""),
            }
        )
    return rows


def build_location_table(assets: Path) -> List[Dict[str, Any]]:
    path = assets / "locations.jsonl"
    rows: List[Dict[str, Any]] = []
    for item in safe_read_jsonl(path):
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "Location_ID": item.get("Location_ID", ""),
                "Location": item.get("Location", ""),
                "Location_description": item.get("Location_description", ""),
            }
        )
    return rows


def stringify_characters(chars: Any) -> str:
    if not chars:
        return ""
    if isinstance(chars, list):
        names: List[str] = []
        for c in chars:
            if isinstance(c, dict):
                name = c.get("Character_Name") or c.get("Character_name") or c.get("Character_Id")
                if isinstance(name, str) and name:
                    names.append(name)
        return "、".join(names)
    if isinstance(chars, dict):
        name = chars.get("Character_Name") or chars.get("Character_name") or chars.get("Character_Id")
        return name if isinstance(name, str) else ""
    return ""


def resolve_character_size_by_attribute(attribute: Optional[str]) -> Optional[str]:
    if isinstance(attribute, str):
        attr = attribute.strip()
        if attr == "人类":
            return runtime_config.CHARACTER_HUMAN_IMAGE_SIZE
        if attr == "兽类":
            return runtime_config.CHARACTER_BEAST_IMAGE_SIZE
    return None


def build_storyboard_table(assets: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    storyboards_dir = assets / "storyboards"
    if not storyboards_dir.exists():
        return rows
    files = sorted(storyboards_dir.glob("storyboard_chapter_*.jsonl"))
    for file in files:
        chapter_name = file.stem
        for item in safe_read_jsonl(file):
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "chapter": chapter_name,
                    "zhangjie_id": item.get("zhangjie_id", ""),
                    "Storyboard_id": item.get("Storyboard_id", ""),
                    "Era": item.get("Era", ""),
                    "Time": item.get("Time", ""),
                    "Location": item.get("Location", ""),
                    "Location_Id": item.get("Location_Id") or item.get("Location_id", ""),
                    "Characters": stringify_characters(item.get("Characters")),
                    "Action": item.get("Action", ""),
                }
            )
    return rows


def resolve_character_image(assets: Path, character_id: str, visual_assets: Optional[Path] = None) -> str:
    if not character_id:
        return ""
    path = assets / "character_images" / f"{character_id}.png"
    if path.exists():
        return str(path)
    if visual_assets:
        visual_path = visual_assets / "character_images" / f"{character_id}.png"
        if visual_path.exists():
            return str(visual_path)
    return ""


def resolve_cloth_image(assets: Path, outfit_id: str, visual_assets: Optional[Path] = None) -> str:
    if not outfit_id:
        return ""
    path = assets / "cloth_images" / f"{outfit_id}.png"
    if path.exists():
        return str(path)
    if visual_assets:
        visual_path = visual_assets / "cloth_images" / f"{outfit_id}.png"
        if visual_path.exists():
            return str(visual_path)
    return ""


def resolve_cloth_changed_image(assets: Path, character_id: str, outfit_id: str, visual_assets: Optional[Path] = None) -> str:
    if not character_id or not outfit_id:
        return ""
    path = assets / "cloth_changed_images" / f"{character_id}_{outfit_id}.png"
    if path.exists():
        return str(path)
    if visual_assets:
        visual_path = visual_assets / "cloth_changed_images" / f"{character_id}_{outfit_id}.png"
        if visual_path.exists():
            return str(visual_path)
    return ""


def resolve_location_image(assets: Path, loc_id: str, background_hint: str, visual_assets: Optional[Path] = None) -> str:
    if not loc_id:
        return ""
    suffix = "standing"
    if isinstance(background_hint, str):
        hint = background_hint.lower()
        if "sitting" in hint or "坐" in background_hint:
            suffix = "sitting"
    path = assets / "location_images" / f"{loc_id}_{suffix}.png"
    if path.exists():
        return str(path)
    fallback = assets / "location_images" / f"{loc_id}.png"
    if fallback.exists():
        return str(fallback)
    if visual_assets:
        visual_path = visual_assets / "location_images" / f"{loc_id}_{suffix}.png"
        if visual_path.exists():
            return str(visual_path)
        visual_fallback = visual_assets / "location_images" / f"{loc_id}.png"
        if visual_fallback.exists():
            return str(visual_fallback)
    return ""


def build_character_details(project: str, assets: Path) -> List[Dict[str, Any]]:
    prompt_map: Dict[str, str] = {}
    prompt_name_map: Dict[str, str] = {}
    prompts_path = assets / "character_prompts.jsonl"
    for item in safe_read_jsonl(prompts_path):
        if not isinstance(item, dict):
            continue
        cid = item.get("Character_Id") or item.get("Character_id") or item.get("character_id")
        if not isinstance(cid, str) or not cid:
            continue
        prompt_text = item.get("st_prompt") or item.get("prompt") or ""
        prompt_map[cid] = prompt_text if isinstance(prompt_text, str) else ""
        prompt_name = item.get("name") or item.get("Character_name") or item.get("Character_Name")
        if isinstance(prompt_name, str) and prompt_name.strip():
            prompt_name_map[cid] = prompt_name
    name_map: Dict[str, str] = {}
    chars_path = assets / "characters.jsonl"
    for item in safe_read_jsonl(chars_path):
        if not isinstance(item, dict):
            continue
        cid = item.get("Character_Id") or item.get("Character_id") or item.get("character_id")
        if not isinstance(cid, str) or not cid:
            continue
        name = item.get("Character_name") or item.get("Character_Name") or item.get("character_name")
        if isinstance(name, str) and name.strip():
            name_map[cid] = name
    main_map: Dict[str, Path] = {}
    main_dir = assets / "character_images"
    if main_dir.exists():
        for p in sorted(main_dir.iterdir()):
            if not p.is_file():
                continue
            if p.suffix.lower() not in (".png", ".jpg", ".jpeg"):
                continue
            main_map[p.stem] = p
    candidate_map: Dict[str, List[str]] = {}
    candidate_dir = assets / "character_candidates"
    if candidate_dir.exists():
        for p in sorted(candidate_dir.iterdir()):
            if not p.is_file():
                continue
            if p.suffix.lower() not in (".png", ".jpg", ".jpeg"):
                continue
            match = re.match(r"(.+)_\d+$", p.stem)
            cid = match.group(1) if match else p.stem
            candidate_map.setdefault(cid, []).append(to_project_relative(project, p))
    ids = sorted(set(prompt_map.keys()) | set(main_map.keys()) | set(candidate_map.keys()))
    rows: List[Dict[str, Any]] = []
    for cid in ids:
        image_path = to_project_relative(project, main_map[cid]) if cid in main_map else ""
        rows.append(
            {
                "character_id": cid,
                "character_name": name_map.get(cid) or prompt_name_map.get(cid, ""),
                "prompt": prompt_map.get(cid, ""),
                "image_path": image_path,
                "candidate_images": candidate_map.get(cid, []),
            }
        )
    return rows


def build_cloth_changed_prompt(outfit_desc: Any) -> str:
    base = "高质量真人摄影，正面及侧面形象拍摄，纯白色背景，采用影视级渲染效果。参考图中的人物站立，全身拍摄。给参考图中的人物换上服装参考图的衣服，穿的鞋不变，并在水平方向展示角色的正视、侧视图形象，保持人物形象不得改变。"
    if isinstance(outfit_desc, str) and outfit_desc.strip():
        return f"{base}服装描述：{outfit_desc}"
    return base


def build_cloth_changed_details(project: str, assets: Path) -> List[Dict[str, Any]]:
    chars_path = assets / "characters.jsonl"
    rows: List[Dict[str, Any]] = []
    candidate_map: Dict[str, List[str]] = {}
    candidate_dir = assets / "cloth_changed_candidates"
    if candidate_dir.exists():
        for p in sorted(candidate_dir.iterdir()):
            if not p.is_file():
                continue
            if p.suffix.lower() not in (".png", ".jpg", ".jpeg"):
                continue
            match = re.match(r"(.+)_\d+$", p.stem)
            key = match.group(1) if match else p.stem
            candidate_map.setdefault(key, []).append(to_project_relative(project, p))
    seen: Set[str] = set()
    for item in safe_read_jsonl(chars_path):
        if not isinstance(item, dict):
            continue
        cid = item.get("Character_Id") or item.get("Character_id") or item.get("character_id")
        if not isinstance(cid, str) or not cid:
            continue
        name = item.get("Character_name") or item.get("Character_Name") or ""
        changes = item.get("Plot_Costume_Change") or []
        if not isinstance(changes, list):
            continue
        for ch in changes:
            if not isinstance(ch, dict):
                continue
            outfit_id = ch.get("Outfit_id")
            if not isinstance(outfit_id, str) or not outfit_id:
                continue
            key = f"{cid}_{outfit_id}"
            if key in seen:
                continue
            seen.add(key)
            prompt_text = ch.get("st_prompt") or ch.get("prompt") or build_cloth_changed_prompt(ch.get("Outfit_Description"))
            image_path = assets / "cloth_changed_images" / f"{key}.png"
            rows.append(
                {
                    "cloth_changed_id": key,
                    "character_id": cid,
                    "outfit_id": outfit_id,
                    "character_name": name if isinstance(name, str) else "",
                    "prompt": prompt_text if isinstance(prompt_text, str) else "",
                    "image_path": to_project_relative(project, image_path) if image_path.exists() else "",
                    "candidate_images": candidate_map.get(key, []),
                }
            )
    return rows


def build_fenjing_details(project: str, assets: Path, visual_assets: Optional[Path] = None) -> Dict[str, List[Dict[str, Any]]]:
    result: Dict[str, List[Dict[str, Any]]] = {}
    storyboards_dir = assets / "storyboards"
    if not storyboards_dir.exists():
        return result
    chars_jsonl = assets / "characters.jsonl"
    defaults = load_char_defaults(chars_jsonl) if chars_jsonl.exists() else {}
    plot_outfits = load_char_plot_outfits(chars_jsonl) if chars_jsonl.exists() else {}
    chapters = sorted([p for p in storyboards_dir.iterdir() if p.is_dir() and CHAPTER_PATTERN.match(p.name)])
    for chapter_dir in chapters:
        candidate_dir = chapter_dir / "fenjing_candidates"
        candidate_map: Dict[str, List[str]] = {}
        if candidate_dir.exists():
            for p in sorted(candidate_dir.iterdir()):
                if not p.is_file():
                    continue
                match = re.match(r"fenjing(\d+)", p.stem, re.IGNORECASE)
                if not match:
                    continue
                fid = match.group(1)
                candidate_map.setdefault(fid, []).append(to_project_relative(project, p))
        prompts_path = chapter_dir / "fenjing_prompts.jsonl"
        rows: List[Dict[str, Any]] = []
        if prompts_path.exists():
            for item in safe_read_jsonl(prompts_path):
                if not isinstance(item, dict):
                    continue
                fenjing_id = str(item.get("fenjing_id", "")).strip()
                outfit_map = build_outfit_map_from_storyboard(assets, chapter_dir.name, fenjing_id)
                bg_hint = item.get("Background_xuanze", "")
                loc_id = str(item.get("Background_pic", "")).strip()
                ref_images: List[Dict[str, Any]] = []
                location_path = resolve_location_image(assets, loc_id, str(bg_hint), visual_assets)
                if location_path:
                    ref_images.append({"type": "location", "id": loc_id, "path": to_project_relative(project, Path(location_path))})
                for idx in range(1, 6):
                    char_key = f"Character_{idx}"
                    outfit_key = f"Character_{idx}_outfit"
                    char_id = str(item.get(char_key, "")).strip()
                    outfit_id = str(item.get(outfit_key, "")).strip()
                    if not outfit_id:
                        outfit_id = outfit_map.get(char_id, "")
                    if char_id:
                        ref_path = ""
                        default_outfit = defaults.get(char_id)
                        if outfit_id and outfit_id != default_outfit:
                            plot_set = plot_outfits.get(char_id)
                            if isinstance(plot_set, set) and outfit_id in plot_set:
                                ref_path = resolve_cloth_changed_image(assets, char_id, outfit_id, visual_assets)
                        if not ref_path:
                            ref_path = resolve_character_image(assets, char_id, visual_assets)
                        if ref_path:
                            ref_images.append({"type": "character", "id": char_id, "path": to_project_relative(project, Path(ref_path))})
                image_path = chapter_dir / "fenjing_images" / f"fenjing{fenjing_id}.png"
                rows.append(
                    {
                        "fenjing_id": fenjing_id,
                        "prompt": item.get("prompt", ""),
                        "duration": item.get("duration", ""),
                        "background": bg_hint,
                        "image_path": to_project_relative(project, image_path) if image_path.exists() else "",
                        "ref_images": ref_images,
                        "candidate_images": candidate_map.get(fenjing_id, []),
                    }
                )
        if not rows:
            storyboard_jsonl = chapter_dir / f"{chapter_dir.name}.jsonl"
            if not storyboard_jsonl.exists():
                storyboard_jsonl = storyboards_dir / f"{chapter_dir.name}.jsonl"
            for idx, item in enumerate(safe_read_jsonl(storyboard_jsonl), start=1):
                if not isinstance(item, dict):
                    continue
                fenjing_id = str(item.get("Storyboard_id", idx)).strip()
                image_path = chapter_dir / "fenjing_images" / f"fenjing{fenjing_id}.png"
                rows.append(
                    {
                        "fenjing_id": fenjing_id,
                        "prompt": item.get("Action", ""),
                        "duration": "",
                        "background": item.get("Time", ""),
                        "image_path": to_project_relative(project, image_path) if image_path.exists() else "",
                        "ref_images": [],
                        "candidate_images": candidate_map.get(fenjing_id, []),
                    }
                )
        result[chapter_dir.name] = rows
    return result


def list_project_assets(project: str) -> Dict[str, Any]:
    assets = storyboard_assets_dir(project)
    visual_assets = visual_audio_assets_dir(project)
    data: Dict[str, Any] = {
        "project": project,
        "assets_root": str(assets),
        "characters": [],
        "character_details": [],
        "cloth_changed_details": [],
        "locations": [],
        "cloth": [],
        "cloth_changed": [],
        "chapters": [],
        "videos": [],
        "character_table": [],
        "location_table": [],
        "storyboard_table": [],
        "fenjing_details": {},
    }
    if not assets.exists() and not visual_assets.exists():
        return data
    
    data["characters"] = [
        to_project_relative(project, Path(p))
        for p in list_files(assets / "character_images", (".png", ".jpg", ".jpeg"))
    ] + [
        to_project_relative(project, Path(p))
        for p in list_files(visual_assets / "character_images", (".png", ".jpg", ".jpeg"))
    ]
    data["character_details"] = build_character_details(project, assets)
    data["cloth_changed_details"] = build_cloth_changed_details(project, assets)
    data["locations"] = [
        to_project_relative(project, Path(p))
        for p in list_files(assets / "location_images", (".png", ".jpg", ".jpeg"))
    ] + [
        to_project_relative(project, Path(p))
        for p in list_files(visual_assets / "location_images", (".png", ".jpg", ".jpeg"))
    ]
    data["cloth"] = [
        to_project_relative(project, Path(p))
        for p in list_files(assets / "cloth_images", (".png", ".jpg", ".jpeg"))
    ]
    data["cloth_changed"] = [
        to_project_relative(project, Path(p))
        for p in list_files(assets / "cloth_changed_images", (".png", ".jpg", ".jpeg"))
    ]
    chapters_dir = assets / "storyboards"
    if chapters_dir.exists():
        for chapter in sorted(chapters_dir.iterdir()):
            if not chapter.is_dir() or not CHAPTER_PATTERN.match(chapter.name):
                continue
            fenjing_dir = chapter / "fenjing_images"
            chapter_data = {
                "name": chapter.name,
                "fenjing_images": [
                    to_project_relative(project, Path(p))
                    for p in list_files(fenjing_dir, (".png", ".jpg", ".jpeg"))
                ],
                "storyboard_jsonl": to_project_relative(project, chapter / f"{chapter.name}.jsonl"),
                "fenjing_prompts": to_project_relative(project, chapter / "fenjing_prompts.jsonl"),
                "shipin_prompts": to_project_relative(project, chapter / "shipin_prompts.jsonl"),
            }
            data["chapters"].append(chapter_data)
    video_map: Dict[str, Dict[str, Any]] = {}
    video_dirs = [project_base_dir(project) / "video", assets / "video"]
    for base_dir in video_dirs:
        if not base_dir.exists():
            continue
        for chapter in sorted(base_dir.iterdir()):
            if not chapter.is_dir():
                continue
            videos = [
                to_project_relative(project, Path(p))
                for p in list_files(chapter, (".mp4", ".mov"))
            ]
            if not videos:
                continue
            entry = video_map.get(chapter.name)
            if entry:
                merged = list(dict.fromkeys(entry["videos"] + videos))
                entry["videos"] = merged
            else:
                video_map[chapter.name] = {"chapter": chapter.name, "videos": videos}
    data["videos"] = [video_map[name] for name in sorted(video_map.keys())]
    data["character_table"] = build_character_table(assets)
    data["location_table"] = build_location_table(assets)
    data["storyboard_table"] = build_storyboard_table(assets)
    data["fenjing_details"] = build_fenjing_details(project, assets, visual_assets)
    return data


def start_job(job_type: str, project: str, runner: callable, payload: Dict[str, Any]) -> Dict[str, Any]:
    job_id = uuid.uuid4().hex
    trace_id = uuid.uuid4().hex
    job = {
        "id": job_id,
        "type": job_type,
        "project": project,
        "status": "running",
        "created_at": time.time(),
        "updated_at": time.time(),
        "payload": payload,
        "trace_id": trace_id,
        "log_path": str(LOG_DIR / f"{job_id}.log"),
        "exit_code": None,
        "error": None,
    }
    persist_job_snapshot(job)
    thread = threading.Thread(target=runner, args=(job_id,), daemon=True)
    thread.start()
    return job


def update_job(job_id: str, **updates: Any) -> None:
    job = find_job_on_disk(job_id)
    if not job:
        return
    job.update(updates)
    job["updated_at"] = time.time()
    persist_job_snapshot(job)


def run_subprocess_job(job_id: str, command: List[str], env: Dict[str, str]) -> None:
    job = find_job_on_disk(job_id)
    if not job:
        return
    log_path = Path(job["log_path"])
    log_event("INFO", "job_start", trace_id=job["trace_id"], job_id=job_id, command=" ".join(command))
    with log_path.open("w", encoding="utf-8") as f:
        proc = subprocess.Popen(
            command,
            stdout=f,
            stderr=subprocess.STDOUT,
            env=env,
            cwd=str(ROOT_DIR),
        )
        exit_code = proc.wait()
    status = "success" if exit_code == 0 else "error"
    update_job(job_id, status=status, exit_code=exit_code)
    log_event("INFO", "job_end", trace_id=job["trace_id"], job_id=job_id, exit_code=exit_code, status=status)


def run_character_regen(job_id: str, project: str, character_id: str) -> None:
    job = find_job_on_disk(job_id)
    if not job:
        return
    log_path = Path(job["log_path"])
    log_event("INFO", "regen_character_start", trace_id=job["trace_id"], job_id=job_id, project=project, character_id=character_id)
    with ThreadLogRedirector(log_path):
        try:
            assets_dir = storyboard_assets_dir(project)
            prompts_path = assets_dir / "character_prompts.jsonl"
            if not prompts_path.exists():
                raise FileNotFoundError(str(prompts_path))
            prompts = read_jsonl(str(prompts_path))
            item = next((p for p in prompts if str(p.get("Character_Id", "")) == character_id), None)
            if not item:
                raise ValueError("character_id_not_found")
            prompt_text = job.get("payload", {}).get("prompt_text") or item.get("st_prompt") or item.get("prompt")
            if not isinstance(prompt_text, str) or not prompt_text.strip():
                raise ValueError("prompt_missing")
            out_dir = assets_dir / "character_candidates"
            out_dir.mkdir(parents=True, exist_ok=True)
            base_id = character_id if character_id.startswith("char_") else f"char_{character_id}"
            prefix = f"{base_id}_{int(time.time() * 1000)}"
            size_override = resolve_character_size_by_attribute(item.get("attribute"))
            path = asyncio.run(generate_and_download(prompt_text, out_dir, prefix, size=size_override))
            if not isinstance(path, Path):
                raise ValueError("generate_failed")
            update_job(job_id, status="success", result={"file": str(path)})
            log_event("INFO", "regen_character_success", trace_id=job["trace_id"], job_id=job_id, file=str(path))
            return
        except Exception as exc:
            update_job(job_id, status="error", error=str(exc))
            log_event("ERROR", "regen_character_error", trace_id=job["trace_id"], job_id=job_id, error=str(exc))


def run_cloth_changed_regen(job_id: str, project: str, character_id: str, outfit_id: str) -> None:
    job = find_job_on_disk(job_id)
    if not job:
        return
    log_path = Path(job["log_path"])
    log_event(
        "INFO",
        "regen_cloth_changed_start",
        trace_id=job["trace_id"],
        job_id=job_id,
        project=project,
        character_id=character_id,
        outfit_id=outfit_id,
    )
    with ThreadLogRedirector(log_path):
        try:
            assets_dir = storyboard_assets_dir(project)
            chars_path = assets_dir / "characters.jsonl"
            if not chars_path.exists():
                raise FileNotFoundError(str(chars_path))
            items = read_jsonl(str(chars_path))
            target = None
            for item in items:
                cid = item.get("Character_Id") or item.get("Character_id") or item.get("character_id")
                if str(cid) != character_id:
                    continue
                changes = item.get("Plot_Costume_Change") or []
                if not isinstance(changes, list):
                    continue
                for ch in changes:
                    if not isinstance(ch, dict):
                        continue
                    oid = ch.get("Outfit_id")
                    if str(oid) == outfit_id:
                        target = ch
                        break
                if target:
                    break
            if not target:
                raise ValueError("outfit_id_not_found")
            prompt_text = job.get("payload", {}).get("prompt_text") or target.get("st_prompt") or target.get("prompt")
            if not isinstance(prompt_text, str) or not prompt_text.strip():
                prompt_text = build_cloth_changed_prompt(target.get("Outfit_Description"))
            out_dir = assets_dir / "cloth_changed_candidates"
            out_dir.mkdir(parents=True, exist_ok=True)
            prefix = f"{character_id}_{outfit_id}_{int(time.time() * 1000)}"
            tos = TosClientWrapper()
            ref_urls: List[str] = []
            if tos.available():
                char_key = f"{runtime_config.TOS_CHARACTER_PREFIX}/{character_id}.png"
                cloth_key = f"{runtime_config.TOS_CLOTH_PREFIX}/{outfit_id}.png"
                char_url = tos.presign_get(runtime_config.TOS_BUCKET, char_key)
                cloth_url = tos.presign_get(runtime_config.TOS_BUCKET, cloth_key)
                if isinstance(char_url, str) and char_url and isinstance(cloth_url, str) and cloth_url:
                    ref_urls = [char_url, cloth_url]
            if ref_urls:
                path = asyncio.run(generate_and_download_with_refs(prompt_text, ref_urls, out_dir, prefix))
            else:
                path = asyncio.run(generate_and_download(prompt_text, out_dir, prefix))
            if not isinstance(path, Path):
                raise ValueError("generate_failed")
            update_job(job_id, status="success", result={"file": str(path)})
            log_event("INFO", "regen_cloth_changed_success", trace_id=job["trace_id"], job_id=job_id, file=str(path))
            return
        except Exception as exc:
            update_job(job_id, status="error", error=str(exc))
            log_event("ERROR", "regen_cloth_changed_error", trace_id=job["trace_id"], job_id=job_id, error=str(exc))


def run_fenjing_regen(job_id: str, project: str, chapter_name: str, fenjing_id: str) -> None:
    job = find_job_on_disk(job_id)
    if not job:
        return
    log_path = Path(job["log_path"])
    log_event("INFO", "regen_fenjing_start", trace_id=job["trace_id"], job_id=job_id, project=project, chapter=chapter_name, fenjing_id=fenjing_id)
    with ThreadLogRedirector(log_path):
        try:
            chapter_dir = storyboard_assets_dir(project) / "storyboards" / chapter_name
            prompts_path = chapter_dir / "fenjing_prompts.jsonl"
            if not prompts_path.exists():
                raise FileNotFoundError(str(prompts_path))
            prompts = read_jsonl(str(prompts_path))
            item = next((p for p in prompts if str(p.get("fenjing_id", "")) == fenjing_id), None)
            if not item:
                raise ValueError("fenjing_id_not_found")
            prompt_text = job.get("payload", {}).get("prompt_text") or item.get("prompt")
            if not isinstance(prompt_text, str) or not prompt_text.strip():
                raise ValueError("prompt_missing")
            out_dir = chapter_dir / "fenjing_candidates"
            out_dir.mkdir(parents=True, exist_ok=True)
            prefix = f"fenjing{fenjing_id}_{int(time.time() * 1000)}"
            ref_urls = build_fenjing_ref_urls(project, chapter_name, fenjing_id, item)
            path = asyncio.run(
                generate_and_download_with_refs(prompt_text, ref_urls, out_dir, prefix)
            ) if ref_urls else asyncio.run(generate_and_download(prompt_text, out_dir, prefix))
            if not isinstance(path, Path):
                raise ValueError("generate_failed")
            update_job(job_id, status="success", result={"file": str(path)})
            log_event("INFO", "regen_fenjing_success", trace_id=job["trace_id"], job_id=job_id, file=str(path))
            return
        except Exception as exc:
            update_job(job_id, status="error", error=str(exc))
            log_event("ERROR", "regen_fenjing_error", trace_id=job["trace_id"], job_id=job_id, error=str(exc))


def run_video_regen(job_id: str, project: str, chapter_name: str, fenjing_id: str) -> None:
    job = find_job_on_disk(job_id)
    if not job:
        return
    log_path = Path(job["log_path"])
    log_event("INFO", "regen_video_start", trace_id=job["trace_id"], job_id=job_id, project=project, chapter=chapter_name, fenjing_id=fenjing_id)
    with ThreadLogRedirector(log_path):
        try:
            chapter_dir = storyboard_assets_dir(project) / "storyboards" / chapter_name
            shipin_prompts_path = chapter_dir / "shipin_prompts.jsonl"
            fenjing_prompts_path = chapter_dir / "fenjing_prompts.jsonl"
            if not shipin_prompts_path.exists():
                raise FileNotFoundError(str(shipin_prompts_path))
            shipin_prompts = read_jsonl(str(shipin_prompts_path))
            shipin_item = next((p for p in shipin_prompts if str(p.get("fenjing_id", "")) == fenjing_id), None)
            if not shipin_item:
                raise ValueError("fenjing_id_not_found")
            prompt_text = shipin_item.get("prompt")
            if not isinstance(prompt_text, str) or not prompt_text.strip():
                raise ValueError("prompt_missing")
            model_version = str(shipin_item.get("model", "1.5"))
            model_ep = runtime_config.VIDEO_MODEL_1_0_EP if "1.0" in model_version else runtime_config.VIDEO_MODEL_1_5_EP
            min_duration = runtime_config.VIDEO_MIN_DURATION_1_0 if "1.0" in model_version else runtime_config.VIDEO_MIN_DURATION_1_5
            duration = 5.0
            if fenjing_prompts_path.exists():
                fenjing_prompts = read_jsonl(str(fenjing_prompts_path))
                fenjing_item = next((p for p in fenjing_prompts if str(p.get("fenjing_id", "")) == fenjing_id), None)
                if isinstance(fenjing_item, dict):
                    dur = fenjing_item.get("duration")
                    if isinstance(dur, (int, float)):
                        duration = float(dur)
            tos = TosClientWrapper()
            if not tos.available():
                raise RuntimeError("tos_unavailable")
            image_key = f"{runtime_config.TOS_FENJING_PREFIX}/{chapter_name}/fenjing{fenjing_id}.png"
            image_url = tos.presign_get(runtime_config.TOS_BUCKET, image_key)
            if not image_url:
                raise RuntimeError("image_presign_failed")
            video_dir = project_base_dir(project) / "video" / chapter_name
            video_dir.mkdir(parents=True, exist_ok=True)
            ok = asyncio.run(
                process_single_video_independent(
                    fenjing_id=fenjing_id,
                    model_ep=model_ep,
                    prompt=prompt_text,
                    image_url=image_url,
                    audio_duration=duration,
                    min_duration=min_duration,
                    video_dir=video_dir,
                    chapter_name=chapter_name,
                )
            )
            if not ok:
                raise RuntimeError("video_generate_failed")
            update_job(job_id, status="success", result={"video_dir": str(video_dir)})
            log_event("INFO", "regen_video_success", trace_id=job["trace_id"], job_id=job_id, video_dir=str(video_dir))
            return
        except Exception as exc:
            update_job(job_id, status="error", error=str(exc))
            log_event("ERROR", "regen_video_error", trace_id=job["trace_id"], job_id=job_id, error=str(exc))


def tail_log(path: Path, max_lines: int = 200) -> List[str]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    return lines[-max_lines:]


def list_jobs_for_project(project: str) -> List[Dict[str, Any]]:
    jobs = load_jobs_from_disk(project)
    jobs.sort(key=lambda item: item.get("updated_at", 0), reverse=True)
    result = []
    for job in jobs:
        log_lines = tail_log(Path(job["log_path"]))
        result.append({**job, "log_tail": log_lines})
    return result


def update_fenjing_prompt(project: str, chapter_name: str, fenjing_id: str, prompt_text: str) -> Dict[str, Any]:
    chapter_dir = storyboard_assets_dir(project) / "storyboards" / chapter_name
    prompts_path = chapter_dir / "fenjing_prompts.jsonl"
    if not prompts_path.exists():
        return {"ok": False, "error": "prompts_missing"}
    items = read_jsonl(str(prompts_path))
    updated = False
    for item in items:
        if str(item.get("fenjing_id", "")) == fenjing_id:
            item["prompt"] = prompt_text
            updated = True
            break
    if not updated:
        return {"ok": False, "error": "fenjing_id_not_found"}
    write_jsonl(str(prompts_path), items)
    return {"ok": True}


def update_character_prompt(project: str, character_id: str, prompt_text: str) -> Dict[str, Any]:
    assets_dir = storyboard_assets_dir(project)
    prompts_path = assets_dir / "character_prompts.jsonl"
    if not prompts_path.exists():
        return {"ok": False, "error": "prompts_missing"}
    items = read_jsonl(str(prompts_path))
    updated = False
    for item in items:
        cid = item.get("Character_Id") or item.get("Character_id") or item.get("character_id")
        if str(cid) == character_id:
            item["prompt"] = prompt_text
            item["st_prompt"] = prompt_text
            updated = True
            break
    if not updated:
        return {"ok": False, "error": "character_id_not_found"}
    write_jsonl(str(prompts_path), items)
    return {"ok": True}


def update_cloth_changed_prompt(project: str, character_id: str, outfit_id: str, prompt_text: str) -> Dict[str, Any]:
    assets_dir = storyboard_assets_dir(project)
    chars_path = assets_dir / "characters.jsonl"
    if not chars_path.exists():
        return {"ok": False, "error": "prompts_missing"}
    items = read_jsonl(str(chars_path))
    updated = False
    for item in items:
        cid = item.get("Character_Id") or item.get("Character_id") or item.get("character_id")
        if str(cid) != character_id:
            continue
        changes = item.get("Plot_Costume_Change") or []
        if not isinstance(changes, list):
            continue
        for ch in changes:
            if not isinstance(ch, dict):
                continue
            oid = ch.get("Outfit_id")
            if str(oid) == outfit_id:
                ch["prompt"] = prompt_text
                ch["st_prompt"] = prompt_text
                updated = True
                break
        if updated:
            break
    if not updated:
        return {"ok": False, "error": "outfit_id_not_found"}
    write_jsonl(str(chars_path), items)
    return {"ok": True}


def publish_character_candidate(project: str, character_id: str, candidate_rel: str) -> Dict[str, Any]:
    if not candidate_rel:
        return {"ok": False, "error": "candidate_missing"}
    candidate_path = resolve_media_path(project, candidate_rel)
    if not candidate_path or not candidate_path.exists():
        return {"ok": False, "error": "candidate_not_found"}
    if "character_candidates" not in candidate_path.parts:
        return {"ok": False, "error": "candidate_invalid"}
    assets_dir = storyboard_assets_dir(project)
    target_dir = assets_dir / "character_images"
    target_dir.mkdir(parents=True, exist_ok=True)
    base_id = character_id if character_id.startswith("char_") else f"char_{character_id}"
    target_path = target_dir / f"{base_id}.png"
    shutil.copyfile(candidate_path, target_path)
    tos = TosClientWrapper()
    if not tos.available():
        return {"ok": False, "error": "tos_unavailable"}
    key = f"{runtime_config.TOS_CHARACTER_PREFIX}/{base_id}.png"
    uri = tos.upload_file(runtime_config.TOS_BUCKET, key, target_path)
    if not uri:
        return {"ok": False, "error": "tos_upload_failed"}
    return {"ok": True, "uri": uri, "path": str(target_path)}


def publish_cloth_changed_candidate(project: str, character_id: str, outfit_id: str, candidate_rel: str) -> Dict[str, Any]:
    if not candidate_rel:
        return {"ok": False, "error": "candidate_missing"}
    candidate_path = resolve_media_path(project, candidate_rel)
    if not candidate_path or not candidate_path.exists():
        return {"ok": False, "error": "candidate_not_found"}
    if "cloth_changed_candidates" not in candidate_path.parts:
        return {"ok": False, "error": "candidate_invalid"}
    assets_dir = storyboard_assets_dir(project)
    target_dir = assets_dir / "cloth_changed_images"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{character_id}_{outfit_id}.png"
    shutil.copyfile(candidate_path, target_path)
    tos = TosClientWrapper()
    if not tos.available():
        return {"ok": False, "error": "tos_unavailable"}
    key = f"{runtime_config.TOS_CLOTH_PREFIX}/{character_id}_{outfit_id}.png"
    uri = tos.upload_file(runtime_config.TOS_BUCKET, key, target_path)
    if not uri:
        return {"ok": False, "error": "tos_upload_failed"}
    return {"ok": True, "uri": uri, "path": str(target_path)}


def publish_fenjing_candidate(project: str, chapter_name: str, fenjing_id: str, candidate_rel: str) -> Dict[str, Any]:
    if not candidate_rel:
        return {"ok": False, "error": "candidate_missing"}
    candidate_path = resolve_media_path(project, candidate_rel)
    if not candidate_path or not candidate_path.exists():
        return {"ok": False, "error": "candidate_not_found"}
    if "fenjing_candidates" not in candidate_path.parts:
        return {"ok": False, "error": "candidate_invalid"}
    chapter_dir = storyboard_assets_dir(project) / "storyboards" / chapter_name
    target_dir = chapter_dir / "fenjing_images"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"fenjing{fenjing_id}.png"
    shutil.copyfile(candidate_path, target_path)
    tos = TosClientWrapper()
    if not tos.available():
        return {"ok": False, "error": "tos_unavailable"}
    key = f"{runtime_config.TOS_FENJING_PREFIX}/{chapter_name}/fenjing{fenjing_id}.png"
    uri = tos.upload_file(runtime_config.TOS_BUCKET, key, target_path)
    if not uri:
        return {"ok": False, "error": "tos_upload_failed"}
    return {"ok": True, "uri": uri, "path": str(target_path)}


def delete_candidate_file(project: str, candidate_rel: str, required_dir: str) -> Dict[str, Any]:
    if not candidate_rel:
        return {"ok": False, "error": "candidate_missing"}
    candidate_path = resolve_media_path(project, candidate_rel)
    if not candidate_path or not candidate_path.exists():
        return {"ok": False, "error": "candidate_not_found"}
    if required_dir not in candidate_path.parts:
        return {"ok": False, "error": "candidate_invalid"}
    try:
        candidate_path.unlink()
    except Exception as exc:
        return {"ok": False, "error": f"candidate_delete_failed:{exc}"}
    return {"ok": True, "path": str(candidate_path)}


def build_outfit_map_from_storyboard(assets_dir: Path, chapter_name: str, fenjing_id: str) -> Dict[str, str]:
    storyboards_path = assets_dir / "storyboards" / f"{chapter_name}.jsonl"
    if not storyboards_path.exists():
        return {}
    try:
        target_id = int(fenjing_id)
    except Exception:
        target_id = None
    for sb in read_jsonl(str(storyboards_path)):
        if not isinstance(sb, dict):
            continue
        sb_id = sb.get("Storyboard_id")
        try:
            sb_id = int(sb_id)
        except Exception:
            sb_id = None
        if target_id is None or sb_id != target_id:
            continue
        chars = sb.get("Characters") or sb.get("characters") or []
        if not isinstance(chars, list):
            continue
        outfit_map: Dict[str, str] = {}
        for c in chars:
            if not isinstance(c, dict):
                continue
            cid = c.get("Character_Id") or c.get("character_id")
            outf = c.get("Outfit") or c.get("outfit")
            if isinstance(cid, str) and isinstance(outf, str):
                outfit_map[cid] = outf
        return outfit_map
    return {}


def build_fenjing_ref_urls(project: str, chapter_name: str, fenjing_id: str, item: Dict[str, Any]) -> List[str]:
    refs: List[str] = []
    assets_dir = storyboard_assets_dir(project)
    chars_jsonl = assets_dir / "characters.jsonl"
    defaults = load_char_defaults(chars_jsonl) if chars_jsonl.exists() else {}
    plot_outfits = load_char_plot_outfits(chars_jsonl) if chars_jsonl.exists() else {}
    outfit_map = build_outfit_map_from_storyboard(assets_dir, chapter_name, fenjing_id)
    tos = TosClientWrapper()
    for pk in character_keys_sorted(item):
        cid = item.get(pk)
        if not isinstance(cid, str) or not cid:
            continue
        num = pk.split("_")[1] if "_" in pk else ""
        prefix = "Character" if pk.startswith("Character_") else "person"
        current_outfit = item.get(f"{prefix}_{num}_outfit") or outfit_map.get(cid)
        default_outfit = defaults.get(cid)
        ref_url = None
        if isinstance(current_outfit, str) and current_outfit and current_outfit != default_outfit:
            plot_set = plot_outfits.get(cid)
            if isinstance(plot_set, set) and current_outfit in plot_set:
                changed_key = f"{runtime_config.TOS_CLOTH_PREFIX}/{cid}_{current_outfit}.png"
                changed_presigned = tos.presign_get(runtime_config.TOS_BUCKET, changed_key) if tos.available() else None
                if isinstance(changed_presigned, str) and changed_presigned:
                    ref_url = changed_presigned
        if not ref_url:
            char_key = f"{runtime_config.TOS_CHARACTER_PREFIX}/{cid}.png"
            ref_url = tos.presign_get(runtime_config.TOS_BUCKET, char_key) if tos.available() else None
        if isinstance(ref_url, str) and ref_url:
            refs.append(ref_url)
    loc_id = str(item.get("Background_pic", "")).strip()
    bg_hint = str(item.get("Background_xuanze", "")).strip()
    typ = "sitting" if ("sitting" in bg_hint.lower() or "坐" in bg_hint) else "standing"
    if loc_id:
        loc_key = f"{runtime_config.TOS_LOCATION_PREFIX}/{loc_id}_{typ}.png"
        url = tos.presign_get(runtime_config.TOS_BUCKET, loc_key) if tos.available() else None
        if isinstance(url, str) and url:
            refs.append(url)
    return refs


def resolve_media_path(project: str, raw_path: str) -> Optional[Path]:
    base = project_base_dir(project)
    candidate = (base / raw_path).resolve()
    try:
        candidate.relative_to(base.resolve())
    except Exception:
        return None
    return candidate if candidate.exists() else None


class ManjuHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PATCH,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            file_path = ROOT_DIR / "manju_web" / "frontend" / "index.html"
            send_file(self, file_path, "text/html; charset=utf-8")
            return
        if path in ("/auth-config", "/auth-config/", "/auth-config/index.html"):
            file_path = ROOT_DIR / "manju_web" / "frontend" / "auth_config.html"
            send_file(self, file_path, "text/html; charset=utf-8")
            return
        if path.startswith("/static/"):
            rel = path[len("/static/") :]
            file_path = ROOT_DIR / "manju_web" / "frontend" / rel
            if file_path.suffix == ".js":
                send_file(self, file_path, "application/javascript; charset=utf-8")
                return
            if file_path.suffix == ".css":
                send_file(self, file_path, "text/css; charset=utf-8")
                return
            send_file(self, file_path, "application/octet-stream")
            return
        if media_handler.handle_get(self, path):
            return
        if config_handler.handle_get(self, self.path):
            return
        if project_handler.handle_get(self, path):
            return
        if job_handler.handle_get(self, path):
            return
        send_json(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        body = read_json_body(self)
        if project_handler.handle_post(self, path, body):
            return
        if job_handler.handle_post(self, path, body):
            return
        send_json(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_PATCH(self) -> None:
        body = read_json_body(self)
        if config_handler.handle_patch(self, self.path, body):
            return
        send_json(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})


class ThreadPoolHTTPServer(ThreadingHTTPServer):
    """带线程数限制的HTTP服务器，防止高并发时线程数爆炸
    
    使用ThreadingHTTPServer的原生能力，添加线程数限制
    通过重写process_request方法，在创建线程前检查信号量
    """
    
    def __init__(self, server_address, RequestHandlerClass, max_threads: int, max_queue_size: int = 100):
        super().__init__(server_address, RequestHandlerClass)
        self.max_threads = max_threads
        self._semaphore = threading.BoundedSemaphore(max_threads)
        
        self.daemon_threads = True
        self.block_on_close = False
        
    def process_request(self, request, client_address):
        """重写process_request，添加信号量限制
        
        ThreadingMixIn的原始实现会创建线程调用process_request_thread，
        我们在这里添加信号量检查，并在请求完成后释放信号量
        """
        if not self._semaphore.acquire(blocking=False):
            self._send_503_error(request)
            self.shutdown_request(request)
            return
        
        try:
            t = threading.Thread(target=self._process_request_wrapper,
                                 args=(request, client_address),
                                 daemon=self.daemon_threads)
            t.start()
        except Exception:
            self._semaphore.release()
            self.handle_error(request, client_address)
            self.shutdown_request(request)
    
    def _process_request_wrapper(self, request, client_address):
        """包装器：处理请求并在完成后释放信号量"""
        try:
            self.finish_request(request, client_address)
        except Exception:
            self.handle_error(request, client_address)
        finally:
            self.shutdown_request(request)
            self._semaphore.release()
    
    def _send_503_error(self, request):
        """发送503服务不可用错误"""
        try:
            error_body = b'{"error": "server_busy", "message": "Server is currently handling too many requests"}'
            request.sendall(
                f"HTTP/1.1 {HTTPStatus.SERVICE_UNAVAILABLE.value} {HTTPStatus.SERVICE_UNAVAILABLE.phrase}\r\n"
                f"Content-Type: application/json\r\n"
                f"Content-Length: {len(error_body)}\r\n"
                f"Connection: close\r\n"
                f"\r\n".encode() + error_body
            )
        except Exception:
            pass


def main() -> None:
    # 从runtime_config加载配置，支持环境变量覆盖
    runtime_config.load()
    host = runtime_config.SERVER_HOST
    port = runtime_config.SERVER_PORT
    max_threads = runtime_config.SERVER_MAX_THREADS
    
    try:
        config_service.list_config_items()
        config_service.list_auth_items()
    except Exception as exc:
        log_event("WARN", "config_defaults_init_failed", trace_id="", error=str(exc))
    try:
        job_repo.reconcile_stale_jobs_on_startup()
    except Exception as exc:
        log_event("WARN", "job_reconcile_failed", trace_id="", error=str(exc))
    try:
        for project in project_repo.list_projects():
            status_service.normalize_state_on_startup(project)
    except Exception as exc:
        log_event("WARN", "flow_state_normalize_failed", trace_id="", error=str(exc))
    
    # 使用带线程池限制的HTTP服务器
    server = ThreadPoolHTTPServer((host, port), ManjuHandler, max_threads=max_threads)
    log_event("INFO", "server_start", trace_id="", host=host, port=port, max_threads=max_threads)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log_event("INFO", "server_shutdown_requested", trace_id="", reason="keyboard_interrupt")
    finally:
        log_event("INFO", "server_shutdown", trace_id="")
        server.shutdown()


if __name__ == "__main__":
    main()
