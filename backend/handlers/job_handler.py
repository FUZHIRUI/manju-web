from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
import os
from threading import Timer
from typing import Dict, Optional
from urllib.parse import parse_qs, urlsplit

from .http_utils import send_json
from ..repositories import project_repo
from ..services import job_service, status_service, workflow_service


def handle_get(handler: BaseHTTPRequestHandler, path: str) -> bool:
    """处理任务查询相关的 GET 请求。"""
    parsed = urlsplit(path)
    clean_path = parsed.path
    if clean_path.startswith("/api/projects/") and clean_path.endswith("/jobs"):
        parts = clean_path.split("/")
        # 解析并校验项目名，避免非法路径访问
        project = project_repo.safe_project_name(parts[3]) if len(parts) >= 5 else None
        if not project:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_project"})
            return True
        # 返回项目下的任务列表
        send_json(handler, HTTPStatus.OK, {"jobs": job_service.list_jobs(project)})
        return True
    if clean_path.startswith("/api/jobs/") and clean_path.endswith("/logs"):
        parts = clean_path.split("/")
        job_id = parts[-2] if len(parts) >= 4 else ""
        if not job_id:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_job"})
            return True
        query = parse_qs(parsed.query)
        offset = _parse_non_negative_int(query.get("offset", [None])[0])
        limit = _parse_non_negative_int(query.get("limit", [None])[0]) or 200
        page = job_service.get_job_log_page(job_id, offset, limit)
        if not page:
            send_json(handler, HTTPStatus.NOT_FOUND, {"error": "job_not_found"})
            return True
        send_json(handler, HTTPStatus.OK, page)
        return True
    if clean_path.startswith("/api/jobs/") and clean_path.endswith("/partial-failures"):
        parts = clean_path.split("/")
        job_id = parts[-2] if len(parts) >= 4 else ""
        if not job_id:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_job"})
            return True
        result = job_service.get_job_partial_failures(job_id)
        if not result:
            send_json(handler, HTTPStatus.NOT_FOUND, {"error": "job_not_found"})
            return True
        send_json(handler, HTTPStatus.OK, result)
        return True
    if clean_path.startswith("/api/jobs/") and clean_path.endswith("/asset-results"):
        parts = clean_path.split("/")
        job_id = parts[-2] if len(parts) >= 4 else ""
        if not job_id:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_job"})
            return True
        result = job_service.get_job_asset_results(job_id)
        if not result:
            send_json(handler, HTTPStatus.NOT_FOUND, {"error": "job_not_found"})
            return True
        send_json(handler, HTTPStatus.OK, result)
        return True
    if clean_path.startswith("/api/jobs/"):
        # 查询单个任务及其日志
        job_id = clean_path.split("/")[-1]
        job = job_service.get_job_with_log(job_id)
        if not job:
            send_json(handler, HTTPStatus.NOT_FOUND, {"error": "job_not_found"})
            return True
        send_json(handler, HTTPStatus.OK, job)
        return True
    return False


def _parse_int(value: object) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except Exception:
        return None
    return parsed if parsed > 0 else None


def _parse_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value == 1
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return False


def _parse_non_negative_int(value: object) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except Exception:
        return None
    return parsed if parsed >= 0 else None


def _resolve_flow_steps(workflow: str, phase: Optional[str]) -> list:
    if workflow == "auto_storyboard":
        token = str(phase or "").strip().lower()
        if token in ["step2", "phase2", "step_storyboard"]:
            return ["step_storyboard"]
        elif token in ["step1", "phase1", "step_extract"]:
            return ["step_extract"]
        elif token in ["step3_upload", "upload", "step_upload"]:
            return ["step_upload"]
        return ["step_extract"]
    if workflow == "visual_audio_assets":
        return status_service.resolve_visual_audio_steps(str(phase or "all"))
    if workflow == "fenjing":
        return ["step_download"]
    if workflow == "fenjing_generate":
        return ["step_download"]
    if workflow == "fenjing_upload":
        return ["step_upload"]
    if workflow == "video":
        token = str(phase or "").strip().lower()
        if token == "prepare_prompts":
            return ["step_prepare", "step_video_prompts"]
        elif token == "generate_videos":
            return ["step_video_generation"]
        elif token == "upload_videos":
            return ["step_video_upload"]
        else:
            return ["step_prepare", "step_video_prompts", "step_video_generation", "step_video_upload"]
    return []


