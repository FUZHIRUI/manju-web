#!/usr/bin/env python3
"""
Bug修复验证测试脚本

验证在phase2运行期间，phase1是否保持completed状态不变。
"""
import argparse
import json
import os
import sys
import time
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

import requests
from playwright.sync_api import sync_playwright


class BugFixVerificationTest:
    """Bug修复验证测试器"""
    
    def __init__(self, base_url: str, project: str, output_dir: str):
        self.base_url = base_url.rstrip('/')
        self.project = project
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.intermediate_checks: List[Dict[str, Any]] = []
        self.session = requests.Session()
        
    def log(self, message: str):
        """记录日志"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        log_line = f"[{timestamp}] {message}"
        print(log_line)
        return log_line
        
    def get_flow_status(self) -> Dict:
        """获取 flow 状态"""
        url = f"{self.base_url}/api/projects/{self.project}/flow-status"
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            self.log(f"获取flow状态失败: {e}")
            return {}
    
    def check_intermediate_state(self, check_index: int) -> Dict[str, Any]:
        """
        检查中间态
        
        关键验证点:
        - auto_storyboard.steps.phase1 必须保持为 completed
        - auto_storyboard.steps.phase2 应该是 running
        """
        timestamp = datetime.now().isoformat()
        flow_status = self.get_flow_status()
        
        flows = flow_status.get("flows", {})
        auto_storyboard = flows.get("auto_storyboard", {})
        steps = auto_storyboard.get("steps", {})
        
        phase1_status = steps.get("phase1", "unknown")
        phase2_status = steps.get("phase2", "unknown")
        flow_status_value = auto_storyboard.get("status", "unknown")
        
        check_result = {
            "check_index": check_index,
            "timestamp": timestamp,
            "phase1_status": phase1_status,
            "phase2_status": phase2_status,
            "flow_status": flow_status_value,
            "phase1_unchanged": phase1_status == "completed",
            "phase2_running": phase2_status == "running",
            "raw_status": flow_status
        }
        
        self.intermediate_checks.append(check_result)
        
        # 记录检查结果
        status1_icon = "✅" if phase1_status == "completed" else "❌"
        status2_icon = "✅" if phase2_status == "running" else "⏳"
        
        self.log(f"中间态检查 #{check_index}:")
        self.log(f"  - 时间: {timestamp}")
        self.log(f"  - phase1 状态: {phase1_status} {status1_icon}")
        self.log(f"  - phase2 状态: {phase2_status} {status2_icon}")
        self.log(f"  - flow 状态: {flow_status_value}")
        
        return check_result
    
    def monitor_during_phase2(self, check_interval: int = 15, max_checks: int = 20) -> Dict:
        """
        在phase2运行期间持续监控中间态
        
        Args:
            check_interval: 检查间隔（秒）
            max_checks: 最大检查次数
            
        Returns:
            监控结果报告
        """
        self.log("=" * 60)
        self.log("开始监控 phase2 执行期间的中间态...")
        self.log(f"项目: {self.project}")
        self.log(f"检查间隔: {check_interval}秒, 最大检查次数: {max_checks}")
        self.log("=" * 60)
        
        phase1_changed = False
        check_count = 0
        
        while check_count < max_checks:
            check_count += 1
            result = self.check_intermediate_state(check_count)
            
            # 检查phase1是否发生变化
            if not result["phase1_unchanged"]:
                phase1_changed = True
                self.log(f"⚠️ 警告: phase1 状态从 completed 变为 {result['phase1_status']}!")
            
            # 如果phase2已经完成或失败，停止监控
            if result["phase2_status"] in ["completed", "failed", "error"]:
                self.log(f"phase2 已结束，状态: {result['phase2_status']}")
                break
            
            # 等待下一次检查
            if check_count < max_checks:
                self.log(f"等待 {check_interval} 秒后进行下一次检查...")
                time.sleep(check_interval)
        
        # 生成最终报告
        report = {
            "project": self.project,
            "test_name": "Bug修复验证 - phase1中间态保持测试",
            "total_checks": check_count,
            "phase1_changed": phase1_changed,
            "test_passed": not phase1_changed,
            "intermediate_checks": self.intermediate_checks,
            "summary": {
                "phase1_always_completed": not phase1_changed,
                "total_check_count": check_count,
                "final_phase1_status": self.intermediate_checks[-1]["phase1_status"] if self.intermediate_checks else "unknown",
                "final_phase2_status": self.intermediate_checks[-1]["phase2_status"] if self.intermediate_checks else "unknown"
            }
        }
        
        return report
    
    def save_report(self, report: Dict):
        """保存测试报告"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = self.output_dir / f"bug_fix_verification_{self.project}_{timestamp}.json"
        
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        self.log(f"\n测试报告已保存: {report_file}")
        return report_file


