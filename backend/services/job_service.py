from typing import Any, Dict, List, Optional

from ..repositories import asset_repo, job_repo, log_repo


def start_job(job_type: str, project: str, runner: callable, payload: Dict[str, Any]) -> Dict[str, Any]:
    return job_repo.start_job(job_type, project, runner, payload)


def update_job(job_id: str, **updates: Any) -> None:
    job_repo.update_job(job_id, **updates)


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    job = job_repo.get_job(job_id)
    if job:
        return job
    return job_repo.find_job_on_disk(job_id)


def list_jobs(project: str) -> List[Dict[str, Any]]:
    return job_repo.list_jobs_for_project(project)


def get_job_with_log(job_id: str) -> Optional[Dict[str, Any]]:
    job = get_job(job_id)
    if not job:
        return None
    log_path = job.get("log_path")
    if isinstance(log_path, str) and log_path:
        log_lines = log_repo.tail_log(job_repo.resolve_log_path(log_path))
        return {
            **job,
            "log_tail": log_lines,
            "log_display_name": job_repo.build_log_display_name(str(job.get("id", "")), job.get("created_at")),
            "log_created_at": job.get("created_at"),
        }
    return job


def get_job_log_page(job_id: str, offset: Optional[int], limit: int) -> Optional[Dict[str, Any]]:
    job = get_job(job_id)
    if not job:
        return None
    log_path = job.get("log_path")
    if not isinstance(log_path, str) or not log_path:
        return {
            "lines": [],
            "offset": 0,
            "next_offset": 0,
            "prev_offset": 0,
            "total": 0,
            "has_more": False,
            "log_display_name": job_repo.build_log_display_name(str(job.get("id", "")), job.get("created_at")),
            "log_created_at": job.get("created_at"),
        }
    page = log_repo.read_log_page(job_repo.resolve_log_path(log_path), offset, limit)
    return {
        **page,
        "log_display_name": job_repo.build_log_display_name(str(job.get("id", "")), job.get("created_at")),
        "log_created_at": job.get("created_at"),
    }


def get_job_asset_results(job_id: str) -> Optional[Dict[str, Any]]:
    job = get_job(job_id)
    if not job:
        return None
    project = str(job.get("project") or "")
    if not project:
        return None
    flow = _resolve_flow_from_job(job.get("type"))
    items = asset_repo.list_asset_results(project, job_id=job_id)
    return {
        "job_id": job_id,
        "project": project,
        "flow": flow,
        "items": items,
    }


def get_job_partial_failures(job_id: str) -> Optional[Dict[str, Any]]:
    job = get_job(job_id)
    if not job:
        return None
    project = str(job.get("project") or "")
    if not project:
        return None
    flow = _resolve_flow_from_job(job.get("type"))
    items = asset_repo.list_asset_results(project, job_id=job_id, status="failed")
    if not items:
        items = asset_repo.build_partial_failures_from_qc(job_id, project)
    summary = asset_repo.aggregate_partial_failures(items)
    return {
        "job_id": job_id,
        "project": project,
        "flow": flow,
        "items": items,
        "counts": summary.get("counts") or {},
        "total": summary.get("partial_failed_count", 0),
    }


def _resolve_flow_from_job(job_type: Optional[str]) -> str:
    mapping = {
        "run_visual_audio_assets": "visual_audio_assets",
        "run_fenjing": "fenjing",
        "run_video": "video",
    }
    return mapping.get(str(job_type or ""), "")
