"""
测试脚本：验证鉴权配置加载逻辑修复

测试范围：
1. API 验证: GET /api/config/auth 返回 source="global" 而非 "runtime"
2. API 验证: PATCH /api/config/auth 正确保存配置到 global_auth.json
3. UI 验证: 使用 Playwright 模拟用户修改配置并刷新页面
4. VLM 验证: 截图并使用 VLM 识别页面上的配置值

边界条件:
- 环境变量存在时不应影响配置加载
- 敏感配置项正确脱敏显示
"""

import json
import os
import time
import pytest
import requests
from playwright.sync_api import Page, expect

BASE_URL = "http://127.0.0.1:8086"
AUTH_CONFIG_URL = f"{BASE_URL}/auth-config"
API_AUTH_URL = f"{BASE_URL}/api/config/auth"

# 测试数据
TEST_EP_VALUE = f"ep-test-{int(time.time())}-vlm"
TEST_CONFIG_ITEM = "auth.video_model_1_5_ep"


class TestAuthConfigAPI:
    """API 测试类"""

    def test_get_auth_config_source_is_global(self):
        """验证 GET /api/config/auth 返回 source=global 而非 runtime"""
        response = requests.get(API_AUTH_URL)
        assert response.status_code == 200
        
        data = response.json()
        assert "items" in data
        
        # 查找 video_model_1_5_ep 配置项
        video_model_item = None
        for item in data["items"]:
            if item.get("id") == TEST_CONFIG_ITEM:
                video_model_item = item
                break
        
        assert video_model_item is not None, f"未找到配置项 {TEST_CONFIG_ITEM}"
        assert video_model_item.get("source") == "global", \
            f"配置项 source 应为 'global'，实际为 '{video_model_item.get('source')}'"
        
        print(f"✓ 配置项 {TEST_CONFIG_ITEM} 的 source 为 '{video_model_item.get('source')}'")

    def test_patch_auth_config_saves_to_json(self):
        """验证 PATCH /api/config/auth 正确保存配置到 global_auth.json"""
        # 发送 PATCH 请求修改配置
        # 注意: API 期望的字段是 "items" 而不是 "updates"
        payload = {
            "scope": "global",
            "items": {
                TEST_CONFIG_ITEM: TEST_EP_VALUE
            }
        }
        
        response = requests.patch(API_AUTH_URL, json=payload)
        assert response.status_code == 200, f"PATCH 请求失败: {response.text}"
        
        # 验证 global_auth.json 文件
        config_path = "/Users/bytedance/Desktop/常见python/manju_web/backend/config/global_auth.json"
        with open(config_path, "r") as f:
            config = json.load(f)
        
        assert "items" in config
        assert config["items"].get(TEST_CONFIG_ITEM) == TEST_EP_VALUE, \
            f"global_auth.json 中 {TEST_CONFIG_ITEM} 应为 '{TEST_EP_VALUE}'"
        
        print(f"✓ 配置已保存到 global_auth.json: {TEST_CONFIG_ITEM} = {TEST_EP_VALUE}")

    def test_auth_config_not_affected_by_env(self):
        """验证环境变量不影响配置加载"""
        # 设置环境变量（模拟干扰）
        env_var = "VIDEO_MODEL_1_5_EP"
        original_value = os.environ.get(env_var)
        os.environ[env_var] = "env-interference-value"
        
        try:
            response = requests.get(API_AUTH_URL)
            assert response.status_code == 200
            
            data = response.json()
            video_model_item = None
            for item in data["items"]:
                if item.get("id") == TEST_CONFIG_ITEM:
                    video_model_item = item
                    break
            
            assert video_model_item is not None
            # 配置值应来自 JSON 文件，而非环境变量
            assert video_model_item.get("value") != "env-interference-value", \
                "配置值不应受环境变量影响"
            assert video_model_item.get("source") == "global", \
                "配置 source 应为 'global'"
            
            print(f"✓ 环境变量未影响配置加载")
        finally:
            # 恢复环境变量
            if original_value is not None:
                os.environ[env_var] = original_value
            else:
                os.environ.pop(env_var, None)


class TestAuthConfigUI:
    """UI 测试类（使用 Playwright）"""

    def test_auth_config_page_loads(self, page: Page):
        """验证配置页面正常加载"""
        page.goto(AUTH_CONFIG_URL)
        
        # 验证页面标题（实际标题是"配置"，使用 .title 类）
        expect(page.locator(".title")).to_contain_text("配置")
        
        # 验证 video_model_1_5_ep 输入框存在
        # 注意: 视频模型配置使用 data-video-model-id 属性
        video_input = page.locator('input[data-video-model-id="auth.video_model_1_5_ep"]')
        expect(video_input).to_be_visible()
        
        print("✓ 配置页面正常加载")

    def test_modify_and_refresh_config(self, page: Page):
        """验证修改配置后刷新页面显示一致"""
        test_value = f"ep-test-{int(time.time())}"
        
        # 1. 访问配置页面
        page.goto(AUTH_CONFIG_URL)
        
        # 2. 修改 video_model_1_5_ep 输入框
        # 注意: 视频模型配置使用 data-video-model-id 属性
        video_input = page.locator('input[data-video-model-id="auth.video_model_1_5_ep"]')
        video_input.fill(test_value)
        
        # 3. 点击视频模型配置的保存按钮
        # 注意: 页面有两个保存按钮，使用 ID 区分
        save_button = page.locator('#saveVideoModelConfig')
        save_button.click()
        
        # 4. 等待保存成功提示（视频模型配置显示"已保存并生效"）
        page.wait_for_selector("text=已保存并生效", timeout=5000)
        
        # 5. 刷新页面
        page.reload()
        
        # 6. 验证输入框显示的值与修改一致
        # 注意: 视频模型配置使用 data-video-model-id 属性
        video_input = page.locator('input[data-video-model-id="auth.video_model_1_5_ep"]')
        expect(video_input).to_have_value(test_value)
        
        print(f"✓ 修改配置后刷新页面显示一致: {test_value}")


