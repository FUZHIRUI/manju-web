"""作业（Job）仓库：负责作业状态的持久化存储与查询。"""

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..services.workflow_runtime.io_jsonl import write_jsonl

from .log_repo import tail_log
from .project_repo import list_projects, project_base_dir, safe_read_jsonl

ROOT_DIR = Path(__file__).resolve().parents[3]
LOG_DIR = ROOT_DIR / "manju_web" / "backend" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
USAGE_EVENTS_PATH = LOG_DIR / "asset_usage_events.jsonl"
USAGE_EVENTS_LOCK = threading.Lock()


def log_event(level: str, message: str, **fields: Any) -> None:
    """输出结构化日志事件，统一包含 trace_id 等关键字段。"""
    payload = {
        "time": time.strftime("%y%m%d %H:%M:%S"),
        "level": level,
        "message": message,
        "trace_id": fields.pop("trace_id", ""),
        **fields,
    }
    try:
        print(json.dumps(payload, ensure_ascii=False))
    except (IOError, OSError, ValueError):
        pass


def _build_usage_event(job: Dict[str, Any], status: str, created_at: float) -> Optional[Dict[str, Any]]:
    job_type = str(job.get("type") or "")
    mapping = {
        "run_visual_audio_assets": ("image", "visual_audio_assets"),
        "run_fenjing": ("image", "fenjing_batch"),
        "run_fenjing_generate": ("image", "fenjing"),  # 统一映射到 fenjing
        "run_fenjing_upload": ("image", "fenjing"),    # 统一映射到 fenjing
        "run_video": ("video", "video_batch"),
        "regenerate_character": ("image", "character"),
        "regenerate_location_image": ("image", "location"),
        "regenerate_cloth": ("image", "cloth"),
        "regenerate_cloth_changed": ("image", "cloth_changed"),
        "regenerate_fenjing": ("image", "fenjing"),
        "regenerate_video": ("video", "video"),
    }
    if job_type not in mapping:
        return None
    asset_type, entry = mapping[job_type]
    return {
        "event_id": f"{job.get('id','')}_{status}_{int(created_at * 1000)}",
        "project": str(job.get("project") or ""),
        "job_id": str(job.get("id") or ""),
        "job_type": job_type,
        "asset_type": asset_type,
        "entry": entry,
        "status": status,
        "created_at": created_at,
    }


def append_usage_event(event: Dict[str, Any]) -> None:
    if not event:
        return
    USAGE_EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(event, ensure_ascii=False)
    try:
        with USAGE_EVENTS_LOCK:
            with USAGE_EVENTS_PATH.open("a", encoding="utf-8") as f:
                f.write(payload + "\n")
    except Exception as exc:
        log_event("ERROR", "usage_event_append_failed", error=str(exc))


def list_usage_events(
    project: Optional[str] = None,
    status: Optional[str] = None,
    asset_type: Optional[str] = None,
    entry: Optional[str] = None,
    job_type: Optional[str] = None,
    job_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    if not USAGE_EVENTS_PATH.exists():
        return []
    items = safe_read_jsonl(USAGE_EVENTS_PATH)
    if project:
        items = [item for item in items if item.get("project") == project]
    if status:
        items = [item for item in items if item.get("status") == status]
    if asset_type:
        items = [item for item in items if item.get("asset_type") == asset_type]
    if entry:
        items = [item for item in items if item.get("entry") == entry]
    if job_type:
        items = [item for item in items if item.get("job_type") == job_type]
    if job_id:
        items = [item for item in items if item.get("job_id") == job_id]
    return items


def aggregate_usage_events(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "total": 0,
        "by_status": {},
        "by_asset_type": {},
        "by_asset_type_status": {},
        "by_entry": {},
        "by_entry_status": {},
        "by_project": {},
        "by_project_status": {},
        "by_job_type": {},
        "by_job_type_status": {},
    }
    for item in items:
        summary["total"] += 1
        status = str(item.get("status") or "unknown")
        asset_type = str(item.get("asset_type") or "unknown")
        entry = str(item.get("entry") or "unknown")
        project = str(item.get("project") or "unknown")
        job_type = str(item.get("job_type") or "unknown")
        summary["by_status"][status] = summary["by_status"].get(status, 0) + 1
        summary["by_asset_type"][asset_type] = summary["by_asset_type"].get(asset_type, 0) + 1
        summary["by_entry"][entry] = summary["by_entry"].get(entry, 0) + 1
        summary["by_project"][project] = summary["by_project"].get(project, 0) + 1
        summary["by_job_type"][job_type] = summary["by_job_type"].get(job_type, 0) + 1
        summary["by_asset_type_status"].setdefault(asset_type, {})
        summary["by_asset_type_status"][asset_type][status] = summary["by_asset_type_status"][asset_type].get(status, 0) + 1
        summary["by_entry_status"].setdefault(entry, {})
        summary["by_entry_status"][entry][status] = summary["by_entry_status"][entry].get(status, 0) + 1
        summary["by_project_status"].setdefault(project, {})
        summary["by_project_status"][project][status] = summary["by_project_status"][project].get(status, 0) + 1
        summary["by_job_type_status"].setdefault(job_type, {})
        summary["by_job_type_status"][job_type][status] = summary["by_job_type_status"][job_type].get(status, 0) + 1
    return summary


def jobs_index_path(project: str) -> Path:
    """返回项目作业索引文件路径（用于作业状态落盘与恢复）。"""
    return project_base_dir(project) / "jobs.jsonl"


def resolve_log_path(log_path: str) -> Path:
    """将日志路径规范化为绝对路径，兼容相对路径（相对 ROOT_DIR）。"""
    path = Path(log_path)
    if path.is_absolute():
        return path
    return ROOT_DIR / path


def build_log_path(job_id: str, created_at: Optional[float] = None) -> str:
    """构造作业日志路径，优先返回相对 ROOT_DIR 的相对路径便于序列化。"""
    timestamp = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime(created_at or time.time()))
    path = LOG_DIR / f"{timestamp}_{job_id}.log"
    try:
        return str(path.relative_to(ROOT_DIR))
    except ValueError:
        return str(path)