def run_phase1(args, project_name: str) -> bool:
    """执行phase1并等待完成"""
    print("\n" + "=" * 60)
    print("步骤1: 执行 phase1 剧本拆解")
    print("=" * 60)
    
    cmd = [
        "python", "scripts/e2e_test.py",
        "--mode", "vlm",
        "--project", project_name,
        "--base-url", args.base_url,
        "--vlm-base-url", args.vlm_base_url,
        "--api-key", args.api_key,
        "--model", args.model,
        "--flow", "auto_storyboard",
        "--phase", "phase1",
        "--action-label", "阶段 1",
        "--wait-steps", "phase1",
        "--novel-path", args.novel_path,
        "--chapter-size", str(args.chapter_size),
        "--vlm-task", "extract",
        "--wait-timeout", "300"
    ]
    
    if not args.headless:
        cmd.append("--headless")
    
    print(f"执行命令: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd="/Users/bytedance/Desktop/常见python/manju_web/skills/manju-workflow-e2e-test", capture_output=True, text=True)
    
    print("STDOUT:", result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr[-1000:] if len(result.stderr) > 1000 else result.stderr)
    
    return result.returncode == 0


def trigger_phase2(args, project_name: str) -> bool:
    """触发phase2执行（不等待完成）"""
    print("\n" + "=" * 60)
    print("步骤2: 触发 phase2 分镜生成")
    print("=" * 60)
    
    cmd = [
        "python", "scripts/e2e_test.py",
        "--mode", "vlm",
        "--project", project_name,
        "--base-url", args.base_url,
        "--vlm-base-url", args.vlm_base_url,
        "--api-key", args.api_key,
        "--model", args.model,
        "--flow", "auto_storyboard",
        "--phase", "phase2",
        "--action-label", "阶段 2",
        "--wait-steps", "",  # 不等待，立即返回
        "--per-chapter-shots", str(args.per_chapter_shots),
        "--vlm-task", "extract",
        "--wait-timeout", "10"  # 短超时，只触发不等待
    ]
    
    if not args.headless:
        cmd.append("--headless")
    
    print(f"执行命令: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd="/Users/bytedance/Desktop/常见python/manju_web/skills/manju-workflow-e2e-test", capture_output=True, text=True)
    
    print("STDOUT:", result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr[-1000:] if len(result.stderr) > 1000 else result.stderr)
    
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description="Bug修复验证测试")
    parser.add_argument("--base-url", default="http://127.0.0.1:8086")
    parser.add_argument("--vlm-base-url", default="https://ark.cn-beijing.volces.com/api/v3")
    parser.add_argument("--api-key", default="58556eed-a35b-4e01-a30c-6736894afb42")
    parser.add_argument("--model", default="ep-20260215001006-86n7g")
    parser.add_argument("--novel-path", default="/Users/bytedance/Desktop/常见python/manju_web/backend/tests/novel.txt")
    parser.add_argument("--chapter-size", type=int, default=2500)
    parser.add_argument("--per-chapter-shots", type=int, default=15)
    parser.add_argument("--check-interval", type=int, default=15, help="中间态检查间隔（秒）")
    parser.add_argument("--max-checks", type=int, default=20, help="最大检查次数")
    parser.add_argument("--output-dir", default="/Users/bytedance/Desktop/常见python/manju_web/skills/manju-workflow-e2e-test/output")
    parser.add_argument("--headless", action="store_true", default=True)
    parser.add_argument("--skip-phase1", action="store_true", help="跳过phase1（使用已有项目）")
    parser.add_argument("--project", default="", help="指定现有项目名称（用于skip-phase1）")
    
    args = parser.parse_args()
    
    # 生成项目名称
    if args.skip_phase1 and args.project:
        project_name = args.project
        print(f"使用现有项目: {project_name}")
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        project_name = f"e2e_test_{timestamp}"
        print(f"创建新项目: {project_name}")
    
    # 步骤1: 执行phase1
    if not args.skip_phase1:
        if not run_phase1(args, project_name):
            print("❌ phase1 执行失败")
            sys.exit(1)
        print("✅ phase1 执行完成")
        
        # 等待一段时间确保状态稳定
        print("等待5秒确保状态稳定...")
        time.sleep(5)
    
    # 步骤2: 触发phase2
    if not trigger_phase2(args, project_name):
        print("⚠️ phase2 触发可能有问题，继续监控...")
    
    # 等待phase2开始运行
    print("等待10秒让phase2开始运行...")
    time.sleep(10)
    
    # 步骤3: 监控中间态
    print("\n" + "=" * 60)
    print("步骤3: 监控 phase2 执行期间的中间态")
    print("=" * 60)
    
    tester = BugFixVerificationTest(
        base_url=args.base_url,
        project=project_name,
        output_dir=args.output_dir
    )
    
    report = tester.monitor_during_phase2(
        check_interval=args.check_interval,
        max_checks=args.max_checks
    )
    
    # 保存报告
    report_file = tester.save_report(report)
    
    # 输出最终结果
    print("\n" + "=" * 60)
    print("测试完成 - 最终结果")
    print("=" * 60)
    print(f"项目名称: {project_name}")
    print(f"测试通过: {'✅ 是' if report['test_passed'] else '❌ 否'}")
    print(f"phase1 始终保持 completed: {'✅ 是' if report['summary']['phase1_always_completed'] else '❌ 否'}")
    print(f"总检查次数: {report['summary']['total_check_count']}")
    print(f"最终 phase1 状态: {report['summary']['final_phase1_status']}")
    print(f"最终 phase2 状态: {report['summary']['final_phase2_status']}")
    print(f"报告文件: {report_file}")
    print("=" * 60)
    
    # 如果测试失败，输出详细信息
    if not report['test_passed']:
        print("\n❌ 测试失败详情:")
        for check in report['intermediate_checks']:
            if not check['phase1_unchanged']:
                print(f"  - 检查 #{check['check_index']}: phase1 状态变为 {check['phase1_status']}")
        sys.exit(1)
    else:
        print("\n✅ 所有检查通过！phase1 在phase2执行期间始终保持completed状态。")
        sys.exit(0)


if __name__ == "__main__":
    main()