class TestAuthConfigVLM:
    """VLM 验证类（截图并使用 VLM 识别）"""

    def _load_vlm_config_from_json(self) -> dict:
        """从 global_auth.json 加载 VLM 配置"""
        config_path = "/Users/bytedance/Desktop/常见python/manju_web/backend/config/global_auth.json"
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
            items = config.get("items", {})
            return {
                "base_url": items.get("auth.ark_base_url", "https://ark.cn-beijing.volces.com/api/v3"),
                "api_key": items.get("auth.ark_api_key", ""),
                "model": items.get("auth.ark_vlm_model", "")
            }
        except Exception as e:
            print(f"⚠ 从 JSON 加载配置失败: {e}")
            return {}

    def _call_vlm(self, image_path: str, prompt: str, base_url: str = None, api_key: str = None, model: str = None) -> dict:
        """
        调用 VLM API 分析截图
        
        Args:
            image_path: 截图文件路径
            prompt: 发送给 VLM 的提示词
            base_url: VLM API 基础 URL
            api_key: API 密钥
            model: 模型名称
        
        Returns:
            VLM 返回的 JSON 响应
        """
        import base64
        import mimetypes
        
        # 优先从参数读取，其次从环境变量，最后从 global_auth.json
        json_config = self._load_vlm_config_from_json()
        
        base_url = base_url or os.environ.get("ARK_BASE_URL") or json_config.get("base_url", "https://ark.cn-beijing.volces.com/api/v3")
        api_key = api_key or os.environ.get("ARK_API_KEY") or json_config.get("api_key", "")
        model = model or os.environ.get("ARK_VLM_MODEL") or json_config.get("model", "")
        
        # 验证 API 密钥不为空
        if not api_key:
            raise ValueError("ARK_API_KEY 未配置，请检查环境变量或 global_auth.json")
        
        # 读取图片并编码为 base64
        mime, _ = mimetypes.guess_type(image_path)
        if not mime:
            mime = "image/png"
        
        with open(image_path, "rb") as f:
            image_base64 = base64.b64encode(f.read()).decode("utf-8")
        
        # 构建请求体
        url = f"{base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime};base64,{image_base64}"
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ]
        }
        
        # 发送请求
        response = requests.post(url, headers=headers, json=payload, timeout=180)
        response.raise_for_status()
        return response.json()

    def test_vlm_verify_config_after_refresh(self, page: Page):
        """
        使用 VLM 验证保存后刷新的结果
        
        步骤:
        1. 生成随机测试数据
        2. 填写到 video_model_1_5_ep 输入框
        3. 点击保存
        4. 刷新页面
        5. 截图并使用 VLM 识别页面上的配置值
        6. 验证识别结果与输入一致
        """
        # 生成随机测试数据
        test_value = f"ep-vlm-{int(time.time())}"
        
        # 1. 访问配置页面
        page.goto(AUTH_CONFIG_URL)
        page.wait_for_load_state("networkidle")
        
        # 2. 修改 video_model_1_5_ep 输入框
        # 注意: 视频模型配置使用 data-video-model-id 属性
        video_input = page.locator('input[data-video-model-id="auth.video_model_1_5_ep"]')
        video_input.fill(test_value)
        
        # 3. 点击视频模型配置的保存按钮
        # 注意: 页面有两个保存按钮，使用 ID 区分
        save_button = page.locator('#saveVideoModelConfig')
        save_button.click()
        
        # 4. 等待保存成功（视频模型配置显示"已保存并生效"）
        page.wait_for_selector("text=已保存并生效", timeout=5000)
        
        # 5. 刷新页面
        page.reload()
        page.wait_for_load_state("networkidle")
        
        # 6. 截图
        screenshot_path = "/Users/bytedance/Desktop/常见python/manju_web/backend/tests/snapshots/auth_config_after_refresh.png"
        page.screenshot(path=screenshot_path, full_page=True)
        
        print(f"✓ 截图已保存: {screenshot_path}")
        print(f"✓ 测试数据: {test_value}")
        
        # 7. 使用 VLM 验证截图中的配置值
        # 构建提示词，要求 VLM 识别页面上的 video_model_1_5_ep 配置值
        vlm_prompt = f"""请分析这张截图，找到 "video_model_1_5_ep" 配置项对应的输入框中的值。

要求：
1. 在截图中找到标签为 "video_model_1_5_ep" 或 "Video Model 1.5 EP" 的输入框
2. 读取该输入框中的值
3. 以 JSON 格式返回结果：{{"value": "输入框中的值"}}

注意：
- 只需要返回 JSON 格式数据，不要其他解释
- 如果找不到该配置项，返回 {{"value": null}}
"""
        
        # 调用 VLM 进行验证（必须实际调用，失败则测试失败）
        vlm_response = self._call_vlm(screenshot_path, vlm_prompt)
        
        # 解析 VLM 响应
        content = vlm_response.get("choices", [{}])[0].get("message", {}).get("content", "")
        print(f"VLM 响应: {content}")
        
        # 从响应中提取 JSON
        import re
        # 匹配 JSON 对象，支持嵌套大括号
        json_match = re.search(r'\{[^{}]*"value"[^{}]*\}', content)
        if not json_match:
            # 尝试更宽松的匹配
            json_match = re.search(r'\{.*"value".*\}', content, re.DOTALL)
        assert json_match is not None, f"VLM 响应中未找到 JSON 数据，响应内容: {content}"
        
        result = json.loads(json_match.group(0))
        recognized_value = result.get("value")
        
        # 验证 VLM 识别的值与输入一致
        assert recognized_value == test_value, \
            f"VLM 识别的值应为 '{test_value}'，实际为 '{recognized_value}'"
        print(f"✓ VLM 验证通过: 识别值 = {recognized_value}")
        
        # 8. 使用 API 验证作为兜底
        response = requests.get(API_AUTH_URL)
        data = response.json()
        
        video_model_item = None
        for item in data["items"]:
            if item.get("id") == TEST_CONFIG_ITEM:
                video_model_item = item
                break
        
        assert video_model_item is not None
        assert video_model_item.get("value") == test_value, \
            f"API 返回的配置值应为 '{test_value}'，实际为 '{video_model_item.get('value')}'"
        assert video_model_item.get("source") == "global", \
            f"API 返回的 source 应为 'global'，实际为 '{video_model_item.get('source')}'"
        
        print(f"✓ API 验证通过: {TEST_CONFIG_ITEM} = {test_value}, source = global")


