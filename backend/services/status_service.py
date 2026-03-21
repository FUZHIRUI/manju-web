import time
import threading
from copy import deepcopy
from typing import Any, Dict, Optional

from ..repositories import project_repo, status_repo
from .workflow_runtime.io_jsonl import read_jsonl


_STATUS_WAITING = "waiting"
_STATUS_PENDING = "pending"
_STATUS_RUNNING = "running"
_STATUS_PARTIAL_RETURNED = "partial_returned"
_STATUS_PARTIAL_COMPLETED = "partial_completed"
_STATUS_COMPLETED = "completed"
_STATUS_ERROR = "error"

_project_locks: Dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()


def _get_project_lock(project: str) -> threading.Lock:
    """获取项目级别的锁，确保同一项目的状态操作线程安全"""
    with _locks_lock:
        if project not in _project_locks:
            _project_locks[project] = threading.Lock()
        return _project_locks[project]


_FLOW_STEPS = {
    "auto_storyboard": [
        "step1",
        "step1_extract",
        "step2",
        "step2_storyboard",
        "step3_upload",
        "step3_upload_assets",
    ],
    "visual_audio_assets": [
        "download_assets",
        "build_prompts",
        "generate_images",
        "generate_tts",
        "upload_assets",
        "character_prompts",
        "character_images",
        "location_prompts",
        "fenjing_prompts",
        "location_images",
        "cloth_images",
        "cloth_changed",
        "tts",
    ],
    "fenjing": ["download_assets", "generate_images", "upload_assets"],
    "video": ["prepare", "phase1_video_prompts", "phase2_video_generation", "fenjing_video_upload"],
}

_PARTIAL_STEPS = {
    "visual_audio_assets": ["character_images", "location_images", "tts", "cloth_images", "cloth_changed"],
    "fenjing": ["generate_images"],
    "video": ["phase2_video_generation"],
}

