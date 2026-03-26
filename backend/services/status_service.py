import threading
import time
from copy import deepcopy
from typing import Any, Dict, Optional

from ..repositories import project_repo, status_repo
from .workflow_runtime.io_jsonl import read_jsonl


WORKFLOW_TO_FLOW_MAP: Dict[str, str] = {
    "fenjing_generate": "fenjing_generate",
    "fenjing_upload": "fenjing_upload",
}

_project_locks: Dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _get_project_lock(project: str) -> threading.Lock:
    with _locks_guard:
        if project not in _project_locks:
            _project_locks[project] = threading.Lock()
        return _project_locks[project]


def _recalculate_flow_status(_flow: str, steps: Dict[str, str]) -> str:
    """根据所有 step 状态推算 flow 整体状态"""
    statuses = list(steps.values())
    if not statuses:
        return _STATUS_WAITING
    if all(s == _STATUS_COMPLETED for s in statuses):
        return _STATUS_COMPLETED
    if any(s == _STATUS_ERROR for s in statuses):
        return _STATUS_ERROR
    if any(s == _STATUS_PARTIAL_RETURNED for s in statuses):
        return _STATUS_PARTIAL_RETURNED
    if any(s == _STATUS_PARTIAL_COMPLETED for s in statuses):
        return _STATUS_PARTIAL_COMPLETED
    if any(s == _STATUS_RUNNING for s in statuses):
        return _STATUS_RUNNING
    return _STATUS_WAITING


_STATUS_WAITING = "waiting"
_STATUS_PENDING = "pending"
_STATUS_RUNNING = "running"
_STATUS_PARTIAL_RETURNED = "partial_returned"
_STATUS_PARTIAL_COMPLETED = "partial_completed"
_STATUS_COMPLETED = "completed"
_STATUS_ERROR = "error"

_FLOW_STEPS = {
    "auto_storyboard": ["step_extract", "step_storyboard", "step_upload"],
    "visual_audio_assets": [
        "step_download",
        "step_character_prompts",
        "step_location_prompts",
        "step_fenjing_prompts",
        "step_character_images",
        "step_location_images",
        "step_cloth_images",
        "step_cloth_changed",
        "step_tts",
        "step_upload",
    ],
    "fenjing_generate": ["step_download", "step_generate"],
    "fenjing_upload": ["step_upload"],
    "video": ["step_prepare", "step_video_prompts", "step_video_generation", "step_video_upload"],
}

_PARTIAL_STEPS = {
    "visual_audio_assets": ["step_character_images", "step_location_images", "step_tts", "step_cloth_images", "step_cloth_changed"],
    "fenjing_generate": ["step_generate"],
    "video": ["step_video_generation"],
}

_STEP_MIGRATION = {
    "auto_storyboard": {
        "phase1": "step_extract", "step1": "step_extract", "step1_extract": "step_extract",
        "phase2": "step_storyboard", "step2": "step_storyboard", "step2_storyboard": "step_storyboard",
        "upload": "step_upload", "step3_upload": "step_upload", "step3_upload_assets": "step_upload",
    },
    "visual_audio_assets": {
        "download_assets": "step_download",
        "character_prompts": "step_character_prompts",
        "location_prompts": "step_location_prompts",
        "fenjing_prompts": "step_fenjing_prompts",
        "character_images": "step_character_images",
        "location_images": "step_location_images",
        "cloth_images": "step_cloth_images",
        "cloth_changed": "step_cloth_changed",
        "tts": "step_tts",
        "upload_assets": "step_upload",
        # 旧父步骤忽略（不迁移）
        "build_prompts": None, "generate_images": None, "generate_tts": None,
    },
    "fenjing_generate": {
        "download_assets": "step_download",
        "generate_images": "step_generate",
    },
    "fenjing_upload": {
        "upload_fenjing_images": "step_upload",
    },
    "video": {
        "prepare": "step_prepare",
        "phase1_video_prompts": "step_video_prompts",
        "phase2_video_generation": "step_video_generation",
        "fenjing_video_upload": "step_video_upload",
    },
}

