#!/usr/bin/env python3
"""
Playwright前端控制器

负责模拟前端用户操作，包括点击按钮、填写表单、截图验证等。
"""
import time
from pathlib import Path
from typing import Dict, List, Optional

from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext


class PlaywrightController:
    """Playwright前端控制器"""
    
    def __init__(self, config):
        self.config = config
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.screenshots: List[str] = []
        
    def __enter__(self):
        """上下文管理器入口"""
        self.start()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.stop()
        return False
    
    def start(self):
        """启动浏览器"""
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=False)
        self.context = self.browser.new_context(
            viewport={"width": 1920, "height": 1080}
        )
        self.page = self.context.new_page()
        
    def stop(self):
        """关闭浏览器"""
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
    
    def navigate_to_project(self, tab: str = "batch"):
        """导航到项目页面"""
        url = f"{self.config.base_url}/?project={self.config.project_name}&tab={tab}"
        self.page.goto(url)
        self.page.wait_for_load_state("networkidle")
        time.sleep(2)  # 等待页面完全加载
        
    def take_screenshot(self, name: str) -> str:
        """截图并保存"""
        screenshot_dir = Path(f"manju_output/{self.config.project_name}/screenshots")
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = int(time.time())
        screenshot_path = screenshot_dir / f"{name}_{timestamp}.png"
        
        self.page.screenshot(path=str(screenshot_path), full_page=True)
        self.screenshots.append(str(screenshot_path))
        
        return str(screenshot_path)
    
    def click_fenjing_button(self) -> bool:
        """点击分镜图生成按钮"""
        try:
            self.navigate_to_project("batch")
            
            # 等待分镜图生成按钮出现
            button = self.page.wait_for_selector(
                "text=分镜图生成",
                timeout=10000
            )
            
            if not button:
                raise Exception("分镜图生成按钮未找到")
            
            # 截图记录点击前状态
            self.take_screenshot("before_click_fenjing")
            
            # 点击按钮
            button.click()
            time.sleep(2)
            
            # 截图记录点击后状态
            self.take_screenshot("after_click_fenjing")
            
            # 验证任务卡片出现
            task_card = self.page.wait_for_selector(
                ".task-card:has-text('分镜图生成')",
                timeout=10000
            )
            
            if not task_card:
                raise Exception("分镜图生成任务卡片未出现")
            
            return True
            
        except Exception as e:
            self.take_screenshot("fenjing_button_error")
            raise e
    
    def execute_fenjing_task(self) -> bool:
        """执行Fenjing任务"""
        try:
            # 找到任务卡片的执行按钮
            execute_button = self.page.wait_for_selector(
                ".task-card:has-text('分镜图生成') button:has-text('执行')",
                timeout=10000
            )
            
            if not execute_button:
                raise Exception("执行按钮未找到")
            
            # 截图记录执行前状态
            self.take_screenshot("before_execute_fenjing")
            
            # 点击执行
            execute_button.click()
            time.sleep(2)
            
            # 截图记录执行后状态
            self.take_screenshot("after_execute_fenjing")
            
            # 验证状态变为running
            self.page.wait_for_selector(
                ".task-card:has-text('分镜图生成') .status-running",
                timeout=10000
            )
            
            return True
            
        except Exception as e:
            self.take_screenshot("fenjing_execute_error")
            raise e
    
    def click_video_button(self) -> bool:
        """点击视频生成按钮"""
        try:
            self.navigate_to_project("batch")
            
            # 等待视频生成按钮出现
            button = self.page.wait_for_selector(
                "text=视频生成",
                timeout=10000
            )
            
            if not button:
                raise Exception("视频生成按钮未找到")
            
            # 截图记录点击前状态
            self.take_screenshot("before_click_video")
            
            # 点击按钮
            button.click()
            time.sleep(2)
            
            # 截图记录点击后状态
            self.take_screenshot("after_click_video")
            
            # 验证任务卡片出现
            task_card = self.page.wait_for_selector(
                ".task-card:has-text('视频生成')",
                timeout=10000
            )
            
            if not task_card:
                raise Exception("视频生成任务卡片未出现")
            
            return True
            
        except Exception as e:
            self.take_screenshot("video_button_error")
            raise e
    
    def execute_video_task(self) -> bool:
        """执行视频生成任务"""
        try:
            # 找到任务卡片的执行按钮
            execute_button = self.page.wait_for_selector(
                ".task-card:has-text('视频生成') button:has-text('执行')",
                timeout=10000
            )
            
            if not execute_button:
                raise Exception("执行按钮未找到")
            
            # 截图记录执行前状态
            self.take_screenshot("before_execute_video")
            
            # 点击执行
            execute_button.click()
            time.sleep(2)
            
            # 截图记录执行后状态
            self.take_screenshot("after_execute_video")
            
            # 验证状态变为running
            self.page.wait_for_selector(
                ".task-card:has-text('视频生成') .status-running",
                timeout=10000
            )
            
            return True
            
        except Exception as e:
            self.take_screenshot("video_execute_error")
            raise e
    
    def observe_video_generation(self) -> bool:
        """进入Videos页面观察视频生成过程"""
        try:
            # 导航到Videos页面
            self.navigate_to_project("videos")
            
            # 等待页面加载
            time.sleep(3)
            
            # 截图记录页面状态
            self.take_screenshot("videos_page")
            
            # 验证左侧分镜提示词区域
            left_panel = self.page.wait_for_selector(
                ".left-panel:has-text('分镜提示词')",
                timeout=10000
            )
            
            if not left_panel:
                raise Exception("分镜提示词区域未找到")
            
            # 验证右侧视频产物区域
            right_panel = self.page.wait_for_selector(
                ".right-panel",
                timeout=10000
            )
            
            if not right_panel:
                raise Exception("视频产物区域未找到")
            
            return True
            
        except Exception as e:
            self.take_screenshot("videos_page_error")
            raise e
    
    def refresh_and_verify(self) -> bool:
        """刷新页面并验证状态一致性"""
        try:
            # 刷新Batch页面
            self.navigate_to_project("batch")
            time.sleep(2)
            self.take_screenshot("batch_after_refresh")
            
            # 刷新Videos页面
            self.navigate_to_project("videos")
            time.sleep(2)
            self.take_screenshot("videos_after_refresh")
            
            return True
            
        except Exception as e:
            self.take_screenshot("refresh_error")
            raise e
    
    def verify_step_status(self, step_name: str, expected_status: str) -> bool:
        """验证步骤状态"""
        try:
            # 在页面上查找步骤状态
            status_element = self.page.wait_for_selector(
                f".step-item:has-text('{step_name}') .status-{expected_status}",
                timeout=5000
            )
            
            return status_element is not None
            
        except Exception:
            return False
    
    def get_current_state(self) -> Dict:
        """获取当前页面状态"""
        try:
            # 截图
            screenshot_path = self.take_screenshot("current_state")
            
            # 获取页面文本内容
            page_text = self.page.inner_text("body")
            
            # 获取所有任务卡片状态
            task_cards = self.page.query_selector_all(".task-card")
            tasks = []
            for card in task_cards:
                task_name = card.inner_text(".task-name")
                task_status = card.inner_text(".task-status")
                tasks.append({
                    "name": task_name,
                    "status": task_status
                })
            
            return {
                "screenshot": screenshot_path,
                "page_text": page_text[:1000],  # 前1000字符
                "tasks": tasks
            }
            
        except Exception as e:
            return {
                "error": str(e),
                "screenshot": self.take_screenshot("state_error")
            }