# Workflow 到 Flow 的映射（用于兼容旧 workflow 名称）
WORKFLOW_TO_FLOW_MAP = {
    "fenjing_generate": "fenjing",
    "fenjing_upload": "fenjing",
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
        if flow not in merged["flows"] or not isinstance(flow_data, dict):
            continue
        merged_flow = merged["flows"][flow]
        status = flow_data.get("status")
        if isinstance(status, str):
            merged_flow["status"] = status
        
        steps = flow_data.get("steps") if isinstance(flow_data.get("steps"), dict) else {}
        
        # 兼容旧状态：先将旧步骤名称映射为新步骤名称
        if flow == "auto_storyboard":
            # 创建步骤名称映射
            step_mapping = {
                "phase1": ["step1", "step1_extract"],
                "phase2": ["step2", "step2_storyboard"],
                "upload": ["step3_upload", "step3_upload_assets"],
            }
            
            # 转换旧步骤名称为新步骤名称
            converted_steps = {}
            for old_step, new_steps in step_mapping.items():
                if old_step in steps:
                    for new_step in new_steps:
                        converted_steps[new_step] = steps[old_step]
            
            # 合并转换后的步骤（如果新步骤名已存在，优先使用转换后的值）
            for step, step_status in converted_steps.items():
                if step in merged_flow["steps"] and isinstance(step_status, str):
                    merged_flow["steps"][step] = step_status
        
        # 合并已存在的步骤（新命名）
        for step, step_status in steps.items():
            if step in merged_flow["steps"] and isinstance(step_status, str):
                merged_flow["steps"][step] = step_status
    
    # 迁移旧的 fenjing_generate 和 fenjing_upload 到统一的 fenjing flow
    merged = _migrate_fenjing_flows(merged)
    
    return merged


def _migrate_fenjing_flows(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    迁移旧的 fenjing_generate 和 fenjing_upload 状态到统一的 fenjing flow
    
    迁移规则：
    - fenjing_generate.download_assets -> fenjing.download_assets
    - fenjing_generate.generate_images -> fenjing.generate_images
    - fenjing_upload.upload_fenjing_images -> fenjing.upload_assets
    """
    flows = state.get("flows", {})
    
    # 检查是否需要迁移
    if "fenjing_generate" not in flows and "fenjing_upload" not in flows:
        return state
    
    # 获取或创建 fenjing flow
    if "fenjing" not in flows:
        flows["fenjing"] = {
            "status": _STATUS_WAITING,
            "steps": {step: _STATUS_WAITING for step in _FLOW_STEPS["fenjing"]}
        }
    
    fenjing_steps = flows["fenjing"].get("steps", {})
    
    # 迁移 fenjing_generate 的步骤状态
    fenjing_generate = flows.pop("fenjing_generate", {})
    gen_steps = fenjing_generate.get("steps", {})
    for step in ["download_assets", "generate_images"]:
        if step in gen_steps:
            fenjing_steps[step] = gen_steps[step]
    
    # 迁移 fenjing_upload 的步骤状态（步骤名变更）
    fenjing_upload = flows.pop("fenjing_upload", {})
    upload_steps = fenjing_upload.get("steps", {})
    if "upload_fenjing_images" in upload_steps:
        fenjing_steps["upload_assets"] = upload_steps["upload_fenjing_images"]
    
    # 重新计算 fenjing flow 的整体状态
    flows["fenjing"]["status"] = _recalculate_flow_status("fenjing", fenjing_steps)
    flows["fenjing"]["steps"] = fenjing_steps
    
    return state


def get_flow_state(project: str) -> Dict[str, Any]:
    path = status_repo.flow_state_path(project)
    data = status_repo.read_flow_state(project)
    normalized = _normalize_state(project, data)
    
    # 重新计算所有flow的整体状态，确保状态一致性
    for flow_name, flow_data in normalized.get("flows", {}).items():
        steps = flow_data.get("steps", {})
        if steps:
            flow_data["status"] = _recalculate_flow_status(flow_name, steps)
    
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
    with _get_project_lock(project):
        state = get_flow_state(project)
        _set_flow_status(state, flow, status)
        state["updated_at"] = time.time()
        status_repo.write_flow_state(project, state)


def update_step_status(project: str, flow: str, step: str, status: str) -> None:
    with _get_project_lock(project):
        state = get_flow_state(project)
        _set_step_status(state, flow, step, status)
        state["updated_at"] = time.time()
        status_repo.write_flow_state(project, state)


def _set_steps_status(state: Dict[str, Any], flow: str, steps: Optional[list], status: str) -> None:
    if not steps:
        return
    for step in steps:
        _set_step_status(state, flow, step, status)


def _normalize_phase_tokens(phase: str) -> set:
    raw = str(phase or "").strip().lower()
    tokens = {p.strip() for p in raw.split(",") if p.strip()}
    return tokens


def resolve_visual_audio_steps(phase: str) -> list:
    tokens = _normalize_phase_tokens(phase)
    if not tokens or "all" in tokens:
        return [
            "download_assets",
            "build_prompts",
            "generate_images",
            "upload_assets",
            "cloth_images",
            "cloth_changed",
            "generate_tts",
        ]
    steps: list = []
    for token in tokens:
        if token in {"download_assets", "download"}:
            steps.append("download_assets")
        elif token in {"build_prompts", "character_prompts", "location_prompts", "fenjing_prompts"}:
            steps.append("build_prompts")
            steps.extend(["character_prompts", "location_prompts", "fenjing_prompts"])
        elif token in {"generate_images", "character_images", "location_images"}:
            steps.append("generate_images")
            steps.extend(["character_images", "location_images"])
        elif token in {"generate_tts", "tts"}:
            steps.append("generate_tts")
            steps.append("tts")
        elif token in {"cloth", "cloth_images"}:
            steps.append("cloth_images")
        elif token in {"cloth_changed", "cloth_changed_images"}:
            steps.append("cloth_changed")
        elif token in {"upload_assets", "upload"}:
            steps.append("upload_assets")
        elif token == "character":
            steps.extend(["build_prompts", "generate_images", "character_prompts", "character_images"])
        elif token == "location":
            steps.extend(["build_prompts", "generate_images", "location_prompts", "location_images"])
        elif token == "fenjing":
            steps.extend(["build_prompts", "fenjing_prompts"])
    deduped: list = []
    for item in steps:
        if item not in deduped:
            deduped.append(item)
    return deduped


def _expand_visual_audio_children(steps: Optional[list]) -> list:
    if not steps:
        return []
    expanded = list(steps)
    if "build_prompts" in steps:
        expanded.extend(["character_prompts", "location_prompts", "fenjing_prompts"])
    if "generate_images" in steps:
        expanded.extend(["character_images", "location_images"])
    if "generate_tts" in steps:
        expanded.append("tts")
    deduped: list = []
    for item in expanded:
        if item not in deduped:
            deduped.append(item)
    return deduped


def _expand_auto_storyboard_children(steps: Optional[list]) -> list:
    """展开 auto_storyboard 的父步骤为子步骤"""
    if not steps:
        return []
    
    expanded = list(steps)
    parent_child_map = {
        "step1": ["step1_extract"],
        "step2": ["step2_storyboard"],
        "step3_upload": ["step3_upload_assets"],
    }
    
    for parent, children in parent_child_map.items():
        if parent in steps:
            expanded.extend(children)
    
    # 去重
    deduped: list = []
    for item in expanded:
        if item not in deduped:
            deduped.append(item)
    return deduped


def mark_flow_running(project: str, flow: str, steps: Optional[list] = None, reset_steps: bool = False) -> None:
    with _get_project_lock(project):
        state = get_flow_state(project)
        if reset_steps:
            _reset_all_steps(state, flow)
        if flow == "visual_audio_assets":
            steps = _expand_visual_audio_children(steps)
        elif flow == "auto_storyboard":
            steps = _expand_auto_storyboard_children(steps)
        _set_flow_status(state, flow, _STATUS_RUNNING)
        _set_steps_status(state, flow, steps, _STATUS_RUNNING)
        if flow == "visual_audio_assets":
            _rollup_visual_audio_steps(state)
        elif flow == "auto_storyboard":
            _rollup_auto_storyboard_steps(state)
        elif flow == "video":
            _rollup_video_steps(state)
        elif flow == "fenjing":
            _rollup_fenjing_steps(state)
        state["updated_at"] = time.time()
        status_repo.write_flow_state(project, state)


def reset_flow_steps(project: str, flow: str, steps: Optional[list]) -> None:
    if not steps:
        return
    with _get_project_lock(project):
        state = get_flow_state(project)
        if flow == "visual_audio_assets":
            steps = _expand_visual_audio_children(steps)
        elif flow == "auto_storyboard":
            steps = _expand_auto_storyboard_children(steps)
        for step in steps:
            current_status = state.get("flows", {}).get(flow, {}).get("steps", {}).get(step, _STATUS_WAITING)
            if current_status != _STATUS_COMPLETED:
                _set_step_status(state, flow, step, _STATUS_WAITING)
        if flow == "visual_audio_assets":
            _rollup_visual_audio_steps(state)
        elif flow == "auto_storyboard":
            _rollup_auto_storyboard_steps(state)
        state["updated_at"] = time.time()
        status_repo.write_flow_state(project, state)


def reset_visual_audio_steps_except(project: str, keep_steps: Optional[list]) -> None:
    with _get_project_lock(project):
        state = get_flow_state(project)
        flow = "visual_audio_assets"
        flows = state.get("flows")
        if not isinstance(flows, dict) or flow not in flows:
            return
        steps = flows[flow].get("steps")
        if not isinstance(steps, dict):
            return
        keep = set(_expand_visual_audio_children(keep_steps)) if keep_steps else set()
        for step_id in list(steps.keys()):
            if step_id in keep:
                continue
            steps[step_id] = _STATUS_WAITING
        _rollup_visual_audio_steps(state)
        state["updated_at"] = time.time()
        status_repo.write_flow_state(project, state)


def mark_flow_completed(project: str, flow: str) -> None:
    with _get_project_lock(project):
        state = get_flow_state(project)
        _set_flow_status(state, flow, _STATUS_COMPLETED)
        _complete_all_steps(state, flow)
        if flow == "visual_audio_assets":
            _rollup_visual_audio_steps(state)
        elif flow == "auto_storyboard":
            _rollup_auto_storyboard_steps(state)
        state["updated_at"] = time.time()
        status_repo.write_flow_state(project, state)


def mark_flow_error(project: str, flow: str, steps: Optional[list] = None) -> None:
    with _get_project_lock(project):
        state = get_flow_state(project)
        _set_flow_status(state, flow, _STATUS_ERROR)
        if flow == "visual_audio_assets":
            steps = _expand_visual_audio_children(steps)
        elif flow == "auto_storyboard":
            steps = _expand_auto_storyboard_children(steps)
        _set_steps_status(state, flow, steps, _STATUS_ERROR)
        if flow == "visual_audio_assets":
            _rollup_visual_audio_steps(state)
        elif flow == "auto_storyboard":
            _rollup_auto_storyboard_steps(state)
        state["updated_at"] = time.time()
        status_repo.write_flow_state(project, state)


def mark_flow_partial(project: str, flow: str, steps: Optional[list] = None) -> None:
    with _get_project_lock(project):
        state = get_flow_state(project)
        _set_flow_status(state, flow, _STATUS_PARTIAL_RETURNED)
        if flow == "visual_audio_assets":
            steps = _expand_visual_audio_children(steps)
        elif flow == "auto_storyboard":
            steps = _expand_auto_storyboard_children(steps)
        _set_steps_status(state, flow, steps, _STATUS_PARTIAL_RETURNED)
        if flow == "visual_audio_assets":
            _rollup_visual_audio_steps(state)
        elif flow == "auto_storyboard":
            _rollup_auto_storyboard_steps(state)
        state["updated_at"] = time.time()
        status_repo.write_flow_state(project, state)


def _resolve_step(flow: str, event: str, step: Optional[str], phase: Optional[str]) -> Optional[str]:
    if flow == "auto_storyboard":
        if phase in {"phase1", "phase2"}:
            return phase
        if step in {"phase1", "phase2", "upload"}:
            return step
        if step == "phase1_api_call":
            return "phase1"
        if step == "phase2_batch_progress":
            return "phase2"
        if event.startswith("upload_"):
            return "upload"
        return None
    if flow == "visual_audio_assets":
        if event == "flow_start":
            return "download_assets"
        if step in {"download_assets", "build_prompts", "generate_images", "generate_tts", "upload_assets"}:
            return step
        if step in {"generate_location_images", "generate_cloth", "generate_cloth_images", "generate_cloth_changed_images", "validate_cloth", "phase_cloth_generation"}:
            return "cloth_images"
        if step in {"cloth", "cloth_images", "cloth_changed"}:
            return "cloth_images" if step == "cloth_images" else "cloth_changed"
        if event.startswith("upload_"):
            return "upload_assets"
        return None
    if flow == "fenjing":
        if phase in {"download_assets", "generate_images", "upload_assets"}:
            return phase
        if phase == "phase_download_assets":
            return "download_assets"
        if phase == "phase_generate_images":
            return "generate_images"
        if step in {"download_assets", "generate_images", "upload_assets"}:
            return step
        if step == "fenjing_image":
            return "generate_images"
        # 兼容旧的事件名称
        if event in {"fenjing_generate_start", "flow_start"}:
            return "download_assets"
        if event in {"fenjing_generate_complete", "fenjing_generate_phase_complete"}:
            return "generate_images"
        if event in {"fenjing_upload_start", "fenjing_upload_progress", "fenjing_upload_complete"}:
            return "upload_assets"
        if event.startswith("upload_"):
            return "upload_assets"
        return None
    if flow == "video":
        if event == "flow_start":
            return "prepare"
        if phase in {"phase1_video_prompts", "phase2_video_generation"}:
            return phase
        if step in {"prepare", "phase1_video_prompts", "phase2_video_generation", "fenjing_video_upload"}:
            return step
        if step in {"video_task_submit", "video_task_queue", "video_task_polling", "fenjing_video_task_create", "fenjing_video_polling", "fenjing_video_download"}:
            return "phase2_video_generation"
        if event in {"fenjing_video_upload_start", "fenjing_video_uploaded", "upload_complete"}:
            return "fenjing_video_upload"
        return None
    return None


def _resolve_steps(flow: str, event: str, step: Optional[str], phase: Optional[str]) -> list:
    if flow != "visual_audio_assets":
        step_id = _resolve_step(flow, event, step, phase)
        return [step_id] if step_id else []
    resolved: list = []
    if event == "flow_start":
        resolved.append("download_assets")
    if step:
        if step in _FLOW_STEPS[flow]:
            resolved.append(step)
        if step in {"character_prompts", "location_prompts", "fenjing_prompts"}:
            resolved.append("build_prompts")
        if step in {"character_images", "location_images"}:
            resolved.append("generate_images")
        if step == "tts":
            resolved.append("generate_tts")
        if step == "generate_location_images":
            resolved.append("location_images")
            resolved.append("generate_images")
        if step in {"generate_cloth", "generate_cloth_images", "validate_cloth", "phase_cloth_generation"}:
            resolved.append("cloth_images")
        if step in {"generate_cloth_changed_images", "cloth_changed"}:
            resolved.append("cloth_changed")
    if event.startswith("upload_") and step == "upload_assets":
        resolved.append("upload_assets")
    deduped: list = []
    for item in resolved:
        if item not in deduped:
            deduped.append(item)
    return deduped


def _rollup_visual_audio_steps(state: Dict[str, Any]) -> None:
    flows = state.get("flows")
    if not isinstance(flows, dict) or "visual_audio_assets" not in flows:
        return
    steps = flows["visual_audio_assets"].get("steps")
    if not isinstance(steps, dict):
        return
    rollups = {
        "build_prompts": ["character_prompts", "location_prompts", "fenjing_prompts"],
        "generate_images": ["character_images", "location_images"],
        "generate_tts": ["tts"],
    }
    for parent, children in rollups.items():
        statuses = [steps.get(child, _STATUS_WAITING) for child in children]
        if any(status == _STATUS_ERROR for status in statuses):
            steps[parent] = _STATUS_ERROR
            continue
        if any(status == _STATUS_PARTIAL_RETURNED for status in statuses):
            steps[parent] = _STATUS_PARTIAL_RETURNED
            continue
        if all(status == _STATUS_COMPLETED for status in statuses):
            steps[parent] = _STATUS_COMPLETED
            continue
        if any(status in {_STATUS_RUNNING, _STATUS_COMPLETED} for status in statuses):
            steps[parent] = _STATUS_RUNNING
            continue
        steps[parent] = _STATUS_WAITING


def _rollup_auto_storyboard_steps(state: Dict[str, Any]) -> None:
    """根据子步骤状态汇总 auto_storyboard 的父步骤状态"""
    flows = state.get("flows")
    if not isinstance(flows, dict) or "auto_storyboard" not in flows:
        return
    
    steps = flows["auto_storyboard"].get("steps")
    if not isinstance(steps, dict):
        return
    
    # 父子步骤映射
    rollups = {
        "step1": ["step1_extract"],
        "step2": ["step2_storyboard"],
        "step3_upload": ["step3_upload_assets"],
    }
    
    for parent, children in rollups.items():
        statuses = [steps.get(child, _STATUS_WAITING) for child in children]
        
        # 优先级：error > partial_returned > running > completed > waiting
        if any(status == _STATUS_ERROR for status in statuses):
            steps[parent] = _STATUS_ERROR
        elif any(status == _STATUS_PARTIAL_RETURNED for status in statuses):
            steps[parent] = _STATUS_PARTIAL_RETURNED
        elif any(status == _STATUS_RUNNING for status in statuses):
            steps[parent] = _STATUS_RUNNING
        elif all(status == _STATUS_COMPLETED for status in statuses):
            steps[parent] = _STATUS_COMPLETED
        else:
            steps[parent] = _STATUS_WAITING


def _rollup_video_steps(state: Dict[str, Any]) -> None:
    """根据子步骤状态汇总 video 的父步骤状态"""
    flows = state.get("flows")
    if not isinstance(flows, dict) or "video" not in flows:
        return
    
    steps = flows["video"].get("steps")
    if not isinstance(steps, dict):
        return
    
    # video 流程的步骤顺序：prepare -> phase1_video_prompts -> phase2_video_generation -> fenjing_video_upload
    # 每个步骤必须等待前一个步骤完成才能开始
    step_order = ["prepare", "phase1_video_prompts", "phase2_video_generation", "fenjing_video_upload"]
    
    for i, step in enumerate(step_order):
        current_status = steps.get(step, _STATUS_WAITING)
        if current_status == _STATUS_COMPLETED:
            continue
        if i > 0:
            prev_step = step_order[i - 1]
            prev_status = steps.get(prev_step, _STATUS_WAITING)
            if prev_status != _STATUS_COMPLETED:
                steps[step] = _STATUS_WAITING


def _rollup_fenjing_steps(state: Dict[str, Any]) -> None:
    """根据子步骤状态汇总 fenjing 的父步骤状态"""
    flows = state.get("flows")
    if not isinstance(flows, dict) or "fenjing" not in flows:
        return
    
    steps = flows["fenjing"].get("steps")
    if not isinstance(steps, dict):
        return
    
    # fenjing 流程的步骤顺序：download_assets -> generate_images -> upload_assets
    # 每个步骤必须等待前一个步骤完成才能开始
    step_order = ["download_assets", "generate_images", "upload_assets"]
    
    for i, step in enumerate(step_order):
        current_status = steps.get(step, _STATUS_WAITING)
        if current_status == _STATUS_COMPLETED:
            continue
        if i > 0:
            prev_step = step_order[i - 1]
            prev_status = steps.get(prev_step, _STATUS_WAITING)
            if prev_status != _STATUS_COMPLETED:
                steps[step] = _STATUS_WAITING


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
    # 兼容旧的 workflow 名称，映射到统一的 flow
    actual_flow = WORKFLOW_TO_FLOW_MAP.get(flow, flow)
    if not project or actual_flow not in _FLOW_STEPS:
        return
    with _get_project_lock(project):
        state = get_flow_state(project)
        step_ids = _resolve_steps(actual_flow, event, step, phase)
        if event == "flow_start":
            # 只重置当前要执行的步骤，不要重置已经完成的步骤
            _set_flow_status(state, actual_flow, _STATUS_RUNNING)
            for step_id in step_ids:
                # 只有非完成状态的步骤才重置为running
                current_status = state.get("flows", {}).get(actual_flow, {}).get("steps", {}).get(step_id, _STATUS_WAITING)
                if current_status != _STATUS_COMPLETED:
                    _set_step_status(state, actual_flow, step_id, _STATUS_RUNNING)
        elif event in {"phase_start", "step_progress", "upload_start", "upload_progress", "fenjing_video_upload_start", "video_task_submitted", "fenjing_upload_start"}:
            _set_flow_status(state, actual_flow, _STATUS_RUNNING)
            for step_id in step_ids:
                _set_step_status(state, actual_flow, step_id, _STATUS_RUNNING)
        elif event in {"phase_complete", "upload_complete", "fenjing_video_uploaded", "fenjing_upload_complete", "fenjing_generate_complete"}:
            for step_id in step_ids:
                current_status = state.get("flows", {}).get(actual_flow, {}).get("steps", {}).get(step_id, _STATUS_WAITING)
                if current_status != _STATUS_COMPLETED:
                    _set_step_status(state, actual_flow, step_id, _STATUS_COMPLETED)
        elif event == "flow_complete":
            _set_flow_status(state, actual_flow, _STATUS_COMPLETED)
            _complete_all_steps(state, actual_flow)
        elif event == "flow_error" or level == "ERROR":
            _set_flow_status(state, actual_flow, _STATUS_ERROR)
            for step_id in step_ids:
                _set_step_status(state, actual_flow, step_id, _STATUS_ERROR)
        if actual_flow == "visual_audio_assets":
            _rollup_visual_audio_steps(state)
        elif actual_flow == "auto_storyboard":
            _rollup_auto_storyboard_steps(state)
        
        # 重新计算flow的整体状态（除非是flow_complete事件，因为已经设置了completed）
        if event != "flow_complete":
            steps = state.get("flows", {}).get(actual_flow, {}).get("steps", {})
            if steps:
                state["flows"][actual_flow]["status"] = _recalculate_flow_status(actual_flow, steps)
        
        state["updated_at"] = time.time()
        status_repo.write_flow_state(project, state)


def create_pending_state(project: str, flow: str) -> None:
    # 兼容旧的 workflow 名称，映射到统一的 flow
    actual_flow = WORKFLOW_TO_FLOW_MAP.get(flow, flow)
    if actual_flow not in _FLOW_STEPS:
        return
    with _get_project_lock(project):
        state = get_flow_state(project)
        if actual_flow in state.get("flows", {}):
            state["flows"][actual_flow]["status"] = _STATUS_PENDING
            state["updated_at"] = time.time()
            status_repo.write_flow_state(project, state)


def clear_pending_state(project: str, flow: str) -> None:
    # 兼容旧的 workflow 名称，映射到统一的 flow
    actual_flow = WORKFLOW_TO_FLOW_MAP.get(flow, flow)
    if actual_flow not in _FLOW_STEPS:
        return
    with _get_project_lock(project):
        state = get_flow_state(project)
        if actual_flow in state.get("flows", {}):
            if state["flows"][actual_flow].get("status") == _STATUS_PENDING:
                state["flows"][actual_flow]["status"] = _STATUS_WAITING
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
        if flow == "fenjing":
            _rollup_fenjing_steps(state)
        elif flow == "video":
            _rollup_video_steps(state)
        new_status = _recalculate_flow_status(flow, steps)
        flows[flow]["status"] = new_status
        state["updated_at"] = time.time()
        status_repo.write_flow_state(project, state)


def _recalculate_flow_status(flow: str, steps: Dict[str, Any]) -> str:
    """根据所有步骤状态重新计算flow的整体状态
    
    状态优先级：error > partial_returned > running > completed > waiting
    当所有步骤都是completed时，flow状态为completed
    """
    if not steps:
        return _STATUS_WAITING
    
    # 基于FLOW_STEPS定义获取该flow应该有的步骤列表
    expected_steps = _FLOW_STEPS.get(flow, [])
    if not expected_steps:
        return _STATUS_WAITING
    
    # 只检查定义的步骤状态
    statuses = [steps.get(step, _STATUS_WAITING) for step in expected_steps]
    
    # 如果有任何步骤出错，flow状态为error
    if any(status == _STATUS_ERROR for status in statuses):
        return _STATUS_ERROR
    
    # 如果有任何步骤是partial_returned或partial_completed，flow状态为partial_completed
    if any(status in {_STATUS_PARTIAL_RETURNED, _STATUS_PARTIAL_COMPLETED} for status in statuses):
        return _STATUS_PARTIAL_COMPLETED
    
    # 如果有任何步骤正在运行，flow状态为running
    if any(status == _STATUS_RUNNING for status in statuses):
        return _STATUS_RUNNING
    
    # 如果所有步骤都完成，flow状态为completed
    if all(status == _STATUS_COMPLETED for status in statuses):
        return _STATUS_COMPLETED
    
    # 默认状态为waiting
    return _STATUS_WAITING


def normalize_state_on_startup(project: str) -> None:
    with _get_project_lock(project):
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

                if steps.get("character_prompts") == _STATUS_COMPLETED:
                    if not has_entries(assets_dir / "character_prompts.jsonl"):
                        steps["character_prompts"] = _STATUS_WAITING
                if steps.get("location_prompts") == _STATUS_COMPLETED:
                    if not has_entries(assets_dir / "location_prompts.jsonl"):
                        steps["location_prompts"] = _STATUS_WAITING
                if steps.get("fenjing_prompts") == _STATUS_COMPLETED:
                    storyboards_dir = assets_dir / "storyboards"
                    has_fenjing = False
                    if storyboards_dir.exists():
                        for fen_path in storyboards_dir.glob("storyboard_chapter_*/fenjing_prompts.jsonl"):
                            if has_entries(fen_path):
                                has_fenjing = True
                                break
                    if not has_fenjing:
                        steps["fenjing_prompts"] = _STATUS_WAITING
                _rollup_visual_audio_steps(state)
            
            # 重新计算flow的整体状态
            flow_data["status"] = _recalculate_flow_status(flow, steps)
        
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
                for img in fenjing_dir.glob("*.png"):
                    return True
    return False


def mark_fenjing_generate_partial(project: str) -> None:
    """标记分镜生成部分完成（已迁移到统一的 fenjing flow）"""
    with _get_project_lock(project):
        state = get_flow_state(project)
        flow = "fenjing"
        steps = state.get("flows", {}).get(flow, {}).get("steps", {})
        generate_status = steps.get("generate_images", _STATUS_WAITING)
        if generate_status == _STATUS_RUNNING:
            if check_fenjing_images_exist(project):
                steps["generate_images"] = _STATUS_PARTIAL_COMPLETED
                state["flows"][flow]["status"] = _STATUS_PARTIAL_COMPLETED
        state["updated_at"] = time.time()
        status_repo.write_flow_state(project, state)
