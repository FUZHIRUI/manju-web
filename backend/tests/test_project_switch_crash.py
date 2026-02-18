#!/usr/bin/env python3
"""
复现测试：点击不同项目后服务崩溃问题
测试场景：快速切换多个项目，验证服务稳定性
"""
import asyncio
import json
import time
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))
MANJU_WEB_DIR = ROOT_DIR / "manju_web"
sys.path.insert(0, str(MANJU_WEB_DIR))

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("Playwright not installed, installing...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "playwright"], check=True)
    from playwright.async_api import async_playwright

BASE_URL = "http://127.0.0.1:8086"
SCREENSHOT_DIR = Path(__file__).parent / "test_screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


async def test_project_switching():
    """测试快速切换项目场景"""
    print("=" * 60)
    print("测试场景：快速切换多个项目")
    print("=" * 60)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        errors = []
        results = []
        
        page.on("pageerror", lambda e: errors.append(f"Page Error: {e}"))
        page.on("console", lambda msg: errors.append(f"Console: {msg.text}") if msg.type == "error" else None)
        
        try:
            print("\n[Step 1] 打开首页...")
            await page.goto(BASE_URL, timeout=30000)
            await page.wait_for_load_state("networkidle", timeout=10000)
            await page.screenshot(path=str(SCREENSHOT_DIR / "01_homepage.png"))
            print("  ✓ 首页加载成功")
            
            projects = ["ms3", "ms4", "ms5", "ms6"]
            
            for i, project in enumerate(projects):
                print(f"\n[Step {i+2}] 切换到项目: {project}")
                
                project_url = f"{BASE_URL}/?project={project}&tab=batch"
                
                try:
                    start_time = time.time()
                    await page.goto(project_url, timeout=30000)
                    await page.wait_for_load_state("networkidle", timeout=15000)
                    load_time = time.time() - start_time
                    
                    await page.screenshot(path=str(SCREENSHOT_DIR / f"0{i+2}_{project}.png"))
                    
                    title = await page.title()
                    url = page.url
                    
                    result = {
                        "project": project,
                        "load_time": round(load_time, 2),
                        "title": title,
                        "url": url,
                        "status": "success"
                    }
                    results.append(result)
                    print(f"  ✓ 项目 {project} 加载成功 (耗时: {load_time:.2f}s)")
                    
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    error_msg = f"项目 {project} 加载失败: {str(e)}"
                    print(f"  ✗ {error_msg}")
                    errors.append(error_msg)
                    results.append({
                        "project": project,
                        "status": "error",
                        "error": str(e)
                    })
            
            print("\n[Step 6] 快速连续切换测试...")
            for _ in range(3):
                for project in projects:
                    try:
                        await page.goto(f"{BASE_URL}/?project={project}&tab=batch", timeout=10000)
                        await page.wait_for_load_state("domcontentloaded", timeout=5000)
                        await asyncio.sleep(0.2)
                    except Exception as e:
                        errors.append(f"快速切换 {project} 失败: {str(e)}")
            
            print("  ✓ 快速切换测试完成")
            
            await page.screenshot(path=str(SCREENSHOT_DIR / "final_state.png"))
            
        except Exception as e:
            errors.append(f"测试执行错误: {str(e)}")
            await page.screenshot(path=str(SCREENSHOT_DIR / "error_state.png"))
        
        finally:
            await browser.close()
    
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    print("\n项目切换结果:")
    for r in results:
        if r.get("status") == "success":
            print(f"  ✓ {r['project']}: {r['load_time']}s")
        else:
            print(f"  ✗ {r['project']}: {r.get('error', 'unknown error')}")
    
    if errors:
        print(f"\n发现 {len(errors)} 个错误:")
        for e in errors[:10]:
            print(f"  - {e}")
    
    return len(errors) == 0, results, errors


async def test_api_concurrent():
    """测试并发API请求"""
    import aiohttp
    
    print("\n" + "=" * 60)
    print("测试场景：并发API请求")
    print("=" * 60)
    
    projects = ["ms3", "ms4", "ms5", "ms6"]
    endpoints = [
        "/api/projects",
        "/api/projects/{project}/assets",
        "/api/projects/{project}/jobs",
        "/api/projects/{project}/flow-status"
    ]
    
    errors = []
    results = []
    
    async with aiohttp.ClientSession() as session:
        for _ in range(3):
            tasks = []
            for project in projects:
                for endpoint in endpoints:
                    url = BASE_URL + endpoint.format(project=project)
                    tasks.append(test_single_api(session, url, project, endpoint))
            
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            
            for resp in responses:
                if isinstance(resp, Exception):
                    errors.append(str(resp))
                elif isinstance(resp, dict):
                    results.append(resp)
    
    success_count = sum(1 for r in results if r.get("status") == 200)
    error_count = len(errors) + sum(1 for r in results if r.get("status") != 200)
    
    print(f"\nAPI请求结果: 成功 {success_count}, 失败 {error_count}")
    
    if errors:
        print("错误详情:")
        for e in errors[:5]:
            print(f"  - {e}")
    
    return error_count == 0, results, errors


async def test_single_api(session, url, project, endpoint):
    """测试单个API"""
    try:
        start = time.time()
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            duration = time.time() - start
            status = resp.status
            if status == 200:
                data = await resp.json()
            else:
                data = None
            return {
                "url": url,
                "project": project,
                "endpoint": endpoint,
                "status": status,
                "duration": round(duration, 3),
                "has_data": data is not None
            }
    except Exception as e:
        return {
            "url": url,
            "project": project,
            "endpoint": endpoint,
            "status": "error",
            "error": str(e)
        }


async def main():
    print("\n" + "=" * 60)
    print("服务稳定性复现测试")
    print("=" * 60)
    
    print("\n[Phase 1] 测试前端页面切换...")
    frontend_ok, frontend_results, frontend_errors = await test_project_switching()
    
    print("\n[Phase 2] 测试并发API请求...")
    api_ok, api_results, api_errors = await test_api_concurrent()
    
    print("\n" + "=" * 60)
    print("最终结论")
    print("=" * 60)
    
    if frontend_ok and api_ok:
        print("✓ 所有测试通过，服务稳定")
        return 0
    else:
        print("✗ 发现问题，需要进一步排查")
        if not frontend_ok:
            print(f"  - 前端测试失败: {len(frontend_errors)} 个错误")
        if not api_ok:
            print(f"  - API测试失败: {len(api_errors)} 个错误")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
