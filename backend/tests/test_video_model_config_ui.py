"""
视频模型端点配置前端UI测试脚本
测试范围:
- 页面加载和显示
- 用户交互（输入、保存、刷新、重置）
- 配置实时更新和持久化

使用Playwright进行端到端测试
"""

import pytest
from playwright.sync_api import Page, expect

BASE_URL = "http://127.0.0.1:8086"


class TestVideoModelConfigUI:
    """视频模型配置UI测试"""
    
    @pytest.fixture(autouse=True)
    def setup_page(self, page: Page):
        """每个测试前访问配置页面"""
        page.goto(f"{BASE_URL}/auth-config")
        # 等待页面加载完成
        page.wait_for_selector("#videoModelConfigTable", state="visible")
    
    def test_video_model_section_display(self, page: Page):
        """TC-001: 页面加载显示视频模型配置区域"""
        # 验证视频模型配置标题
        expect(page.locator("text=视频模型配置")).to_be_visible()
        
        # 验证表格存在
        table = page.locator("#videoModelConfigTable")
        expect(table).to_be_visible()
        
        # 验证配置项行存在
        expect(page.locator("text=video_model_1_5_ep")).to_be_visible()
        expect(page.locator("text=video_model_1_0_ep")).to_be_visible()
        
        # 验证按钮存在
        expect(page.locator("#reloadVideoModelConfig")).to_be_visible()
        expect(page.locator("#saveVideoModelConfig")).to_be_visible()
        expect(page.locator("#resetVideoModelConfig")).to_be_visible()
    
    def test_input_fields_exist(self, page: Page):
        """验证输入框存在且有正确的属性"""
        # video_model_1_5_ep 输入框
        input_1_5 = page.locator('input[data-video-model-id="auth.video_model_1_5_ep"]')
        expect(input_1_5).to_be_visible()
        expect(input_1_5).to_have_attribute("type", "text")
        expect(input_1_5).to_have_class("video-model-input")
        
        # video_model_1_0_ep 输入框
        input_1_0 = page.locator('input[data-video-model-id="auth.video_model_1_0_ep"]')
        expect(input_1_0).to_be_visible()
        expect(input_1_0).to_have_attribute("type", "text")
        expect(input_1_0).to_have_class("video-model-input")
    
    def test_save_video_model_config(self, page: Page):
        """TC-003: 保存视频模型配置"""
        test_value = "ep-20250101-test123"
        
        # 找到输入框并输入值
        input_1_5 = page.locator('input[data-video-model-id="auth.video_model_1_5_ep"]')
        input_1_5.fill(test_value)
        
        # 点击保存按钮
        page.locator("#saveVideoModelConfig").click()
        
        # 验证保存成功提示
        status = page.locator("#videoModelConfigStatus")
        expect(status).to_contain_text("已保存")
        expect(status).not_to_have_class("error")
        
        # 刷新页面验证持久化
        page.reload()
        page.wait_for_selector("#videoModelConfigTable", state="visible")
        
        # 验证值已持久化
        input_1_5_after_reload = page.locator('input[data-video-model-id="auth.video_model_1_5_ep"]')
        expect(input_1_5_after_reload).to_have_value(test_value)
    
    def test_save_both_configs(self, page: Page):
        """同时保存两个视频模型配置"""
        test_value_1_5 = "ep-20250101-model15"
        test_value_1_0 = "ep-20250101-model10"
        
        # 输入两个配置值
        page.locator('input[data-video-model-id="auth.video_model_1_5_ep"]').fill(test_value_1_5)
        page.locator('input[data-video-model-id="auth.video_model_1_0_ep"]').fill(test_value_1_0)
        
        # 点击保存
        page.locator("#saveVideoModelConfig").click()
        
        # 验证保存成功
        expect(page.locator("#videoModelConfigStatus")).to_contain_text("已保存")
        
        # 刷新验证
        page.reload()
        page.wait_for_selector("#videoModelConfigTable", state="visible")
        
        expect(page.locator('input[data-video-model-id="auth.video_model_1_5_ep"]')).to_have_value(test_value_1_5)
        expect(page.locator('input[data-video-model-id="auth.video_model_1_0_ep"]')).to_have_value(test_value_1_0)
    
    def test_reset_video_model_config(self, page: Page):
        """TC-005: 重置视频模型配置"""
        # 先设置一个值
        input_1_5 = page.locator('input[data-video-model-id="auth.video_model_1_5_ep"]')
        input_1_5.fill("ep-20250101-test123")
        page.locator("#saveVideoModelConfig").click()
        expect(page.locator("#videoModelConfigStatus")).to_contain_text("已保存")
        
        # 点击重置按钮
        page.locator("#resetVideoModelConfig").click()
        
        # 验证重置成功提示
        expect(page.locator("#videoModelConfigStatus")).to_contain_text("已重置")
        
        # 验证输入框为空
        expect(input_1_5).to_have_value("")
    
    def test_reload_config(self, page: Page):
        """TC-009: 刷新配置"""
        # 先设置一个值
        test_value = "ep-20250101-reload-test"
        input_1_5 = page.locator('input[data-video-model-id="auth.video_model_1_5_ep"]')
        input_1_5.fill(test_value)
        page.locator("#saveVideoModelConfig").click()
        expect(page.locator("#videoModelConfigStatus")).to_contain_text("已保存")
        
        # 清空输入框（模拟用户误操作）
        input_1_5.fill("")
        
        # 点击刷新按钮
        page.locator("#reloadVideoModelConfig").click()
        
        # 验证值已重新加载
        expect(input_1_5).to_have_value(test_value)
        expect(page.locator("#videoModelConfigStatus")).to_contain_text("已刷新")
    
    def test_input_placeholder(self, page: Page):
        """验证输入框placeholder"""
        input_1_5 = page.locator('input[data-video-model-id="auth.video_model_1_5_ep"]')
        expect(input_1_5).to_have_attribute("placeholder", "ep-YYYYMMDD-xxxxx")
    
    def test_help_text_display(self, page: Page):
        """验证帮助文本显示"""
        help_text = page.locator(".video-model-help")
        expect(help_text).to_be_visible()
        expect(help_text).to_contain_text("火山引擎ARK平台")
        expect(help_text).to_contain_text("ep-YYYYMMDD-xxxxx")
    
    def test_no_change_save(self, page: Page):
        """测试没有变更时保存"""
        # 直接点击保存，不做任何修改
        page.locator("#saveVideoModelConfig").click()
        
        # 验证提示没有变更
        expect(page.locator("#videoModelConfigStatus")).to_contain_text("没有需要保存的变更")
    
    def test_empty_string_save(self, page: Page):
        """TC-007: 保存空字符串"""
        # 先设置一个值
        page.locator('input[data-video-model-id="auth.video_model_1_5_ep"]').fill("ep-20250101-test")
        page.locator("#saveVideoModelConfig").click()
        
        # 清空输入框
        page.locator('input[data-video-model-id="auth.video_model_1_5_ep"]').fill("")
        page.locator("#saveVideoModelConfig").click()
        
        # 验证保存成功
        expect(page.locator("#videoModelConfigStatus")).to_contain_text("已保存")
        
        # 刷新验证
        page.reload()
        page.wait_for_selector("#videoModelConfigTable", state="visible")
        expect(page.locator('input[data-video-model-id="auth.video_model_1_5_ep"]')).to_have_value("")
    
    def test_special_characters_input(self, page: Page):
        """TC-008: 输入特殊字符"""
        test_value = "ep-20250101-test!@#"
        
        input_1_5 = page.locator('input[data-video-model-id="auth.video_model_1_5_ep"]')
        input_1_5.fill(test_value)
        page.locator("#saveVideoModelConfig").click()
        
        # 验证保存成功
        expect(page.locator("#videoModelConfigStatus")).to_contain_text("已保存")
        
        # 刷新验证
        page.reload()
        page.wait_for_selector("#videoModelConfigTable", state="visible")
        expect(page.locator('input[data-video-model-id="auth.video_model_1_5_ep"]')).to_have_value(test_value)


class TestVideoModelConfigWithAuthConfig:
    """视频模型配置与鉴权配置的集成测试"""
    
    def test_both_configs_work_together(self, page: Page):
        """验证视频模型配置和鉴权配置可以共存"""
        page.goto(f"{BASE_URL}/auth-config")
        page.wait_for_selector("#authConfigTable", state="visible")
        page.wait_for_selector("#videoModelConfigTable", state="visible")
        
        # 验证两个区域都显示
        expect(page.locator("text=鉴权与连接配置")).to_be_visible()
        expect(page.locator("text=视频模型配置")).to_be_visible()
        
        # 验证两个表格都有数据
        auth_rows = page.locator("#authConfigTable tbody tr")
        video_rows = page.locator("#videoModelConfigTable tbody tr")
        
        expect(auth_rows).to_have_count.greater_than(0)
        expect(video_rows).to_have_count(2)  # 两个视频模型配置项


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
