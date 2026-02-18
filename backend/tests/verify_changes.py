import json
import pytest
import requests
from playwright.sync_api import Page, expect

BASE_URL = "http://127.0.0.1:8086"
PROJECT = "ms3"

TEST_MATRIX = [
    ("正常", {"project": PROJECT, "flows": {}}),
    ("边界:空值", None),
    ("边界:超长", {"project": "A" * 256, "flows": {}}),
    ("边界:非法字符", {"project": "<script>", "flows": {}}),
]


def build_job(job_id: str, flow: str, status: str, updated_at: float, log_tail=None) -> dict:
    return {
        "id": job_id,
        "type": f"run_{flow}",
        "status": status,
        "created_at": updated_at,
        "updated_at": updated_at,
        "project": PROJECT,
        "log_tail": log_tail or [],
    }


def build_flow_status(flow_steps: dict) -> dict:
    return {"project": PROJECT, "flows": flow_steps}


def route_api(page: Page, jobs: list, flow_status: dict) -> None:
    def handle_api(route) -> None:
        url = route.request.url
        if url.endswith("/api/projects"):
            route.fulfill(status=200, body=json.dumps({"projects": [PROJECT], "default_project": PROJECT}))
            return
        if url.endswith(f"/api/projects/{PROJECT}/jobs"):
            route.fulfill(status=200, body=json.dumps({"project": PROJECT, "jobs": jobs}))
            return
        if url.endswith(f"/api/projects/{PROJECT}/flow-status"):
            body = flow_status if flow_status is not None else {"project": PROJECT, "flows": {}}
            route.fulfill(status=200, body=json.dumps(body))
            return
        route.fulfill(status=200, body=json.dumps({}))

    page.route("**/api/**", handle_api)


class TestPhaseUnificationContracts:
    def test_status_service_contract(self) -> None:
        from backend.services import status_service

        flow_steps = status_service._FLOW_STEPS
        assert flow_steps["auto_storyboard"] == ["phase1", "phase2", "upload"]
        assert flow_steps["fenjing"] == ["download_assets", "generate_images", "upload_assets"]
        assert flow_steps["video"] == ["prepare", "phase1_video_prompts", "phase2_video_generation", "fenjing_video_upload"]
        assert "build_prompts" in flow_steps["visual_audio_assets"]
        assert "cloth_changed" in flow_steps["visual_audio_assets"]

        partial = status_service._PARTIAL_STEPS
        assert "cloth_changed" in partial["visual_audio_assets"]
        assert "phase2_video_generation" in partial["video"]

    def test_resolve_video_phases(self) -> None:
        from backend.services import status_service

        assert status_service._resolve_step("video", "phase_start", "phase1_video_prompts", "phase1_video_prompts") == "phase1_video_prompts"
        assert status_service._resolve_step("video", "phase_start", "phase2_video_generation", "phase2_video_generation") == "phase2_video_generation"
        assert status_service._resolve_step("video", "upload_complete", "fenjing_video_upload", None) == "fenjing_video_upload"


