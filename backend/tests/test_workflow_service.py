from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from manju_web.backend.repositories import job_repo, project_repo
from manju_web.backend.services import workflow_service


def _start_job(job_type: str, project: str) -> Dict[str, Any]:
    def runner(job_id: str) -> None:
        return None

    return job_repo.start_job(job_type, project, runner, {})


def test_load_manju_context_sets_env(project_output_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    called: List[str] = []

    def fake_apply_runtime(project: str) -> None:
        called.append(project)

    monkeypatch.setattr(workflow_service.config_service, "apply_runtime", fake_apply_runtime)
    workflow_service.load_manju_context("demo")
    assert called == ["demo"]
    assert "PROJECT_NAME" in workflow_service.os.environ
    assert workflow_service.os.environ["PROJECT_NAME"] == "demo"
    assert workflow_service.os.environ["MANJU_OUTPUT_DIR"] == str(project_repo.OUTPUT_DIR)


def test_run_auto_storyboard_success(job_repo_state: Path, project_output_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    job = _start_job("auto_storyboard", "demo")

    class Limiter:
        def __init__(self) -> None:
            self.released = False

        def release(self) -> None:
            self.released = True

    limiter = Limiter()
    monkeypatch.setattr(workflow_service.throttle_service, "acquire_stage_limit", lambda _: limiter)
    monkeypatch.setattr(workflow_service, "load_manju_context", lambda project: None)
    monkeypatch.setattr(workflow_service.auto_storyboard, "run_workflow", lambda _: None)

    workflow_service.run_auto_storyboard(job["id"], "demo", "/tmp/novel.txt", phase="phase1")
    updated = job_repo.get_job(job["id"])
    assert updated and updated["status"] == "success"
    assert limiter.released is True
    from manju_web.backend.services import status_service
    state = status_service.get_flow_state("demo")
    steps = state.get("flows", {}).get("auto_storyboard", {}).get("steps", {})
    assert steps.get("phase1") == "completed"
    assert steps.get("phase2") == "waiting"
    assert steps.get("upload") == "waiting"


def test_run_auto_storyboard_phase2_completes_all(job_repo_state: Path, project_output_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    job = _start_job("auto_storyboard", "demo")

    class Limiter:
        def __init__(self) -> None:
            self.released = False

        def release(self) -> None:
            self.released = True

    limiter = Limiter()
    monkeypatch.setattr(workflow_service.throttle_service, "acquire_stage_limit", lambda _: limiter)
    monkeypatch.setattr(workflow_service, "load_manju_context", lambda project: None)
    monkeypatch.setattr(workflow_service.auto_storyboard, "run_workflow", lambda _: None)

    workflow_service.run_auto_storyboard(job["id"], "demo", "/tmp/novel.txt", phase="phase2")
    updated = job_repo.get_job(job["id"])
    assert updated and updated["status"] == "success"
    assert limiter.released is True
    from manju_web.backend.services import status_service
    state = status_service.get_flow_state("demo")
    steps = state.get("flows", {}).get("auto_storyboard", {}).get("steps", {})
    assert steps.get("phase1") == "completed"
    assert steps.get("phase2") == "completed"
    assert steps.get("upload") == "completed"


def test_run_auto_storyboard_error(job_repo_state: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    job = _start_job("auto_storyboard", "demo")

    class Limiter:
        def __init__(self) -> None:
            self.released = False

        def release(self) -> None:
            self.released = True

    limiter = Limiter()
    monkeypatch.setattr(workflow_service.throttle_service, "acquire_stage_limit", lambda _: limiter)
    monkeypatch.setattr(workflow_service, "load_manju_context", lambda project: None)

    def boom(_: str) -> None:
        raise RuntimeError("bad")

    monkeypatch.setattr(workflow_service.auto_storyboard, "run_workflow", boom)
    workflow_service.run_auto_storyboard(job["id"], "demo", "/tmp/novel.txt")
    updated = job_repo.get_job(job["id"])
    assert updated and updated["status"] == "error"
    assert updated["error"] == "bad"
    assert limiter.released is True


def test_run_visual_audio_assets_success(
    job_repo_state: Path, project_output_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = _start_job("visual_audio_assets", "demo")
    argv_backup = workflow_service.sys.argv[:]

    class Limiter:
        def __init__(self) -> None:
            self.released = False

        def release(self) -> None:
            self.released = True

    limiter = Limiter()
    monkeypatch.setattr(workflow_service.throttle_service, "acquire_stage_limit", lambda _: limiter)
    monkeypatch.setattr(workflow_service, "load_manju_context", lambda project: None)

    async def fake_main() -> None:
        return None

    monkeypatch.setattr(workflow_service.visual_audio_assets, "main", fake_main)
    workflow_service.run_visual_audio_assets(job["id"], "demo")
    updated = job_repo.get_job(job["id"])
    assert updated and updated["status"] == "success"
    assert workflow_service.sys.argv == argv_backup
    assert limiter.released is True


def test_run_fenjing_and_video_success(
    job_repo_state: Path, project_output_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_fenjing = _start_job("fenjing", "demo")
    job_video = _start_job("video", "demo")

    monkeypatch.setattr(workflow_service.throttle_service, "acquire_stage_limit", lambda _: None)
    monkeypatch.setattr(workflow_service, "load_manju_context", lambda project: None)
    monkeypatch.setattr(workflow_service.fenjing, "run_fenjing_workflow_multi", lambda: None)
    monkeypatch.setattr(
        workflow_service.asset_repo,
        "build_fenjing_asset_results",
        lambda *_: [{"status": "success"}],
    )

    async def fake_video(_: Path) -> None:
        return None

    monkeypatch.setattr(workflow_service.video, "run_video_workflow_multi", fake_video)

    workflow_service.run_fenjing(job_fenjing["id"], "demo")
    workflow_service.run_video(job_video["id"], "demo")
    updated_fenjing = job_repo.get_job(job_fenjing["id"])
    updated_video = job_repo.get_job(job_video["id"])
    assert updated_fenjing and updated_fenjing["status"] == "success"
    assert updated_video and updated_video["status"] == "success"


def test_run_fenjing_empty_output_marks_error(
    job_repo_state: Path, project_output_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_fenjing = _start_job("fenjing", "demo")
    monkeypatch.setattr(workflow_service.throttle_service, "acquire_stage_limit", lambda _: None)
    monkeypatch.setattr(workflow_service, "load_manju_context", lambda project: None)
    monkeypatch.setattr(workflow_service.fenjing, "run_fenjing_workflow_multi", lambda: None)
    monkeypatch.setattr(workflow_service.asset_repo, "build_fenjing_asset_results", lambda *_: [])

    workflow_service.run_fenjing(job_fenjing["id"], "demo")
    updated = job_repo.get_job(job_fenjing["id"])
    assert updated and updated["status"] == "error"
    from manju_web.backend.services import status_service
    state = status_service.get_flow_state("demo")
    steps = state.get("flows", {}).get("fenjing", {}).get("steps", {})
    assert state.get("flows", {}).get("fenjing", {}).get("status") == "error"
    assert steps.get("generate_images") == "error"


def test_run_character_regen_success(
    job_repo_state: Path, project_output_dir: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    job = _start_job("character_regen", "demo")
    assets_dir = project_repo.storyboard_assets_dir("demo")
    prompts_path = assets_dir / "character_prompts.jsonl"
    prompts_path.parent.mkdir(parents=True, exist_ok=True)
    prompts_path.write_text("[]", encoding="utf-8")

    monkeypatch.setattr(workflow_service, "load_manju_context", lambda project: None)
    monkeypatch.setattr(
        workflow_service,
        "read_jsonl",
        lambda _: [{"Character_Id": "char_1", "prompt": "ok", "attribute": "human"}],
    )
    monkeypatch.setattr(workflow_service.asset_repo, "resolve_character_size_by_attribute", lambda _: None)
    out_path = tmp_path / "out.png"

    async def fake_generate(*args: Any, **kwargs: Any) -> Path:
        return out_path

    monkeypatch.setattr(workflow_service, "generate_and_download", fake_generate)

    workflow_service.run_character_regen(job["id"], "demo", "char_1")
    updated = job_repo.get_job(job["id"])
    assert updated and updated["status"] == "success"
    assert updated["result"]["file"] == str(out_path)


def test_run_character_regen_missing_prompts(
    job_repo_state: Path, project_output_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = _start_job("character_regen", "demo")
    monkeypatch.setattr(workflow_service, "load_manju_context", lambda project: None)
    workflow_service.run_character_regen(job["id"], "demo", "char_1")
    updated = job_repo.get_job(job["id"])
    assert updated and updated["status"] == "error"
    assert "character_prompts.jsonl" in str(updated["error"])


def test_run_fenjing_regen_success(
    job_repo_state: Path, project_output_dir: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    job = _start_job("fenjing_regen", "demo")
    chapter_dir = project_repo.storyboard_assets_dir("demo") / "storyboards" / "storyboard_chapter_1"
    prompts_path = chapter_dir / "fenjing_prompts.jsonl"
    prompts_path.parent.mkdir(parents=True, exist_ok=True)
    prompts_path.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(workflow_service, "load_manju_context", lambda project: None)
    monkeypatch.setattr(
        workflow_service, "read_jsonl", lambda _: [{"fenjing_id": "1", "prompt": "ok"}]
    )
    monkeypatch.setattr(workflow_service.asset_repo, "build_fenjing_ref_urls", lambda *args, **kwargs: [])
    out_path = tmp_path / "fenjing.png"

    async def fake_generate(*args: Any, **kwargs: Any) -> Path:
        return out_path

    monkeypatch.setattr(workflow_service, "generate_and_download", fake_generate)
    workflow_service.run_fenjing_regen(job["id"], "demo", "storyboard_chapter_1", "1")
    updated = job_repo.get_job(job["id"])
    assert updated and updated["status"] == "success"
    assert updated["result"]["file"] == str(out_path)


def test_run_video_regen_tos_unavailable(
    job_repo_state: Path, project_output_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = _start_job("video_regen", "demo")
    chapter_dir = project_repo.storyboard_assets_dir("demo") / "storyboards" / "storyboard_chapter_1"
    shipin_path = chapter_dir / "shipin_prompts.jsonl"
    shipin_path.parent.mkdir(parents=True, exist_ok=True)
    shipin_path.write_text("[]", encoding="utf-8")
    manju_ctx = SimpleNamespace(
        VIDEO_MODEL_1_0_EP="",
        VIDEO_MODEL_1_5_EP="",
        VIDEO_MIN_DURATION_1_0=1.0,
        VIDEO_MIN_DURATION_1_5=1.0,
        TOS_BUCKET="",
        TOS_FENJING_PREFIX="",
    )
    monkeypatch.setattr(workflow_service, "load_manju_context", lambda project: manju_ctx)

    def fake_read_jsonl(path: str) -> List[Dict[str, Any]]:
        if "shipin_prompts.jsonl" in path:
            return [{"fenjing_id": "1", "prompt": "ok", "model": "1.5"}]
        if "fenjing_prompts.jsonl" in path:
            return [{"fenjing_id": "1", "duration": 5.0}]
        return []

    monkeypatch.setattr(workflow_service, "read_jsonl", fake_read_jsonl)

    class FakeTos:
        def available(self) -> bool:
            return False

    monkeypatch.setattr(workflow_service, "TosClientWrapper", FakeTos)
    workflow_service.run_video_regen(job["id"], "demo", "storyboard_chapter_1", "1")
    updated = job_repo.get_job(job["id"])
    assert updated and updated["status"] == "error"
    assert updated["error"] == "tos_unavailable"