# Rollup 配置：父子聚合
_ROLLUP_PARENT_CHILD = {
    "visual_audio_assets": {
        "step_prompts": ["step_character_prompts", "step_location_prompts", "step_fenjing_prompts"],
        "step_images": ["step_character_images", "step_location_images"],
    },
}

# Rollup 配置：顺序依赖
_ROLLUP_SEQUENTIAL = {
    "video": ["step_prepare", "step_video_prompts", "step_video_generation", "step_video_upload"],
    "fenjing_generate": ["step_download", "step_generate"],
}


def _default_flow_state(project: str) -> Dict[str, Any]:
    flows: Dict[str, Any] = {}
    for flow, steps in _FLOW_STEPS.items():
        flows[flow] = {
            "status": _STATUS_WAITING,
            "steps": {step: _STATUS_WAITING for step in steps},
        }
    return {"project": project, "updated_at": time.time(), "flows": flows}


def _normalize_state(project: str, data: Dict[str, Any]) -> Dict[str, Any]:
    base = _default_flow_state(project)
    if not isinstance(data, dict):
        return base
    flows = data.get("flows") if isinstance(data.get("flows"), dict) else {}
    merged = deepcopy(base)
    merged["updated_at"] = data.get("updated_at", merged["updated_at"])

    for flow, flow_data in flows.items():
        # 跳过已删除的 flow（如旧的 "fenjing"）
        if flow not in merged["flows"] or not isinstance(flow_data, dict):
            continue
        merged_flow = merged["flows"][flow]
        status = flow_data.get("status")
        if isinstance(status, str):
            merged_flow["status"] = status

        steps = flow_data.get("steps") if isinstance(flow_data.get("steps"), dict) else {}

        # 通用迁移：使用 _STEP_MIGRATION 将旧步骤名映射到新步骤名
        if flow in _STEP_MIGRATION:
            migration = _STEP_MIGRATION[flow]
            for old_step, old_status in steps.items():
                if old_step in migration:
                    new_step = migration[old_step]
                    if new_step is not None and new_step in merged_flow["steps"] and isinstance(old_status, str):
                        # 只在新步骤仍为 waiting 时迁移（避免覆盖已有的新格式值）
                        if merged_flow["steps"][new_step] == _STATUS_WAITING:
                            merged_flow["steps"][new_step] = old_status

        # 合并已存在的步骤（新命名）
        for step, step_status in steps.items():
            if step in merged_flow["steps"] and isinstance(step_status, str):
                merged_flow["steps"][step] = step_status

    return merged


def get_flow_state(project: str) -> Dict[str, Any]:
    path = status_repo.flow_state_path(project)
    data = status_repo.read_flow_state(project)
    normalized = _normalize_state(project, data)
    if path.exists() and data != normalized:
        status_repo.write_flow_state(project, normalized)
    return normalized


def _set_flow_status(state: Dict[str, Any], flow: str, status: str) -> None:
    flows = state.get("flows")
    if not isinstance(flows, dict) or flow not in flows:
        return
    flows[flow]["status"] = status


def _set_step_status(state: Dict[str, Any], flow: str, step: str, status: str) -> None:
    flows = state.get("flows")
    if not isinstance(flows, dict) or flow not in flows:
        return
    steps = flows[flow].get("steps")
    if not isinstance(steps, dict) or step not in steps:
        return
    steps[step] = status


def update_flow_status(project: str, flow: str, status: str) -> None:
    state = get_flow_state(project)
    _set_flow_status(state, flow, status)
    state["updated_at"] = time.time()
    status_repo.write_flow_state(project, state)


def update_step_status(project: str, flow: str, step: str, status: str) -> None:
    state = get_flow_state(project)
    _set_step_status(state, flow, step, status)
    state["updated_at"] = time.time()
    status_repo.write_flow_state(project, state)


def _set_steps_status(state: Dict[str, Any], flow: str, steps: Optional[list], status: str) -> None:
    if not steps:
        return
    for step in steps:
        _set_step_status(state, flow, step, status)