class TestFenjingApiContracts:
    def test_flow_status_api(self) -> None:
        res = requests.get(f"{BASE_URL}/api/projects/{PROJECT}/flow-status", timeout=5)
        assert res.status_code == 200
        payload = res.json()
        assert isinstance(payload, dict)
        assert "flows" in payload

    def test_projects_api(self) -> None:
        res = requests.get(f"{BASE_URL}/api/projects", timeout=5)
        assert res.status_code == 200
        payload = res.json()
        assert isinstance(payload, dict)
        assert "projects" in payload

    def test_flow_state_helpers(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        from backend.repositories import project_repo
        from backend.services.workflow_runtime import runtime_config
        from backend.services import status_service

        monkeypatch.setattr(project_repo, "OUTPUT_DIR", tmp_path)
        monkeypatch.setattr(runtime_config, "OUTPUT_DIR", str(tmp_path))

        project = "demo"
        steps = status_service.resolve_visual_audio_steps("build_prompts")
        status_service.mark_flow_running(project, "visual_audio_assets", steps, reset_steps=True)
        state = status_service.get_flow_state(project)
        assert state["flows"]["visual_audio_assets"]["status"] == "running"
        assert state["flows"]["visual_audio_assets"]["steps"]["build_prompts"] == "running"

        status_service.mark_flow_partial(project, "visual_audio_assets", ["character_images"])
        state = status_service.get_flow_state(project)
        assert state["flows"]["visual_audio_assets"]["status"] == "partial_returned"
        assert state["flows"]["visual_audio_assets"]["steps"]["character_images"] == "partial_returned"

        status_service.mark_flow_error(project, "visual_audio_assets", ["build_prompts"])
        state = status_service.get_flow_state(project)
        assert state["flows"]["visual_audio_assets"]["status"] == "error"
        assert state["flows"]["visual_audio_assets"]["steps"]["build_prompts"] == "error"

        status_service.mark_flow_completed(project, "visual_audio_assets")
        state = status_service.get_flow_state(project)
        assert state["flows"]["visual_audio_assets"]["status"] == "completed"
        assert state["flows"]["visual_audio_assets"]["steps"]["build_prompts"] == "completed"

    def test_reset_visual_audio_prompt_steps(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        from backend.repositories import project_repo
        from backend.services.workflow_runtime import runtime_config
        from backend.services import status_service

        monkeypatch.setattr(project_repo, "OUTPUT_DIR", tmp_path)
        monkeypatch.setattr(runtime_config, "OUTPUT_DIR", str(tmp_path))

        project = "demo"
        steps = status_service.resolve_visual_audio_steps("build_prompts")
        status_service.mark_flow_completed(project, "visual_audio_assets")
        status_service.reset_flow_steps(project, "visual_audio_assets", steps)
        state = status_service.get_flow_state(project)
        assert state["flows"]["visual_audio_assets"]["steps"]["build_prompts"] == "waiting"
        assert state["flows"]["visual_audio_assets"]["steps"]["character_prompts"] == "waiting"
        assert state["flows"]["visual_audio_assets"]["steps"]["location_prompts"] == "waiting"
        assert state["flows"]["visual_audio_assets"]["steps"]["fenjing_prompts"] == "waiting"


class TestPhaseUnificationFrontend:
    @pytest.mark.parametrize("desc, flow_status", TEST_MATRIX)
    def test_flow_status_payload_resilience(self, page: Page, desc: str, flow_status: dict) -> None:
        jobs = [build_job("job_va", "visual_audio_assets", "pending", 1000)]
        route_api(page, jobs, flow_status)
        page.goto(f"{BASE_URL}/?project={PROJECT}&tab=batch")
        page.wait_for_timeout(1000)
        expect(page).not_to_have_url("about:blank")

    def test_partial_returned_flow_status(self, page: Page) -> None:
        jobs = [build_job("job_va", "visual_audio_assets", "success", 1000)]
        flow_status = build_flow_status({
            "visual_audio_assets": {
                "status": "partial_returned",
                "steps": {
                    "build_prompts": "completed",
                    "character_images": "partial_returned",
                    "location_images": "completed",
                    "tts": "completed",
                },
            }
        })
        route_api(page, jobs, flow_status)
        page.goto(f"{BASE_URL}/?project={PROJECT}&tab=batch")
        page.wait_for_timeout(1000)
        expect(page).not_to_have_url("about:blank")

    def test_video_tree_labels(self, page: Page) -> None:
        jobs = [build_job("job_video", "video", "success", 1000)]
        flow_status = build_flow_status({
            "video": {
                "status": "running",
                "steps": {
                    "prepare": "completed",
                    "phase1_video_prompts": "running",
                    "phase2_video_generation": "waiting",
                    "fenjing_video_upload": "waiting",
                },
            }
        })
        route_api(page, jobs, flow_status)
        page.goto(f"{BASE_URL}/?project={PROJECT}&tab=batch")
        expect(page.locator("#jobList .tree-label", has_text="分镜提示词").first).to_be_visible()
        expect(page.locator("#jobList .tree-label", has_text="视频生成").first).to_be_visible()
        expect(page.locator("#jobList .tree-label", has_text="上传视频").first).to_be_visible()

    def test_auto_storyboard_phase_buttons(self, page: Page) -> None:
        jobs = [build_job("job_story", "auto_storyboard", "success", 1000)]
        flow_status = build_flow_status({
            "auto_storyboard": {
                "status": "waiting",
                "steps": {
                    "phase1": "waiting",
                    "phase2": "waiting",
                    "upload": "waiting",
                },
            }
        })
        route_api(page, jobs, flow_status)
        page.goto(f"{BASE_URL}/?project={PROJECT}&tab=batch")
        phase1 = page.locator(".tree-action-row", has=page.get_by_text("阶段 1"))
        phase2 = page.locator(".tree-action-row", has=page.get_by_text("阶段 2"))
        expect(phase1.get_by_role("button")).to_be_enabled()
        expect(phase2.get_by_role("button")).to_be_enabled()

    def test_auto_storyboard_partial_completed_visible(self, page: Page) -> None:
        jobs = [build_job("job_story", "auto_storyboard", "success", 1000)]
        flow_status = build_flow_status({
            "auto_storyboard": {
                "status": "partial_completed",
                "steps": {
                    "phase1": "completed",
                    "phase2": "waiting",
                    "upload": "waiting",
                },
            }
        })
        route_api(page, jobs, flow_status)
        page.goto(f"{BASE_URL}/?project={PROJECT}&tab=batch")
        expect(page.locator(".job-item", has=page.get_by_text("剧本拆解")).first).to_be_visible()

    def test_visual_audio_partial_returned_visible(self, page: Page) -> None:
        jobs = [build_job("job_va", "visual_audio_assets", "success", 1000)]
        flow_status = build_flow_status({
            "visual_audio_assets": {
                "status": "partial_returned",
                "steps": {
                    "download_assets": "waiting",
                    "build_prompts": "completed",
                    "generate_images": "partial_returned",
                    "generate_tts": "waiting",
                    "upload_assets": "running",
                },
            }
        })
        route_api(page, jobs, flow_status)
        page.goto(f"{BASE_URL}/?project={PROJECT}&tab=batch")
        expect(page.locator(".job-item", has=page.get_by_text("角色与素材生成")).first).to_be_visible()

    def test_fenjing_video_execute_buttons(self, page: Page) -> None:
        jobs = [
            build_job("job_fenjing", "fenjing", "success", 1000),
            build_job("job_video", "video", "success", 1000),
        ]
        flow_status = build_flow_status({
            "fenjing": {"status": "waiting", "steps": {"download_assets": "waiting"}},
            "video": {"status": "waiting", "steps": {"prepare": "waiting"}},
        })
        route_api(page, jobs, flow_status)
        page.goto(f"{BASE_URL}/?project={PROJECT}&tab=batch")
        fenjing_item = page.locator(".job-item", has=page.get_by_text("分镜图生成"))
        video_item = page.locator(".job-item", has=page.get_by_text("视频生成"))
        fenjing_btn = fenjing_item.get_by_role("button", name="执行")
        video_btn = video_item.get_by_role("button", name="执行")
        expect(fenjing_btn).to_be_enabled()
        expect(video_btn).to_be_enabled()

    def test_visual_audio_button_states(self, page: Page) -> None:
        jobs = [build_job("job_va", "visual_audio_assets", "success", 1000)]
        flow_status = build_flow_status({
            "visual_audio_assets": {
                "status": "running",
                "steps": {
                    "download_assets": "completed",
                    "build_prompts": "completed",
                    "generate_images": "waiting",
                    "generate_tts": "waiting",
                    "cloth_images": "waiting",
                    "cloth_changed": "waiting",
                    "upload_assets": "waiting",
                    "character_prompts": "completed",
                    "location_prompts": "completed",
                    "fenjing_prompts": "completed",
                    "character_images": "waiting",
                    "location_images": "waiting",
                    "tts": "waiting",
                },
            }
        })
        route_api(page, jobs, flow_status)
        page.goto(f"{BASE_URL}/?project={PROJECT}&tab=batch")

        row = page.locator(".tree-action-row", has=page.get_by_text("第一步：提示词"))
        btn = row.get_by_role("button")
        expect(btn).to_have_text("已完成")
        expect(btn).to_be_disabled()

        row = page.locator(".tree-action-row", has=page.get_by_text("第二步：生成"))
        expect(row.get_by_role("button")).to_be_enabled()

        row = page.locator(".tree-action-row", has=page.get_by_text("第二步：TTS语音"))
        expect(row.get_by_role("button")).to_be_enabled()

    def test_visual_audio_prompt_locked_by_later_step(self, page: Page) -> None:
        jobs = [build_job("job_va", "visual_audio_assets", "success", 1000)]
        flow_status = build_flow_status({
            "visual_audio_assets": {
                "status": "running",
                "steps": {
                    "download_assets": "completed",
                    "build_prompts": "waiting",
                    "generate_images": "completed",
                    "generate_tts": "waiting",
                    "cloth_images": "waiting",
                    "cloth_changed": "waiting",
                    "upload_assets": "waiting",
                    "character_prompts": "waiting",
                    "location_prompts": "waiting",
                    "fenjing_prompts": "waiting",
                    "character_images": "completed",
                    "location_images": "completed",
                    "tts": "waiting",
                },
            }
        })
        route_api(page, jobs, flow_status)
        page.goto(f"{BASE_URL}/?project={PROJECT}&tab=batch")

        row = page.locator(".tree-action-row", has=page.get_by_text("第一步：提示词"))
        btn = row.get_by_role("button")
        expect(btn).to_have_text("执行")
        expect(btn).to_be_enabled()

    def test_visual_audio_prompt_locked_by_running_step(self, page: Page) -> None:
        jobs = [build_job("job_va", "visual_audio_assets", "success", 1000)]
        flow_status = build_flow_status({
            "visual_audio_assets": {
                "status": "running",
                "steps": {
                    "download_assets": "completed",
                    "build_prompts": "waiting",
                    "generate_images": "running",
                    "generate_tts": "waiting",
                    "cloth_images": "waiting",
                    "cloth_changed": "waiting",
                    "upload_assets": "waiting",
                    "character_prompts": "waiting",
                    "location_prompts": "waiting",
                    "fenjing_prompts": "waiting",
                    "character_images": "running",
                    "location_images": "waiting",
                    "tts": "waiting",
                },
            }
        })
        route_api(page, jobs, flow_status)
        page.goto(f"{BASE_URL}/?project={PROJECT}&tab=batch")

        row = page.locator(".tree-action-row", has=page.get_by_text("第一步：提示词"))
        btn = row.get_by_role("button")
        expect(btn).to_have_text("执行")
        expect(btn).to_be_enabled()

    def test_visual_audio_all_completed_disabled(self, page: Page) -> None:
        jobs = [build_job("job_va", "visual_audio_assets", "success", 1000)]
        flow_status = build_flow_status({
            "visual_audio_assets": {
                "status": "completed",
                "steps": {
                    "download_assets": "completed",
                    "build_prompts": "completed",
                    "generate_images": "completed",
                    "generate_tts": "completed",
                    "cloth_images": "completed",
                    "cloth_changed": "completed",
                    "upload_assets": "completed",
                    "character_prompts": "completed",
                    "location_prompts": "completed",
                    "fenjing_prompts": "completed",
                    "character_images": "completed",
                    "location_images": "completed",
                    "tts": "completed",
                },
            }
        })
        route_api(page, jobs, flow_status)
        page.goto(f"{BASE_URL}/?project={PROJECT}&tab=batch")
        row = page.locator(".tree-action-row", has=page.get_by_text("第一步：提示词"))
        expect(row.get_by_role("button")).to_be_disabled()

    def test_backend_down_graceful_handling(self, page: Page) -> None:
        def handle_route(route):
            route.fulfill(status=500, body=json.dumps({"error": "server_error"}))

        page.route("**/api/**", handle_route)
        page.goto(f"{BASE_URL}/?project={PROJECT}&tab=batch")
        page.wait_for_timeout(1000)
        expect(page).not_to_have_url("about:blank")
        page.unroute("**/api/**", handle_route)

    def test_upload_progress_not_trigger_upload_assets_running(self, page: Page, monkeypatch, tmp_path) -> None:
        from backend.repositories import project_repo
        from backend.services.workflow_runtime import runtime_config
        from backend.services import status_service

        monkeypatch.setattr(project_repo, "OUTPUT_DIR", tmp_path)
        monkeypatch.setattr(runtime_config, "OUTPUT_DIR", str(tmp_path))

        project = "demo"
        steps = status_service.resolve_visual_audio_steps("build_prompts")
        status_service.mark_flow_running(project, "visual_audio_assets", steps, reset_steps=True)

        status_service.update_from_event(
            "visual_audio_assets",
            "upload_progress",
            "INFO",
            "character_images",
            None,
            project,
        )

        state = status_service.get_flow_state(project)
        assert state["flows"]["visual_audio_assets"]["steps"]["upload_assets"] != "running"
        assert state["flows"]["visual_audio_assets"]["steps"]["character_images"] == "running"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
