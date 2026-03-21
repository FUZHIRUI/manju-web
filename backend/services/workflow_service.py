import asyncio
import inspect
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .workflow_runtime.io_jsonl import read_jsonl
from .workflow_runtime.provider_runtime import TosClientWrapper, generate_and_download, generate_and_download_with_refs
from .workflow_runtime.thread_safe_logging import ThreadLogRedirector

from ..repositories import asset_repo, job_repo, project_repo
from . import config_service, status_service, throttle_service
from .workflow_runtime import auto_storyboard, fenjing, runtime_config, video, visual_audio_assets


def load_manju_context(project: str) -> Any:
    """
    加载项目上下文（线程安全版本）

    【重要说明】
    不再修改全局环境变量，而是返回项目特定的配置
    调用者应该使用返回的配置对象，而不是依赖runtime_config全局变量
    """
    # 注意：不再设置 os.environ["PROJECT_NAME"] 以避免线程安全问题
    os.environ["MANJU_OUTPUT_DIR"] = str(project_repo.OUTPUT_DIR)
    # 不再调用 config_service.apply_runtime(project)，因为它会修改全局 runtime_config.PROJECT_NAME
    # 这会导致并发执行时的竞态条件
    # config_service.apply_runtime(project)

    # 只应用非PROJECT_NAME相关的配置
    _apply_runtime_without_project(project)

    # 返回项目特定的配置前缀
    return runtime_config.get_project_prefixes(project)


def _apply_runtime_without_project(project: str) -> None:
    """
    应用运行时配置，但不修改全局PROJECT_NAME
    这是为了避免并发执行时的竞态条件
    """
    items = config_service.get_effective_config(project)
    global_items = config_service._get_effective_global_config()
    auth_items = config_service.get_effective_auth_config(project)

    # 只应用非PROJECT_NAME相关的环境变量
    for item in items:
        env = item.get("env")
        if env and env != "PROJECT_NAME" and not item.get("model_key"):
            os.environ[env] = str(item["value"])

    for item in global_items:
        env = item.get("env")
        if env and env != "PROJECT_NAME" and item.get("model_key"):
            os.environ[env] = str(item["value"])

    for item in auth_items:
        env = item.get("env")
        if env and env != "PROJECT_NAME":
            os.environ[env] = str(item["value"])

    # 不调用 runtime_config.load()，因为这会修改全局PROJECT_NAME
    # 而是只配置限流器
    model_limits: Dict[str, Dict[str, float]] = {}
    stage_limits: Dict[str, Dict[str, float]] = {}
    for item in global_items:
        model_key = item.get("model_key")
        if model_key:
            if item["key"].endswith("_qps"):
                model_limits.setdefault(model_key, {})["qps"] = float(item["value"])
            elif item["key"].endswith("_concurrency"):
                model_limits.setdefault(model_key, {})["concurrency"] = float(item["value"])
    for item in global_items:
        if item["key"] == "stage_concurrency":
            stage_limits.setdefault(item["stage"], {})["concurrency"] = float(item["value"])
    throttle_service.configure_model_limiters(model_limits)
    throttle_service.configure_stage_limiters(stage_limits)


def run_subprocess_job(job_id: str, command: List[str], env: Dict[str, str]) -> None:
    job = job_repo.get_job(job_id)
    if not job:
        return
    log_path = job_repo.resolve_log_path(str(job["log_path"]))
    job_repo.log_event("INFO", "job_start", trace_id=job["trace_id"], job_id=job_id, command=" ".join(command))
    with log_path.open("w", encoding="utf-8") as f:
        proc = subprocess.Popen(
            command,
            stdout=f,
            stderr=subprocess.STDOUT,
            env=env,
            cwd=str(job_repo.ROOT_DIR),
        )
        exit_code = proc.wait()
    status = "success" if exit_code == 0 else "error"
    job_repo.update_job(job_id, status=status, exit_code=exit_code)
    job_repo.log_event("INFO", "job_end", trace_id=job["trace_id"], job_id=job_id, exit_code=exit_code, status=status)


def call_with_project(func: Any, *args: Any, project_name: str, **kwargs: Any) -> Any:
    try:
        return func(*args, project_name=project_name, **kwargs)
    except TypeError as e:
        # 打印完整的错误堆栈以便调试
        import traceback
        print(f"TypeError in call_with_project: {e}")
        traceback.print_exc()
        try:
            params = inspect.signature(func).parameters
        except Exception:
            return func(*args, **kwargs)
        if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
            return func(*args, project_name=project_name, **kwargs)
        filtered: Dict[str, Any] = {k: v for k, v in kwargs.items() if k in params}
        if "project_name" in params:
            filtered["project_name"] = project_name
        return func(*args, **filtered)