class TestAuthConfigSensitive:
    """敏感配置测试类"""

    def test_sensitive_config_masked(self, page: Page):
        """验证敏感配置项正确脱敏显示"""
        page.goto(AUTH_CONFIG_URL)
        
        # 查找敏感配置项（如 ark_api_key）
        sensitive_input = page.locator('input[data-config-id="auth.ark_api_key"]')
        
        # 如果存在，验证其值为空（脱敏）
        if sensitive_input.count() > 0:
            input_value = sensitive_input.input_value()
            # 敏感配置项应显示为空或占位符
            assert input_value == "", f"敏感配置项应脱敏显示，实际值为 '{input_value}'"
            print("✓ 敏感配置项正确脱敏显示")


def test_full_workflow():
    """
    完整工作流测试
    
    验证整个配置修改流程:
    1. 获取当前配置
    2. 修改配置
    3. 验证保存成功
    4. 验证刷新后显示一致
    5. 验证 source 为 global
    """
    test_value = f"ep-workflow-{int(time.time())}"
    
    # 1. 获取当前配置
    response = requests.get(API_AUTH_URL)
    assert response.status_code == 200
    original_data = response.json()
    
    # 2. 修改配置
    # 注意: API 期望的字段是 "items" 而不是 "updates"
    payload = {
        "scope": "global",
        "items": {
            TEST_CONFIG_ITEM: test_value
        }
    }
    response = requests.patch(API_AUTH_URL, json=payload)
    assert response.status_code == 200
    
    # 3. 验证保存成功
    response = requests.get(API_AUTH_URL)
    data = response.json()
    
    video_model_item = None
    for item in data["items"]:
        if item.get("id") == TEST_CONFIG_ITEM:
            video_model_item = item
            break
    
    assert video_model_item is not None
    assert video_model_item.get("value") == test_value
    assert video_model_item.get("source") == "global"
    
    print(f"✓ 完整工作流测试通过")
    print(f"  - 配置项: {TEST_CONFIG_ITEM}")
    print(f"  - 值: {test_value}")
    print(f"  - 来源: {video_model_item.get('source')}")


if __name__ == "__main__":
    # 运行 API 测试
    print("=" * 50)
    print("开始 API 测试")
    print("=" * 50)
    
    api_tests = TestAuthConfigAPI()
    api_tests.test_get_auth_config_source_is_global()
    api_tests.test_patch_auth_config_saves_to_json()
    api_tests.test_auth_config_not_affected_by_env()
    
    print("\n" + "=" * 50)
    print("开始完整工作流测试")
    print("=" * 50)
    test_full_workflow()
    
    print("\n" + "=" * 50)
    print("所有测试通过!")
    print("=" * 50)
