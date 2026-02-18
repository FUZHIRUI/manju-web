from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from typing import Dict
from urllib.parse import parse_qs, urlsplit

from ..services.workflow_runtime import runtime_config

from .http_utils import send_json
from ..repositories import asset_repo, job_repo, project_repo
from ..services import project_service, status_service
from ..services.asset_stats_service import calculate_asset_stats, format_stats_for_api


def handle_get(handler: BaseHTTPRequestHandler, path: str) -> bool:
    if path == "/api/projects":
        send_json(handler, HTTPStatus.OK, {"projects": project_service.list_projects(), "default_project": runtime_config.PROJECT_NAME})
        return True
    parsed = urlsplit(path)
    clean_path = parsed.path
    if clean_path == "/api/asset-usage":
        query = parse_qs(parsed.query)
        project = str(query.get("project", [""])[0]).strip() or None
        status = str(query.get("status", [""])[0]).strip() or None
        asset_type = str(query.get("asset_type", [""])[0]).strip() or None
        entry = str(query.get("entry", [""])[0]).strip() or None
        job_type = str(query.get("job_type", [""])[0]).strip() or None
        job_id = str(query.get("job_id", [""])[0]).strip() or None
        items = job_repo.list_usage_events(
            project=project,
            status=status,
            asset_type=asset_type,
            entry=entry,
            job_type=job_type,
            job_id=job_id,
        )
        summary = job_repo.aggregate_usage_events(items)
        send_json(handler, HTTPStatus.OK, {"filters": {
            "project": project,
            "status": status,
            "asset_type": asset_type,
            "entry": entry,
            "job_type": job_type,
            "job_id": job_id,
        }, "summary": summary, "total": summary.get("total", 0)})
        return True
    if clean_path.startswith("/api/projects/") and clean_path.endswith("/flow-status"):
        parts = clean_path.split("/")
        project = project_repo.safe_project_name(parts[3]) if len(parts) >= 4 else None
        if not project:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_project"})
            return True
        send_json(handler, HTTPStatus.OK, status_service.get_flow_state(project))
        return True
    if clean_path.startswith("/api/projects/") and clean_path.endswith("/assets"):
        parts = clean_path.split("/")
        project = project_repo.safe_project_name(parts[3]) if len(parts) >= 4 else None
        if not project:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_project"})
            return True
        send_json(handler, HTTPStatus.OK, project_service.list_project_assets(project))
        return True
    if clean_path.startswith("/api/projects/") and clean_path.endswith("/partial-failures"):
        parts = clean_path.split("/")
        project = project_repo.safe_project_name(parts[3]) if len(parts) >= 4 else None
        if not project:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_project"})
            return True
        query = parse_qs(parsed.query)
        flow = str(query.get("flow", [""])[0]).strip()
        items = asset_repo.list_asset_results(project, flow=flow or None, status="failed")
        summary = asset_repo.aggregate_partial_failures(items)
        send_json(
            handler,
            HTTPStatus.OK,
            {
                "project": project,
                "flow": flow,
                "items": items,
                "counts": summary.get("counts") or {},
                "total": summary.get("partial_failed_count", 0),
            },
        )
        return True
    if clean_path.startswith("/api/projects/") and clean_path.endswith("/asset-stats"):
        parts = clean_path.split("/")
        project = project_repo.safe_project_name(parts[3]) if len(parts) >= 4 else None
        if not project:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_project"})
            return True
        assets_data = project_service.list_project_assets(project)
        results_data = asset_repo.read_asset_results(project)
        stats_result = calculate_asset_stats(assets_data, results_data)
        send_json(handler, HTTPStatus.OK, {"project": project, **format_stats_for_api(stats_result)})
        return True
    if clean_path.startswith("/api/projects/") and clean_path.endswith("/jobs"):
        parts = clean_path.split("/")
        project = project_repo.safe_project_name(parts[3]) if len(parts) >= 4 else None
        if not project:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_project"})
            return True
        query = parse_qs(parsed.query)
        job_type = str(query.get("type", [""])[0]).strip() or None
        jobs = job_repo.list_jobs_for_project(project)
        if job_type:
            jobs = [j for j in jobs if j.get("type") == job_type]
        job_summaries = []
        for job in jobs:
            job_id = str(job.get("id") or "")
            agg = asset_repo.aggregate_results_by_job(project, job_id) if job_id else None
            job_summaries.append({
                "id": job_id,
                "type": job.get("type"),
                "status": job.get("status"),
                "created_at": job.get("created_at"),
                "updated_at": job.get("updated_at"),
                "log_display_name": job.get("log_display_name"),
                "asset_stats": agg,
            })
        send_json(handler, HTTPStatus.OK, {"project": project, "jobs": job_summaries})
        return True
    if clean_path.startswith("/api/projects/") and "/jobs/" in clean_path:
        parts = clean_path.split("/")
        project = project_repo.safe_project_name(parts[3]) if len(parts) >= 5 else None
        job_id = parts[5] if len(parts) >= 6 else ""
        if not project or not job_id:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
            return True
        jobs = job_repo.list_jobs_for_project(project)
        job = next((j for j in jobs if j.get("id") == job_id), None)
        if not job:
            send_json(handler, HTTPStatus.NOT_FOUND, {"error": "job_not_found"})
            return True
        results = asset_repo.list_asset_results(project, job_id=job_id)
        agg = asset_repo.aggregate_results_by_job(project, job_id)
        send_json(handler, HTTPStatus.OK, {
            "project": project,
            "job": {
                "id": job.get("id"),
                "type": job.get("type"),
                "status": job.get("status"),
                "created_at": job.get("created_at"),
                "updated_at": job.get("updated_at"),
                "log_display_name": job.get("log_display_name"),
                "log_tail": job.get("log_tail"),
            },
            "asset_stats": agg,
            "results": results,
        })
        return True
    if clean_path.startswith("/api/projects/") and clean_path.endswith("/asset-results"):
        parts = clean_path.split("/")
        project = project_repo.safe_project_name(parts[3]) if len(parts) >= 4 else None
        if not project:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_project"})
            return True
        query = parse_qs(parsed.query)
        job_id = str(query.get("job_id", [""])[0]).strip() or None
        asset_type = str(query.get("asset_type", [""])[0]).strip() or None
        status_filter = str(query.get("status", [""])[0]).strip() or None
        chapter_id = str(query.get("chapter_id", [""])[0]).strip() or None
        results = asset_repo.list_asset_results(project, job_id=job_id, status=status_filter)
        if asset_type:
            results = [r for r in results if r.get("asset_type") == asset_type]
        if chapter_id:
            results = [r for r in results if r.get("chapter_id") == chapter_id]
        send_json(handler, HTTPStatus.OK, {"project": project, "results": results, "total": len(results)})
        return True
    return False