def _normalize_step_tokens(step_filter: str) -> set:
    raw = str(step_filter or "").strip().lower()
    tokens = {p.strip() for p in raw.split(",") if p.strip()}
    return tokens


def resolve_visual_audio_steps(step_filter: str) -> list:
    tokens = _normalize_step_tokens(step_filter)
    if not tokens or "all" in tokens:
        return [
            "step_download",
            "step_character_prompts", "step_location_prompts", "step_fenjing_prompts",
            "step_character_images", "step_location_images",
            "step_cloth_images", "step_cloth_changed",
            "step_tts",
            "step_upload",
        ]
    steps: list = []
    for token in tokens:
        if token in {"download_assets", "download", "step_download"}:
            steps.append("step_download")
        elif token in {"build_prompts", "character_prompts", "location_prompts", "fenjing_prompts",
                       "step_character_prompts", "step_location_prompts", "step_fenjing_prompts"}:
            steps.extend(["step_character_prompts", "step_location_prompts", "step_fenjing_prompts"])
        elif token in {"generate_images", "character_images", "location_images",
                       "step_character_images", "step_location_images"}:
            steps.extend(["step_character_images", "step_location_images"])
        elif token in {"generate_tts", "tts", "step_tts"}:
            steps.append("step_tts")
        elif token in {"cloth", "cloth_images", "step_cloth_images"}:
            steps.append("step_cloth_images")
        elif token in {"cloth_changed", "cloth_changed_images", "step_cloth_changed"}:
            steps.append("step_cloth_changed")
        elif token in {"upload_assets", "upload", "step_upload"}:
            steps.append("step_upload")
        elif token == "character":
            steps.extend(["step_character_prompts", "step_character_images"])
        elif token == "location":
            steps.extend(["step_location_prompts", "step_location_images"])
        elif token == "fenjing":
            steps.append("step_fenjing_prompts")
    deduped: list = []
    for item in steps:
        if item not in deduped:
            deduped.append(item)
    return deduped


def _rollup_parent_child(state: Dict[str, Any], flow: str) -> None:
    """按 _ROLLUP_PARENT_CHILD 配置聚合子步骤→虚拟父步骤"""
    if flow not in _ROLLUP_PARENT_CHILD:
        return
    flows = state.get("flows")
    if not isinstance(flows, dict) or flow not in flows:
        return
    steps = flows[flow].get("steps")
    if not isinstance(steps, dict):
        return
    for parent, children in _ROLLUP_PARENT_CHILD[flow].items():
        statuses = [steps.get(child, _STATUS_WAITING) for child in children]
        if any(status == _STATUS_ERROR for status in statuses):
            steps[parent] = _STATUS_ERROR
        elif any(status == _STATUS_PARTIAL_RETURNED for status in statuses):
            steps[parent] = _STATUS_PARTIAL_RETURNED
        elif all(status == _STATUS_COMPLETED for status in statuses):
            steps[parent] = _STATUS_COMPLETED
        elif any(status in {_STATUS_RUNNING, _STATUS_COMPLETED} for status in statuses):
            steps[parent] = _STATUS_RUNNING
        else:
            steps[parent] = _STATUS_WAITING


def _rollup_sequential(state: Dict[str, Any], flow: str) -> None:
    """按 _ROLLUP_SEQUENTIAL 配置检查顺序依赖"""
    if flow not in _ROLLUP_SEQUENTIAL:
        return
    flows = state.get("flows")
    if not isinstance(flows, dict) or flow not in flows:
        return
    steps = flows[flow].get("steps")
    if not isinstance(steps, dict):
        return
    step_order = _ROLLUP_SEQUENTIAL[flow]
    for i, step in enumerate(step_order):
        current_status = steps.get(step, _STATUS_WAITING)
        if current_status == _STATUS_COMPLETED:
            continue
        if i > 0:
            prev_step = step_order[i - 1]
            prev_status = steps.get(prev_step, _STATUS_WAITING)
            if prev_status != _STATUS_COMPLETED:
                steps[step] = _STATUS_WAITING