def run_auto_storyboard(
    job_id: str,
    project: str,
    novel_path: str,
    phase: str = "full",
    chapter_size: Optional[int] = None,
    target_chapters: Optional[int] = None,
    per_chapter_shots: Optional[int] = None,
    previous_response_id: Optional[str] = None,
    phase1_force_regen: bool = False,
) -> None:
    job = job_repo.get_job(job_id)
    if not job:
        return
    log_path = job_repo.resolve_log_path(str(job["log_path"]))
    
    # 兼容新旧命名映射
    phase_mapping = {
        "step1": "phase1",
        "step2": "phase2",
        "step3_upload": "upload",
    }
    internal_phase = phase_mapping.get(phase, phase)
    
    stage_limiter = throttle_service.acquire_stage_limit("auto_storyboard")
    try:
        with ThreadLogRedirector(log_path):
            # 将日志事件移到 ThreadLogRedirector 上下文内
            job_repo.log_event("INFO", "run_auto_storyboard_start", trace_id=job["trace_id"], job_id=job_id, project=project)
            try:
                load_manju_context(project)
                call_with_project(
                    auto_storyboard.run_workflow,
                    novel_path,
                    project_name=project,
                    phase=internal_phase,
                    chapter_size=chapter_size,
                    target_chapters=target_chapters,
                    per_chapter_shots=per_chapter_shots,
                    previous_response_id=previous_response_id,
                    phase1_force_regen=phase1_force_regen,
                )
                job_repo.update_job(job_id, status="success")
                
                # 状态更新使用新的 step 命名
                if phase == "full":
                    # 只有 full 才标记所有步骤为 completed
                    status_service.mark_flow_completed(project, "auto_storyboard")
                elif phase in {"step1", "phase1"}:
                    status_service.update_step_status(project, "auto_storyboard", "step1", "completed")
                    status_service.update_step_status(project, "auto_storyboard", "step1_extract", "completed")
                    flow_status = status_service.get_flow_state(project).get("flows", {}).get("auto_storyboard", {}).get("status")
                    if flow_status != "completed":
                        status_service.update_flow_status(project, "auto_storyboard", "partial_completed")
                elif phase in {"step2", "phase2"}:
                    # step2 只标记 step2 相关步骤为 completed，不标记 step3
                    status_service.update_step_status(project, "auto_storyboard", "step2", "completed")
                    status_service.update_step_status(project, "auto_storyboard", "step2_storyboard", "completed")
                    flow_status = status_service.get_flow_state(project).get("flows", {}).get("auto_storyboard", {}).get("status")
                    if flow_status != "completed":
                        status_service.update_flow_status(project, "auto_storyboard", "partial_completed")
                elif phase in {"step3_upload", "upload"}:
                    status_service.update_step_status(project, "auto_storyboard", "step3_upload", "completed")
                    status_service.update_step_status(project, "auto_storyboard", "step3_upload_assets", "completed")
                
                job_repo.log_event("INFO", "run_auto_storyboard_success", trace_id=job["trace_id"], job_id=job_id)
                return
            except Exception as exc:
                job_repo.update_job(job_id, status="error", error=str(exc))
                # 错误处理使用新的 step 命名
                error_step = phase
                if phase in {"step1", "phase1"}:
                    error_step = "step1"
                elif phase in {"step2", "phase2"}:
                    error_step = "step2"
                elif phase in {"step3_upload", "upload"}:
                    error_step = "step3_upload"
                status_service.mark_flow_error(project, "auto_storyboard", [error_step])
                job_repo.log_event("ERROR", "run_auto_storyboard_error", trace_id=job["trace_id"], job_id=job_id, error=str(exc))
    finally:
        if stage_limiter:
            stage_limiter.release()


