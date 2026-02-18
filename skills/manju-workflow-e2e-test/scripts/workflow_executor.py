#!/usr/bin/env python3
"""
Manju Web Workflow Executor

核心工作流执行器，负责按照预定义的顺序执行工作流的所有步骤。
支持串行执行、状态检查、结果收集和异常处理。
"""
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests


class StepStatus(Enum):
    """步骤状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"
    TIMEOUT = "timeout"


@dataclass
class StepResult:
    """步骤执行结果"""
    step_name: str
    status: StepStatus
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_seconds: float = 0.0
    api_response: Optional[Dict] = None
    artifacts: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    logs: List[str] = field(default_factory=list)
    screenshots: List[str] = field(default_factory=list)


@dataclass
class WorkflowConfig:
    """工作流配置"""
    base_url: str = "http://127.0.0.1:8086"
    project_name: str = ""
    novel_path: str = ""
    chapter_size: int = 2500
    per_chapter_shots: int = 15
    timeout_seconds: int = 600
    poll_interval: int = 5
    backend_path: Optional[str] = None  # backend目录路径，用于服务重启


class WorkflowExecutor:
    """
    工作流执行器
    
    负责按照full_workflow_e2e_test_plan.md中定义的18个步骤顺序执行工作流。
    """
    
    def __init__(self, config: WorkflowConfig):
        self.config = config
        self.results: List[StepResult] = []
        self.current_step: int = 0
        self._session = requests.Session()
        
    def execute_full_workflow(self) -> Tuple[bool, List[StepResult]]:
        """
        执行完整工作流（18个步骤）
        
        Returns:
            (success, results): 是否成功，所有步骤的结果列表
        """
        steps = self._get_workflow_steps()
        
        for i, step in enumerate(steps, 1):
            self.current_step = i
            print(f"\n{'='*60}")
            print(f"步骤 {i}/{len(steps)}: {step['name']}")
            print(f"{'='*60}")
            
            # 检查前置条件
            if not self._check_prerequisites(step):
                print(f"❌ 前置条件检查失败: {step['name']}")
                result = StepResult(
                    step_name=step['name'],
                    status=StepStatus.ERROR,
                    start_time=datetime.now(),
                    end_time=datetime.now(),
                    errors=["前置条件检查失败"]
                )
                self.results.append(result)
                return False, self.results
            
            # 执行步骤
            result = self._execute_step(step)
            self.results.append(result)
            
            if result.status != StepStatus.COMPLETED:
                print(f"❌ 步骤执行失败: {step['name']} - {result.status.value}")
                # 尝试异常恢复
                if not self._attempt_recovery(step, result):
                    return False, self.results
            else:
                print(f"✅ 步骤执行成功: {step['name']}")
        
        return True, self.results
    
    def _get_workflow_steps(self) -> List[Dict[str, Any]]:
        """获取工作流步骤定义"""
        return [
            # 阶段1: 项目创建与剧本拆解
            {
                "name": "创建项目",
                "flow": None,
                "action": self._step_create_project,
                "prerequisites": []
            },
            {
                "name": "上传小说并执行阶段1",
                "flow": "auto_storyboard",
                "phase": "phase1",
                "action": self._step_auto_storyboard_phase1,
                "prerequisites": ["创建项目"],
                "wait_for": {"flow": "auto_storyboard", "status": "completed"}
            },
            # 阶段2: 分镜生成
            {
                "name": "执行阶段2（分镜生成）",
                "flow": "auto_storyboard",
                "phase": "phase2",
                "action": self._step_auto_storyboard_phase2,
                "prerequisites": ["上传小说并执行阶段1"],
                "wait_for": {"flow": "auto_storyboard", "status": "completed"}
            },
            {
                "name": "确认分镜文件生成",
                "flow": None,
                "action": self._step_verify_storyboard_files,
                "prerequisites": ["执行阶段2（分镜生成）"],
                "check_files": ["storyboard_assets/storyboards/storyboard_chapter_1.jsonl"]
            },
            # 阶段3: 角色与素材生成
            {
                "name": "提示词生成",
                "flow": "visual_audio_assets",
                "phase": "build_prompts",
                "action": self._step_build_prompts,
                "prerequisites": ["确认分镜文件生成"],
                "wait_for": {"flow": "visual_audio_assets", "steps": ["character_prompts", "location_prompts", "fenjing_prompts"], "status": "completed"}
            },
            {
                "name": "图片生成",
                "flow": "visual_audio_assets",
                "phase": "generate_images",
                "action": self._step_generate_images,
                "prerequisites": ["提示词生成"],
                "wait_for": {"flow": "visual_audio_assets", "steps": ["character_images", "location_images"], "status": "completed"}
            },
            {
                "name": "TTS语音生成",
                "flow": "visual_audio_assets",
                "phase": "generate_tts",
                "action": self._step_generate_tts,
                "prerequisites": ["图片生成"],
                "wait_for": {"flow": "visual_audio_assets", "steps": ["tts"], "status": "completed"}
            },
            {
                "name": "换装",
                "flow": "visual_audio_assets",
                "phase": "cloth_images,cloth_changed",
                "action": self._step_cloth_change,
                "prerequisites": ["TTS语音生成"],
                "wait_for": {"flow": "visual_audio_assets", "steps": ["cloth_images", "cloth_changed"], "status": "completed"}
            },
            {
                "name": "上传资产",
                "flow": "visual_audio_assets",
                "phase": "upload_assets",
                "action": self._step_upload_assets,
                "prerequisites": ["换装"],
                "wait_for": {"flow": "visual_audio_assets", "steps": ["upload_assets"], "status": "completed"}
            },
            # 阶段4: Fenjing图片生成
            {
                "name": "Batch页面点击分镜图生成",
                "flow": "fenjing",
                "action": self._step_click_fenjing_button,
                "prerequisites": ["上传资产"]
            },
            {
                "name": "点击任务栏卡片执行Fenjing",
                "flow": "fenjing",
                "action": self._step_execute_fenjing,
                "prerequisites": ["Batch页面点击分镜图生成"]
            },
            {
                "name": "等待Fenjing生成完成",
                "flow": "fenjing",
                "action": self._step_wait_fenjing_complete,
                "prerequisites": ["点击任务栏卡片执行Fenjing"],
                "wait_for": {"flow": "fenjing", "status": "completed"}
            },
            # 阶段5: 视频生成
            {
                "name": "Batch页面点击视频生成",
                "flow": "video",
                "action": self._step_click_video_button,
                "prerequisites": ["等待Fenjing生成完成"]
            },
            {
                "name": "点击任务栏卡片执行视频生成",
                "flow": "video",
                "action": self._step_execute_video,
                "prerequisites": ["Batch页面点击视频生成"]
            },
            {
                "name": "进入Videos页面观察生成过程",
                "flow": "video",
                "action": self._step_observe_video_generation,
                "prerequisites": ["点击任务栏卡片执行视频生成"],
                "wait_for": {"flow": "video", "steps": ["phase1_video_prompts"], "status": "completed"}
            },
            {
                "name": "观察视频产物生成",
                "flow": "video",
                "action": self._step_wait_video_complete,
                "prerequisites": ["进入Videos页面观察生成过程"],
                "wait_for": {"flow": "video", "steps": ["phase2_video_generation", "fenjing_video_upload"], "status": "completed"}
            },
            {
                "name": "验证任务完成",
                "flow": "video",
                "action": self._step_verify_video_completion,
                "prerequisites": ["观察视频产物生成"]
            },
            {
                "name": "刷新验证",
                "flow": None,
                "action": self._step_refresh_verify,
                "prerequisites": ["验证任务完成"]
            }
        ]
    
    def _check_prerequisites(self, step: Dict[str, Any]) -> bool:
        """检查前置条件"""
        prerequisites = step.get("prerequisites", [])
        
        for prereq in prerequisites:
            # 检查之前的步骤是否成功
            prereq_result = next((r for r in self.results if r.step_name == prereq), None)
            if not prereq_result or prereq_result.status != StepStatus.COMPLETED:
                return False
        
        # 检查文件是否存在
        check_files = step.get("check_files", [])
        for file_path in check_files:
            full_path = Path(f"manju_output/{self.config.project_name}/{file_path}")
            if not full_path.exists():
                return False
        
        return True
    
    def _execute_step(self, step: Dict[str, Any]) -> StepResult:
        """执行单个步骤"""
        start_time = datetime.now()
        result = StepResult(
            step_name=step['name'],
            status=StepStatus.RUNNING,
            start_time=start_time
        )
        
        try:
            # 执行步骤动作
            action = step['action']
            action_result = action(step)
            
            # 等待完成（如果需要）
            wait_for = step.get('wait_for')
            if wait_for:
                self._wait_for_completion(wait_for, result)
            
            result.status = StepStatus.COMPLETED
            
        except TimeoutError as e:
            result.status = StepStatus.TIMEOUT
            result.errors.append(str(e))
        except Exception as e:
            result.status = StepStatus.ERROR
            result.errors.append(str(e))
        
        result.end_time = datetime.now()
        result.duration_seconds = (result.end_time - start_time).total_seconds()
        
        return result
    
    def _wait_for_completion(self, wait_config: Dict[str, Any], result: StepResult):
        """等待步骤完成"""
        flow = wait_config['flow']
        timeout = self.config.timeout_seconds
        start = time.time()
        
        while time.time() - start < timeout:
            try:
                response = self._session.get(
                    f"{self.config.base_url}/api/projects/{self.config.project_name}/flow-status"
                )
                response.raise_for_status()
                status_data = response.json()
                
                flow_status = status_data.get(flow, {})
                current_status = flow_status.get('status', 'unknown')
                
                # 检查特定步骤状态
                steps = wait_config.get('steps', [])
                if steps:
                    steps_data = flow_status.get('steps', {})
                    all_completed = all(
                        steps_data.get(step) == 'completed' 
                        for step in steps
                    )
                    if all_completed:
                        result.api_response = status_data
                        return
                else:
                    # 检查整体flow状态
                    if current_status == 'completed':
                        result.api_response = status_data
                        return
                    elif current_status == 'error':
                        raise Exception(f"Flow {flow} failed with error status")
                
                time.sleep(self.config.poll_interval)
                
            except requests.RequestException as e:
                result.errors.append(f"API request failed: {e}")
                time.sleep(self.config.poll_interval)
        
        raise TimeoutError(f"Timeout waiting for {flow} to complete")
    
    def _attempt_recovery(self, step: Dict[str, Any], result: StepResult) -> bool:
        """尝试异常恢复"""
        print(f"🔄 尝试恢复步骤: {step['name']}")
        
        # 收集诊断信息
        from exception_handler import ExceptionHandler
        handler = ExceptionHandler(self.config)
        
        diagnosis = handler.diagnose(step, result)
        
        if diagnosis.get('recoverable'):
            recovery_action = diagnosis.get('recovery_action')
            if recovery_action:
                try:
                    recovery_action()
                    # 重试步骤
                    new_result = self._execute_step(step)
                    if new_result.status == StepStatus.COMPLETED:
                        self.results[-1] = new_result
                        return True
                except Exception as e:
                    print(f"❌ 恢复失败: {e}")
        
        return False
    
    # ========== 具体步骤实现 ==========
    
    def _step_create_project(self, step: Dict[str, Any]) -> bool:
        """步骤1: 创建项目"""
        response = self._session.post(
            f"{self.config.base_url}/api/projects",
            json={"project_name": self.config.project_name}
        )
        response.raise_for_status()
        return True
    
    def _step_auto_storyboard_phase1(self, step: Dict[str, Any]) -> bool:
        """步骤2: 剧本拆解阶段1"""
        # 上传小说并执行阶段1
        response = self._session.post(
            f"{self.config.base_url}/api/projects/{self.config.project_name}/upload-novel",
            files={"file": open(self.config.novel_path, "rb")}
        )
        response.raise_for_status()
        
        # 触发阶段1执行
        response = self._session.post(
            f"{self.config.base_url}/api/projects/{self.config.project_name}/execute",
            json={
                "flow": "auto_storyboard",
                "phase": "phase1",
                "chapter_size": self.config.chapter_size
            }
        )
        response.raise_for_status()
        return True
    
    def _step_auto_storyboard_phase2(self, step: Dict[str, Any]) -> bool:
        """步骤3: 分镜生成阶段2"""
        response = self._session.post(
            f"{self.config.base_url}/api/projects/{self.config.project_name}/execute",
            json={
                "flow": "auto_storyboard",
                "phase": "phase2",
                "per_chapter_shots": self.config.per_chapter_shots
            }
        )
        response.raise_for_status()
        return True
    
    def _step_verify_storyboard_files(self, step: Dict[str, Any]) -> bool:
        """步骤4: 确认分镜文件生成"""
        storyboard_file = Path(f"manju_output/{self.config.project_name}/storyboard_assets/storyboards/storyboard_chapter_1.jsonl")
        if not storyboard_file.exists():
            raise FileNotFoundError(f"Storyboard file not found: {storyboard_file}")
        return True
    
    def _step_build_prompts(self, step: Dict[str, Any]) -> bool:
        """步骤5: 提示词生成"""
        response = self._session.post(
            f"{self.config.base_url}/api/projects/{self.config.project_name}/execute",
            json={
                "flow": "visual_audio_assets",
                "phase": "build_prompts"
            }
        )
        response.raise_for_status()
        return True
    
    def _step_generate_images(self, step: Dict[str, Any]) -> bool:
        """步骤6: 图片生成"""
        response = self._session.post(
            f"{self.config.base_url}/api/projects/{self.config.project_name}/execute",
            json={
                "flow": "visual_audio_assets",
                "phase": "generate_images"
            }
        )
        response.raise_for_status()
        return True
    
    def _step_generate_tts(self, step: Dict[str, Any]) -> bool:
        """步骤7: TTS语音生成"""
        response = self._session.post(
            f"{self.config.base_url}/api/projects/{self.config.project_name}/execute",
            json={
                "flow": "visual_audio_assets",
                "phase": "generate_tts"
            }
        )
        response.raise_for_status()
        return True
    
    def _step_cloth_change(self, step: Dict[str, Any]) -> bool:
        """步骤8: 换装"""
        response = self._session.post(
            f"{self.config.base_url}/api/projects/{self.config.project_name}/execute",
            json={
                "flow": "visual_audio_assets",
                "phase": "cloth_images,cloth_changed"
            }
        )
        response.raise_for_status()
        return True
    
    def _step_upload_assets(self, step: Dict[str, Any]) -> bool:
        """步骤9: 上传资产"""
        response = self._session.post(
            f"{self.config.base_url}/api/projects/{self.config.project_name}/execute",
            json={
                "flow": "visual_audio_assets",
                "phase": "upload_assets"
            }
        )
        response.raise_for_status()
        return True
    
    def _step_click_fenjing_button(self, step: Dict[str, Any]) -> bool:
        """步骤10: Batch页面点击分镜图生成按钮"""
        # 这里需要Playwright前端操作
        from playwright_controller import PlaywrightController
        controller = PlaywrightController(self.config)
        return controller.click_fenjing_button()
    
    def _step_execute_fenjing(self, step: Dict[str, Any]) -> bool:
        """步骤11: 点击任务栏卡片执行Fenjing"""
        from playwright_controller import PlaywrightController
        controller = PlaywrightController(self.config)
        return controller.execute_fenjing_task()
    
    def _step_wait_fenjing_complete(self, step: Dict[str, Any]) -> bool:
        """步骤12: 等待Fenjing生成完成"""
        # 等待逻辑在_wait_for_completion中处理
        return True
    
    def _step_click_video_button(self, step: Dict[str, Any]) -> bool:
        """步骤13: Batch页面点击视频生成按钮"""
        from playwright_controller import PlaywrightController
        controller = PlaywrightController(self.config)
        return controller.click_video_button()
    
    def _step_execute_video(self, step: Dict[str, Any]) -> bool:
        """步骤14: 点击任务栏卡片执行视频生成"""
        from playwright_controller import PlaywrightController
        controller = PlaywrightController(self.config)
        return controller.execute_video_task()
    
    def _step_observe_video_generation(self, step: Dict[str, Any]) -> bool:
        """步骤15: 进入Videos页面观察生成过程"""
        from playwright_controller import PlaywrightController
        controller = PlaywrightController(self.config)
        return controller.observe_video_generation()
    
    def _step_wait_video_complete(self, step: Dict[str, Any]) -> bool:
        """步骤16: 等待视频产物生成"""
        # 等待逻辑在_wait_for_completion中处理
        return True
    
    def _step_verify_video_completion(self, step: Dict[str, Any]) -> bool:
        """步骤17: 验证视频生成完成"""
        # 检查视频文件是否存在
        video_dir = Path(f"manju_output/{self.config.project_name}/video/videos")
        if not video_dir.exists():
            raise FileNotFoundError(f"Video directory not found: {video_dir}")
        
        video_files = list(video_dir.glob("*.mp4"))
        if len(video_files) == 0:
            raise FileNotFoundError("No video files found")
        
        return True
    
    def _step_refresh_verify(self, step: Dict[str, Any]) -> bool:
        """步骤18: 刷新验证"""
        from playwright_controller import PlaywrightController
        controller = PlaywrightController(self.config)
        return controller.refresh_and_verify()


def main():
    """主函数"""
    if len(sys.argv) < 3:
        print("Usage: workflow_executor.py <project_name> <novel_path>")
        sys.exit(1)
    
    config = WorkflowConfig(
        project_name=sys.argv[1],
        novel_path=sys.argv[2]
    )
    
    executor = WorkflowExecutor(config)
    success, results = executor.execute_full_workflow()
    
    # 输出结果报告
    print("\n" + "="*60)
    print("工作流执行报告")
    print("="*60)
    
    for result in results:
        status_icon = "✅" if result.status == StepStatus.COMPLETED else "❌"
        print(f"{status_icon} {result.step_name}: {result.status.value} ({result.duration_seconds:.1f}s)")
        if result.errors:
            for error in result.errors:
                print(f"   错误: {error}")
    
    print("="*60)
    print(f"总体结果: {'成功' if success else '失败'}")
    print(f"成功步骤: {sum(1 for r in results if r.status == StepStatus.COMPLETED)}/{len(results)}")
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
