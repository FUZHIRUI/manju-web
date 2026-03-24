"""
auto_storyboard.py - 自动分镜生成模块

【模块职责】
负责小说文本的自动分镜生成，是整个视频生成工作流的第一阶段(Phase 1/2)。

【执行流程】
Phase 1: 从小说文本提取结构化信息
  1. 读取小说内容
  2. 调用LLM提取角色列表、章节摘要、地点列表
  3. 资产ID清洗与重置(防止重复)
  4. 保存到JSONL文件

Phase 2: 基于Phase 1产出生成分镜剧本
  1. 按批次处理章节(支持并行)
  2. 调用LLM生成每个分镜的详细信息
  3. ID校验与修正(确保人物/地点ID正确)
  4. 保存分镜剧本到storyboards目录
  5. 上传到TOS存储

【关键函数】
- run_workflow: 主入口，支持phase1/phase2/full三种模式
- call_ark_responses_api: 同步调用Ark Responses API
- call_ark_responses_api_async: 异步调用Ark Responses API
- process_batch_async: 异步处理单个批次
- sanitize_assets: 清洗资产ID，使用随机ID替换可能的重复ID
- validate_and_fix_storyboard_ids: 校验并修正分镜中的ID

【依赖】
- runtime_config: 配置管理
- provider_runtime: API调用封装
- retry_runtime: 重试策略
- json_parse/json_fields: JSON处理
"""

import json
import time
import requests
import asyncio
import httpx
import uuid
import shutil
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from .json_parse import extract_json_lists
from .json_fields import build_character_name_map, build_location_name_map, enforce_storyboard_fields
from .io_jsonl import read_jsonl

from . import runtime_config
from .provider_runtime import TosClientWrapper, emit_event, api_log_event, _build_retry_loggers
from .retry_runtime import ResponseData, execute_sync, get_retry_policy
from .. import throttle_service

# Prompt模板目录
PROMPT_DIR = Path(__file__).resolve().parent / "prompt"


class ContentFilterError(Exception):
    """当API返回content_filter finish_reason时抛出此异常"""

def read_text(path: str) -> str:
    """读取文本文件内容"""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def ensure_dir(path: Path) -> None:
    """确保目录存在，不存在则创建"""
    path.mkdir(parents=True, exist_ok=True)

