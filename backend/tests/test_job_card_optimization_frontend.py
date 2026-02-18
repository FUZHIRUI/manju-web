import json
import pytest
import requests
from playwright.sync_api import Page, expect

BASE_URL = "http://127.0.0.1:8086"
PROJECT = "ms3"
STAGE_TYPES = ["auto_storyboard", "visual_audio_assets", "fenjing", "video"]


def build_flow_status(overrides=None, default_status="waiting") -> dict:
    flows = {flow: {"status": default_status, "steps": {}} for flow in STAGE_TYPES}
    overrides = overrides or {}
    for flow, data in overrides.items():
        if flow not in flows:
            continue
        flows[flow]["status"] = data.get("status", flows[flow]["status"])
        flows[flow]["steps"] = data.get("steps", flows[flow]["steps"])
    return {"project": PROJECT, "flows": flows}


def build_job(job_id: str, flow: str, status: str, updated_at: float) -> dict:
    return {
        "id": job_id,
        "type": f"run_{flow}",
        "status": status,
        "created_at": updated_at,
        "updated_at": updated_at,
        "project": PROJECT,
    }


def route_api(page: Page, jobs: list, flow_status: dict, assets=None) -> None:
    def handle_api(route) -> None:
        url = route.request.url
        if url.endswith("/api/projects"):
            route.fulfill(status=200, body=json.dumps({"projects": [PROJECT], "default_project": PROJECT}))
            return
        if f"/api/projects/{PROJECT}/jobs" in url:
            route.fulfill(status=200, body=json.dumps({"project": PROJECT, "jobs": jobs}))
            return
        if url.endswith(f"/api/projects/{PROJECT}/flow-status"):
            body = flow_status if flow_status is not None else {"project": PROJECT, "flows": {}}
            route.fulfill(status=200, body=json.dumps(body))
            return
        if url.endswith(f"/api/projects/{PROJECT}/assets"):
            route.fulfill(status=200, body=json.dumps(assets or {}))
            return
        if f"/api/projects/{PROJECT}/flow/" in url and url.endswith("/pending"):
            route.fulfill(status=200, body=json.dumps({"ok": True}))
            return
        if f"/api/projects/{PROJECT}/flow/" in url and url.endswith("/pending/clear"):
            route.fulfill(status=200, body=json.dumps({"ok": True}))
            return
        route.fulfill(status=200, body=json.dumps({}))

    page.route("**/api/**", handle_api)


class TestJobCardOptimizationContracts:
    def test_projects_api_contract(self) -> None:
        try:
            res = requests.get(f"{BASE_URL}/api/projects", timeout=2)
        except requests.RequestException:
            pytest.skip("server_not_ready")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data.get("projects"), list)
        assert "default_project" in data


class TestJobCardOptimizationFrontend:
    def test_card_hidden_when_waiting_and_not_touched(self, page: Page) -> None:
        page.add_init_script("localStorage.removeItem('manju_flow_touched')")
        route_api(page, [], build_flow_status())
        page.goto(f"{BASE_URL}/?project={PROJECT}&tab=batch")
        expect(page.get_by_text("暂无任务")).to_be_visible()
        expect(page.locator(".job-item")).to_have_count(0)

    def test_card_visible_after_click_flow_button(self, page: Page) -> None:
        page.add_init_script("localStorage.removeItem('manju_flow_touched')")
        route_api(page, [], build_flow_status())
        page.goto(f"{BASE_URL}/?project={PROJECT}&tab=batch")
        btn = page.get_by_role("button", name="角色与素材生成")
        expect(btn).to_be_enabled()
        btn.click()
        expect(page.locator(".job-item[data-status='pending']")).to_be_visible()
        touched = page.evaluate("JSON.parse(localStorage.getItem('manju_flow_touched') || '{}')")
        assert touched.get(PROJECT, {}).get("visual_audio_assets") is True

    def test_card_hidden_when_project_fresh_even_if_touched(self, page: Page) -> None:
        page.add_init_script(
            "localStorage.setItem('manju_flow_touched', JSON.stringify({'ms3': {'visual_audio_assets': true}}))"
        )
        route_api(page, [], build_flow_status())
        page.goto(f"{BASE_URL}/?project={PROJECT}&tab=batch")
        expect(page.get_by_text("暂无任务")).to_be_visible()
        touched = page.evaluate("JSON.parse(localStorage.getItem('manju_flow_touched') || '{}')")
        assert PROJECT not in touched

    def test_partial_completed_hint_visible(self, page: Page) -> None:
        jobs = [build_job("job_va", "visual_audio_assets", "running", 1000)]
        flow_status_first = build_flow_status(
            {
                "visual_audio_assets": {
                    "status": "running",
                    "steps": {
                        "build_prompts": "completed",
                        "generate_images": "running",
                        "generate_tts": "waiting",
                        "upload_assets": "waiting",
                    },
                }
            }
        )
        flow_status_after = build_flow_status(
            {
                "visual_audio_assets": {
                    "status": "running",
                    "steps": {
                        "build_prompts": "completed",
                        "generate_images": "partial_completed",
                        "generate_tts": "waiting",
                        "upload_assets": "waiting",
                    },
                }
            }
        )
        route_api(page, jobs, flow_status_first)
        page.goto(f"{BASE_URL}/?project={PROJECT}&tab=batch")
        page.unroute("**/api/**")
        route_api(page, jobs, flow_status_after)
        page.reload()
        expect(page.get_by_text("阶段部分完成", exact=False)).to_be_visible()

    def test_flow_button_disabled_when_pending(self, page: Page) -> None:
        flow_status = build_flow_status({"visual_audio_assets": {"status": "pending", "steps": {}}})
        route_api(page, [], flow_status)
        page.goto(f"{BASE_URL}/?project={PROJECT}&tab=batch")
        btn = page.get_by_role("button", name="角色与素材生成")
        expect(btn).to_be_disabled()
        expect(btn).to_have_attribute("title", "任务进行中/已触发")

    def test_cloth_tree_not_completed_when_cloth_changed_waiting(self, page: Page) -> None:
        jobs = [build_job("job_va", "visual_audio_assets", "success", 1000)]
        flow_status = build_flow_status(
            {
                "visual_audio_assets": {
                    "status": "running",
                    "steps": {
                        "download_assets": "completed",
                        "build_prompts": "completed",
                        "generate_images": "running",
                        "generate_tts": "waiting",
                        "upload_assets": "waiting",
                        "character_prompts": "completed",
                        "location_prompts": "completed",
                        "fenjing_prompts": "completed",
                        "character_images": "completed",
                        "location_images": "completed",
                        "cloth_images": "completed",
                        "cloth_changed": "waiting",
                        "tts": "waiting",
                    },
                }
            }
        )
        route_api(page, jobs, flow_status)
        page.goto(f"{BASE_URL}/?project={PROJECT}&tab=batch")
        status = page.locator('.tree-node-card[data-node="cloth_images"] .tree-node-status')
        expect(status).not_to_have_text("已完成")

    def test_backend_down_graceful_handling(self, page: Page) -> None:
        def handle_route(route):
            route.fulfill(status=500, body=json.dumps({"error": "server_error"}))

        page.route("**/api/**", handle_route)
        page.goto(f"{BASE_URL}/?project={PROJECT}&tab=batch")
        page.wait_for_timeout(1000)
        expect(page).not_to_have_url("about:blank")
        page.unroute("**/api/**", handle_route)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
