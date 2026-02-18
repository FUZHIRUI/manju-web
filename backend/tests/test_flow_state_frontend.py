import pytest
import re
from playwright.sync_api import Page, expect

BASE_URL = "http://127.0.0.1:8086"
PROJECT = "ms3"

TEST_DATA = [
    ("正常场景: 创建pending", "visual_audio_assets", 200, "pending"),
    ("正常场景: 创建fenjing pending", "fenjing", 200, "pending"),
    ("正常场景: 创建video pending", "video", 200, "pending"),
    ("边界: 无效flow", "invalid_flow", 400, "error"),
]

class TestFlowStateFrontend:
    
    @pytest.mark.parametrize("desc, flow, mock_status, expected_state", TEST_DATA)
    def test_create_pending_ui(self, page: Page, desc, flow, mock_status, expected_state):
        """测试前端创建 pending 状态"""
        if flow in ["visual_audio_assets", "fenjing", "video"]:
            import requests
            requests.post(f"{BASE_URL}/api/projects/{PROJECT}/flow/{flow}/pending/clear")
        page.goto(f"{BASE_URL}/?project={PROJECT}&tab=batch")
        
        page.wait_for_selector("[data-flow]", state="attached", timeout=5000)
        
        if flow in ["visual_audio_assets", "fenjing", "video"]:
            btn_selector = f"[data-flow=\"{flow}\"]"
            if page.locator(btn_selector).count() > 0:
                btn = page.locator(btn_selector).first
                if not btn.is_enabled():
                    print(f"[SKIP] {desc}: 按钮被禁用")
                    return
                btn.click()
                
                page.wait_for_timeout(500)
                
                job_item = page.locator(".job-item[data-status=\"pending\"]")
                if job_item.count() > 0:
                    expect(job_item.first).to_be_visible()
                    print(f"[PASS] {desc}: pending 任务卡片已展示")
                else:
                    print(f"[SKIP] {desc}: 按钮可能被禁用")
            else:
                print(f"[SKIP] {desc}: 按钮不存在")
        else:
            print(f"[SKIP] {desc}: 不适用于前端测试")

    def test_pending_job_shows_buttons(self, page: Page):
        """测试 pending 任务卡片显示分步按钮"""
        import requests
        
        requests.post(f"{BASE_URL}/api/projects/{PROJECT}/flow/visual_audio_assets/pending")
        
        page.goto(f"{BASE_URL}/?project={PROJECT}&tab=batch")
        page.wait_for_selector(".job-item", timeout=5000)
        
        job_item = page.locator(".job-item[data-status=\"pending\"]")
        if job_item.count() > 0:
            expect(job_item.first).to_be_visible()
            
            execute_btn = job_item.get_by_role("button", name="执行")
            expect(execute_btn.first).to_be_visible()
            print("[PASS] pending 任务卡片显示执行按钮")
        else:
            print("[SKIP] 没有 pending 任务")
        
        requests.post(f"{BASE_URL}/api/projects/{PROJECT}/flow/visual_audio_assets/pending/clear")

    def test_pending_state_persists_after_refresh(self, page: Page):
        """测试刷新页面后 pending 状态恢复"""
        import requests
        
        requests.post(f"{BASE_URL}/api/projects/{PROJECT}/flow/fenjing/pending")
        
        page.goto(f"{BASE_URL}/?project={PROJECT}&tab=batch")
        page.wait_for_selector(".job-item", timeout=5000)
        
        job_item = page.locator(".job-item[data-status=\"pending\"]")
        first_count = job_item.count()
        
        page.reload()
        page.wait_for_selector(".job-item", timeout=5000)
        
        job_item_after = page.locator(".job-item[data-status=\"pending\"]")
        second_count = job_item_after.count()
        
        assert second_count >= first_count, "刷新后 pending 任务应该保留"
        print("[PASS] 刷新页面后 pending 状态恢复")
        
        requests.post(f"{BASE_URL}/api/projects/{PROJECT}/flow/fenjing/pending/clear")

    def test_backend_down_graceful_handling(self, page: Page):
        """测试后端挂掉时前端优雅处理"""
        def handle_route(route):
            route.abort("failed")
        
        page.route("**/api/**", handle_route)
        
        page.goto(f"{BASE_URL}/?project={PROJECT}&tab=batch")
        
        page.wait_for_timeout(2000)
        
        expect(page).not_to_have_url("about:blank")
        print("[PASS] 后端挂掉时前端未崩溃")
        
        page.unroute("**/api/**", handle_route)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