def _rollup(state: Dict[str, Any], flow: str) -> None:
    """根据 flow 名自动选择对应 rollup"""
    if flow in _ROLLUP_PARENT_CHILD:
        _rollup_parent_child(state, flow)
    if flow in _ROLLUP_SEQUENTIAL:
        _rollup_sequential(state, flow)


def mark_flow_running(project: str, flow: str, steps: Optional[list] = None, reset_steps: bool = False) -> None:
    state = get_flow_state(project)
    if reset_steps:
        _reset_all_steps(state, flow)
    _set_flow_status(state, flow, _STATUS_RUNNING)
    _set_steps_status(state, flow, steps, _STATUS_RUNNING)
    _rollup(state, flow)
    state["updated_at"] = time.time()
    status_repo.write_flow_state(project, state)


def reset_flow_steps(project: str, flow: str, steps: Optional[list]) -> None:
    if not steps:
        return
    state = get_flow_state(project)
    for step in steps:
        current_status = state.get("flows", {}).get(flow, {}).get("steps", {}).get(step, _STATUS_WAITING)
        if current_status != _STATUS_COMPLETED:
            _set_step_status(state, flow, step, _STATUS_WAITING)
    _rollup(state, flow)
    state["updated_at"] = time.time()
    status_repo.write_flow_state(project, state)


def reset_visual_audio_steps_except(project: str, keep_steps: Optional[list]) -> None:
    state = get_flow_state(project)
    flow = "visual_audio_assets"
    flows = state.get("flows")
    if not isinstance(flows, dict) or flow not in flows:
        return
    steps = flows[flow].get("steps")
    if not isinstance(steps, dict):
        return
    keep = set(keep_steps) if keep_steps else set()
    for step_id in list(steps.keys()):
        if step_id in keep:
            continue
        steps[step_id] = _STATUS_WAITING
    _rollup(state, flow)
    state["updated_at"] = time.time()
    status_repo.write_flow_state(project, state)


def mark_flow_completed(project: str, flow: str) -> None:
    state = get_flow_state(project)
    _set_flow_status(state, flow, _STATUS_COMPLETED)
    _complete_all_steps(state, flow)
    _rollup(state, flow)
    state["updated_at"] = time.time()
    status_repo.write_flow_state(project, state)


def mark_flow_error(project: str, flow: str, steps: Optional[list] = None) -> None:
    state = get_flow_state(project)
    _set_flow_status(state, flow, _STATUS_ERROR)
    _set_steps_status(state, flow, steps, _STATUS_ERROR)
    _rollup(state, flow)
    state["updated_at"] = time.time()
    status_repo.write_flow_state(project, state)


def mark_flow_partial(project: str, flow: str, steps: Optional[list] = None) -> None:
    state = get_flow_state(project)
    _set_flow_status(state, flow, _STATUS_PARTIAL_RETURNED)
    _set_steps_status(state, flow, steps, _STATUS_PARTIAL_RETURNED)
    _rollup(state, flow)
    state["updated_at"] = time.time()
    status_repo.write_flow_state(project, state)


