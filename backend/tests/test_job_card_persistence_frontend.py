import json

import pytest
from playwright.sync_api import Page, expect

BASE_URL = "http://127.0.0.1:8086"
PROJECT = "ms3"


def build_job(job_id: str, flow: str, status: str, updated_at: float) -> dict:
    return {
        "id": job_id,
        "type": f"run_{flow}",
        "status": status,
        "created_at": updated_at,
        "updated_at": updated_at,
        "project": PROJECT,
    }


@pytest.mark.parametrize("count", [2, 6])
def test_job_cards_persist_and_limit(page: Page, count: int) -> None:
    flows = ["auto_storyboard", "visual_audio_assets", "fenjing", "video"]
    jobs = [build_job(f"job_{idx}", flows[idx % len(flows)], "success", 1000 + idx) for idx in range(count)]
    cache_key = f"manju_jobs_cache_{PROJECT}"

    cache_value = json.dumps(jobs).replace("\\", "\\\\").replace("'", "\\'")
    page.add_init_script(
        script=f"localStorage.setItem('{cache_key}', '{cache_value}');",
    )

    def handle_api(route) -> None:
        url = route.request.url
        if url.endswith("/api/projects"):
            route.fulfill(status=200, body=json.dumps({"projects": [PROJECT], "default_project": PROJECT}))
            return
        if url.endswith(f"/api/projects/{PROJECT}/jobs"):
            route.fulfill(status=200, body=json.dumps({"project": PROJECT, "jobs": []}))
            return
        if url.endswith(f"/api/projects/{PROJECT}/flow-status"):
            route.fulfill(status=200, body=json.dumps({"project": PROJECT, "flows": {}}))
            return
        route.fulfill(status=200, body=json.dumps({}))

    page.route("**/api/**", handle_api)
    page.goto(f"{BASE_URL}/?project={PROJECT}&tab=batch")
    page.wait_for_selector(".job-item", timeout=5000)

    job_cards = page.locator(".job-item")
    unique_flows = len({job["type"] for job in jobs})
    expected = min(unique_flows, 4)
    expect(job_cards).to_have_count(expected)
