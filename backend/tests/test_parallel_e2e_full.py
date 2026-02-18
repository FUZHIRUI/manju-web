#!/usr/bin/env python3
"""
多项目并行E2E测试脚本
按照 full_workflow_e2e_test_plan.md 执行完整的 step 1-17 流程
同时监控服务稳定性
"""
import asyncio
import json
import time
import sys
import os
import subprocess
import threading
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT_DIR = Path(__file__).resolve().parents[2]
MANJU_WEB_DIR = ROOT_DIR / "manju_web"
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(MANJU_WEB_DIR))

BASE_URL = "http://127.0.0.1:8086"
NOVEL_PATH = "/Users/bytedance/Desktop/常见python/manju_web/backend/manju_output/ms3/novel.txt"
SCRIPT_PATH = "/Users/bytedance/Desktop/常见python/manju_web/skills/manju-verifier/scripts/get_latest_requirement.py"
LOG_DIR = Path(__file__).parent / "test_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

TEST_PROJECTS = [
    "parallel_test_a",
    "parallel_test_b", 
    "parallel_test_c"
]

service_health_log = []
service_health_lock = threading.Lock()


def log_service_health():
    """记录服务健康状态"""
    import requests
    try:
        start = time.time()
        resp = requests.get(f"{BASE_URL}/api/projects", timeout=5)
        duration = time.time() - start
        status = "healthy" if resp.status_code == 200 else "unhealthy"
    except Exception as e:
        duration = -1
        status = f"error: {str(e)[:50]}"
    
    entry = {
        "time": datetime.now().isoformat(),
        "status": status,
        "duration": duration
    }
    with service_health_lock:
        service_health_log.append(entry)
    return status == "healthy"


def monitor_service(interval=10, stop_event=None):
    """后台监控服务健康状态"""
    while not stop_event.is_set():
        log_service_health()
        stop_event.wait(interval)


def run_command(cmd, project_name, step_name, timeout=300):
    """执行命令并记录结果"""
    log_file = LOG_DIR / f"{project_name}_{step_name}.log"
    result = {
        "project": project_name,
        "step": step_name,
        "cmd": " ".join(cmd) if isinstance(cmd, list) else cmd,
        "start_time": datetime.now().isoformat(),
        "success": False,
        "output": ""
    }
    
    print(f"[{project_name}] 执行步骤: {step_name}")
    
    try:
        proc = subprocess.run(
            cmd if isinstance(cmd, list) else cmd,
            shell=isinstance(cmd, str),
            capture_output=True,
            text=True,
            timeout=timeout
        )
        result["exit_code"] = proc.returncode
        result["output"] = proc.stdout[-2000:] if len(proc.stdout) > 2000 else proc.stdout
        result["error"] = proc.stderr[-500:] if proc.stderr else ""
        result["success"] = proc.returncode == 0
        
        with open(log_file, "w") as f:
            f.write(f"=== {step_name} ===\n")
            f.write(f"Command: {result['cmd']}\n")
            f.write(f"Exit Code: {proc.returncode}\n")
            f.write(f"=== STDOUT ===\n{proc.stdout}\n")
            f.write(f"=== STDERR ===\n{proc.stderr}\n")
            
    except subprocess.TimeoutExpired:
        result["error"] = f"Timeout after {timeout}s"
        result["success"] = False
    except Exception as e:
        result["error"] = str(e)
        result["success"] = False
    
    result["end_time"] = datetime.now().isoformat()
    
    status_icon = "✓" if result["success"] else "✗"
    print(f"[{project_name}] {status_icon} 步骤 {step_name} 完成")
    
    return result