def run_visual_audio_assets(job_id: str, project: str, phase: str = "all") -> None:
    job = job_repo.get_job(job_id)
    if not job:
        return
    log_path = job_repo.resolve_log_path(str(job["log_path"]))
    stage_limiter = throttle_service.acquire_stage_limit("visual_audio_assets")
    try:
        with ThreadLogRedirector(log_path):
            job_repo.log_event("INFO", "run_visual_audio_assets_start", trace_id=job["trace_id"], job_id=job_id, project=project)
            try:
                load_manju_context(project)
                cleanup = asset_repo.clean_visual_audio_assets_by_phase(project, phase)
                if not cleanup.get("ok"):
                    job_repo.update_job(job_id, status="error", error="asset_cleanup_failed")
                    status_service.mark_flow_error(project, "visual_audio_assets", status_service.resolve_visual_audio_steps(phase))
                    job_repo.log_event(
                        "ERROR",
                        "visual_audio_assets_cleanup_error",
                        trace_id=job["trace_id"],
                        job_id=job_id,
                        project=project,
                        error=str(cleanup.get("errors") or cleanup.get("error")),
                    )
                    try:
                        print(f"[ERROR] visual_audio_assets cleanup failed: {cleanup}")
                    except (IOError, OSError, ValueError):
                        pass
                    return
                job_repo.log_event(
                    "INFO",
                    "visual_audio_assets_cleanup",
                    trace_id=job["trace_id"],
                    job_id=job_id,
                    project=project,
                    removed=len(cleanup.get("removed") or []),
                )
                assets_dir = project_repo.visual_audio_assets_dir(project)
                # 确保visual_audio_assets目录存在
                assets_dir.mkdir(parents=True, exist_ok=True)
                # 从storyboard_assets复制必要的jsonl文件
                storyboard_dir = project_repo.storyboard_assets_dir(project)
                for jsonl_file in ["characters.jsonl", "locations.jsonl", "summaries.jsonl"]:
                    src = storyboard_dir / jsonl_file
                    dst = assets_dir / jsonl_file
                    if src.exists() and not dst.exists():
                        import shutil
                        shutil.copy2(src, dst)
                # 复制storyboards目录
                src_storyboards = storyboard_dir / "storyboards"
                dst_storyboards = assets_dir / "storyboards"
                if src_storyboards.exists() and not dst_storyboards.exists():
                    import shutil
                    shutil.copytree(src_storyboards, dst_storyboards)
                # 使用asyncio.run运行异步函数，并传递project_name参数
                asyncio.run(visual_audio_assets.main(
                    project_name=project,
                    assets_dir=str(assets_dir),
                    phase=phase
                ))
                try:
                    phase_tokens = {p.strip().lower() for p in str(phase or "").split(",") if p.strip()}
                    full_phase_run = not phase_tokens or "all" in phase_tokens
                    phase_steps = status_service.resolve_visual_audio_steps(phase)
                    allowed_types = set()
                    if "character_images" in phase_steps:
                        allowed_types.add("character")
                    if "location_images" in phase_steps:
                        allowed_types.add("location")
                    results = asset_repo.build_visual_audio_asset_results(job_id, project, allowed_types)
                    asset_repo.append_asset_results(project, results)
                    summary = asset_repo.aggregate_partial_failures(results)
                    job_repo.update_job(
                        job_id,
                        status="success",
                        partial_failed=summary.get("partial_failed", False),
                        partial_failed_count=summary.get("partial_failed_count", 0),
                        partial_failed_types=summary.get("partial_failed_types", []),
                    )
                    if summary.get("partial_failed"):
                        steps: list = []
                        for item in summary.get("partial_failed_types", []):
                            if item == "character":
                                steps.append("character_images")
                            elif item == "location":
                                steps.append("location_images")
                        for step_id in steps:
                            status_service.update_step_partial(project, "visual_audio_assets", step_id)
                        status_service.mark_flow_partial(project, "visual_audio_assets", steps)
                    else:
                        if full_phase_run:
                            status_service.mark_flow_completed(project, "visual_audio_assets")
                        else:
                            for step_id in phase_steps:
                                status_service.update_step_status(project, "visual_audio_assets", step_id, "completed")
                            flow_status = status_service.get_flow_state(project).get("flows", {}).get("visual_audio_assets", {}).get("status")
                            if flow_status != "completed":
                                status_service.update_flow_status(project, "visual_audio_assets", "partial_completed")
                except Exception as exc:
                    job_repo.update_job(job_id, status="success")
                    phase_tokens = {p.strip().lower() for p in str(phase or "").split(",") if p.strip()}
                    full_phase_run = not phase_tokens or "all" in phase_tokens
                    if full_phase_run:
                        status_service.mark_flow_completed(project, "visual_audio_assets")
                    else:
                        phase_steps = status_service.resolve_visual_audio_steps(phase)
                        for step_id in phase_steps:
                            status_service.update_step_status(project, "visual_audio_assets", step_id, "completed")
                        flow_status = status_service.get_flow_state(project).get("flows", {}).get("visual_audio_assets", {}).get("status")
                        if flow_status != "completed":
                            status_service.update_flow_status(project, "visual_audio_assets", "partial_completed")
                    job_repo.log_event(
                        "ERROR",
                        "asset_results_build_error",
                        trace_id=job["trace_id"],
                        job_id=job_id,
                        project=project,
                        flow="visual_audio_assets",
                        error=str(exc),
                    )
                job_repo.log_event("INFO", "run_visual_audio_assets_success", trace_id=job["trace_id"], job_id=job_id)
                return
            except Exception as exc:
                job_repo.update_job(job_id, status="error", error=str(exc))
                status_service.mark_flow_error(project, "visual_audio_assets", status_service.resolve_visual_audio_steps(phase))
                job_repo.log_event("ERROR", "run_visual_audio_assets_error", trace_id=job["trace_id"], job_id=job_id, error=str(exc))
    finally:
        if stage_limiter:
            stage_limiter.release()