def call_ark_responses_api(
    messages: List[Dict[str, Any]],
    model: Optional[str] = None,
    previous_response_id: Optional[str] = None,
    stream: bool = False,
    thinking_config: Optional[str] = None,
    reasoning_effort_config: Optional[str] = None,
    project_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    同步调用火山引擎 Ark Responses API
    
    【功能说明】
    用于Phase 1的小说文本分析，提取角色、摘要、地点信息
    
    【参数】
    - messages: 对话消息列表
    - model: 模型名称，默认使用配置中的ARK_CHAT_MODEL
    - previous_response_id: 前一次响应ID，用于多轮对话保持上下文
    - stream: 是否流式输出
    - thinking_config: 思考模式配置
    - reasoning_effort_config: 推理努力程度配置
    
    【返回值】
    API响应的JSON字典
    
    【参考文档】
    https://www.volcengine.com/docs/82379/1569618?lang=zh
    """
    limiter = throttle_service.get_model_limiter("ark")
    if limiter:
        asyncio.run(limiter.acquire())
    # Adjust URL if base url ends with /api/v3
    base_url = runtime_config.ARK_BASE_URL.rstrip("/")
    if not base_url.endswith("/api/v3"):
        # Attempt to guess or append if missing, but config says it has /api/v3
        pass
    
    url = f"{base_url}/responses"
    
    headers = {
        "Authorization": f"Bearer {runtime_config.ARK_API_KEY}",
        "Content-Type": "application/json",
    }
    
    # Construct payload
    # "input" field takes the list of messages
    # Each message has "role", "content", and "type"="message"
    formatted_messages = []
    for msg in messages:
        formatted_messages.append({
            "role": msg["role"],
            "content": msg["content"],
            "type": "message" 
        })
        
    payload = {
        "model": model or runtime_config.ARK_CHAT_MODEL,
        "input": formatted_messages,
        "stream": stream,
    }
    
    #使用config的配置文件来控制思考预算
    
    if thinking_config and thinking_config != "disabled":
        thinking_payload = {"type": thinking_config}
        payload["thinking"] = thinking_payload
        
        # 根据用户反馈，通过 reasoning 字典调节思考长度
        if reasoning_effort_config and reasoning_effort_config != "disabled":
             # 格式: reasoning={"effort": "low"}
             payload["reasoning"] = {"effort": reasoning_effort_config}
    
    if previous_response_id:
        payload["previous_response_id"] = previous_response_id
        
    # print(f"[DEBUG] 调用 Responses API: {url}")
    # print(f"[DEBUG] Payload keys: {payload.keys()}")
    
    def _do_request(current_payload):
        response = requests.post(url, headers=headers, json=current_payload, timeout=runtime_config.ARK_TIMEOUT)
        return response

    try:
        request_payload = {"headers": headers, "payload": payload}
        log_retry, log_summary = _build_retry_loggers(
            "ark_responses",
            url,
            "POST",
            payload.get("model"),
            "ark_responses",
            request_payload,
            project=project_name,
        )
        policy, _, _ = get_retry_policy("ark_llm")
        timeout_sec = max(1, int(policy.timeout_ms)) / 1000 if policy.timeout_ms else runtime_config.ARK_TIMEOUT

        def request_once() -> ResponseData:
            start_time = time.time()
            api_log_event(
                "INFO",
                "api",
                "api_request",
                "ark responses request",
                api_name="ark_responses",
                endpoint=url,
                method="POST",
                model=payload.get("model"),
                request_payload=request_payload,
                step="ark_responses",
                project=project_name,
            )
            response = requests.post(url, headers=headers, json=payload, timeout=timeout_sec)
            if response.status_code == 400:
                err_text = response.text
                if "unknown field" in err_text and ("reasoning" in err_text or "effort" in err_text):
                    if "reasoning" in payload:
                        del payload["reasoning"]
                    if "thinking" in payload and isinstance(payload["thinking"], dict):
                        if "reasoning_effort" in payload["thinking"]:
                            del payload["thinking"]["reasoning_effort"]
                    response = requests.post(url, headers=headers, json=payload, timeout=timeout_sec)
            duration_ms = int((time.time() - start_time) * 1000)
            if response.status_code != 200:
                return ResponseData(
                    ok=False,
                    status_code=response.status_code,
                    response_json=None,
                    response_text=response.text,
                    headers=dict(response.headers),
                    finish_reason=None,
                    tts_code=None,
                    request_id=None,
                )
            resp_json = response.json()
            request_id = None
            if isinstance(resp_json, dict):
                request_id = resp_json.get("id") or resp_json.get("response_id")
            api_log_event(
                "INFO",
                "api",
                "api_response",
                "ark responses response",
                api_name="ark_responses",
                endpoint=url,
                method="POST",
                model=payload.get("model"),
                status_code=response.status_code,
                duration_ms=duration_ms,
                request_id=request_id,
                response_payload=resp_json,
                step="ark_responses",
                project=project_name,
            )
            finish_reason = None
            if "choices" in resp_json and isinstance(resp_json["choices"], list):
                for choice in resp_json["choices"]:
                    if choice.get("finish_reason") == "content_filter":
                        finish_reason = "content_filter"
                        break
            if finish_reason == "content_filter":
                return ResponseData(
                    ok=False,
                    status_code=response.status_code,
                    response_json=resp_json,
                    response_text=None,
                    headers=dict(response.headers),
                    finish_reason=finish_reason,
                    tts_code=None,
                    request_id=request_id,
                )
            return ResponseData(
                ok=True,
                status_code=response.status_code,
                response_json=resp_json,
                response_text=None,
                headers=dict(response.headers),
                finish_reason=finish_reason,
                tts_code=None,
                request_id=request_id,
            )

        result = execute_sync("ark_llm", request_once, log_retry, log_summary)
        if not result:
            return None
        if not isinstance(result.response_json, dict):
            return None
        return result.response_json
    finally:
        if limiter:
            limiter.release()

async def call_ark_responses_api_async(
    messages: List[Dict[str, Any]],
    model: Optional[str] = None,
    previous_response_id: Optional[str] = None,
    stream: bool = False,
    thinking_config: Optional[str] = None,
    reasoning_effort_config: Optional[str] = None,
    project_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    异步调用 Volcengine Ark Responses API。
    """
    limiter = await throttle_service.acquire_model_limit("ark")
    base_url = runtime_config.ARK_BASE_URL.rstrip("/")
    url = f"{base_url}/responses"
    
    headers = {
        "Authorization": f"Bearer {runtime_config.ARK_API_KEY}",
        "Content-Type": "application/json",
    }
    
    formatted_messages = []
    for msg in messages:
        formatted_messages.append({
            "role": msg["role"],
            "content": msg["content"],
            "type": "message" 
        })
        
    payload = {
        "model": model or runtime_config.ARK_CHAT_MODEL,
        "input": formatted_messages,
        "stream": stream,
    }
    
    if thinking_config and thinking_config != "disabled":
        thinking_payload = {"type": thinking_config}
        payload["thinking"] = thinking_payload
        if reasoning_effort_config and reasoning_effort_config != "disabled":
             payload["reasoning"] = {"effort": reasoning_effort_config}
    
    if previous_response_id:
        payload["previous_response_id"] = previous_response_id
        
    async with httpx.AsyncClient(timeout=runtime_config.ARK_TIMEOUT) as client:
        try:
            start_time = time.time()
            api_log_event(
                "INFO",
                "api",
                "api_request",
                "ark responses request",
                api_name="ark_responses",
                endpoint=url,
                method="POST",
                model=payload.get("model"),
                request_payload={"headers": headers, "payload": payload},
                step="ark_responses",
                project=project_name,
            )
            response = await client.post(url, headers=headers, json=payload)
            
            # 处理 400 错误 (复用同步版本的逻辑)
            if response.status_code == 400:
                err_text = response.text
                if "unknown field" in err_text and ("reasoning" in err_text or "effort" in err_text):
                    emit_event(
                        "WARN",
                        "auto_storyboard",
                        "log",
                        f"[WARN] [Async] API 不支持 reasoning 参数。正在重试...",
                        step="storyboard",
                        project=project_name,
                    )
                    if "reasoning" in payload:
                        del payload["reasoning"]
                    if "thinking" in payload and isinstance(payload["thinking"], dict):
                        if "reasoning_effort" in payload["thinking"]:
                            del payload["thinking"]["reasoning_effort"]
                    response = await client.post(url, headers=headers, json=payload)

            response.raise_for_status()
            resp_json = response.json()
            duration_ms = int((time.time() - start_time) * 1000)
            request_id = None
            if isinstance(resp_json, dict):
                request_id = resp_json.get("id") or resp_json.get("response_id")
            api_log_event(
                "INFO",
                "api",
                "api_response",
                "ark responses response",
                api_name="ark_responses",
                endpoint=url,
                method="POST",
                model=payload.get("model"),
                status_code=response.status_code,
                duration_ms=duration_ms,
                request_id=request_id,
                response_payload=resp_json,
                step="ark_responses",
                project=project_name,
            )
            
            # 检查 content_filter
            if "choices" in resp_json and isinstance(resp_json["choices"], list):
                for choice in resp_json["choices"]:
                    if choice.get("finish_reason") == "content_filter":
                        raise ContentFilterError(f"请求触发内容风控 (finish_reason='content_filter')")
            
            return resp_json
        except httpx.HTTPStatusError as e:
            emit_event(
                "ERROR",
                "auto_storyboard",
                "flow_error",
                f"[ERROR] [Async] API 请求失败: {e}",
                step="storyboard",
                project=project_name,
            )
            emit_event(
                "ERROR",
                "auto_storyboard",
                "flow_error",
                f"[ERROR] 响应内容: {e.response.text}",
                step="storyboard",
                project=project_name,
            )
            api_log_event(
                "ERROR",
                "api",
                "api_error",
                "ark responses error",
                api_name="ark_responses",
                endpoint=url,
                method="POST",
                model=payload.get("model"),
                status_code=e.response.status_code,
                response_payload=e.response.text,
                error_type=type(e).__name__,
                error_message=str(e),
                step="ark_responses",
                project=project_name,
            )
            raise
        except httpx.RequestError as e:
            emit_event(
                "ERROR",
                "auto_storyboard",
                "flow_error",
                f"[ERROR] [Async] 网络错误: {e}",
                step="storyboard",
                project=project_name,
            )
            api_log_event(
                "ERROR",
                "api",
                "api_error",
                "ark responses error",
                api_name="ark_responses",
                endpoint=url,
                method="POST",
                model=payload.get("model"),
                error_type=type(e).__name__,
                error_message=str(e),
                step="ark_responses",
                project=project_name,
            )
            raise
        finally:
            if limiter:
                limiter.release()

def extract_all_json_lists(text: str) -> List[Any]:
    """从文本中提取所有JSON列表"""
    return extract_json_lists(text)


def save_jsonl(data: List[Any], path: Path) -> None:
    """保存数据到JSONL文件"""
    ensure_dir(path.parent)
    with open(path, "w", encoding="utf-8") as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

def extract_text_content(response_data: Any) -> str:
    """
    从响应数据中提取文本内容（可能是字符串或列表）。
    忽略 'reasoning' 或其他类型。
    """
    if isinstance(response_data, str):
        return response_data
    elif isinstance(response_data, list):
        text_parts = []
        for item in response_data:
            if isinstance(item, dict):
                # print(f"[DEBUG] 输出项类型: {item.get('type')}")
                # 包含 'text' 以及可能的其他非 reasoning 内容类型
                # 如果类型缺失，假设它是内容？
                ctype = item.get("type", "text")
                if ctype != "reasoning":
                    content = item.get("content", "")
                    if isinstance(content, str):
                        text_parts.append(content)
                    elif isinstance(content, list):
                        for part in content:
                            if isinstance(part, str):
                                text_parts.append(part)
                            elif isinstance(part, dict):
                                if "text" in part:
                                    text_parts.append(part["text"])
                                elif "content" in part:
                                    text_parts.append(str(part["content"]))
        return "".join(text_parts)
    return ""

def generate_short_id(prefix: str) -> str:
    """
    生成带有前缀的短随机ID (8位)
    
    【参数】
    - prefix: ID前缀，如 "char"(角色)、"loc"(地点)、"outfit"(服装)
    
    【返回值】
    格式为 "prefix_xxxxxx" 的随机ID字符串
    
    【示例】
    generate_short_id("char") -> "char_a1b2c3"
    """
    return f"{prefix}_{uuid.uuid4().hex[:6]}"

def sanitize_assets(characters: List[Dict], locations: List[Dict]) -> Tuple[List[Dict], List[Dict], Dict[str, str]]:
    """
    清洗资产 ID，使用随机 ID 替换可能的重复 ID
    
    【功能说明】
    Phase 1中使用，防止LLM生成的ID可能存在的重复问题
    为每个角色、地点、服装生成新的随机ID
    
    【处理逻辑】
    1. 为每个角色生成新的Character_Id
    2. 为每个服装生成新的Outfit_id
    3. 为每个地点生成新的Location_ID(基于地点名称去重)
    4. 记录旧ID到新ID的映射关系
    
    【参数】
    - characters: 角色列表
    - locations: 地点列表
    
    【返回值】
    - new_chars: 清洗后的角色列表
    - new_locs: 清洗后的地点列表  
    - id_map: 旧ID到新ID的映射表
    """
    id_map = {}
    new_chars = []
    new_locs = []
    
    # 1. 处理人物
    for char in characters:
        if not isinstance(char, dict):
            new_chars.append(char)
            continue
            
        new_char = char.copy()
        
        # 处理 Character_Id
        old_cid = new_char.get("Character_Id") or new_char.get("character_id")
        new_cid = generate_short_id("char")
        
        # 统一 key 为 Character_Id
        if "character_id" in new_char:
            del new_char["character_id"]
        new_char["Character_Id"] = new_cid
        
        if old_cid:
            id_map[old_cid] = new_cid
            
        # 处理服装 ID (Default_Outfit)
        def_outfit = new_char.get("Default_Outfit (Clothing)")
        if isinstance(def_outfit, dict):
            old_oid = def_outfit.get("Outfit_id")
            new_oid = generate_short_id("outfit")
            if old_oid:
                def_outfit["Outfit_id"] = new_oid
                id_map[old_oid] = new_oid
            else:
                def_outfit["Outfit_id"] = new_oid
        
        # 处理服装变更 (Plot_Costume_Change)
        changes = new_char.get("Plot_Costume_Change")
        if isinstance(changes, list):
            for change in changes:
                if isinstance(change, dict):
                    old_oid = change.get("Outfit_id")
                    new_oid = generate_short_id("outfit")
                    if old_oid:
                        change["Outfit_id"] = new_oid
                        id_map[old_oid] = new_oid
                    else:
                        change["Outfit_id"] = new_oid
                        
        new_chars.append(new_char)

    # 2. 处理地点
    # 新增: 基于地点名称的去重逻辑
    loc_name_to_new_id = {}
    
    for loc in locations:
        if not isinstance(loc, dict):
            new_locs.append(loc)
            continue
            
        new_loc = loc.copy()
        
        # 获取旧 ID (可能不存在，因为用户已经去掉了)
        # 仍然保留检查以防万一模型输出了，或者为了兼容旧数据
        old_lid = new_loc.get("Location_ID") or new_loc.get("location_id")
        
        # 获取地点名称 (用于去重)
        loc_name = new_loc.get("Location") or new_loc.get("Location_Name")
        if loc_name:
            loc_name = loc_name.strip()
            
        # 决定新 ID
        if loc_name and loc_name in loc_name_to_new_id:
            # 如果名字已存在，复用已生成的 ID
            new_lid = loc_name_to_new_id[loc_name]
        else:
            # 否则生成新 ID
            new_lid = generate_short_id("loc")
            if loc_name:
                loc_name_to_new_id[loc_name] = new_lid
        
        # 统一 key
        if "location_id" in new_loc:
            del new_loc["location_id"]
        # 清理可能存在的旧 Location_id (大小写变体)
        if "Location_id" in new_loc:
             del new_loc["Location_id"]
             
        new_loc["Location_ID"] = new_lid
        
        # 如果存在旧 ID，记录映射关系，以防 Phase 1 偶然输出了 ID
        # 或者如果有引用关系需要维护
        if old_lid:
            id_map[old_lid] = new_lid
        

        
        is_duplicate = False
        for existing in new_locs:
            if existing.get("Location_ID") == new_lid:
                is_duplicate = True
                break
        
        if not is_duplicate:
            new_locs.append(new_loc)
        
    return new_chars, new_locs, id_map

def validate_and_fix_storyboard_ids(storyboard_list: List[Dict], characters: List[Dict], locations: List[Dict]) -> Tuple[List[Dict], Dict[str, int]]:
    """
    校验并修正分镜中的 ID
    
    【功能说明】
    Phase 2中使用，校验分镜中引用的角色ID和地点ID是否有效
    如果ID无效但名称有效，则根据名称反查并修正ID
    
    【校验策略】
    1. 构建角色ID集合和名称映射表
    2. 构建地点ID集合和名称映射表
    3. 遍历每个分镜，检查Location_ID和Character_ID
    4. 如果ID无效，尝试通过名称查找正确的ID
    5. 调用enforce_storyboard_fields确保字段完整
    
    【参数】
    - storyboard_list: 分镜列表
    - characters: 角色列表(用于构建ID索引)
    - locations: 地点列表(用于构建ID索引)
    
    【返回值】
    - validated_list: 校验后的分镜列表
    - fixed_count: 修正统计信息(char_fixed/loc_fixed/char_unknown/loc_unknown)
    """
    # 1. 构建索引
    char_id_set = set()
    loc_id_set = set()
    
    char_name_map, _ = build_character_name_map(characters)
    loc_name_map = build_location_name_map(locations)
    for c in characters:
        cid = c.get("Character_Id")
        if cid:
            char_id_set.add(cid)
    for l in locations:
        lid = l.get("Location_ID") or l.get("Location_Id")
        if lid:
            loc_id_set.add(lid)
            
    # 2. 遍历修正
    fixed_count = {"char_fixed": 0, "loc_fixed": 0, "char_unknown": 0, "loc_unknown": 0}
    validated_list = []
    
    for shot in storyboard_list:
        if not isinstance(shot, dict):
            validated_list.append(shot)
            continue
            
        new_shot = shot.copy()
        
        # --- 修正地点 ---
        # 优先读取可能的 Key
        lid = new_shot.get("Location_ID") or new_shot.get("Location_Id") or new_shot.get("location_id")
        lname = new_shot.get("Location")
        
        final_lid = lid
        
        # 如果 ID 不在集合中，尝试通过名称修复
        if lid not in loc_id_set:
            # ID 无效或缺失，尝试用名字找
            if lname and lname in loc_name_map:
                final_lid = loc_name_map[lname]
                fixed_count["loc_fixed"] += 1
            else:
                fixed_count["loc_unknown"] += 1
        
        if final_lid:
            new_shot["Location_Id"] = final_lid
        
        char_list = new_shot.get("Characters")
        if not isinstance(char_list, list):
            char_list = new_shot.get("Character_List")
        if not isinstance(char_list, list):
            char_list = new_shot.get("characters")
        if isinstance(char_list, list):
            new_char_list = []
            for item in char_list:
                if not isinstance(item, dict):
                    new_char_list.append(item)
                    continue
                new_item = item.copy()
                cid = new_item.get("Character_Id") or new_item.get("Character_id") or new_item.get("character_id")
                cname = new_item.get("Character_name") or new_item.get("Character_Name") or new_item.get("name")
                if cid not in char_id_set:
                    if cname and cname in char_name_map:
                        correct_id = char_name_map[cname]
                        new_item["Character_Id"] = correct_id
                        new_item["Character_id"] = correct_id
                        fixed_count["char_fixed"] += 1
                    else:
                        fixed_count["char_unknown"] += 1
                new_char_list.append(new_item)
            new_shot["Characters"] = new_char_list
            new_shot["Character_List"] = new_char_list

        new_shot = enforce_storyboard_fields(new_shot, final_lid)
        validated_list.append(new_shot)
        
    return validated_list, fixed_count

def save_json(data: Any, path: Path) -> None:
    """保存数据到JSON文件(带缩进格式)"""
    ensure_dir(path.parent)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def upload_generated_assets(local_base_dir: Path, prefix: str = "", project_name: str = "") -> bool:
    """
    将生成的资产文件上传到 TOS

    【上传内容】
    1. 根目录下的 jsonl 文件(characters.jsonl, locations.jsonl, summaries.jsonl)
    2. storyboards 子目录下的分镜剧本文件

    【参数】
    - local_base_dir: 本地资产目录
    - prefix: 日志前缀
    - project_name: 项目名称（用于线程安全）

    【返回值】
    - True: 上传成功
    - False: 上传失败或TOS不可用
    """
    # 使用传入的project_name获取项目特定的TOS前缀（线程安全）
    actual_project_name = project_name
    project_prefixes = runtime_config.get_project_prefixes(actual_project_name)
    tos_assets_prefix = project_prefixes["TOS_ASSETS_PREFIX"]

    emit_event(
        "INFO",
        "auto_storyboard",
        "upload_start",
        f"开始上传资产到 TOS: {runtime_config.TOS_BUCKET}/{tos_assets_prefix}",
        step="upload",
        project=actual_project_name,
    )
    emit_event(
        "INFO",
        "auto_storyboard",
        "log",
        f"[*] {prefix}开始上传资产到 TOS: {runtime_config.TOS_BUCKET}/{tos_assets_prefix} ...",
        step="storyboard",
        project=actual_project_name,
    )
    try:
        tos = TosClientWrapper()
        if not tos.available():
            emit_event(
                "WARN",
                "auto_storyboard",
                "upload_complete",
                "TOS 客户端不可用，跳过上传",
                step="upload",
                project=actual_project_name,
                data={"skipped": True},
            )
            emit_event(
                "WARN",
                "auto_storyboard",
                "log",
                f"[WARN] {prefix}TOS 客户端不可用，跳过上传。",
                step="storyboard",
                project=actual_project_name,
            )
            return False

        # 1. 上传根目录下的 jsonl (characters, locations, summaries)
        uploaded_count = 0
        for f in local_base_dir.glob("*.jsonl"):
            key = f"{tos_assets_prefix}/{f.name}"
            tos.upload_file(runtime_config.TOS_BUCKET, key, f)
            uploaded_count += 1
            emit_event(
                "INFO",
                "auto_storyboard",
                "upload_progress",
                f"Uploaded: {f.name} -> {key}",
                step="upload",
                project=actual_project_name,
                data={"file": f.name, "key": key, "uploaded": uploaded_count},
            )
            emit_event(
                "INFO",
                "auto_storyboard",
                "log",
                f"[INFO] {prefix}Uploaded: {f.name} -> {key}",
                step="storyboard",
                project=actual_project_name,
            )

        # 2. 上传 storyboards 子目录
        sb_dir = local_base_dir / "storyboards"
        if sb_dir.exists():
            for f in sb_dir.glob("*.jsonl"):
                key = f"{tos_assets_prefix}/storyboards/{f.name}"
                tos.upload_file(runtime_config.TOS_BUCKET, key, f)
                uploaded_count += 1
                emit_event(
                    "INFO",
                    "auto_storyboard",
                    "upload_progress",
                    f"Uploaded: storyboards/{f.name} -> {key}",
                    step="upload",
                    project=actual_project_name,
                    data={"file": f"storyboards/{f.name}", "key": key, "uploaded": uploaded_count},
                )
                emit_event(
                    "INFO",
                    "auto_storyboard",
                    "log",
                    f"[INFO] {prefix}Uploaded: storyboards/{f.name} -> {key}",
                    step="storyboard",
                    project=actual_project_name,
                )

        emit_event(
            "INFO",
            "auto_storyboard",
            "upload_complete",
            "资产上传完成",
            step="upload",
            project=actual_project_name,
            data={"uploaded": uploaded_count},
        )
        emit_event(
            "INFO",
            "auto_storyboard",
            "log",
            f"[*] {prefix}资产上传完成。",
            step="storyboard",
            project=actual_project_name,
        )
        return True
    except (IOError, OSError) as e:
        emit_event(
            "ERROR",
            "auto_storyboard",
            "flow_error",
            f"资产上传失败: {e}",
            step="upload",
            project=actual_project_name,
        )
        emit_event(
            "ERROR",
            "auto_storyboard",
            "flow_error",
            f"[ERROR] {prefix}资产上传失败: {e}",
            step="storyboard",
            project=actual_project_name,
        )
        return False

def run_workflow(
    novel_path: str,
    project_name: Optional[str] = None,
    phase: str = "full",
    chapter_size: Optional[int] = None,
    target_chapters: Optional[int] = None,
    per_chapter_shots: Optional[int] = None,
    previous_response_id: Optional[str] = None,
    phase1_force_regen: bool = False,
):
    """
    自动分镜生成工作流主入口

    【功能说明】
    协调执行Phase 1和Phase 2，完成从小说文本到分镜剧本的完整转换

    【执行模式】
    - phase="phase1": 仅执行Phase 1，提取角色/摘要/地点
    - phase="phase2": 仅执行Phase 2，基于已有资产生成分镜
    - phase="full": 执行完整流程(Phase 1 + Phase 2)

    【参数】
    - novel_path: 小说文件路径
    - project_name: 项目名称，用于输出目录和事件追踪
    - phase: 执行阶段("phase1"/"phase2"/"full")
    - chapter_size: 每章字数(用于估算章节数)
    - target_chapters: 目标章节数(优先级高于chapter_size)
    - per_chapter_shots: 每章分镜数
    - previous_response_id: 前一次API响应ID(用于多轮对话)
    - phase1_force_regen: 是否强制重新生成Phase 1

    【输出】
    - 角色列表: characters.jsonl
    - 地点列表: locations.jsonl
    - 章节摘要: summaries.jsonl
    - 分镜剧本: storyboards/storyboard_chapter_*.jsonl
    """
    project_info = f"[{project_name}] " if project_name else ""
    prefix = project_info
    
    emit_event(
        "INFO",
        "auto_storyboard",
        "flow_start",
        f"开始处理小说: {novel_path}",
        step="start",
        phase=phase,
        project=project_name,
    )
    # 使用传入的project_name或runtime_config中的值
    actual_project_name = project_name
    
    emit_event(
        "INFO",
        "auto_storyboard",
        "log",
        f"[*] {prefix}开始处理小说: {novel_path}",
        step="storyboard",
        project=actual_project_name,
    )
    
    if phase not in {"phase1", "phase2", "full", "upload"}:
        raise ValueError("invalid_phase")

    output_base = Path(runtime_config.OUTPUT_DIR) / actual_project_name / "storyboard_assets"
    ensure_dir(output_base)
    manifest_path = output_base / "phase1_manifest.json"

    def remove_path(path: Path, removed: List[str], errors: List[str]) -> None:
        if not path.exists():
            return
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            removed.append(str(path))
        except (IOError, OSError) as exc:
            errors.append(f"{path}:{exc}")

    def clear_phase1_assets() -> None:
        removed: List[str] = []
        errors: List[str] = []
        targets = [
            output_base / "characters.jsonl",
            output_base / "locations.jsonl",
            output_base / "summaries.jsonl",
            output_base / "raw_characters.jsonl",
            output_base / "raw_locations.jsonl",
            output_base / "raw_summaries.jsonl",
            manifest_path,
        ]
        for target in targets:
            remove_path(target, removed, errors)
        emit_event(
            "INFO" if not errors else "WARN",
            "auto_storyboard",
            "phase_cleanup",
            "清理 Phase 1 产物",
            step="phase_cleanup",
            phase="phase1",
            project=project_name,
            data={"removed": removed, "errors": errors},
        )
        emit_event(
            "INFO",
            "auto_storyboard",
            "log",
            f"[*] {prefix}清理 Phase 1 产物，删除 {len(removed)} 项。",
            step="phase1",
            project=actual_project_name,
        )

    def clear_phase2_assets() -> None:
        removed: List[str] = []
        errors: List[str] = []
        storyboards_dir = output_base / "storyboards"
        if storyboards_dir.exists():
            for item in sorted(storyboards_dir.iterdir()):
                if item.is_file() and item.name.startswith("storyboard_chapter_") and item.suffix.lower() == ".jsonl":
                    remove_path(item, removed, errors)
        emit_event(
            "INFO" if not errors else "WARN",
            "auto_storyboard",
            "phase_cleanup",
            "清理 Phase 2 产物",
            step="phase_cleanup",
            phase="phase2",
            project=project_name,
            data={"removed": removed, "errors": errors},
        )
        emit_event(
            "INFO",
            "auto_storyboard",
            "log",
            f"[*] {prefix}清理 Phase 2 产物，删除 {len(removed)} 项。",
            step="phase2",
            project=actual_project_name,
        )

    def load_phase1_manifest() -> Optional[Dict[str, Any]]:
        if not manifest_path.exists():
            return None
        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def load_phase1_assets() -> Optional[Tuple[List[Dict], List[Dict], List[Dict]]]:
        chars_path = output_base / "characters.jsonl"
        sums_path = output_base / "summaries.jsonl"
        locs_path = output_base / "locations.jsonl"
        if not chars_path.exists() or not sums_path.exists() or not locs_path.exists():
            return None
        return read_jsonl(str(chars_path)), read_jsonl(str(sums_path)), read_jsonl(str(locs_path))

    phase1_response_id = None
    characters_list: List[Dict] = []
    summaries_list: List[Dict] = []
    locations_list: List[Dict] = []

    # Phase 1：文本抽取与结构化产出（角色/摘要/地点），用于后续分镜生成
    if phase in {"phase1", "full"}:
        clear_phase2_assets()
        clear_phase1_assets()
        if not characters_list:
            prompt_path = str(PROMPT_DIR / "storyboard.txt")
            system_prompt_content = read_text(prompt_path)
            novel_content = read_text(novel_path)
            word_count = len(novel_content)
            if target_chapters and target_chapters > 0:
                final_target_chapters = target_chapters
            elif chapter_size and chapter_size > 0:
                final_target_chapters = max(1, int((word_count + chapter_size - 1) // chapter_size))
            else:
                final_target_chapters = max(1, word_count // 2500)
            resolved_target_chapters = final_target_chapters
            emit_event(
                "INFO",
                "auto_storyboard",
                "log",
                f"[INFO] {prefix}小说字数: {word_count}, 建议章节数: {final_target_chapters} ",
                step="storyboard",
                project=actual_project_name,
            )
            emit_event(
                "INFO",
                "auto_storyboard",
                "phase_start",
                "阶段 1: 提取人物、摘要和地点",
                step="phase1",
                phase="phase1",
                project=project_name,
            )
            emit_event(
                "INFO",
                "auto_storyboard",
                "log",
                f"[*] {prefix}阶段 1: 提取人物、摘要和地点...",
                step="storyboard",
                project=actual_project_name,
            )

            phase1_instruction = (
                f"请分析小说内容，并输出三个独立的JSON列表（不要合并到一个列表中）：\n"
                f"1. 【角色抽取列表】：请严格遵循系统提示词中的定义和示例格式，输出人物列表。\n"
                f"2. 【章节剧本总结】：请严格遵循系统提示词中的定义和示例格式，输出章节摘要。建议将小说分成{final_target_chapters}章左右（浮动±1）。\n"
                f"3. 【地点列表】：请提取小说中的关键地点。\n"
                f"请确保输出格式为标准的 JSON 列表，可以直接被解析。"
            )

            messages_phase1 = [
                {"role": "system", "content": system_prompt_content},
                {"role": "user", "content": f"{novel_content}\n\n{phase1_instruction}"}
            ]

            phase1_retry_count = 0
            max_retries = 3
            phase1_content = ""
            while phase1_retry_count < max_retries:
                emit_event(
                    "INFO",
                    "auto_storyboard",
                    "step_progress",
                    f"阶段 1 调用 API (尝试 {phase1_retry_count + 1}/{max_retries})",
                    step="phase1_api_call",
                    phase="phase1",
                    project=project_name,
                    data={"attempt": phase1_retry_count + 1, "max": max_retries},
                )
                emit_event(
                    "INFO",
                    "auto_storyboard",
                    "retry",
                    f"[*] {prefix}阶段 1 调用 API (尝试 {phase1_retry_count + 1}/{max_retries})...",
                    step="storyboard",
                    project=actual_project_name,
                )
                try:
                    resp_phase1 = call_ark_responses_api(
                        messages_phase1,
                        thinking_config=runtime_config.PHASE1_THINKING,
                        reasoning_effort_config=runtime_config.PHASE1_REASONING_EFFORT,
                        previous_response_id=previous_response_id,
                        project_name=actual_project_name,
                    )
                    if not isinstance(resp_phase1, dict):
                        emit_event(
                            "WARN",
                            "auto_storyboard",
                            "phase_error",
                            "阶段 1 API 无响应或响应格式异常",
                            step="phase1",
                            phase="phase1",
                            project=project_name,
                        )
                        emit_event(
                            "WARN",
                            "auto_storyboard",
                            "log",
                            f"[WARN] {prefix}阶段 1 API 无响应或响应格式异常。",
                            step="storyboard",
                            project=actual_project_name,
                        )
                        phase1_retry_count += 1
                        continue

                    phase1_response_id = resp_phase1.get("id") or previous_response_id
                    phase1_content = ""

                    if "choices" in resp_phase1:
                        phase1_content = resp_phase1["choices"][0]["message"]["content"]
                    elif "output" in resp_phase1:
                        phase1_content = extract_text_content(resp_phase1["output"])
                    elif "content" in resp_phase1:
                        phase1_content = extract_text_content(resp_phase1["content"])
                    else:
                        emit_event(
                            "ERROR",
                            "auto_storyboard",
                            "flow_error",
                            f"[ERROR] {prefix}意外的响应结构: {resp_phase1.keys()}",
                            step="storyboard",
                            project=actual_project_name,
                        )
                        phase1_retry_count += 1
                        continue

                    emit_event(
                        "INFO",
                        "auto_storyboard",
                        "log",
                        f"[*] {prefix}阶段 1 完成。Response ID: {phase1_response_id}",
                        step="storyboard",
                        project=actual_project_name,
                    )

                    emit_event(
                        "INFO",
                        "auto_storyboard",
                        "log",
                        f"[*] {prefix}正在校验 Phase 1 输出格式...",
                        step="phase1",
                        project=actual_project_name,
                    )
                    extracted_lists = extract_all_json_lists(phase1_content)

                    if extracted_lists:
                        for lst in extracted_lists:
                            if not lst:
                                continue
                            first = lst[0]
                            if isinstance(first, dict):
                                keys_lower = [str(k).lower() for k in first.keys()]
                                is_char = any("character_name" in k for k in keys_lower)
                                is_sum = any("description" in k for k in keys_lower) and not any("location" in k for k in keys_lower)
                                is_loc = any("location" in k for k in keys_lower)
                                if is_char and not characters_list:
                                    characters_list = lst
                                elif is_sum and not summaries_list:
                                    summaries_list = lst
                                elif is_loc and not locations_list:
                                    locations_list = lst

                    missing = []
                    if not characters_list:
                        missing.append("人物表")
                    if not summaries_list:
                        missing.append("摘要表")
                    if not locations_list:
                        missing.append("地点表")

                    if not missing:
                        emit_event(
                            "INFO",
                            "auto_storyboard",
                            "phase_complete",
                            f"阶段 1 完成。Response ID: {phase1_response_id}",
                            step="phase1",
                            phase="phase1",
                            project=project_name,
                            data={"response_id": phase1_response_id},
                        )
                        emit_event(
                            "INFO",
                            "auto_storyboard",
                            "log",
                            f"[INFO] {prefix}Phase 1 校验通过，提取成功。",
                            step="phase1",
                            project=actual_project_name,
                        )
                        break
                    emit_event(
                        "WARN",
                        "auto_storyboard",
                        "log",
                        f"[WARN] {prefix}Phase 1 校验失败，缺失: {', '.join(missing)}。",
                        step="phase1",
                        project=actual_project_name,
                    )
                    emit_event(
                        "DEBUG",
                        "auto_storyboard",
                        "log",
                        f"[DEBUG] {prefix}原始内容前 500 字符:\n{phase1_content[:500]}",
                        step="storyboard",
                        project=actual_project_name,
                    )

                    phase1_retry_count += 1
                    if phase1_retry_count < max_retries:
                        retry_msg_parts = ["请提取并输出以下列表，务必严格使用 JSON 列表格式："]
                        if "人物表" in missing:
                            retry_msg_parts.append("- 【角色抽取列表】")
                        if "摘要表" in missing:
                            retry_msg_parts.append("- 【章节剧本总结】")
                        if "地点表" in missing:
                            retry_msg_parts.append("- 【地点列表】")
                        retry_instruction = "\n".join(retry_msg_parts)
                        messages_phase1.append({"role": "user", "content": retry_instruction})
                        time.sleep(2)
                except (IOError, OSError, ValueError) as e:
                    emit_event(
                        "ERROR",
                        "auto_storyboard",
                        "flow_error",
                        f"[ERROR] {prefix}Phase 1 API 调用异常: {e}",
                        step="phase1",
                        project=actual_project_name,
                    )
                    phase1_retry_count += 1
                    time.sleep(2)

            if phase1_retry_count >= max_retries:
                emit_event(
                    "ERROR",
                    "auto_storyboard",
                    "flow_error",
                    "Phase 1 重试多次后仍失败。无法继续执行工作流。",
                    step="phase1",
                    phase="phase1",
                    project=project_name,
                )
                emit_event(
                "ERROR",
                "auto_storyboard",
                "flow_error",
                f"[ERROR] {prefix}Phase 1 重试多次后仍失败。无法继续执行工作流。",
                step="phase1",
                project=actual_project_name,
            )
                return

            emit_event(
                "INFO",
                "auto_storyboard",
                "log",
                f"[*] {prefix}保存原始资产 (Raw)...",
                step="storyboard",
                project=actual_project_name,
            )
            save_jsonl(characters_list, output_base / "raw_characters.jsonl")
            save_jsonl(summaries_list, output_base / "raw_summaries.jsonl")
            save_jsonl(locations_list, output_base / "raw_locations.jsonl")
            emit_event(
                "INFO",
                "auto_storyboard",
                "log",
                f"[*] {prefix}正在执行资产 ID 清洗与重置...",
                step="storyboard",
                project=actual_project_name,
            )
            characters_list, locations_list, id_map = sanitize_assets(characters_list, locations_list)
            emit_event(
                "INFO",
                "auto_storyboard",
                "log",
                f"[INFO] {prefix}已重置 {len(id_map)} 个 ID。示例映射: {list(id_map.items())[:3]}",
                step="storyboard",
                project=actual_project_name,
            )
            save_jsonl(characters_list, output_base / "characters.jsonl")
            save_jsonl(summaries_list, output_base / "summaries.jsonl")
            save_jsonl(locations_list, output_base / "locations.jsonl")

            save_json(
                {
                    "phase1_response_id": phase1_response_id,
                    "chapter_size": chapter_size,
                    "target_chapters": resolved_target_chapters,
                    "total_chapters": len(summaries_list),
                    "generated_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
                    "sources": {"novel_path": str(novel_path)},
                },
                manifest_path,
            )

            emit_event(
                "INFO",
                "auto_storyboard",
                "step_progress",
                f"资产已保存到 {output_base}",
                step="assets_saved",
                project=project_name,
            )
            emit_event(
                "INFO",
                "auto_storyboard",
                "log",
                f"[*] {prefix}资产已保存到 {output_base}",
                step="storyboard",
                project=actual_project_name,
            )

            if phase == "phase1":
                return
    
    # Upload 模式：直接执行上传，不进入 Phase 2
    if phase == "upload":
        emit_event(
            "INFO",
            "auto_storyboard",
            "phase_start",
            "阶段 3: 上传资产",
            step="upload",
            phase="upload",
            project=actual_project_name,
        )
        upload_ok = upload_generated_assets(output_base, prefix, actual_project_name)
        if upload_ok:
            emit_event(
                "INFO",
                "auto_storyboard",
                "phase_complete",
                "上传完成",
                step="upload",
                phase="upload",
                project=actual_project_name,
            )
        return
    
    # Phase 2：基于 Phase 1 产出生成分镜内容
    if phase == "phase2":
        clear_phase2_assets()
        cached_assets = load_phase1_assets()
        if not cached_assets:
            emit_event(
                "ERROR",
                "auto_storyboard",
                "flow_error",
                "Phase 1 产物不存在，无法执行 Phase 2",
                step="phase2",
                phase="phase2",
                project=project_name,
            )
            emit_event(
                "ERROR",
                "auto_storyboard",
                "flow_error",
                f"[ERROR] {prefix}Phase 1 产物不存在，无法执行 Phase 2",
                step="phase1",
                project=actual_project_name,
            )
            raise RuntimeError("Phase 1 产物不存在，无法执行 Phase 2")
        characters_list, summaries_list, locations_list = cached_assets
        cached_manifest = load_phase1_manifest()
        phase1_response_id = previous_response_id or (cached_manifest.get("phase1_response_id") if cached_manifest else None)
    
    if not summaries_list:
        emit_event(
            "ERROR",
            "auto_storyboard",
            "flow_error",
            "摘要表为空，无法执行 Phase 2",
            step="phase2",
            phase="phase2",
            project=project_name,
        )
        emit_event(
                "ERROR",
                "auto_storyboard",
                "flow_error",
                f"[ERROR] {prefix}摘要表为空，无法执行 Phase 2",
                step="phase2",
                project=actual_project_name,
            )
        return

    emit_event(
        "INFO",
        "auto_storyboard",
        "phase_start",
        "阶段 2: 生成分镜",
        step="phase2",
        phase="phase2",
        project=project_name,
    )
    emit_event(
            "INFO",
            "auto_storyboard",
            "log",
            f"[*] {prefix}阶段 2: 生成分镜...",
            step="storyboard",
            project=actual_project_name,
        )
    
    import asyncio
    STORYBOARD_BATCH_SIZE = runtime_config.STORYBOARD_BATCH_SIZE
    STORYBOARD_THINKING = runtime_config.STORYBOARD_THINKING
    STORYBOARD_REASONING_EFFORT = runtime_config.STORYBOARD_REASONING_EFFORT

    batch_size = STORYBOARD_BATCH_SIZE
    shots_per_chapter = per_chapter_shots if per_chapter_shots and per_chapter_shots > 0 else 15
    
    # 准备 Prompt 中的资产字符串
    chars_str = json.dumps(characters_list, ensure_ascii=False)
    locs_str = json.dumps(locations_list, ensure_ascii=False)
    sums_str = json.dumps(summaries_list, ensure_ascii=False)

    # 内部函数：处理单个批次 (异步版)
    async def process_batch_async(batch_start, batch_end, context_chapters=None, base_response_id=None, include_allend: bool = True):
        chapter_info = f"[Chapter {batch_start}-{batch_end}] "
        full_prefix = f"{prefix}{chapter_info}"
        
        emit_event(
            "INFO",
            "auto_storyboard",
            "step_progress",
            f"开始处理章节 {batch_start}-{batch_end}",
            step="phase2_batch_progress",
            phase="phase2",
            project=project_name,
            chapter=f"{batch_start}-{batch_end}",
            data={"batch_start": batch_start, "batch_end": batch_end},
        )
        emit_event(
            "INFO",
            "auto_storyboard",
            "step_progress",
            f"[*] {full_prefix}开始处理章节 {batch_start}-{batch_end}...",
            step="storyboard",
            project=actual_project_name,
        )
        
        # 智能切片
        current_batch_sums = []
        if summaries_list:
            if len(summaries_list) >= batch_end:
                s_idx = max(0, batch_start - 1)
                e_idx = min(len(summaries_list), batch_end)
                current_batch_sums = summaries_list[s_idx : e_idx]
                emit_event(
                    "DEBUG",
                    "auto_storyboard",
                    "step_progress",
                    f"[DEBUG] {full_prefix}批次 {batch_start}-{batch_end} 使用摘要索引 {s_idx}-{e_idx} (共 {len(current_batch_sums)} 条)",
                    step="storyboard",
                    project=actual_project_name,
                )
            else:
                emit_event(
                    "WARN",
                    "auto_storyboard",
                    "log",
                    f"[WARN] {full_prefix}摘要数量 ({len(summaries_list)}) 少于目标章节 {batch_end}，发送全部摘要",
                    step="storyboard",
                    project=actual_project_name,
                )
                current_batch_sums = summaries_list
        
        batch_sums_str = json.dumps(current_batch_sums, ensure_ascii=False)
        
        allend_instruction = "，如果已经是小说最后一章结尾，则输出allend" if include_allend else ""
        batch_instruction = f"请输出{batch_start}-{batch_end}章的章节的剧本，确保剧本中的人物与场景都在之前的人物列表和地点列表中，每个章节不少于{shots_per_chapter}个分镜片段，每个剧本使用独立的json列表进行输出{allend_instruction}"
        
        user_input_content = ""
        if not context_chapters:
            user_input_content = (
                f"当前批次章节摘要：{batch_sums_str}，\n"
                f"角色信息：{chars_str}，\n"
                f"地点信息{locs_str}。\n\n"
                f"{batch_instruction}"
            )
        else:
            context_list = []
            for chap_data in context_chapters:
                c_num = chap_data.get("chapter")
                c_content = chap_data.get("content")
                context_list.append(f"【第{c_num}章剧本】\n{json.dumps(c_content, ensure_ascii=False)}")
            recent_boards_str = "\n".join(context_list)
            user_input_content = (
                f"当前批次章节摘要：{batch_sums_str}，\n"
                f"近三章分镜剧本（供参考连贯性）：\n{recent_boards_str}，\n"
                f"角色信息：{chars_str}，\n"
                f"地点信息{locs_str}。\n\n"
                f"{batch_instruction}"
            )

        messages_p2 = [{"role": "user", "content": user_input_content}]
        
        retry_count = 0
        max_retries = 3
        
        while retry_count < max_retries:
            try:
                resp_p2 = await call_ark_responses_api_async(
                    messages_p2,
                    thinking_config=STORYBOARD_THINKING,
                    reasoning_effort_config=STORYBOARD_REASONING_EFFORT,
                    previous_response_id=base_response_id,
                    project_name=actual_project_name
                )
                
                content_p2 = ""
                if "choices" in resp_p2:
                    content_p2 = resp_p2["choices"][0]["message"]["content"]
                elif "output" in resp_p2:
                    content_p2 = extract_text_content(resp_p2["output"])
                elif "content" in resp_p2:
                    content_p2 = extract_text_content(resp_p2["content"])
                    
                is_end = "allend" in content_p2
                
                data_lists = extract_all_json_lists(content_p2)
                
                if not data_lists:
                    # 解析失败，尝试重试
                    emit_event(
                        "WARN",
                        "auto_storyboard",
                        "retry",
                        f"[WARN] {full_prefix}未提取到 JSON 列表 (尝试 {retry_count+1}/{max_retries})",
                        step="storyboard",
                        project=actual_project_name,
                    )
                    retry_count += 1
                    if retry_count < max_retries:
                        retry_msg = "\n\n上一次生成的内容未包含有效的 JSON 列表，请务必使用 JSON 列表格式输出分镜剧本。"
                        # 追加到消息历史
                        messages_p2.append({"role": "user", "content": retry_msg})
                        await asyncio.sleep(2)
                    continue
                
                # 解析成功，进行后续处理
                batch_results = []
                c_idx = 0
                for lst in data_lists:
                    if not lst:
                        continue
                    
                    # --- ID 校验与修正 ---
                    validated_lst, stats = validate_and_fix_storyboard_ids(lst, characters_list, locations_list)
                    if stats["char_fixed"] > 0 or stats["loc_fixed"] > 0:
                        emit_event(
                            "INFO",
                            "auto_storyboard",
                            "log",
                            f"[INFO] {full_prefix}修正: 人物ID修正={stats['char_fixed']}, 地点ID修正={stats['loc_fixed']}",
                            step="storyboard",
                            project=actual_project_name,
                        )
                    # -------------------------
                    
                    c_num = batch_start + c_idx
                    # 保存文件
                    c_filename = f"storyboard_chapter_{c_num}.jsonl"
                    save_jsonl(validated_lst, output_base / "storyboards" / c_filename)
                    
                    batch_results.append({
                        "chapter": c_num,
                        "content": validated_lst
                    })
                    c_idx += 1
                    
                return batch_results, is_end
            except ContentFilterError:
                emit_event(
                    "ERROR",
                    "auto_storyboard",
                    "flow_error",
                    f"[ERROR] {full_prefix}触发内容风控！跳过此批次。",
                    step="storyboard",
                    project=actual_project_name,
                )
                err_dir = output_base / "storyboards"
                ensure_dir(err_dir)
                with open(err_dir / f"ERROR_CONTENT_FILTER_{batch_start}_{batch_end}.txt", "w", encoding="utf-8") as f:
                    f.write("Content Filter Triggered. Skipped.")
                return [], False
            except (IOError, OSError, ValueError) as e:
                emit_event(
                    "ERROR",
                    "auto_storyboard",
                    "flow_error",
                    f"[ERROR] {full_prefix}API 调用失败: {e} (尝试 {retry_count+1}/{max_retries})",
                    step="storyboard",
                    project=actual_project_name,
                )
                retry_count += 1
                if retry_count < max_retries:
                    await asyncio.sleep(2)
                else:
                    # 最终失败
                    emit_event(
                        "ERROR",
                        "auto_storyboard",
                        "flow_error",
                        f"Phase 2 批次 {batch_start}-{batch_end} 重试超限，API 调用失败",
                        step="phase2",
                        phase="phase2",
                        project=project_name,
                        data={
                            "batch_start": batch_start,
                            "batch_end": batch_end,
                            "attempt": retry_count,
                            "max_retries": max_retries,
                            "error": str(e),
                        },
                    )
                    err_dir = output_base / "storyboards"
                    ensure_dir(err_dir)
                    with open(err_dir / f"ERROR_EXCEPTION_{batch_start}_{batch_end}.txt", "w", encoding="utf-8") as f:
                        f.write(f"Exception: {str(e)}")
                    return [], False
        
        if retry_count >= max_retries:
            emit_event(
                "ERROR",
                "auto_storyboard",
                "flow_error",
                f"Phase 2 批次 {batch_start}-{batch_end} 重试超限，未解析到有效 JSON 列表",
                step="phase2",
                phase="phase2",
                project=project_name,
                data={
                    "batch_start": batch_start,
                    "batch_end": batch_end,
                    "attempt": retry_count,
                    "max_retries": max_retries,
                },
            )
        return [], False

    if target_chapters and target_chapters > 0 and summaries_list:
        summaries_list = summaries_list[:target_chapters]
    total_chapters_est = len(summaries_list) if summaries_list else 0
    emit_event(
        "INFO",
        "auto_storyboard",
        "log",
        f"[INFO] {prefix}根据摘要列表估算总章节数: {total_chapters_est}",
        step="storyboard",
        project=actual_project_name,
    )
    if total_chapters_est == 0:
        emit_event(
            "WARN",
            "auto_storyboard",
            "log",
            f"[WARN] {prefix}无法估算总章节数，跳过分镜生成。",
            step="storyboard",
            project=actual_project_name,
        )
        return

    async def run_parallel():
        emit_event(
            "INFO",
            "auto_storyboard",
            "log",
            f"[INFO] {prefix}固定并行生成 (Async Coroutines)，并发由模型限流统一控制。",
            step="storyboard",
            project=actual_project_name,
        )
        emit_event(
            "WARN",
            "auto_storyboard",
            "log",
            f"[WARN] {prefix}并行模式下，将无法使用'最近三章分镜'作为上下文，仅依赖章节摘要。",
            step="storyboard",
            project=actual_project_name,
        )
        tasks = []
        curr = 1
        total_requests = (total_chapters_est + batch_size - 1) // batch_size
        emit_event(
            "INFO",
            "auto_storyboard",
            "log",
            f"[INFO] {prefix}预计总请求数: {total_requests}",
            step="storyboard",
            project=actual_project_name,
        )
        req_count = 0
        while curr <= total_chapters_est:
            end = min(curr + batch_size - 1, total_chapters_est)
            tasks.append(process_batch_async(curr, end, None, phase1_response_id, False))
            curr += batch_size
            req_count += 1
        for coro in asyncio.as_completed(tasks):
            try:
                res, is_end = await coro
                if res:
                    first_chap = res[0]["chapter"]
                    last_chap = res[-1]["chapter"]
                    emit_event(
                        "INFO",
                        "auto_storyboard",
                        "step_progress",
                        f"批次 {first_chap}-{last_chap} 完成",
                        step="phase2_batch_progress",
                        phase="phase2",
                        project=project_name,
                        chapter=f"{first_chap}-{last_chap}",
                        data={"batch_start": first_chap, "batch_end": last_chap, "status": "completed"},
                    )
                    emit_event(
                        "INFO",
                        "auto_storyboard",
                        "log",
                        f"[*] {prefix}批次 {first_chap}-{last_chap} 完成。",
                        step="storyboard",
                        project=actual_project_name,
                    )
            except (IOError, OSError, ValueError) as e:
                emit_event(
                    "ERROR",
                    "auto_storyboard",
                    "flow_error",
                    f"[ERROR] {prefix}异步任务异常: {e}",
                    step="storyboard",
                    project=actual_project_name,
                )

    asyncio.run(run_parallel())
    emit_event(
        "INFO",
        "auto_storyboard",
        "phase_complete",
        "并行生成完成",
        step="phase2",
        phase="phase2",
        project=project_name,
    )
    emit_event(
        "INFO",
        "auto_storyboard",
        "log",
        f"[*] {prefix}并行生成完成。",
        step="storyboard",
        project=actual_project_name,
    )
    # 只有 full 模式才自动执行上传，step2 模式需要单独调用 step3_upload
    if phase == "full":
        upload_ok = upload_generated_assets(output_base, prefix, actual_project_name)
        if upload_ok:
            emit_event(
                "INFO",
                "auto_storyboard",
                "flow_complete",
                "auto_storyboard 完成",
                step="complete",
                project=actual_project_name,
            )
    else:
        # step2 模式，发送 phase_complete 事件但不执行上传
        emit_event(
            "INFO",
            "auto_storyboard",
            "phase_complete",
            "阶段 2 完成",
            step="phase2",
            phase="phase2",
            project=actual_project_name,
        )
    return

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        run_workflow(sys.argv[1])
    else:
        emit_event(
            "INFO",
            "auto_storyboard",
            "log",
            "用法: python -m backend.services.workflow_runtime.auto_storyboard <novel_path>",
            step="storyboard",
            project=runtime_config.PROJECT_NAME,
        )