def build_log_display_name(job_id: str, created_at: Optional[float]) -> str:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(created_at or time.time()))
    return f"{timestamp} {job_id}.log"


def load_jobs_from_disk(project: str) -> List[Dict[str, Any]]:
    """从磁盘加载项目作业索引，文件不存在时返回空列表。"""
    path = jobs_index_path(project)
    if not path.exists():
        return []
    return safe_read_jsonl(path)


def write_jobs_to_disk(project: str, jobs: List[Dict[str, Any]]) -> None:
    """将项目作业索引写入磁盘，失败时记录错误日志。"""
    path = jobs_index_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        write_jsonl(str(path), jobs)
    except Exception as exc:
        log_event("ERROR", "job_persist_failed", project=project, error=str(exc))


def reconcile_stale_jobs_on_startup() -> int:
    now = time.time()
    updated_count = 0
    for project in list_projects():
        jobs = load_jobs_from_disk(project)
        if not jobs:
            continue
        changed = False
        for job in jobs:
            if job.get("status") != "running":
                continue
            job["status"] = "error"
            job["updated_at"] = now
            if job.get("exit_code") is None:
                job["exit_code"] = -1
            if not job.get("error"):
                job["error"] = "服务重启后任务未完成"
            changed = True
            updated_count += 1
        if changed:
            write_jobs_to_disk(project, jobs)
    if updated_count:
        log_event("WARN", "job_reconcile_stale_running", count=updated_count)
    return updated_count


def persist_job_snapshot(job: Dict[str, Any]) -> None:
    """将单个作业快照合并进项目作业索引并落盘，支持更新与新增。"""
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
    """在所有项目的落盘索引中查找指定 job_id，用于进程重启后的恢复查询。"""
    for project in list_projects():
        jobs = load_jobs_from_disk(project)
        for job in jobs:
            if job.get("id") == job_id:
                return job
    return None


def start_job(job_type: str, project: str, runner: callable, payload: Dict[str, Any]) -> Dict[str, Any]:
    """创建作业并在后台线程执行 runner，同时写入初始快照到磁盘。"""
    job_id = uuid.uuid4().hex
    trace_id = uuid.uuid4().hex
    created_at = time.time()
    job = {
        "id": job_id,
        "type": job_type,
        "project": project,
        "status": "running",
        "created_at": created_at,
        "updated_at": created_at,
        "payload": payload,
        "trace_id": trace_id,
        "log_path": build_log_path(job_id, created_at),
        "exit_code": None,
        "error": None,
        "partial_failed": False,
        "partial_failed_count": 0,
        "partial_failed_types": [],
    }
    persist_job_snapshot(job)
    usage_event = _build_usage_event(job, "running", created_at)
    if usage_event:
        append_usage_event(usage_event)
    thread = threading.Thread(target=runner, args=(job_id,), daemon=True)
    thread.start()
    return job


def update_job(job_id: str, **updates: Any) -> None:
    """更新作业状态并同步落盘，保证刷新 updated_at 用于列表排序。"""
    job = find_job_on_disk(job_id)
    if not job:
        return
    prev_status = job.get("status")
    job.update(updates)
    job["updated_at"] = time.time()
    persist_job_snapshot(job)
    new_status = updates.get("status")
    if isinstance(new_status, str) and new_status != prev_status:
        usage_event = _build_usage_event(job, new_status, job.get("updated_at", time.time()))
        if usage_event:
            append_usage_event(usage_event)


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """从磁盘读取作业状态。"""
    return find_job_on_disk(job_id)


def list_jobs_for_project(project: str) -> List[Dict[str, Any]]:
    """列出项目作业：从磁盘索引读取，并附带日志尾部用于快速展示。"""
    jobs = load_jobs_from_disk(project)
    jobs.sort(key=lambda item: item.get("updated_at", 0), reverse=True)
    result = []
    for job in jobs:
        log_lines = tail_log(resolve_log_path(str(job["log_path"])))
        result.append(
            {
                **job,
                "log_tail": log_lines,
                "log_display_name": build_log_display_name(str(job.get("id", "")), job.get("created_at")),
                "log_created_at": job.get("created_at"),
            }
        )
    return result