def run_fenjing(job_id: str, project: str, phase: str = "all") -> None:
    """
    统一的分镜工作流执行函数
    
    Args:
        job_id: 任务ID
        project: 项目名称
        phase: 执行阶段，可选 "generate_images", "upload_assets", "all"
    """
    job = job_repo.get_job(job_id)
    if not job:
        return
    log_path = job_repo.resolve_log_path(str(job["log_path"]))
    job_repo.log_event("INFO", "run_fenjing_start", trace_id=job["trace_id"], job_id=job_id, project=project, phase=phase)
    stage_limiter = throttle_service.acquire_stage_limit("fenjing")
    try:
        with ThreadLogRedirector(log_path):
            try:
                load_manju_context(project)
                
                if phase in ("all", "generate_images"):
                    job_repo.log_event("INFO", "run_fenjing_generate_phase_start", trace_id=job["trace_id"], job_id=job_id, project=project)
                    call_with_project(fenjing.run_fenjing_generate_workflow, project_name=project)
                    try:
                        results = asset_repo.build_fenjing_asset_results(job_id, project)
                        asset_repo.append_asset_results(project, results)
                        summary = asset_repo.aggregate_partial_failures(results)
                        success_count = sum(1 for item in results if item.get("status") == "success")
                        if not results or success_count == 0:
                            job_repo.update_job(job_id, status="error", error="fenjing_generate_output_empty")
                            status_service.mark_flow_error(project, "fenjing", ["generate_images"])
                            job_repo.log_event(
                                "ERROR",
                                "fenjing_generate_output_empty",
                                trace_id=job["trace_id"],
                                job_id=job_id,
                                project=project,
                                flow="fenjing",
                            )
                            return
                        if summary.get("partial_failed"):
                            status_service.update_step_partial(project, "fenjing", "generate_images")
                        else:
                            status_service.mark_step_completed(project, "fenjing", "generate_images")
                    except Exception as exc:
                        job_repo.update_job(job_id, status="error", error=str(exc))
                        status_service.mark_flow_error(project, "fenjing", ["generate_images"])
                        job_repo.log_event(
                            "ERROR",
                            "asset_results_build_error",
                            trace_id=job["trace_id"],
                            job_id=job_id,
                            project=project,
                            flow="fenjing",
                            error=str(exc),
                        )
                        return
                
                if phase in ("all", "upload_assets"):
                    job_repo.log_event("INFO", "run_fenjing_upload_phase_start", trace_id=job["trace_id"], job_id=job_id, project=project)
                    call_with_project(fenjing.run_fenjing_upload_workflow, project_name=project)
                    status_service.mark_step_completed(project, "fenjing", "upload_assets")
                
                job_repo.update_job(job_id, status="success")
                job_repo.log_event("INFO", "run_fenjing_success", trace_id=job["trace_id"], job_id=job_id, project=project, phase=phase)
                return
            except Exception as exc:
                import sys, traceback
                error_msg = f"{str(exc)}\n{traceback.format_exc()}"
                sys.__stderr__.write(f"=== FENJING ERROR ===\n")
                sys.__stderr__.write(error_msg)
                sys.__stderr__.write(f"\n=====================\n")
                sys.__stderr__.flush()
                job_repo.update_job(job_id, status="error", error=str(exc))
                status_service.mark_flow_error(project, "fenjing", ["generate_images", "upload_assets"])
                job_repo.log_event("ERROR", "run_fenjing_error", trace_id=job["trace_id"], job_id=job_id, error=str(exc))
    finally:
        if stage_limiter:
            stage_limiter.release()


