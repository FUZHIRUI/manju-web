from pathlib import Path
from typing import Optional

from .project_repo import project_base_dir


def resolve_media_path(project: str, raw_path: str) -> Optional[Path]:
    base = project_base_dir(project)
    candidate = (base / raw_path).resolve()
    try:
        candidate.relative_to(base.resolve())
    except Exception:
        return None
    return candidate if candidate.exists() else None