def _resolve_step(flow: str, event: str, step: Optional[str], phase: Optional[str]) -> Optional[str]:
    # 直通逻辑：step 已在 _FLOW_STEPS 中则直接返回
    if step and flow in _FLOW_STEPS and step in _FLOW_STEPS[flow]:
        return step
    # 检查 _STEP_MIGRATION
    if step and flow in _STEP_MIGRATION:
        migrated = _STEP_MIGRATION[flow].get(step)
        if migrated is not None:
            return migrated
    # phase 也可能是旧名
    if phase and flow in _STEP_MIGRATION:
        migrated = _STEP_MIGRATION[flow].get(phase)
        if migrated is not None:
            return migrated

    if flow == "auto_storyboard":
        if phase in {"phase1", "phase2"}:
            return _STEP_MIGRATION["auto_storyboard"].get(phase)
        if step in {"phase1", "phase2", "upload"}:
            return _STEP_MIGRATION["auto_storyboard"].get(step)
        if step == "phase1_api_call":
            return "step_extract"
        if step == "phase2_batch_progress":
            return "step_storyboard"
        if event.startswith("upload_"):
            return "step_upload"
        return None
    if flow == "visual_audio_assets":
        if event == "flow_start":
            return "step_download"
        if step in {"generate_location_images", "generate_cloth", "generate_cloth_images", "generate_cloth_changed_images", "validate_cloth", "phase_cloth_generation"}:
            return "step_cloth_images"
        if step == "cloth_changed":
            return "step_cloth_changed"
        if event.startswith("upload_"):
            return "step_upload"
        return None
    if flow == "fenjing":
        # 旧 fenjing flow 的事件映射到 fenjing_generate
        if phase == "phase_download_assets":
            return "step_download"
        if phase == "phase_generate_images":
            return "step_generate"
        if step == "fenjing_image":
            return "step_generate"
        if event.startswith("upload_"):
            return "step_upload"
        return None
    if flow == "fenjing_generate":
        if event in {"fenjing_generate_start", "flow_start"}:
            return "step_download"
        if phase == "phase_download_assets":
            return "step_download"
        if phase == "phase_generate_images":
            return "step_generate"
        if step == "fenjing_image":
            return "step_generate"
        if event in {"fenjing_generate_complete", "fenjing_generate_phase_complete"}:
            return "step_generate"
        return None
    if flow == "fenjing_upload":
        if event in {"fenjing_upload_start", "fenjing_upload_progress", "fenjing_upload_complete"}:
            return "step_upload"
        return None
    if flow == "video":
        if event == "flow_start":
            return "step_prepare"
        if step in {"video_task_submit", "video_task_queue", "video_task_polling", "fenjing_video_task_create", "fenjing_video_polling", "fenjing_video_download"}:
            return "step_video_generation"
        if event in {"fenjing_video_upload_start", "fenjing_video_uploaded", "upload_complete"}:
            return "step_video_upload"
        return None
    return None


def _resolve_steps(flow: str, event: str, step: Optional[str], phase: Optional[str]) -> list:
    if flow != "visual_audio_assets":
        step_id = _resolve_step(flow, event, step, phase)
        return [step_id] if step_id else []
    resolved: list = []
    if event == "flow_start":
        resolved.append("step_download")
    if step:
        # 直通：step 已在 _FLOW_STEPS 中
        if step in _FLOW_STEPS[flow]:
            resolved.append(step)
        # 迁移映射
        elif step in _STEP_MIGRATION.get(flow, {}):
            migrated = _STEP_MIGRATION[flow][step]
            if migrated is not None:
                resolved.append(migrated)
        # 特殊旧名映射
        if step in {"character_prompts", "location_prompts", "fenjing_prompts"}:
            migrated = _STEP_MIGRATION["visual_audio_assets"].get(step)
            if migrated and migrated not in resolved:
                resolved.append(migrated)
        if step in {"character_images", "location_images"}:
            migrated = _STEP_MIGRATION["visual_audio_assets"].get(step)
            if migrated and migrated not in resolved:
                resolved.append(migrated)
        if step == "tts":
            if "step_tts" not in resolved:
                resolved.append("step_tts")
        if step == "generate_location_images":
            if "step_location_images" not in resolved:
                resolved.append("step_location_images")
        if step in {"generate_cloth", "generate_cloth_images", "validate_cloth", "phase_cloth_generation"}:
            if "step_cloth_images" not in resolved:
                resolved.append("step_cloth_images")
        if step in {"generate_cloth_changed_images", "cloth_changed"}:
            if "step_cloth_changed" not in resolved:
                resolved.append("step_cloth_changed")
    if event.startswith("upload_") and step in {"upload_assets", "step_upload"}:
        if "step_upload" not in resolved:
            resolved.append("step_upload")
    deduped: list = []
    for item in resolved:
        if item not in deduped:
            deduped.append(item)
    return deduped