def execute_full_workflow(project_name):
    """执行完整的E2E测试流程 (step 1-17)"""
    results = []
    
    print(f"\n{'='*60}")
    print(f"开始项目: {project_name}")
    print(f"{'='*60}")
    
    # Step 1: 创建项目
    result = run_command(
        f'curl -s -X POST "{BASE_URL}/api/projects" -H "Content-Type: application/json" -d \'{{"project_name": "{project_name}"}}\'',
        project_name, "step01_create_project",
        timeout=30
    )
    results.append(result)
    if not result["success"]:
        return results
    
    # Step 2: 上传小说并执行阶段1
    result = run_command(
        [
            "python", SCRIPT_PATH,
            "--mode", "vlm",
            "--project", project_name,
            "--base-url", BASE_URL,
            "--flow", "auto_storyboard",
            "--phase", "phase1",
            "--action-label", "阶段 1",
            "--wait-steps", "phase1",
            "--novel-path", NOVEL_PATH,
            "--chapter-size", "2500"
        ],
        project_name, "step02_phase1_storyboard",
        timeout=600
    )
    results.append(result)
    
    # Step 3: 执行阶段2
    result = run_command(
        [
            "python", SCRIPT_PATH,
            "--mode", "vlm",
            "--project", project_name,
            "--base-url", BASE_URL,
            "--vlm-task", "extract",
            "--flow", "auto_storyboard",
            "--phase", "phase2",
            "--action-label", "阶段 2",
            "--wait-steps", "phase2",
            "--per-chapter-shots", "15"
        ],
        project_name, "step03_phase2_storyboard",
        timeout=600
    )
    results.append(result)
    
    # Step 4: 确认分镜文件生成 (通过API检查)
    result = run_command(
        f'curl -s "{BASE_URL}/api/projects/{project_name}/flow-status"',
        project_name, "step04_verify_storyboard",
        timeout=30
    )
    results.append(result)
    
    # Step 5: 提示词生成
    result = run_command(
        [
            "python", SCRIPT_PATH,
            "--mode", "vlm",
            "--project", project_name,
            "--base-url", BASE_URL,
            "--vlm-task", "extract",
            "--flow", "visual_audio_assets",
            "--phase", "build_prompts",
            "--action-label", "第一步：提示词",
            "--wait-steps", "character_prompts,location_prompts,fenjing_prompts"
        ],
        project_name, "step05_build_prompts",
        timeout=600
    )
    results.append(result)
    
    # Step 6: 图片生成
    result = run_command(
        [
            "python", SCRIPT_PATH,
            "--mode", "vlm",
            "--project", project_name,
            "--base-url", BASE_URL,
            "--vlm-task", "extract",
            "--flow", "visual_audio_assets",
            "--phase", "generate_images",
            "--action-label", "第二步：生成",
            "--wait-steps", "character_images,location_images"
        ],
        project_name, "step06_generate_images",
        timeout=600
    )
    results.append(result)
    
    # Step 7: TTS语音生成
    result = run_command(
        [
            "python", SCRIPT_PATH,
            "--mode", "vlm",
            "--project", project_name,
            "--base-url", BASE_URL,
            "--vlm-task", "extract",
            "--flow", "visual_audio_assets",
            "--phase", "generate_tts",
            "--action-label", "第二步：TTS语音",
            "--wait-steps", "tts"
        ],
        project_name, "step07_generate_tts",
        timeout=600
    )
    results.append(result)
    
    # Step 8: 换装
    result = run_command(
        [
            "python", SCRIPT_PATH,
            "--mode", "vlm",
            "--project", project_name,
            "--base-url", BASE_URL,
            "--vlm-task", "extract",
            "--flow", "visual_audio_assets",
            "--phase", "cloth_images,cloth_changed",
            "--action-label", "第三步：换装",
            "--wait-steps", "cloth_images,cloth_changed"
        ],
        project_name, "step08_cloth_images",
        timeout=600
    )
    results.append(result)
    
    # Step 9: 上传
    result = run_command(
        [
            "python", SCRIPT_PATH,
            "--mode", "vlm",
            "--project", project_name,
            "--base-url", BASE_URL,
            "--vlm-task", "extract",
            "--flow", "visual_audio_assets",
            "--phase", "upload_assets",
            "--action-label", "第四步：上传",
            "--wait-steps", "upload_assets"
        ],
        project_name, "step09_upload_assets",
        timeout=600
    )
    results.append(result)
    
    # Step 10-12: Fenjing图片生成
    result = run_command(
        [
            "python", SCRIPT_PATH,
            "--mode", "vlm",
            "--project", project_name,
            "--base-url", BASE_URL,
            "--vlm-task", "extract",
            "--flow", "fenjing",
            "--phase", "generate_fenjing",
            "--wait-steps", "generate_fenjing"
        ],
        project_name, "step10_12_fenjing",
        timeout=600
    )
    results.append(result)
    
    # Step 13-17: 视频生成
    result = run_command(
        [
            "python", SCRIPT_PATH,
            "--mode", "vlm",
            "--project", project_name,
            "--base-url", BASE_URL,
            "--vlm-task", "extract",
            "--flow", "video",
            "--phase", "phase1_video_prompts,phase2_video_generation",
            "--wait-steps", "phase1_video_prompts,phase2_video_generation"
        ],
        project_name, "step13_17_video",
        timeout=1200
    )
    results.append(result)
    
    print(f"\n[{project_name}] 完整流程执行完毕")
    
    return results