def run_fenjing_generate(job_id: str, project: str) -> None:
    """运行分镜生成工作流（已废弃，请使用 run_fenjing(phase="generate_images")）"""
    run_fenjing(job_id, project, phase="generate_images")


def run_fenjing_upload(job_id: str, project: str) -> None:
    """运行分镜上传工作流（已废弃，请使用 run_fenjing(phase="upload_assets")）"""
    run_fenjing(job_id, project, phase="upload_assets")


def run_video(job_id: str, project: str, phase: str = "all") -> None:
    job = job_repo.get_job(job_id)
    if not job:
        return
    log_path = job_repo.resolve_log_path(str(job["log_path"]))
    job_repo.log_event("INFO", "run_video_start", trace_id=job["trace_id"], job_id=job_id, project=project, phase=phase)
    stage_limiter = throttle_service.acquire_stage_limit("video")
    try:
        with ThreadLogRedirector(log_path):
            try:
                load_manju_context(project)
                local_out = project_repo.storyboard_assets_dir(project)

                if phase == "prepare_prompts":
                    result_entries = asyncio.run(call_with_project(video.run_video_prepare_prompts, local_out, project_name=project))
                    if not result_entries:
                        job_repo.update_job(job_id, status="error", error="prepare_prompts_empty")
                        status_service.mark_flow_error(project, "video", ["prepare", "phase1_video_prompts"])
                        return
                    status_service.mark_step_completed(project, "video", "prepare")
                    status_service.mark_step_completed(project, "video", "phase1_video_prompts")
                    job_repo.update_job(job_id, status="success")
                    job_repo.log_event("INFO", "run_video_success", trace_id=job["trace_id"], job_id=job_id, phase=phase)
                    return

                elif phase == "generate_videos":
                    success_count, error_count = asyncio.run(call_with_project(video.run_video_generate_only, local_out, project_name=project))
                    try:
                        results = asset_repo.build_video_asset_results(job_id, project)
                        asset_repo.append_asset_results(project, results)
                        summary = asset_repo.aggregate_partial_failures(results)
                    except Exception:
                        results = []
                        summary = {}
                    if success_count == 0:
                        job_repo.update_job(job_id, status="error", error="generate_videos_all_failed")
                        status_service.mark_flow_error(project, "video", ["phase2_video_generation"])
                        return
                    if error_count > 0:
                        status_service.update_step_partial(project, "video", "phase2_video_generation")
                        job_repo.update_job(
                            job_id, status="success",
                            partial_failed=True,
                            partial_failed_count=error_count,
                            partial_failed_types=summary.get("partial_failed_types", []),
                        )
                    else:
                        status_service.mark_step_completed(project, "video", "phase2_video_generation")
                        job_repo.update_job(job_id, status="success")
                    job_repo.log_event("INFO", "run_video_success", trace_id=job["trace_id"], job_id=job_id, phase=phase)
                    return

                elif phase == "upload_videos":
                    success_count, error_count = asyncio.run(call_with_project(video.run_video_upload_only, local_out, project_name=project))
                    if success_count == 0:
                        job_repo.update_job(job_id, status="error", error="upload_videos_all_failed")
                        status_service.mark_flow_error(project, "video", ["fenjing_video_upload"])
                        return
                    status_service.mark_step_completed(project, "video", "fenjing_video_upload")
                    job_repo.update_job(job_id, status="success")
                    job_repo.log_event("INFO", "run_video_success", trace_id=job["trace_id"], job_id=job_id, phase=phase)
                    return

                else:
                    # phase == "all": 保持原有行为不变
                    asyncio.run(call_with_project(video.run_video_workflow_multi, local_out, project_name=project))
                    try:
                        results = asset_repo.build_video_asset_results(job_id, project)
                        asset_repo.append_asset_results(project, results)
                        summary = asset_repo.aggregate_partial_failures(results)
                        job_repo.update_job(
                            job_id,
                            status="success",
                            partial_failed=summary.get("partial_failed", False),
                            partial_failed_count=summary.get("partial_failed_count", 0),
                            partial_failed_types=summary.get("partial_failed_types", []),
                        )
                        if summary.get("partial_failed"):
                            status_service.update_step_partial(project, "video", "phase2_video_generation")
                            status_service.mark_flow_partial(project, "video")
                        else:
                            status_service.mark_flow_completed(project, "video")
                    except Exception as exc:
                        job_repo.update_job(job_id, status="error", error=str(exc))
                        status_service.mark_flow_error(project, "video", ["phase2_video_generation"])
                        job_repo.log_event(
                            "ERROR", "asset_results_build_error",
                            trace_id=job["trace_id"], job_id=job_id,
                            project=project, flow="video", error=str(exc),
                        )
                    job_repo.log_event("INFO", "run_video_success", trace_id=job["trace_id"], job_id=job_id)
                    return
            except Exception as exc:
                job_repo.update_job(job_id, status="error", error=str(exc))
                step_list = {
                    "prepare_prompts": ["prepare", "phase1_video_prompts"],
                    "generate_videos": ["phase2_video_generation"],
                    "upload_videos": ["fenjing_video_upload"],
                }.get(phase, ["phase2_video_generation"])
                status_service.mark_flow_error(project, "video", step_list)
                job_repo.log_event("ERROR", "run_video_error", trace_id=job["trace_id"], job_id=job_id, error=str(exc))
    finally:
        if stage_limiter:
            stage_limiter.release()


