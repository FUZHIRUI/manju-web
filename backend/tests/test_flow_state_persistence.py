import pytest
import requests
import json
import time
from pathlib import Path

BASE_URL = "http://127.0.0.1:8086"
PROJECT = "ms3"

class TestFlowStatePersistence:
    
    def test_01_create_pending_state(self):
        """验证创建 pending 状态"""
        resp = requests.post(f"{BASE_URL}/api/projects/{PROJECT}/flow/visual_audio_assets/pending")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert data.get("status") == "pending", f"Expected pending, got {data}"
        print("[PASS] 创建 pending 状态成功")
    
    def test_02_get_flow_state_has_pending(self):
        """验证 flow-state 返回 pending 状态"""
        resp = requests.get(f"{BASE_URL}/api/projects/{PROJECT}/flow-status")
        assert resp.status_code == 200
        data = resp.json()
        flows = data.get("flows", {})
        va_flow = flows.get("visual_audio_assets", {})
        assert va_flow.get("status") == "pending", f"Expected pending, got {va_flow.get('status')}"
        print("[PASS] flow-state 返回 pending 状态")
    
    def test_03_clear_pending_state(self):
        """验证清除 pending 状态"""
        resp = requests.post(f"{BASE_URL}/api/projects/{PROJECT}/flow/visual_audio_assets/pending/clear")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert data.get("status") == "cleared", f"Expected cleared, got {data}"
        print("[PASS] 清除 pending 状态成功")
    
    def test_04_flow_state_after_clear(self):
        """验证清除后状态变为 waiting"""
        resp = requests.get(f"{BASE_URL}/api/projects/{PROJECT}/flow-status")
        assert resp.status_code == 200
        data = resp.json()
        flows = data.get("flows", {})
        va_flow = flows.get("visual_audio_assets", {})
        assert va_flow.get("status") == "waiting", f"Expected waiting, got {va_flow.get('status')}"
        print("[PASS] 清除后状态变为 waiting")
    
    def test_05_pending_state_persisted_to_file(self):
        """验证 pending 状态持久化到文件"""
        flow_state_file = Path(f"/Users/bytedance/Desktop/常见python/manju_web/manju_output/{PROJECT}/flow_state.json")
        assert flow_state_file.exists(), "flow_state.json 不存在"
        
        requests.post(f"{BASE_URL}/api/projects/{PROJECT}/flow/visual_audio_assets/pending")
        
        with open(flow_state_file, "r") as f:
            data = json.load(f)
        
        flows = data.get("flows", {})
        va_flow = flows.get("visual_audio_assets", {})
        assert va_flow.get("status") == "pending", f"文件中状态应为 pending，实际为 {va_flow.get('status')}"
        print("[PASS] pending 状态已持久化到文件")
        
        requests.post(f"{BASE_URL}/api/projects/{PROJECT}/flow/visual_audio_assets/pending/clear")


class TestStatusConstants:
    
    def test_status_constants_exist(self):
        """验证新增状态常量存在"""
        from backend.services import status_service
        
        assert hasattr(status_service, "_STATUS_PENDING"), "缺少 _STATUS_PENDING"
        assert hasattr(status_service, "_STATUS_PARTIAL_RETURNED"), "缺少 _STATUS_PARTIAL_RETURNED"
        assert hasattr(status_service, "_STATUS_PARTIAL_COMPLETED"), "缺少 _STATUS_PARTIAL_COMPLETED"
        
        assert status_service._STATUS_PENDING == "pending"
        assert status_service._STATUS_PARTIAL_RETURNED == "partial_returned"
        assert status_service._STATUS_PARTIAL_COMPLETED == "partial_completed"
        print("[PASS] 状态常量定义正确")
    
    def test_partial_steps_config(self):
        """验证 _PARTIAL_STEPS 配置"""
        from backend.services import status_service
        
        assert hasattr(status_service, "_PARTIAL_STEPS"), "缺少 _PARTIAL_STEPS"
        
        partial_steps = status_service._PARTIAL_STEPS
        assert "visual_audio_assets" in partial_steps
        assert "fenjing" in partial_steps
        assert "video" in partial_steps
        
        va_partial = partial_steps["visual_audio_assets"]
        assert "character_images" in va_partial, "character_images 应在 partial_steps 中"
        assert "location_images" in va_partial, "location_images 应在 partial_steps 中"
        assert "tts" in va_partial, "tts 应在 partial_steps 中"
        print("[PASS] _PARTIAL_STEPS 配置正确")


class TestNormalizeStateOnStartup:
    
    def test_normalize_running_to_error(self):
        """验证 running 状态在启动时转换为 error"""
        from backend.services import status_service
        from backend.repositories import status_repo
        
        state = status_service._default_flow_state(PROJECT)
        state["flows"]["visual_audio_assets"]["status"] = "running"
        state["flows"]["visual_audio_assets"]["steps"]["character_prompts"] = "running"
        status_repo.write_flow_state(PROJECT, state)
        
        status_service.normalize_state_on_startup(PROJECT)
        
        result = status_repo.read_flow_state(PROJECT)
        va_flow = result.get("flows", {}).get("visual_audio_assets", {})
        
        assert va_flow.get("status") == "error", f"大阶段状态应为 error，实际为 {va_flow.get('status')}"
        
        steps = va_flow.get("steps", {})
        assert steps.get("character_prompts") == "error", f"小阶段状态应为 error，实际为 {steps.get('character_prompts')}"
        print("[PASS] running 状态正确转换为 error")
    
    def test_normalize_partial_returned_to_partial_completed(self):
        """验证 partial_returned 状态转换为 partial_completed"""
        from backend.services import status_service
        from backend.repositories import status_repo
        
        state = status_service._default_flow_state(PROJECT)
        state["flows"]["visual_audio_assets"]["steps"]["character_images"] = "partial_returned"
        status_repo.write_flow_state(PROJECT, state)
        
        status_service.normalize_state_on_startup(PROJECT)
        
        result = status_repo.read_flow_state(PROJECT)
        va_flow = result.get("flows", {}).get("visual_audio_assets", {})
        steps = va_flow.get("steps", {})
        
        assert steps.get("character_images") == "partial_completed", f"状态应为 partial_completed，实际为 {steps.get('character_images')}"
        print("[PASS] partial_returned 正确转换为 partial_completed")


class TestAPIEndpoints:
    
    def test_pending_api_for_invalid_flow(self):
        """验证无效 flow 返回 400"""
        resp = requests.post(f"{BASE_URL}/api/projects/{PROJECT}/flow/invalid_flow/pending")
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
        print("[PASS] 无效 flow 返回 400")
    
    def test_pending_clear_api_for_invalid_flow(self):
        """验证无效 flow 清除返回 400"""
        resp = requests.post(f"{BASE_URL}/api/projects/{PROJECT}/flow/invalid_flow/pending/clear")
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
        print("[PASS] 无效 flow 清除返回 400")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