def _complete_all_steps(state: Dict[str, Any], flow: str) -> None:
    flows = state.get("flows")
    if not isinstance(flows, dict) or flow not in flows:
        return
    steps = flows[flow].get("steps")
    if not isinstance(steps, dict):
        return
    for step in list(steps.keys()):
        steps[step] = _STATUS_COMPLETED


def _reset_all_steps(state: Dict[str, Any], flow: str) -> None:
    flows = state.get("flows")
    if not isinstance(flows, dict) or flow not in flows:
        return
    steps = flows[flow].get("steps")
    if not isinstance(steps, dict):
        return
    for step in list(steps.keys()):
        steps[step] = _STATUS_WAITING


def update_from_event(
    flow: str,
    event: str,
    level: str,
    step: Optional[str],
    phase: Optional[str],
    project: Optional[str],
) -> None:
    if not project or flow not in _FLOW_STEPS:
        return
    state = get_flow_state(project)
    step_ids = _resolve_steps(flow, event, step, phase)
    if event == "flow_start":
        _set_flow_status(state, flow, _STATUS_RUNNING)
        for step_id in step_ids:
            current_status = state.get("flows", {}).get(flow, {}).get("steps", {}).get(step_id, _STATUS_WAITING)
            if current_status != _STATUS_COMPLETED:
                _set_step_status(state, flow, step_id, _STATUS_RUNNING)
    elif event in {"phase_start", "step_progress", "upload_start", "upload_progress", "fenjing_video_upload_start", "video_task_submitted", "fenjing_upload_start"}:
        _set_flow_status(state, flow, _STATUS_RUNNING)
        for step_id in step_ids:
            _set_step_status(state, flow, step_id, _STATUS_RUNNING)
    elif event in {"phase_complete", "upload_complete", "fenjing_video_uploaded", "fenjing_upload_complete"}:
        for step_id in step_ids:
            current_status = state.get("flows", {}).get(flow, {}).get("steps", {}).get(step_id, _STATUS_WAITING)
            if current_status != _STATUS_COMPLETED:
                _set_step_status(state, flow, step_id, _STATUS_COMPLETED)
    elif event == "flow_complete":
        _set_flow_status(state, flow, _STATUS_COMPLETED)
        _complete_all_steps(state, flow)
    elif event == "flow_error" or level == "ERROR":
        _set_flow_status(state, flow, _STATUS_ERROR)
        for step_id in step_ids:
            _set_step_status(state, flow, step_id, _STATUS_ERROR)
    _rollup(state, flow)
    state["updated_at"] = time.time()
    status_repo.write_flow_state(project, state)


def create_pending_state(project: str, flow: str) -> None:
    if flow not in _FLOW_STEPS:
        return
    state = get_flow_state(project)
    if flow in state.get("flows", {}):
        state["flows"][flow]["status"] = _STATUS_PENDING
        state["updated_at"] = time.time()
        status_repo.write_flow_state(project, state)


def clear_pending_state(project: str, flow: str) -> None:
    if flow not in _FLOW_STEPS:
        return
    state = get_flow_state(project)
    if flow in state.get("flows", {}):
        if state["flows"][flow].get("status") == _STATUS_PENDING:
            state["flows"][flow]["status"] = _STATUS_WAITING
            state["updated_at"] = time.time()
            status_repo.write_flow_state(project, state)


def update_step_partial(project: str, flow: str, step: str) -> None:
    if flow not in _PARTIAL_STEPS or step not in _PARTIAL_STEPS.get(flow, []):
        return
    with _get_project_lock(project):
        state = get_flow_state(project)
        steps = state.get("flows", {}).get(flow, {}).get("steps", {})
        if step in steps:
            steps[step] = _STATUS_PARTIAL_RETURNED
            _set_flow_status(state, flow, _STATUS_PARTIAL_RETURNED)
            state["updated_at"] = time.time()
            status_repo.write_flow_state(project, state)


