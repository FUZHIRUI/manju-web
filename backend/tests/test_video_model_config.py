"""
视频模型端点配置测试脚本
测试范围:
- API: /api/config/auth (GET, PATCH)
- 配置持久化和运行时同步
- 配置验证和错误处理
"""

import json
import pytest
import requests
from pathlib import Path

BASE_URL = "http://127.0.0.1:8086"
CONFIG_FILE = Path(__file__).parents[2] / "config" / "global_auth_config.json"


class TestVideoModelConfigAPI:
    """视频模型配置API测试"""
    
    def setup_method(self):
        """每个测试方法前执行：保存原始配置"""
        self.original_config = None
        if CONFIG_FILE.exists():
            self.original_config = CONFIG_FILE.read_text()
    
    def teardown_method(self):
        """每个测试方法后执行：恢复原始配置"""
        if self.original_config is not None:
            CONFIG_FILE.write_text(self.original_config)
        elif CONFIG_FILE.exists():
            CONFIG_FILE.unlink()
    
    def test_get_auth_config_includes_video_model(self):
        """TC-002: 获取配置API返回视频模型配置"""
        resp = requests.get(f"{BASE_URL}/api/config/auth")
        assert resp.status_code == 200, f"期望状态码200，实际{resp.status_code}"
        
        data = resp.json()
        assert "items" in data, "响应应包含items字段"
        
        items = data["items"]
        video_model_ids = ["auth.video_model_1_5_ep", "auth.video_model_1_0_ep"]
        
        # 验证包含视频模型配置项
        found_items = [item for item in items if item["id"] in video_model_ids]
        assert len(found_items) == 2, f"应包含两个视频模型配置项，实际找到{len(found_items)}个"
        
        # 验证配置项结构
        for item in found_items:
            assert "id" in item, "配置项应包含id"
            assert "stage" in item, "配置项应包含stage"
            assert "key" in item, "配置项应包含key"
            assert "type" in item, "配置项应包含type"
            assert "value" in item, "配置项应包含value"
            assert "source" in item, "配置项应包含source"
            assert "default" in item, "配置项应包含default"
            assert "description" in item, "配置项应包含description"
            assert "sensitive" in item, "配置项应包含sensitive"
            
            # 验证类型
            assert item["type"] == "string", f"配置项类型应为string，实际为{item['type']}"
            assert item["sensitive"] == False, "配置项不应为敏感类型"
            assert item["stage"] == "video", f"配置项stage应为video，实际为{item['stage']}"
    
    def test_update_video_model_1_5_config(self):
        """TC-004: 更新视频模型1.5配置"""
        test_value = "ep-20250101-test456"
        
        resp = requests.patch(
            f"{BASE_URL}/api/config/auth",
            json={
                "scope": "global",
                "items": {
                    "auth.video_model_1_5_ep": test_value
                }
            }
        )
        assert resp.status_code == 200, f"期望状态码200，实际{resp.status_code}"
        
        data = resp.json()
        assert "items" in data, "响应应包含items字段"
        
        # 验证更新后的值
        video_1_5_item = next(
            (item for item in data["items"] if item["id"] == "auth.video_model_1_5_ep"),
            None
        )
        assert video_1_5_item is not None, "应返回video_model_1_5_ep配置项"
        assert video_1_5_item["value"] == test_value, f"配置值应为{test_value}，实际为{video_1_5_item['value']}"
        assert video_1_5_item["source"] == "global", f"配置来源应为global，实际为{video_1_5_item['source']}"
    
    def test_update_video_model_1_0_config(self):
        """更新视频模型1.0配置"""
        test_value = "ep-20250101-test789"
        
        resp = requests.patch(
            f"{BASE_URL}/api/config/auth",
            json={
                "scope": "global",
                "items": {
                    "auth.video_model_1_0_ep": test_value
                }
            }
        )
        assert resp.status_code == 200
        
        data = resp.json()
        video_1_0_item = next(
            (item for item in data["items"] if item["id"] == "auth.video_model_1_0_ep"),
            None
        )
        assert video_1_0_item is not None
        assert video_1_0_item["value"] == test_value
    
    def test_update_both_video_model_configs(self):
        """同时更新两个视频模型配置"""
        test_values = {
            "auth.video_model_1_5_ep": "ep-20250101-model15",
            "auth.video_model_1_0_ep": "ep-20250101-model10"
        }
        
        resp = requests.patch(
            f"{BASE_URL}/api/config/auth",
            json={
                "scope": "global",
                "items": test_values
            }
        )
        assert resp.status_code == 200
        
        data = resp.json()
        for item in data["items"]:
            if item["id"] in test_values:
                assert item["value"] == test_values[item["id"]]
                assert item["source"] == "global"
    
    def test_reset_video_model_config(self):
        """TC-005: 重置视频模型配置"""
        # 先设置一个值
        requests.patch(
            f"{BASE_URL}/api/config/auth",
            json={
                "scope": "global",
                "items": {
                    "auth.video_model_1_5_ep": "ep-20250101-test123"
                }
            }
        )
        
        # 然后重置
        resp = requests.patch(
            f"{BASE_URL}/api/config/auth",
            json={
                "scope": "global",
                "items": {
                    "auth.video_model_1_5_ep": None
                }
            }
        )
        assert resp.status_code == 200
        
        data = resp.json()
        video_1_5_item = next(
            (item for item in data["items"] if item["id"] == "auth.video_model_1_5_ep"),
            None
        )
        assert video_1_5_item is not None
        # 重置后应为空值或默认值
        assert video_1_5_item["value"] == "", f"重置后值应为空字符串，实际为{video_1_5_item['value']}"
    
    def test_update_empty_string_config(self):
        """TC-007: 更新为空字符串"""
        resp = requests.patch(
            f"{BASE_URL}/api/config/auth",
            json={
                "scope": "global",
                "items": {
                    "auth.video_model_1_5_ep": ""
                }
            }
        )
        assert resp.status_code == 200
        
        data = resp.json()
        video_1_5_item = next(
            (item for item in data["items"] if item["id"] == "auth.video_model_1_5_ep"),
            None
        )
        assert video_1_5_item is not None
        assert video_1_5_item["value"] == ""
    
    def test_update_special_characters_config(self):
        """TC-008: 更新包含特殊字符的配置"""
        test_value = "ep-20250101-test!@#"
        
        resp = requests.patch(
            f"{BASE_URL}/api/config/auth",
            json={
                "scope": "global",
                "items": {
                    "auth.video_model_1_5_ep": test_value
                }
            }
        )
        assert resp.status_code == 200
        
        data = resp.json()
        video_1_5_item = next(
            (item for item in data["items"] if item["id"] == "auth.video_model_1_5_ep"),
            None
        )
        assert video_1_5_item is not None
        assert video_1_5_item["value"] == test_value
    
    def test_invalid_config_key(self):
        """测试无效的配置项ID"""
        resp = requests.patch(
            f"{BASE_URL}/api/config/auth",
            json={
                "scope": "global",
                "items": {
                    "auth.invalid_video_model_key": "some-value"
                }
            }
        )
        assert resp.status_code == 400, "无效配置项应返回400错误"
    
    def test_invalid_scope(self):
        """测试无效的scope"""
        resp = requests.patch(
            f"{BASE_URL}/api/config/auth",
            json={
                "scope": "invalid_scope",
                "items": {
                    "auth.video_model_1_5_ep": "some-value"
                }
            }
        )
        assert resp.status_code == 400, "无效scope应返回400错误"
    
    def test_config_persistence(self):
        """TC-010: 配置持久化验证"""
        test_value = "ep-20250101-persistent"
        
        # 设置配置
        requests.patch(
            f"{BASE_URL}/api/config/auth",
            json={
                "scope": "global",
                "items": {
                    "auth.video_model_1_5_ep": test_value
                }
            }
        )
        
        # 验证配置文件存在
        assert CONFIG_FILE.exists(), "配置文件应存在"
        
        # 验证文件内容
        config_data = json.loads(CONFIG_FILE.read_text())
        assert "items" in config_data, "配置文件应包含items"
        assert "global" in config_data["items"], "配置文件应包含global作用域"
        assert config_data["items"]["global"].get("auth.video_model_1_5_ep") == test_value


class TestVideoModelConfigIntegration:
    """视频模型配置集成测试"""
    
    def test_config_sync_to_runtime(self):
        """验证配置同步到runtime_config"""
        # 注意：此测试需要直接访问runtime_config模块
        # 实际测试时可能需要调整导入路径
        try:
            from backend.services.workflow_runtime import runtime_config
            
            test_value = "ep-20250101-runtime-test"
            
            # 更新配置
            requests.patch(
                f"{BASE_URL}/api/config/auth",
                json={
                    "scope": "global",
                    "items": {
                        "auth.video_model_1_5_ep": test_value
                    }
                }
            )
            
            # 验证runtime_config已更新
            assert runtime_config.VIDEO_MODEL_1_5_EP == test_value, \
                f"runtime_config.VIDEO_MODEL_1_5_EP应为{test_value}，实际为{runtime_config.VIDEO_MODEL_1_5_EP}"
        except ImportError:
            pytest.skip("无法导入runtime_config模块，跳过此测试")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