def run_character_regen(job_id: str, project: str, character_id: str) -> None:
    job = job_repo.get_job(job_id)
    if not job:
        return
    log_path = job_repo.resolve_log_path(str(job["log_path"]))
    with ThreadLogRedirector(log_path):
        try:
            load_manju_context(project)
            job_repo.log_event(
                "INFO",
                "regen_character_start",
                trace_id=job["trace_id"],
                job_id=job_id,
                project=project,
                character_id=character_id,
            )
            assets_dir = project_repo.storyboard_assets_dir(project)
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
            size_override = asset_repo.resolve_character_size_by_attribute(item.get("attribute"))
            path = asyncio.run(generate_and_download(prompt_text, out_dir, prefix, size=size_override))
            if not isinstance(path, Path):
                raise ValueError("generate_failed")
            job_repo.update_job(job_id, status="success", result={"file": str(path)})
            job_repo.log_event("INFO", "regen_character_success", trace_id=job["trace_id"], job_id=job_id, file=str(path))
            return
        except Exception as exc:
            job_repo.update_job(job_id, status="error", error=str(exc))
            job_repo.log_event("ERROR", "regen_character_error", trace_id=job["trace_id"], job_id=job_id, error=str(exc))


def run_cloth_regen(job_id: str, project: str, outfit_id: str) -> None:
    job = job_repo.get_job(job_id)
    if not job:
        return
    log_path = job_repo.resolve_log_path(str(job["log_path"]))
    with ThreadLogRedirector(log_path):
        try:
            load_manju_context(project)
            job_repo.log_event(
                "INFO",
                "regen_cloth_start",
                trace_id=job["trace_id"],
                job_id=job_id,
                project=project,
                outfit_id=outfit_id,
            )
            assets_dir = project_repo.storyboard_assets_dir(project)
            chars_path = assets_dir / "characters.jsonl"
            if not chars_path.exists():
                raise FileNotFoundError(str(chars_path))
            items = read_jsonl(str(chars_path))
            target = None
            for item in items:
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
            desc = target.get("Outfit_Description")
            prompt_text = job.get("payload", {}).get("prompt_text")
            if not isinstance(prompt_text, str) or not prompt_text.strip():
                prompt_text = f"高质量纯商品摄影，服装商品展示图，将服装平铺在白色背景上，展示服装的全貌。{desc}。**图片中不得出现任何人物**" if isinstance(desc, str) and desc.strip() else "高质量纯商品摄影，服装商品展示图，将服装平铺在白色背景上，展示服装的全貌。**图片中不得出现任何人物**"
            out_dir = assets_dir / "cloth_images"
            out_dir.mkdir(parents=True, exist_ok=True)
            path = asyncio.run(generate_and_download(prompt_text, out_dir, outfit_id))
            if not isinstance(path, Path):
                raise ValueError("generate_failed")
            job_repo.update_job(job_id, status="success", result={"file": str(path)})
            job_repo.log_event("INFO", "regen_cloth_success", trace_id=job["trace_id"], job_id=job_id, file=str(path))
            return
        except Exception as exc:
            job_repo.update_job(job_id, status="error", error=str(exc))
            job_repo.log_event("ERROR", "regen_cloth_error", trace_id=job["trace_id"], job_id=job_id, error=str(exc))