def mark_step_completed(project: str, flow: str, step: str) -> None:
    """标记特定步骤完成，并重新计算flow状态（不改变其他步骤状态）"""
    with _get_project_lock(project):
        state = get_flow_state(project)
        flows = state.get("flows")
        if not isinstance(flows, dict) or flow not in flows:
            return
        steps = flows[flow].get("steps")
        if not isinstance(steps, dict) or step not in steps:
            return
        steps[step] = _STATUS_COMPLETED
        _rollup(state, flow)
        new_status = _recalculate_flow_status(flow, steps)
        flows[flow]["status"] = new_status
        state["updated_at"] = time.time()
        status_repo.write_flow_state(project, state)


def normalize_state_on_startup(project: str) -> None:
    state = get_flow_state(project)
    for flow, flow_data in state.get("flows", {}).items():
        flow_status = flow_data.get("status")
        if flow_status == _STATUS_RUNNING:
            flow_data["status"] = _STATUS_ERROR
        elif flow_status == _STATUS_PENDING:
            pass
        steps = flow_data.get("steps", {})
        for step, status in list(steps.items()):
            if status == _STATUS_RUNNING:
                if flow in _PARTIAL_STEPS and step in _PARTIAL_STEPS[flow]:
                    steps[step] = _STATUS_ERROR
                else:
                    steps[step] = _STATUS_ERROR
            elif status == _STATUS_PARTIAL_RETURNED:
                steps[step] = _STATUS_PARTIAL_COMPLETED
        if flow == "visual_audio_assets" and isinstance(steps, dict):
            assets_dir = project_repo.visual_audio_assets_dir(project)

            def has_entries(path) -> bool:
                try:
                    if not path.exists():
                        return False
                    return len(read_jsonl(str(path))) > 0
                except Exception:
                    return False

            if steps.get("step_character_prompts") == _STATUS_COMPLETED:
                if not has_entries(assets_dir / "character_prompts.jsonl"):
                    steps["step_character_prompts"] = _STATUS_WAITING
            if steps.get("step_location_prompts") == _STATUS_COMPLETED:
                if not has_entries(assets_dir / "location_prompts.jsonl"):
                    steps["step_location_prompts"] = _STATUS_WAITING
            if steps.get("step_fenjing_prompts") == _STATUS_COMPLETED:
                storyboards_dir = assets_dir / "storyboards"
                has_fenjing = False
                if storyboards_dir.exists():
                    for fen_path in storyboards_dir.glob("storyboard_chapter_*/fenjing_prompts.jsonl"):
                        if has_entries(fen_path):
                            has_fenjing = True
                            break
                if not has_fenjing:
                    steps["step_fenjing_prompts"] = _STATUS_WAITING
            _rollup(state, flow)
    state["updated_at"] = time.time()
    status_repo.write_flow_state(project, state)


def check_fenjing_images_exist(project: str) -> bool:
    """检查是否存在分镜图片"""
    assets_dir = project_repo.storyboard_assets_dir(project)
    if not assets_dir.exists():
        return False
    storyboards_dir = assets_dir / "storyboards"
    if not storyboards_dir.exists():
        return False
    for chapter_dir in storyboards_dir.iterdir():
        if chapter_dir.is_dir():
            fenjing_dir = chapter_dir / "fenjing"
            if fenjing_dir.exists():
                for _img in fenjing_dir.glob("*.png"):
                    return True
    return False


def mark_fenjing_generate_partial(project: str) -> None:
    """标记分镜生成部分完成"""
    state = get_flow_state(project)
    flow = "fenjing_generate"
    steps = state.get("flows", {}).get(flow, {}).get("steps", {})
    generate_status = steps.get("step_generate", _STATUS_WAITING)
    if generate_status == _STATUS_RUNNING:
        if check_fenjing_images_exist(project):
            steps["step_generate"] = _STATUS_PARTIAL_COMPLETED
            state["flows"][flow]["status"] = _STATUS_PARTIAL_COMPLETED
    state["updated_at"] = time.time()
    status_repo.write_flow_state(project, state)