def handle_post(handler: BaseHTTPRequestHandler, path: str, body: Dict[str, object]) -> bool:
    if path.startswith("/api/projects/") and "/clean/" in path:
        parts = path.split("/")
        project = project_repo.safe_project_name(parts[3]) if len(parts) >= 6 else None
        flow = parts[5] if len(parts) >= 6 else ""
        if not project or flow not in {"auto_storyboard", "visual_audio_assets", "fenjing", "fenjing_generate", "fenjing_upload", "video"}:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
            return True
        result = project_service.clean_stage_assets(project, flow)
        if not result.get("ok"):
            status = HTTPStatus.BAD_REQUEST if result.get("error") else HTTPStatus.INTERNAL_SERVER_ERROR
            send_json(handler, status, result)
            return True
        send_json(handler, HTTPStatus.OK, result)
        return True
    if path.startswith("/api/projects/") and "/chapters/" in path and "/fenjing/" in path and path.endswith("/prompt"):
        parts = path.split("/")
        project = project_repo.safe_project_name(parts[3]) if len(parts) >= 9 else None
        chapter_name = parts[5] if len(parts) >= 9 else ""
        fenjing_id = parts[7] if len(parts) >= 9 else ""
        prompt_text = str(body.get("prompt_text", "")).strip()
        if not project or not chapter_name or not fenjing_id or not prompt_text:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
            return True
        result = project_service.update_fenjing_prompt(project, chapter_name, fenjing_id, prompt_text)
        if not result.get("ok"):
            job_repo.log_event(
                "ERROR",
                "fenjing_prompt_update_error",
                trace_id="",
                project=project,
                chapter=chapter_name,
                fenjing_id=fenjing_id,
                error=str(result.get("error", "update_failed")),
            )
            send_json(handler, HTTPStatus.BAD_REQUEST, result)
            return True
        job_repo.log_event(
            "INFO",
            "fenjing_prompt_update",
            trace_id="",
            project=project,
            chapter=chapter_name,
            fenjing_id=fenjing_id,
            prompt_length=len(prompt_text),
        )
        send_json(handler, HTTPStatus.OK, {"ok": True})
        return True
    if path.startswith("/api/projects/") and "/chapters/" in path and "/video/" in path and path.endswith("/prompt"):
        parts = path.split("/")
        project = project_repo.safe_project_name(parts[3]) if len(parts) >= 9 else None
        chapter_name = parts[5] if len(parts) >= 9 else ""
        fenjing_id = parts[7] if len(parts) >= 9 else ""
        prompt_text = str(body.get("prompt_text", "")).strip()
        if not project or not chapter_name or not fenjing_id or not prompt_text:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
            return True
        result = project_service.update_video_prompt(project, chapter_name, fenjing_id, prompt_text)
        if not result.get("ok"):
            job_repo.log_event(
                "ERROR",
                "video_prompt_update_error",
                trace_id="",
                project=project,
                chapter=chapter_name,
                fenjing_id=fenjing_id,
                error=str(result.get("error", "update_failed")),
            )
            send_json(handler, HTTPStatus.BAD_REQUEST, result)
            return True
        job_repo.log_event(
            "INFO",
            "video_prompt_update",
            trace_id="",
            project=project,
            chapter=chapter_name,
            fenjing_id=fenjing_id,
            prompt_length=len(prompt_text),
        )
        send_json(handler, HTTPStatus.OK, {"ok": True})
        return True
    if path.startswith("/api/projects/") and "/characters/" in path and path.endswith("/prompt"):
        parts = path.split("/")
        project = project_repo.safe_project_name(parts[3]) if len(parts) >= 7 else None
        character_id = parts[5] if len(parts) >= 7 else ""
        prompt_text = str(body.get("prompt_text", "")).strip()
        if not project or not character_id or not prompt_text:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
            return True
        result = project_service.update_character_prompt(project, character_id, prompt_text)
        if not result.get("ok"):
            send_json(handler, HTTPStatus.BAD_REQUEST, result)
            return True
        send_json(handler, HTTPStatus.OK, {"ok": True})
        return True
    if path.startswith("/api/projects/") and "/cloth-changed/" in path and path.endswith("/prompt"):
        parts = path.split("/")
        project = project_repo.safe_project_name(parts[3]) if len(parts) >= 8 else None
        character_id = parts[5] if len(parts) >= 8 else ""
        outfit_id = parts[6] if len(parts) >= 8 else ""
        prompt_text = str(body.get("prompt_text", "")).strip()
        if not project or not character_id or not outfit_id or not prompt_text:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
            return True
        result = project_service.update_cloth_changed_prompt(project, character_id, outfit_id, prompt_text)
        if not result.get("ok"):
            send_json(handler, HTTPStatus.BAD_REQUEST, result)
            return True
        send_json(handler, HTTPStatus.OK, {"ok": True})
        return True
    if path.startswith("/api/projects/") and "/chapters/" in path and "/fenjing/" in path and path.endswith("/publish"):
        parts = path.split("/")
        project = project_repo.safe_project_name(parts[3]) if len(parts) >= 9 else None
        chapter_name = parts[5] if len(parts) >= 9 else ""
        fenjing_id = parts[7] if len(parts) >= 9 else ""
        candidate_rel = str(body.get("candidate_path", "")).strip()
        if not project or not chapter_name or not fenjing_id or not candidate_rel:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
            return True
        result = project_service.publish_fenjing_candidate(project, chapter_name, fenjing_id, candidate_rel)
        if not result.get("ok"):
            job_repo.log_event(
                "ERROR",
                "fenjing_candidate_publish_error",
                trace_id="",
                project=project,
                chapter=chapter_name,
                fenjing_id=fenjing_id,
                candidate_path=candidate_rel,
                error=str(result.get("error", "publish_failed")),
            )
            send_json(handler, HTTPStatus.BAD_REQUEST, result)
            return True
        job_repo.log_event(
            "INFO",
            "fenjing_candidate_publish",
            trace_id="",
            project=project,
            chapter=chapter_name,
            fenjing_id=fenjing_id,
            candidate_path=candidate_rel,
            published_path=str(result.get("path", "")),
            uri=str(result.get("uri", "")),
        )
        send_json(handler, HTTPStatus.OK, result)
        return True
    if path.startswith("/api/projects/") and "/chapters/" in path and "/video/" in path and path.endswith("/publish"):
        parts = path.split("/")
        project = project_repo.safe_project_name(parts[3]) if len(parts) >= 9 else None
        chapter_name = parts[5] if len(parts) >= 9 else ""
        fenjing_id = parts[7] if len(parts) >= 9 else ""
        candidate_rel = str(body.get("candidate_path", "")).strip()
        if not project or not chapter_name or not fenjing_id or not candidate_rel:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
            return True
        result = project_service.publish_video_candidate(project, chapter_name, candidate_rel)
        if not result.get("ok"):
            job_repo.log_event(
                "ERROR",
                "video_candidate_publish_error",
                trace_id="",
                project=project,
                chapter=chapter_name,
                fenjing_id=fenjing_id,
                candidate_path=candidate_rel,
                error=str(result.get("error", "publish_failed")),
            )
            send_json(handler, HTTPStatus.BAD_REQUEST, result)
            return True
        job_repo.log_event(
            "INFO",
            "video_candidate_publish",
            trace_id="",
            project=project,
            chapter=chapter_name,
            fenjing_id=fenjing_id,
            candidate_path=candidate_rel,
            published_path=str(result.get("path", "")),
            uri=str(result.get("uri", "")),
        )
        send_json(handler, HTTPStatus.OK, result)
        return True
    if path.startswith("/api/projects/") and "/cloth-changed/" in path and path.endswith("/publish"):
        parts = path.split("/")
        project = project_repo.safe_project_name(parts[3]) if len(parts) >= 8 else None
        character_id = parts[5] if len(parts) >= 8 else ""
        outfit_id = parts[6] if len(parts) >= 8 else ""
        candidate_rel = str(body.get("candidate_path", "")).strip()
        if not project or not character_id or not outfit_id or not candidate_rel:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
            return True
        result = project_service.publish_cloth_changed_candidate(project, character_id, outfit_id, candidate_rel)
        if not result.get("ok"):
            send_json(handler, HTTPStatus.BAD_REQUEST, result)
            return True
        send_json(handler, HTTPStatus.OK, result)
        return True
    if path.startswith("/api/projects/") and "/chapters/" in path and "/fenjing/" in path and path.endswith("/candidate/delete"):
        parts = path.split("/")
        project = project_repo.safe_project_name(parts[3]) if len(parts) >= 9 else None
        chapter_name = parts[5] if len(parts) >= 9 else ""
        fenjing_id = parts[7] if len(parts) >= 9 else ""
        candidate_rel = str(body.get("candidate_path", "")).strip()
        if not project or not chapter_name or not fenjing_id or not candidate_rel:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
            return True
        result = project_service.delete_candidate_file(project, candidate_rel, "fenjing_candidates")
        if not result.get("ok"):
            job_repo.log_event(
                "ERROR",
                "fenjing_candidate_delete_error",
                trace_id="",
                project=project,
                chapter=chapter_name,
                fenjing_id=fenjing_id,
                candidate_path=candidate_rel,
                error=str(result.get("error", "delete_failed")),
            )
            send_json(handler, HTTPStatus.BAD_REQUEST, result)
            return True
        job_repo.log_event(
            "INFO",
            "fenjing_candidate_delete",
            trace_id="",
            project=project,
            chapter=chapter_name,
            fenjing_id=fenjing_id,
            candidate_path=candidate_rel,
        )
        send_json(handler, HTTPStatus.OK, result)
        return True
    if path.startswith("/api/projects/") and "/chapters/" in path and "/video/" in path and path.endswith("/candidate/delete"):
        parts = path.split("/")
        project = project_repo.safe_project_name(parts[3]) if len(parts) >= 9 else None
        chapter_name = parts[5] if len(parts) >= 9 else ""
        fenjing_id = parts[7] if len(parts) >= 9 else ""
        candidate_rel = str(body.get("candidate_path", "")).strip()
        if not project or not chapter_name or not fenjing_id or not candidate_rel:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
            return True
        result = project_service.delete_video_candidate(project, candidate_rel)
        if not result.get("ok"):
            job_repo.log_event(
                "ERROR",
                "video_candidate_delete_error",
                trace_id="",
                project=project,
                chapter=chapter_name,
                fenjing_id=fenjing_id,
                candidate_path=candidate_rel,
                error=str(result.get("error", "delete_failed")),
            )
            send_json(handler, HTTPStatus.BAD_REQUEST, result)
            return True
        job_repo.log_event(
            "INFO",
            "video_candidate_delete",
            trace_id="",
            project=project,
            chapter=chapter_name,
            fenjing_id=fenjing_id,
            candidate_path=candidate_rel,
        )
        send_json(handler, HTTPStatus.OK, result)
        return True
    if path.startswith("/api/projects/") and "/cloth-changed/" in path and path.endswith("/candidate/delete"):
        parts = path.split("/")
        project = project_repo.safe_project_name(parts[3]) if len(parts) >= 8 else None
        character_id = parts[5] if len(parts) >= 8 else ""
        outfit_id = parts[6] if len(parts) >= 8 else ""
        candidate_rel = str(body.get("candidate_path", "")).strip()
        if not project or not character_id or not outfit_id or not candidate_rel:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
            return True
        result = project_service.delete_candidate_file(project, candidate_rel, "cloth_changed_candidates")
        if not result.get("ok"):
            send_json(handler, HTTPStatus.BAD_REQUEST, result)
            return True
        send_json(handler, HTTPStatus.OK, result)
        return True
    if path.startswith("/api/projects/") and "/characters/" in path and path.endswith("/publish"):
        parts = path.split("/")
        project = project_repo.safe_project_name(parts[3]) if len(parts) >= 7 else None
        character_id = parts[5] if len(parts) >= 7 else ""
        candidate_rel = str(body.get("candidate_path", "")).strip()
        if not project or not character_id or not candidate_rel:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
            return True
        result = project_service.publish_character_candidate(project, character_id, candidate_rel)
        if not result.get("ok"):
            send_json(handler, HTTPStatus.BAD_REQUEST, result)
            return True
        send_json(handler, HTTPStatus.OK, result)
        return True
    if path.startswith("/api/projects/") and "/characters/" in path and path.endswith("/candidate/delete"):
        parts = path.split("/")
        project = project_repo.safe_project_name(parts[3]) if len(parts) >= 7 else None
        character_id = parts[5] if len(parts) >= 7 else ""
        candidate_rel = str(body.get("candidate_path", "")).strip()
        if not project or not character_id or not candidate_rel:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
            return True
        result = project_service.delete_candidate_file(project, candidate_rel, "character_candidates")
        if not result.get("ok"):
            send_json(handler, HTTPStatus.BAD_REQUEST, result)
            return True
        send_json(handler, HTTPStatus.OK, result)
        return True
    if path == "/api/projects":
        project = project_repo.safe_project_name(str(body.get("project_name", "")))
        if not project:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_project"})
            return True
        dirs = project_service.ensure_project(project)
        send_json(handler, HTTPStatus.OK, {"project": project, "dirs": dirs})
        return True
    if path.startswith("/api/projects/") and path.endswith("/novel"):
        parts = path.split("/")
        project = project_repo.safe_project_name(parts[3]) if len(parts) >= 4 else None
        if not project:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_project"})
            return True
        text = body.get("novel_text", "")
        novel_path = body.get("novel_path", "")
        if isinstance(text, str) and text.strip():
            result = project_service.save_novel(project, text, None)
            send_json(handler, HTTPStatus.OK, {"project": project, "novel_path": result.get("path", "")})
            return True
        if isinstance(novel_path, str) and str(novel_path).strip():
            send_json(handler, HTTPStatus.OK, {"project": project, "novel_path": novel_path})
            return True
        send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "novel_missing"})
        return True
    if path.startswith("/api/projects/") and "/flow/" in path and path.endswith("/pending"):
        parts = path.split("/")
        project = project_repo.safe_project_name(parts[3]) if len(parts) >= 6 else None
        flow = parts[5] if len(parts) >= 6 else ""
        if not project or flow not in {"auto_storyboard", "visual_audio_assets", "fenjing", "fenjing_generate", "fenjing_upload", "video"}:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
            return True
        status_service.create_pending_state(project, flow)
        send_json(handler, HTTPStatus.OK, {"project": project, "flow": flow, "status": "pending"})
        return True
    if path.startswith("/api/projects/") and "/flow/" in path and path.endswith("/pending/clear"):
        parts = path.split("/")
        project = project_repo.safe_project_name(parts[3]) if len(parts) >= 6 else None
        flow = parts[5] if len(parts) >= 6 else ""
        if not project or flow not in {"auto_storyboard", "visual_audio_assets", "fenjing", "fenjing_generate", "fenjing_upload", "video"}:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
            return True
        status_service.clear_pending_state(project, flow)
        send_json(handler, HTTPStatus.OK, {"project": project, "flow": flow, "status": "cleared"})
        return True
    return False