def run_location_image_regen(job_id: str, project: str, location_id: str, bg_type: str) -> None:
    job = job_repo.get_job(job_id)
    if not job:
        return
    log_path = job_repo.resolve_log_path(str(job["log_path"]))
    with ThreadLogRedirector(log_path):
        try:
            load_manju_context(project)
            job_repo.log_event(
                "INFO",
                "regen_location_image_start",
                trace_id=job["trace_id"],
                job_id=job_id,
                project=project,
                location_id=location_id,
                bg_type=bg_type,
            )
            assets_dir = project_repo.storyboard_assets_dir(project)
            prompts_path = assets_dir / "location_prompts.jsonl"
            if not prompts_path.exists():
                raise FileNotFoundError(str(prompts_path))
            prompts = read_jsonl(str(prompts_path))
            target = None
            for item in prompts:
                if not isinstance(item, dict):
                    continue
                loc_id = item.get("Location_Id") or item.get("location_id")
                if str(loc_id) == location_id:
                    target = item
                    break
            if not target:
                raise ValueError("location_id_not_found")
            prompt_text = job.get("payload", {}).get("prompt_text")
            if not isinstance(prompt_text, str) or not prompt_text.strip():
                key = "prompt_sitting" if bg_type == "sitting" else "prompt_standing"
                prompt_text = target.get(key)
            if not isinstance(prompt_text, str) or not prompt_text.strip():
                raise ValueError("prompt_missing")
            out_dir = assets_dir / "location_images"
            out_dir.mkdir(parents=True, exist_ok=True)
            name_prefix = f"{location_id}_{bg_type}"
            path = asyncio.run(generate_and_download(prompt_text, out_dir, name_prefix))
            if not isinstance(path, Path):
                raise ValueError("generate_failed")
            job_repo.update_job(job_id, status="success", result={"file": str(path)})
            job_repo.log_event("INFO", "regen_location_image_success", trace_id=job["trace_id"], job_id=job_id, file=str(path))
            return
        except Exception as exc:
            job_repo.update_job(job_id, status="error", error=str(exc))
            job_repo.log_event("ERROR", "regen_location_image_error", trace_id=job["trace_id"], job_id=job_id, error=str(exc))


def run_cloth_changed_regen(job_id: str, project: str, character_id: str, outfit_id: str) -> None:
    job = job_repo.get_job(job_id)
    if not job:
        return
    log_path = job_repo.resolve_log_path(str(job["log_path"]))
    with ThreadLogRedirector(log_path):
        try:
            manju_ctx = load_manju_context(project)
            job_repo.log_event(
                "INFO",
                "regen_cloth_changed_start",
                trace_id=job["trace_id"],
                job_id=job_id,
                project=project,
                character_id=character_id,
                outfit_id=outfit_id,
            )
            assets_dir = project_repo.storyboard_assets_dir(project)
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
                prompt_text = asset_repo.build_cloth_changed_prompt(target.get("Outfit_Description"))
            out_dir = assets_dir / "cloth_changed_candidates"
            out_dir.mkdir(parents=True, exist_ok=True)
            prefix = f"{character_id}_{outfit_id}_{int(time.time() * 1000)}"
            tos = TosClientWrapper()
            ref_urls: List[str] = []
            if tos.available():
                char_key = f"{manju_ctx['TOS_CHARACTER_PREFIX']}/{character_id}.png"
                cloth_key = f"{manju_ctx['TOS_CLOTH_PREFIX']}/{outfit_id}.png"
                bucket = runtime_config.TOS_BUCKET
                char_url = tos.presign_get(bucket, char_key)
                cloth_url = tos.presign_get(bucket, cloth_key)
                job_repo.log_event(
                    "INFO",
                    "refs_used",
                    trace_id=job["trace_id"],
                    job_id=job_id,
                    project=project,
                    character_id=character_id,
                    outfit_id=outfit_id,
                    char_ref=char_url,
                    cloth_ref=cloth_url,
                )
                if isinstance(char_url, str) and char_url and isinstance(cloth_url, str) and cloth_url:
                    ref_urls = [char_url, cloth_url]
            if ref_urls:
                path = asyncio.run(generate_and_download_with_refs(prompt_text, ref_urls, out_dir, prefix))
            else:
                path = asyncio.run(generate_and_download(prompt_text, out_dir, prefix))
            if not isinstance(path, Path):
                raise ValueError("generate_failed")
            job_repo.update_job(job_id, status="success", result={"file": str(path)})
            job_repo.log_event("INFO", "regen_cloth_changed_success", trace_id=job["trace_id"], job_id=job_id, file=str(path))
            return
        except Exception as exc:
            job_repo.update_job(job_id, status="error", error=str(exc))
            job_repo.log_event("ERROR", "regen_cloth_changed_error", trace_id=job["trace_id"], job_id=job_id, error=str(exc))


