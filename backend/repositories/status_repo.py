import json
from pathlib import Path
from typing import Any, Dict
import uuid

def flow_state_path(project: str) -> Path:
    from .project_repo import project_base_dir

    return project_base_dir(project) / "flow_state.json"


def read_flow_state(project: str) -> Dict[str, Any]:
    if not project:
        return {}
    path = flow_state_path(project)
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_flow_state(project: str, state: Dict[str, Any]) -> None:
    if not project:
        return
    path = flow_state_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    tmp_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(path)
