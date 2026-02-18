import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..services.workflow_runtime import runtime_config
from ..services.workflow_runtime.io_jsonl import read_jsonl

OUTPUT_DIR = Path(os.environ.get("MANJU_OUTPUT_DIR", str(runtime_config.OUTPUT_DIR)))
PROJECT_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
CHAPTER_PATTERN = re.compile(r"^storyboard_chapter_\d+$")


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


def visual_audio_assets_dir(project: str) -> Path:
    return project_base_dir(project) / "visual_audio_assets"


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