def run_fenjing_regen(job_id: str, project: str, chapter_name: str, fenjing_id: str) -> None:
    job = job_repo.get_job(job_id)
    if not job:
        return
    log_path = job_repo.resolve_log_path(str(job["log_path"]))
    with ThreadLogRedirector(log_path):
        try:
            load_manju_context(project)
            job_repo.log_event(
                "INFO",
                "regen_fenjing_start",
                trace_id=job["trace_id"],
                job_id=job_id,
                project=project,
                chapter=chapter_name,
                fenjing_id=fenjing_id,
            )
            chapter_dir = project_repo.storyboard_assets_dir(project) / "storyboards" / chapter_name
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
            ref_urls = asset_repo.build_fenjing_ref_urls(project, chapter_name, fenjing_id, item)
            if ref_urls:
                path = asyncio.run(generate_and_download_with_refs(prompt_text, ref_urls, out_dir, prefix))
            else:
                path = asyncio.run(generate_and_download(prompt_text, out_dir, prefix))
            if not isinstance(path, Path):
                raise ValueError("generate_failed")
            job_repo.update_job(job_id, status="success", result={"file": str(path)})
            job_repo.log_event(
                "INFO",
                "regen_fenjing_success",
                trace_id=job["trace_id"],
                job_id=job_id,
                project=project,
                chapter=chapter_name,
                fenjing_id=fenjing_id,
                file=str(path),
            )
            return
        except Exception as exc:
            job_repo.update_job(job_id, status="error", error=str(exc))
            job_repo.log_event(
                "ERROR",
                "regen_fenjing_error",
                trace_id=job["trace_id"],
                job_id=job_id,
                project=project,
                chapter=chapter_name,
                fenjing_id=fenjing_id,
                error=str(exc),
            )


def run_video_regen(job_id: str, project: str, chapter_name: str, fenjing_id: str, model_version: str = "1.5") -> None:
    job = job_repo.get_job(job_id)
    if not job:
        return
    log_path = job_repo.resolve_log_path(str(job["log_path"]))
    with ThreadLogRedirector(log_path):
        try:
            manju_ctx = load_manju_context(project)
            job_repo.log_event(
                "INFO",
                "regen_video_start",
                trace_id=job["trace_id"],
                job_id=job_id,
                project=project,
                chapter=chapter_name,
                fenjing_id=fenjing_id,
                model=model_version,
            )
            chapter_dir = project_repo.storyboard_assets_dir(project) / "storyboards" / chapter_name
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
            model_ep = manju_ctx.VIDEO_MODEL_1_0_EP if "1.0" in model_version else manju_ctx.VIDEO_MODEL_1_5_EP
            min_duration = manju_ctx.VIDEO_MIN_DURATION_1_0 if "1.0" in model_version else manju_ctx.VIDEO_MIN_DURATION_1_5
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
            image_key = f"{manju_ctx.TOS_FENJING_PREFIX}/{chapter_name}/fenjing{fenjing_id}.png"
            image_url = tos.presign_get(manju_ctx.TOS_BUCKET, image_key)
            if not image_url:
                raise RuntimeError("image_presign_failed")
            video_dir = project_repo.project_base_dir(project) / "video" / chapter_name
            video_dir.mkdir(parents=True, exist_ok=True)
            timestamp = int(time.time() * 1000)
            video_filename = f"fenjing_{fenjing_id}_{timestamp}.mp4"
            ok = asyncio.run(
                video.process_single_video_independent(
                    fenjing_id=fenjing_id,
                    model_ep=model_ep,
                    prompt=prompt_text,
                    image_url=image_url,
                    audio_duration=duration,
                    min_duration=min_duration,
                    video_dir=video_dir,
                    chapter_name=chapter_name,
                    video_filename=video_filename,
                    project_name=project,
                )
            )
            if not ok:
                raise RuntimeError("video_generate_failed")
            job_repo.update_job(job_id, status="success", result={"video_dir": str(video_dir), "video_filename": video_filename})
            job_repo.log_event(
                "INFO",
                "regen_video_success",
                trace_id=job["trace_id"],
                job_id=job_id,
                project=project,
                chapter=chapter_name,
                fenjing_id=fenjing_id,
                model=model_version,
                video_dir=str(video_dir),
                video_filename=video_filename,
            )
            return
        except Exception as exc:
            job_repo.update_job(job_id, status="error", error=str(exc))
            job_repo.log_event(
                "ERROR",
                "regen_video_error",
                trace_id=job["trace_id"],
                job_id=job_id,
                project=project,
                chapter=chapter_name,
                fenjing_id=fenjing_id,
                model=model_version,
                error=str(exc),
            )
