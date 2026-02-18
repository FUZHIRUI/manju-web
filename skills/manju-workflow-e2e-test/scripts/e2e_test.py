import argparse
import base64
import glob
import json
import mimetypes
import os
import re
import sys
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

REQ_DIR = "/Users/bytedance/Desktop/常见python/manju_web/requirments_doc"


def get_latest_file():
    files = glob.glob(os.path.join(REQ_DIR, "*.md"))
    if not files:
        print(f"No requirement documents found in {REQ_DIR}")
        return None
    latest_file = max(files, key=os.path.getmtime)
    return latest_file


def read_latest_requirement():
    latest = get_latest_file()
    if not latest:
        return None, None
    try:
        with open(latest, "r", encoding="utf-8") as f:
            return latest, f.read()
    except Exception as e:
        print(f"Error reading file: {e}")
        return latest, None


def ensure_dir(path: str):
    Path(path).mkdir(parents=True, exist_ok=True)


def read_text(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def api_get_json(url: str, headers=None, timeout=60):
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    if not resp.text:
        return {}
    return resp.json()


def api_post_json(url: str, headers=None, payload=None, timeout=60):
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    resp.raise_for_status()
    if not resp.text:
        return {}
    return resp.json()


def upload_file(file_path: str, base_url: str, api_key: str):
    url = f"{base_url.rstrip('/')}/files"
    headers = {"Authorization": f"Bearer {api_key}"}
    with open(file_path, "rb") as handle:
        resp = requests.post(
            url,
            headers=headers,
            files={"file": handle},
            data={"purpose": "user_data"},
            timeout=120,
        )
    resp.raise_for_status()
    data = resp.json()
    file_id = data.get("id") or data.get("file_id")
    if not file_id:
        raise RuntimeError("file_id_missing")
    return file_id


def wait_file_active(file_id: str, base_url: str, api_key: str, timeout_sec: int):
    url = f"{base_url.rstrip('/')}/files/{file_id}"
    headers = {"Authorization": f"Bearer {api_key}"}
    start = time.time()
    while time.time() - start < timeout_sec:
        data = api_get_json(url, headers=headers, timeout=60)
        status = data.get("status")
        if status == "active":
            return data
        if status in {"failed", "error"}:
            raise RuntimeError(f"file_status_{status}")
        time.sleep(2)
    raise TimeoutError("file_wait_timeout")


def build_image_payload(path: str):
    mime, _ = mimetypes.guess_type(path)
    if not mime:
        mime = "image/png"
    with open(path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")
    return {"type": "input_image", "image_url": f"data:{mime};base64,{encoded}"}


def extract_json_block(text: str):
    if not text:
        return None
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    raw = match.group(0)
    try:
        return json.loads(raw)
    except Exception:
        return None


def call_vlm(file_items, base_url: str, api_key: str, model: str, prompt: str, disable_thinking: bool = True):
    url = f"{base_url.rstrip('/')}/responses"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    content = []
    for label, path in file_items:
        content.append(build_image_payload(path))
        content.append({"type": "input_text", "text": label})
    content.append({"type": "input_text", "text": prompt})
    payload = {"model": model, "input": [{"role": "user", "content": content}]}
    # 禁用 thinking 以提高响应速度
    if disable_thinking:
        payload["thinking"] = {"type": "disabled"}
    resp = requests.post(url, headers=headers, json=payload, timeout=180)
    if not resp.ok:
        print(f"vlm_response_error status={resp.status_code} body={resp.text}")
    resp.raise_for_status()
    return resp.json()


def build_vlm_fallback_prompt(target_action: str, target_flow: str = "") -> str:
    """构建 VLM 兜底操作的 prompt，让 VLM 指导如何点击"""
    return (
        f"你是前端自动化测试助手。当前需要执行操作：{target_action}"
        + (f" (flow: {target_flow})" if target_flow else "")
        + "\n\n请分析当前页面截图，告诉我：\n"
        "1. 页面上有哪些可操作的按钮或元素？\n"
        f"2. 如果要执行'{target_action}'，应该点击哪个按钮？\n"
        "3. 该按钮的准确文字内容是什么？\n"
        "4. 该按钮在页面上的大致位置（如：左上方、右侧列表中等）\n\n"
        "请输出 JSON 格式：\n"
        "{\n"
        '  "analysis": "页面分析简述",\n'
        '  "target_button_text": "按钮准确文字",\n'
        '  "target_button_location": "按钮位置描述",\n'
        '  "alternative_buttons": ["备选按钮1", "备选按钮2"],\n'
        '  "confidence": "high/medium/low",\n'
        '  "reasoning": "选择该按钮的理由"\n'
        "}"
    )


def vlm_guided_click(page, screenshot_path: str, target_action: str, target_flow: str,
                     vlm_base_url: str, api_key: str, model: str) -> dict:
    """使用 VLM 指导点击操作，作为兜底方案"""
    prompt = build_vlm_fallback_prompt(target_action, target_flow)
    file_items = [("当前页面截图", screenshot_path)]
    
    try:
        response = call_vlm(file_items, vlm_base_url, api_key, model, prompt, disable_thinking=True)
        output_text = ""
        for item in response.get("output", []):
            if item.get("type") == "message":
                parts = item.get("content") or []
                for part in parts:
                    if part.get("type") == "output_text":
                        output_text = part.get("text") or ""
                        break
        
        guidance = extract_json_block(output_text) or {}
        if not guidance:
            return {"success": False, "error": "vlm_parse_failed", "raw": output_text}
        
        button_text = guidance.get("target_button_text", "")
        confidence = guidance.get("confidence", "low")
        
        if not button_text or confidence == "low":
            return {"success": False, "error": "low_confidence", "guidance": guidance}
        
        # 尝试点击 VLM 建议的按钮
        clicked = try_click_action(page, button_text)
        if clicked:
            return {"success": True, "clicked_button": button_text, "guidance": guidance}
        
        # 尝试备选按钮
        for alt_button in guidance.get("alternative_buttons", []):
            clicked = try_click_action(page, alt_button)
            if clicked:
                return {"success": True, "clicked_button": alt_button, "guidance": guidance, "is_alternative": True}
        
        return {"success": False, "error": "click_failed", "guidance": guidance}
        
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_flow_status(base_url: str, project: str):
    url = f"{base_url.rstrip('/')}/api/projects/{project}/flow-status"
    return api_get_json(url, timeout=30)


def wait_flow_steps(base_url: str, project: str, flow: str, steps: list, timeout_sec: int):
    start = time.time()
    last_status = ""
    last_steps = {}
    while time.time() - start < timeout_sec:
        flow_status = get_flow_status(base_url, project)
        flows = flow_status.get("flows") or {}
        flow_state = flows.get(flow) or {}
        flow_steps = flow_state.get("steps") or {}
        last_steps = flow_steps
        last_status = flow_state.get("status") or ""
        if steps:
            values = [flow_steps.get(step) for step in steps if step in flow_steps]
            if any(val and val != "waiting" for val in values):
                return {"status": last_status, "steps": last_steps}
        else:
            if last_status and last_status != "waiting":
                return {"status": last_status, "steps": last_steps}
        time.sleep(2)
    return {"status": last_status, "steps": last_steps}


def capture_screenshot(page, output_dir: str, name: str):
    ensure_dir(output_dir)
    path = os.path.join(output_dir, f"{name}.png")
    page.screenshot(path=path, full_page=True)
    return path


def try_click_action(page, label: str):
    row = page.locator(".tree-action-row", has=page.get_by_text(label))
    if row.count() == 0:
        return False
    btn = row.first.get_by_role("button")
    if not btn.is_enabled():
        return False
    try:
        close_overlay(page)
        btn.click()
        return True
    except Exception:
        close_overlay(page)
        try:
            btn.click()
            return True
        except Exception:
            return False


def close_overlay(page):
    overlay = page.locator(".modal-backdrop")
    if overlay.count() > 0:
        try:
            cancel_btn = overlay.first.locator(".modal-actions button", has_text="取消")
            if cancel_btn.count() > 0:
                cancel_btn.first.click()
                page.wait_for_timeout(200)
            overlay.first.click()
            page.wait_for_timeout(200)
            if overlay.first.is_visible():
                page.keyboard.press("Escape")
                page.wait_for_timeout(200)
        except Exception:
            return


def close_log_modal(page):
    modal = page.locator("#logModal")
    if modal.count() == 0:
        return
    if not modal.is_visible():
        return
    close_btn = page.locator("#logModalClose")
    if close_btn.count() > 0:
        close_btn.first.click()
        page.wait_for_timeout(200)


def upload_novel_with_dialog(page, novel_text: str, chapter_size: int):
    # 尝试新版标题
    title = page.locator(".modal-title", has_text="上传剧本并拆解")
    if title.count() == 0:
        # 尝试旧版标题
        title = page.locator(".modal-title", has_text="上传小说")
        if title.count() == 0:
            return False
    textarea = page.locator(".modal-text")
    if textarea.count() == 0:
        return False
    textarea.fill(novel_text)
    if chapter_size and chapter_size > 0:
        input_box = page.locator(".modal-settings input[type=number]")
        if input_box.count() > 0:
            input_box.first.fill(str(chapter_size))
    # 尝试新版按钮
    confirm = page.locator(".modal-actions button", has_text="上传并拆解")
    if confirm.count() == 0:
        # 尝试旧版按钮
        confirm = page.locator(".modal-actions button", has_text="确认")
        if confirm.count() == 0:
            return False
    confirm.first.click()
    page.wait_for_timeout(500)
    return True


def run_auto_storyboard_phase_dialog(page, phase: str, value: int):
    # 支持新旧命名映射
    phase_mapping = {
        "step1": "phase1",
        "step2": "phase2",
        "phase1": "phase1",
        "phase2": "phase2"
    }
    internal_phase = phase_mapping.get(phase, phase)
    title_text = "运行步骤 2" if internal_phase == "phase2" else "运行步骤 1"
    title = page.locator(".modal-title", has_text=title_text)
    if title.count() == 0:
        # 尝试旧版标题
        title_text_old = "运行阶段 2" if internal_phase == "phase2" else "运行阶段 1"
        title = page.locator(".modal-title", has_text=title_text_old)
        if title.count() == 0:
            return False
    input_box = page.locator(".modal-settings input[type=number]")
    if input_box.count() > 0 and value and value > 0:
        input_box.first.fill(str(value))
    confirm_text = "运行步骤 2" if internal_phase == "phase2" else "确认并运行步骤 1"
    confirm = page.locator(".modal-actions button", has_text=confirm_text)
    if confirm.count() == 0:
        # 尝试旧版按钮文字
        confirm_text_old = "运行阶段 2" if internal_phase == "phase2" else "确认并运行阶段 1"
        confirm = page.locator(".modal-actions button", has_text=confirm_text_old)
        if confirm.count() == 0:
            return False
    confirm.first.click()
    page.wait_for_timeout(500)
    return True


def ensure_project_exists(base_url: str, project: str):
    url = f"{base_url.rstrip('/')}/api/projects"
    try:
        api_post_json(url, payload={"project_name": project}, timeout=30)
    except Exception:
        return


def build_requirement_prompt(latest_path: str, content: str, fallback: str):
    if not content:
        return fallback
    return (
        "你是前端验收助手。请基于以下需求文档，结合三张截图进行核验。"
        "输出 JSON，字段包含 passed(boolean)、details(string)、evidence(string)。"
        f"\n\n需求文档路径: {latest_path}\n需求文档内容:\n{content}\n"
        "\n核验要求：根据需求文档的验收标准，判断页面组件状态与文案是否符合。"
        "如文档未明确指向具体组件，请输出需要补充的验收项。"
    )


def build_extract_prompt() -> str:
    return (
        "你是前端任务卡片信息抽取助手。请只基于截图内容抽取任务卡片信息，输出 JSON。"
        "字段包含 flow(string)、project(string)、steps(array)。"
        "steps 每项包含 label(string)、status(string)、progress(string)。"
        "status 仅使用：waiting/running/completed/failed/blocked/unknown。"
        "progress 可为空字符串。只输出 JSON，不要附加解释。"
    )


def parse_vlm_config(content: str):
    if not content:
        return {}
    start_token = "```vlm_config"
    end_token = "```"
    start = content.find(start_token)
    if start == -1:
        return {}
    start = content.find("\n", start)
    if start == -1:
        return {}
    end = content.find(end_token, start)
    if end == -1:
        return {}
    raw = content[start:end].strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def infer_action_from_requirement(content: str):
    if not content:
        return {}
    text = content.lower()
    action = {}
    if "auto_storyboard" in text or "剧本拆解" in text:
        action["flow"] = "auto_storyboard"
        if "step2" in text or "步骤 2" in text or "步骤2" in text or "phase2" in text or "阶段 2" in text:
            action["phase"] = "step2"
            action["action_label"] = "步骤 2"
            action["wait_steps"] = ["step2", "step2_storyboard"]
            action["action_name"] = "auto_storyboard_step2"
        elif "step3" in text or "步骤 3" in text or "步骤3" in text or "upload" in text or "上传" in text:
            action["phase"] = "step3_upload"
            action["action_label"] = "步骤 3"
            action["wait_steps"] = ["step3_upload", "step3_upload_assets"]
            action["action_name"] = "auto_storyboard_step3_upload"
        else:
            action["phase"] = "step1"
            action["action_label"] = "步骤 1"
            action["wait_steps"] = ["step1", "step1_extract"]
            action["action_name"] = "auto_storyboard_step1"
        return action
    if "fenjing" in text or "分镜图生成" in text:
        action["flow"] = "fenjing"
        action["action_label"] = "执行"
        action["wait_steps"] = ["download_assets"]
        action["action_name"] = "fenjing"
        return action
    if "video" in text or "视频生成" in text:
        action["flow"] = "video"
        action["action_label"] = "执行"
        action["wait_steps"] = ["prepare"]
        action["action_name"] = "video"
        return action
    if "visual_audio_assets" in text or "角色与素材生成" in text or "visual audio" in text:
        action["flow"] = "visual_audio_assets"
        if "提示词" in text or "build_prompts" in text:
            action.update({
                "phase": "build_prompts",
                "action_label": "第一步：提示词",
                "wait_steps": ["character_prompts", "location_prompts", "fenjing_prompts"],
                "action_name": "build_prompts"
            })
            return action
        if "tts" in text or "generate_tts" in text:
            action.update({
                "phase": "generate_tts",
                "action_label": "第二步：TTS语音",
                "wait_steps": ["tts"],
                "action_name": "generate_tts"
            })
            return action
        if "换装" in text or "cloth_changed" in text or "cloth_images" in text:
            action.update({
                "phase": "cloth_changed",
                "action_label": "第三步：换装",
                "wait_steps": ["cloth_images", "cloth_changed"],
                "action_name": "cloth_changed"
            })
            return action
        if "上传" in text or "upload_assets" in text:
            action.update({
                "phase": "upload_assets",
                "action_label": "第四步：上传",
                "wait_steps": ["upload_assets"],
                "action_name": "upload_assets"
            })
            return action
        action.update({
            "phase": "generate_images",
            "action_label": "第二步：生成",
            "wait_steps": ["character_images", "location_images"],
            "action_name": "generate_images"
        })
        return action
    return action


def normalize_action_config(config: dict):
    if not config:
        return {}
    normalized = {}
    for key in ["flow", "phase", "action_label", "action_name"]:
        value = config.get(key)
        if isinstance(value, str) and value.strip():
            normalized[key] = value.strip()
    steps = config.get("wait_steps")
    if isinstance(steps, list):
        normalized["wait_steps"] = [str(step).strip() for step in steps if str(step).strip()]
    return normalized


def parse_wait_steps(raw: str):
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def resolve_action_config(latest_content: str, args):
    config = normalize_action_config(parse_vlm_config(latest_content or ""))
    inferred = normalize_action_config(infer_action_from_requirement(latest_content or ""))
    resolved = {**inferred, **config}
    if args.flow:
        resolved["flow"] = args.flow
    if args.phase:
        resolved["phase"] = args.phase
    if args.action_label:
        resolved["action_label"] = args.action_label
    if args.action_name:
        resolved["action_name"] = args.action_name
    if args.wait_steps:
        resolved["wait_steps"] = parse_wait_steps(args.wait_steps)
    return resolved


def ensure_flow_tab(page, flow: str, phase: str):
    if not flow:
        return
    # 支持新旧命名映射
    if flow == "auto_storyboard" and phase in {"step2", "phase2"}:
        return
    selector = f'[data-flow="{flow}"]'
    if page.locator(selector).count() == 0:
        return
    btn = page.locator(selector).first
    if btn.is_enabled():
        btn.click()


def trigger_flow_action(base_url: str, project: str, action: dict):
    flow = action.get("flow")
    phase = action.get("phase")
    if not flow:
        return
    payload = {}
    if flow == "auto_storyboard":
        # 支持新旧命名映射，后端 API 仍使用 step1/step2/step3_upload
        phase_mapping = {
            "phase1": "step1",
            "phase2": "step2",
            "upload": "step3_upload"
        }
        payload["phase"] = phase_mapping.get(phase, phase) or "step1"
    elif flow == "visual_audio_assets":
        payload["phase"] = phase or "all"
    api_post_json(
        f"{base_url.rstrip('/')}/api/projects/{project}/run/{flow}",
        payload=payload,
        timeout=60,
    )


def build_screenshot_name(prefix: str, suffix: str):
    safe = prefix or "flow_check"
    safe = safe.replace(" ", "_")
    return f"{safe}_{suffix}"


def run_vlm_verify(args):
    base_url = args.base_url
    vlm_base_url = args.vlm_base_url or os.getenv("ARK_VLM_BASE_URL", "") or base_url
    project = args.project
    output_dir = os.path.abspath(args.output_dir)
    api_key = args.api_key or os.getenv("ARK_API_KEY", "")
    model = args.model or os.getenv("ARK_VLM_MODEL", "")
    novel_text = ""
    if args.novel_text:
        novel_text = args.novel_text
    elif args.novel_path:
        novel_text = read_text(args.novel_path)
    if not api_key:
        print("missing_api_key")
        sys.exit(2)
    if not model:
        print("missing_model")
        sys.exit(2)
    latest_path, latest_content = read_latest_requirement()
    action = resolve_action_config(latest_content or "", args)
    ensure_project_exists(base_url, project)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        page = browser.new_page()
        page.goto(f"{base_url}/?project={project}&tab=batch")
        page.wait_for_timeout(1000)
        close_log_modal(page)
        close_overlay(page)
        ensure_flow_tab(page, action.get("flow"), action.get("phase"))
        page.wait_for_timeout(1000)
        action_name = action.get("action_name") or action.get("flow") or "flow_check"
        before_path = capture_screenshot(page, output_dir, build_screenshot_name(action_name, "before"))
        triggered = False
        fallback_result = None
        if action.get("flow") == "auto_storyboard" and action.get("phase") in {"step1", "phase1"} and novel_text:
            triggered = upload_novel_with_dialog(page, novel_text, args.chapter_size)
        elif action.get("action_label"):
            close_overlay(page)
            triggered = try_click_action(page, action["action_label"])
            # 如果常规点击失败，启用 VLM 兜底
            if not triggered:
                print(f"常规点击失败，启用 VLM 兜底: {action['action_label']}")
                fallback_result = vlm_guided_click(
                    page, before_path, action["action_label"], 
                    action.get("flow", ""), vlm_base_url, api_key, model
                )
                triggered = fallback_result.get("success", False)
                if triggered:
                    print(f"VLM 兜底成功，点击按钮: {fallback_result.get('clicked_button')}")
                else:
                    print(f"VLM 兜底失败: {fallback_result}")
            if triggered and action.get("flow") == "auto_storyboard" and action.get("phase") in {"step1", "step2"}:
                 value = args.chapter_size if action.get("phase") == "step1" else args.per_chapter_shots
                 run_auto_storyboard_phase_dialog(page, action.get("phase"), value)
        if not triggered and action.get("flow"):
            trigger_flow_action(base_url, project, action)
        status_after = wait_flow_steps(
            base_url,
            project,
            action.get("flow") or "visual_audio_assets",
            action.get("wait_steps") or [],
            args.wait_timeout,
        )
        page.wait_for_timeout(2000)
        after_path = capture_screenshot(page, output_dir, build_screenshot_name(action_name, "after"))
        page.reload()
        page.wait_for_timeout(1000)
        refresh_path = capture_screenshot(page, output_dir, build_screenshot_name(action_name, "refresh"))
        browser.close()

    file_items = [
        ("执行前截图", before_path),
        ("执行后截图", after_path),
        ("刷新后截图", refresh_path),
    ]

    if args.vlm_task == "extract":
        prompt = args.prompt or build_extract_prompt()
        response = call_vlm(file_items, vlm_base_url, api_key, model, prompt)
        output_text = ""
        for item in response.get("output", []):
            if item.get("type") == "message":
                parts = item.get("content") or []
                for part in parts:
                    if part.get("type") == "output_text":
                        output_text = part.get("text") or ""
                        break
        extracted = extract_json_block(output_text) or output_text
        result = {
            "project": project,
            "vlm_base_url": vlm_base_url,
            "status_after": status_after,
            "requirement_file": latest_path,
            "prompt_used": prompt,
            "action_used": action,
            "screenshots": {
                "before": before_path,
                "after": after_path,
                "refresh": refresh_path,
            },
            "extracted": extracted,
            "fallback_used": fallback_result is not None,
            "fallback_result": fallback_result,
        }
        print(json.dumps(result, ensure_ascii=False))
        return
    fallback_prompt = (
        "请对比三张截图，判断 cloth_changed 对应的树节点状态是否符合："
        "执行前为等待中，执行后为已完成，刷新后保持一致。"
        "输出 JSON，字段包含 passed(boolean)、details(string)。"
    )
    prompt = args.prompt or build_requirement_prompt(latest_path or "", latest_content or "", fallback_prompt)
    response = call_vlm(file_items, vlm_base_url, api_key, model, prompt)
    result = {
        "project": project,
        "vlm_base_url": vlm_base_url,
        "status_after": status_after,
        "requirement_file": latest_path,
        "prompt_used": prompt,
        "action_used": action,
        "screenshots": {
            "before": before_path,
            "after": after_path,
            "refresh": refresh_path,
        },
        "vlm_response": response,
        "fallback_used": fallback_result is not None,
        "fallback_result": fallback_result,
    }
    print(json.dumps(result, ensure_ascii=False))


def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="latest", choices=["latest", "vlm"])
    parser.add_argument("--project", default="ms3")
    parser.add_argument("--base-url", default="http://127.0.0.1:8086")
    parser.add_argument("--vlm-base-url", default="https://ark.cn-beijing.volces.com/api/v3")
    parser.add_argument("--output-dir", default=os.path.join(os.path.dirname(__file__), "..", "output"))
    parser.add_argument("--api-key", default="58556eed-a35b-4e01-a30c-6736894afb42")
    parser.add_argument("--model", default="ep-20260215001006-86n7g")
    parser.add_argument("--prompt", default="")
    parser.add_argument("--flow", default="")
    parser.add_argument("--phase", default="")
    parser.add_argument("--action-label", default="")
    parser.add_argument("--action-name", default="")
    parser.add_argument("--vlm-task", default="check", choices=["check", "extract"])
    parser.add_argument("--wait-steps", default="")
    parser.add_argument("--wait-timeout", type=int, default=120)
    parser.add_argument("--file-wait-timeout", type=int, default=300)
    parser.add_argument("--novel-path", default="")
    parser.add_argument("--novel-text", default="")
    parser.add_argument("--chapter-size", type=int, default=0)
    parser.add_argument("--per-chapter-shots", type=int, default=0)
    parser.add_argument("--headless", action="store_true")
    return parser


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()
    if args.mode == "latest":
        latest, content = read_latest_requirement()
        if latest:
            print(f"Latest requirement file: {latest}")
            print("-" * 40)
        if content:
            print(content)
        if not latest:
            sys.exit(1)
    else:
        run_vlm_verify(args)