def _schedule_job_timeout(job_id: str, project: str, flow: str, steps: list) -> None:
    try:
        timeout_sec = int(os.environ.get("FLOW_JOB_TIMEOUT_SEC", "1800"))
    except Exception:
        timeout_sec = 1800
    if timeout_sec <= 0:
        return

    def _on_timeout() -> None:
        job = job_service.get_job(job_id)
        if not job or job.get("status") != "running":
            return
        job_service.update_job(job_id, status="error", error="job_timeout")
        status_service.mark_flow_error(project, flow, steps)

    timer = Timer(timeout_sec, _on_timeout)
    timer.daemon = True
    timer.start()


def handle_post(handler: BaseHTTPRequestHandler, path: str, body: Dict[str, object]) -> bool:
    """处理任务创建与重新生成的 POST 请求。"""
    if path.startswith("/api/projects/") and "/run/" in path:
        parts = path.split("/")
        # 提取项目与 workflow 名称并做白名单校验
        project = project_repo.safe_project_name(parts[3]) if len(parts) >= 5 else None
        workflow = parts[5] if len(parts) >= 6 else ""
        if not project or workflow not in {"auto_storyboard", "visual_audio_assets", "fenjing", "fenjing_generate", "fenjing_upload", "video"}:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
            return True
        if workflow == "auto_storyboard":
            # 自动分镜支持传入小说路径，默认落到项目目录
            novel_path = body.get("novel_path") or str(project_repo.project_base_dir(project) / "novel.txt")
            raw_phase = body.get("phase")
            if raw_phase is None:
                send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "missing_phase"})
                return True
            phase = str(raw_phase).strip().lower()
            # 支持新的 step 命名和旧的 phase 命名
            if phase not in {"phase1", "phase2", "full", "step1", "step2", "step3_upload", "step_extract", "step_storyboard", "step_upload"}:
                send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_phase"})
                return True
            chapter_size = _parse_int(body.get("chapter_size"))
            target_chapters = _parse_int(body.get("target_chapters"))
            per_chapter_shots = _parse_int(body.get("per_chapter_shots"))
            previous_response_id = body.get("previous_response_id")
            if not isinstance(previous_response_id, str) or not previous_response_id.strip():
                previous_response_id = None
            phase1_force_regen = _parse_bool(body.get("phase1_force_regen"))
            job = job_service.start_job(
                "run_auto_storyboard",
                project,
                lambda job_id: workflow_service.run_auto_storyboard(
                    job_id,
                    project,
                    str(novel_path),
                    phase=phase,
                    chapter_size=chapter_size,
                    target_chapters=target_chapters,
                    per_chapter_shots=per_chapter_shots,
                    previous_response_id=previous_response_id,
                    phase1_force_regen=phase1_force_regen,
                ),
                {
                    "novel_path": str(novel_path),
                    "phase": phase,
                    "chapter_size": chapter_size,
                    "target_chapters": target_chapters,
                    "per_chapter_shots": per_chapter_shots,
                    "previous_response_id": previous_response_id,
                    "phase1_force_regen": phase1_force_regen,
                },
            )
        elif workflow == "visual_audio_assets":
            # 启动视觉与音频资产阶段
            phase = str(body.get("phase", "all")).strip().lower()
            phase_tokens = [p.strip().lower() for p in phase.split(",") if p.strip()]
            allowed_phases = {
                "all",
                "download_assets",
                "build_prompts",
                "generate_images",
                "generate_tts",
                "upload_assets",
                "character",
                "location",
                "location_prompts",
                "location_images",
                "fenjing",
                "fenjing_prompts",
                "tts",
                "cloth",
                "cloth_images",
                "cloth_changed",
                "cloth_changed_images",
            }
            if phase_tokens and any(p not in allowed_phases for p in phase_tokens):
                send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_phase"})
                return True
            job = job_service.start_job(
                "run_visual_audio_assets",
                project,
                lambda job_id: workflow_service.run_visual_audio_assets(job_id, project, phase=phase),
                {"phase": phase},
            )
        elif workflow == "fenjing":
            job = job_service.start_job(
                "run_fenjing",
                project,
                lambda job_id: workflow_service.run_fenjing(job_id, project),
                {},
            )
        elif workflow == "fenjing_generate":
            job = job_service.start_job(
                "run_fenjing_generate",
                project,
                lambda job_id: workflow_service.run_fenjing_generate(job_id, project),
                {},
            )
        elif workflow == "fenjing_upload":
            job = job_service.start_job(
                "run_fenjing_upload",
                project,
                lambda job_id: workflow_service.run_fenjing_upload(job_id, project),
                {},
            )
        else:
            # 启动视频生成阶段
            phase = str(body.get("phase", "all")).strip().lower()
            job = job_service.start_job(
                "run_video",
                project,
                lambda job_id, p=phase: workflow_service.run_video(job_id, project, phase=p),
                {"phase": phase},
            )
        phase_value = body.get("phase") if isinstance(body, dict) else None
        steps = _resolve_flow_steps(workflow, phase_value)
        reset_steps = True
        if workflow == "visual_audio_assets":
            token = str(phase_value or "").strip().lower()
            if token and token != "all":
                reset_steps = False
                status_service.reset_flow_steps(project, workflow, steps)
        elif workflow == "auto_storyboard":
            # 当只运行特定phase时，只重置当前phase的步骤，保留其他phase的状态
            token = str(phase_value or "").strip().lower()
            # 支持新的 step 命名和旧的 phase 命名
            if token in {"phase1", "phase2", "step1", "step2", "step3_upload", "step_extract", "step_storyboard", "step_upload"}:
                reset_steps = False
                status_service.reset_flow_steps(project, workflow, steps)
        elif workflow == "fenjing":
            token = str(phase_value or "").strip().lower()
            if token in {"generate_images", "upload_assets"}:
                reset_steps = False
        elif workflow in {"fenjing_generate", "fenjing_upload"}:
            reset_steps = False
        elif workflow == "video":
            token = str(phase_value or "").strip().lower()
            if token in {"prepare_prompts", "generate_videos", "upload_videos"}:
                reset_steps = False
        actual_flow = status_service.WORKFLOW_TO_FLOW_MAP.get(workflow, workflow)
        status_service.mark_flow_running(project, actual_flow, steps, reset_steps=reset_steps)
        _schedule_job_timeout(job.get("id", ""), project, actual_flow, steps)
        send_json(handler, HTTPStatus.OK, job)
        return True
    if path.startswith("/api/projects/") and path.endswith("/regenerate/character"):
        parts = path.split("/")
        # 解析角色重生成参数
        project = project_repo.safe_project_name(parts[3]) if len(parts) >= 5 else None
        character_id = str(body.get("character_id", "")).strip()
        prompt_text = str(body.get("prompt_text", "")).strip() if isinstance(body.get("prompt_text"), str) else ""
        if not project or not character_id:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
            return True
        # prompt_text 可选，不传时沿用当前提示词
        payload = {"character_id": character_id, "prompt_text": prompt_text} if prompt_text else {"character_id": character_id}
        job = job_service.start_job(
            "regenerate_character",
            project,
            lambda job_id: workflow_service.run_character_regen(job_id, project, character_id),
            payload,
        )
        send_json(handler, HTTPStatus.OK, job)
        return True
    if path.startswith("/api/projects/") and path.endswith("/regenerate/cloth-changed"):
        parts = path.split("/")
        # 解析换装重生成参数
        project = project_repo.safe_project_name(parts[3]) if len(parts) >= 5 else None
        character_id = str(body.get("character_id", "")).strip()
        outfit_id = str(body.get("outfit_id", "")).strip()
        prompt_text = str(body.get("prompt_text", "")).strip() if isinstance(body.get("prompt_text"), str) else ""
        if not project or not character_id or not outfit_id:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
            return True
        # prompt_text 可选，未提供时走默认提示词
        payload = {"character_id": character_id, "outfit_id": outfit_id, "prompt_text": prompt_text} if prompt_text else {"character_id": character_id, "outfit_id": outfit_id}
        job = job_service.start_job(
            "regenerate_cloth_changed",
            project,
            lambda job_id: workflow_service.run_cloth_changed_regen(job_id, project, character_id, outfit_id),
            payload,
        )
        send_json(handler, HTTPStatus.OK, job)
        return True
    if path.startswith("/api/projects/") and path.endswith("/regenerate/cloth"):
        parts = path.split("/")
        project = project_repo.safe_project_name(parts[3]) if len(parts) >= 5 else None
        outfit_id = str(body.get("outfit_id", "")).strip()
        prompt_text = str(body.get("prompt_text", "")).strip() if isinstance(body.get("prompt_text"), str) else ""
        if not project or not outfit_id:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
            return True
        payload = {"outfit_id": outfit_id, "prompt_text": prompt_text} if prompt_text else {"outfit_id": outfit_id}
        job = job_service.start_job(
            "regenerate_cloth",
            project,
            lambda job_id: workflow_service.run_cloth_regen(job_id, project, outfit_id),
            payload,
        )
        send_json(handler, HTTPStatus.OK, job)
        return True
    if path.startswith("/api/projects/") and path.endswith("/regenerate/location-image"):
        parts = path.split("/")
        project = project_repo.safe_project_name(parts[3]) if len(parts) >= 5 else None
        location_id = str(body.get("location_id", "")).strip()
        bg_type = str(body.get("bg_type", "standing")).strip().lower()
        prompt_text = str(body.get("prompt_text", "")).strip() if isinstance(body.get("prompt_text"), str) else ""
        if not project or not location_id or bg_type not in {"standing", "sitting"}:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
            return True
        payload = {"location_id": location_id, "bg_type": bg_type, "prompt_text": prompt_text} if prompt_text else {"location_id": location_id, "bg_type": bg_type}
        job = job_service.start_job(
            "regenerate_location_image",
            project,
            lambda job_id: workflow_service.run_location_image_regen(job_id, project, location_id, bg_type),
            payload,
        )
        send_json(handler, HTTPStatus.OK, job)
        return True
    if path.startswith("/api/projects/") and path.endswith("/regenerate/fenjing"):
        parts = path.split("/")
        # 解析分镜重生成参数
        project = project_repo.safe_project_name(parts[3]) if len(parts) >= 5 else None
        chapter_name = str(body.get("chapter_name", "")).strip()
        fenjing_id = str(body.get("fenjing_id", "")).strip()
        prompt_text = str(body.get("prompt_text", "")).strip() if isinstance(body.get("prompt_text"), str) else ""
        if not project or not chapter_name or not fenjing_id:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
            return True
        # prompt_text 可选，未提供时重用原提示词
        payload = {"chapter_name": chapter_name, "fenjing_id": fenjing_id, "prompt_text": prompt_text} if prompt_text else {"chapter_name": chapter_name, "fenjing_id": fenjing_id}
        job = job_service.start_job(
            "regenerate_fenjing",
            project,
            lambda job_id: workflow_service.run_fenjing_regen(job_id, project, chapter_name, fenjing_id),
            payload,
        )
        send_json(handler, HTTPStatus.OK, job)
        return True
    if path.startswith("/api/projects/") and path.endswith("/regenerate/video"):
        parts = path.split("/")
        # 解析视频重生成参数
        project = project_repo.safe_project_name(parts[3]) if len(parts) >= 5 else None
        chapter_name = str(body.get("chapter_name", "")).strip()
        fenjing_id = str(body.get("fenjing_id", "")).strip()
        model_version = str(body.get("model", "1.5")).strip()
        if not project or not chapter_name or not fenjing_id:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
            return True
        job = job_service.start_job(
            "regenerate_video",
            project,
            lambda job_id: workflow_service.run_video_regen(job_id, project, chapter_name, fenjing_id, model_version),
            {"chapter_name": chapter_name, "fenjing_id": fenjing_id, "model": model_version},
        )
        send_json(handler, HTTPStatus.OK, job)
        return True
    return False