def check_service_before_test():
    """测试前检查服务状态"""
    import requests
    try:
        resp = requests.get(f"{BASE_URL}/api/projects", timeout=5)
        if resp.status_code == 200:
            print("✓ 服务正常运行")
            return True
        else:
            print(f"✗ 服务响应异常: {resp.status_code}")
            return False
    except Exception as e:
        print(f"✗ 服务不可用: {e}")
        return False


def main():
    print("=" * 60)
    print("多项目并行E2E测试")
    print(f"测试项目: {TEST_PROJECTS}")
    print(f"测试时间: {datetime.now().isoformat()}")
    print("=" * 60)
    
    if not check_service_before_test():
        print("服务不可用，请先启动服务")
        return 1
    
    stop_event = threading.Event()
    monitor_thread = threading.Thread(
        target=monitor_service,
        args=(15, stop_event),
        daemon=True
    )
    monitor_thread.start()
    print("✓ 服务监控已启动")
    
    all_results = {}
    
    try:
        print("\n开始并行执行3个项目的E2E测试...")
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(execute_full_workflow, project): project
                for project in TEST_PROJECTS
            }
            
            for future in as_completed(futures):
                project = futures[future]
                try:
                    results = future.result()
                    all_results[project] = results
                except Exception as e:
                    print(f"[{project}] 执行异常: {e}")
                    all_results[project] = [{"error": str(e)}]
    
    finally:
        stop_event.set()
        monitor_thread.join(timeout=5)
    
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    for project, results in all_results.items():
        success_count = sum(1 for r in results if r.get("success"))
        total_count = len(results)
        print(f"\n[{project}]: {success_count}/{total_count} 步骤成功")
        for r in results:
            status = "✓" if r.get("success") else "✗"
            print(f"  {status} {r.get('step', 'unknown')}")
    
    print("\n" + "=" * 60)
    print("服务健康状态记录")
    print("=" * 60)
    
    healthy_count = sum(1 for e in service_health_log if e["status"] == "healthy")
    total_checks = len(service_health_log)
    print(f"健康检查: {healthy_count}/{total_checks} 成功")
    
    unhealthy = [e for e in service_health_log if e["status"] != "healthy"]
    if unhealthy:
        print("\n异常记录:")
        for e in unhealthy[:5]:
            print(f"  - {e['time']}: {e['status']}")
    
    report_file = LOG_DIR / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, "w") as f:
        json.dump({
            "projects": all_results,
            "service_health": service_health_log
        }, f, indent=2, ensure_ascii=False)
    print(f"\n详细报告已保存: {report_file}")
    
    if healthy_count < total_checks * 0.9:
        print("\n⚠ 服务在测试过程中出现不稳定!")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
