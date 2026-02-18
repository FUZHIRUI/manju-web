"""
json_parse.py - JSON解析与修复工具模块

【模块职责】
提供强大的JSON解析功能，能够处理各种非标准或损坏的JSON格式

【主要功能】
1. 代码块清理：去除markdown代码块标记(```json ... ```)
2. JSONL解析：按行解析JSON Lines格式
3. 平衡括号解析：通过追踪大括号匹配提取JSON对象
4. 多列表提取：从复杂文本中提取多个JSON列表
5. 容错修复：使用json_repair库修复损坏的JSON

【使用场景】
- LLM返回的JSON数据解析(常包含markdown格式)
- 大文本中嵌入多个JSON对象的提取
- 损坏JSON的自动修复

【解析策略】
1. 首先尝试标准json.loads
2. 失败时尝试json_repair修复
3. 再失败时按行解析JSONL
4. 最后使用平衡括号算法提取对象
"""

import json
import re
from typing import Any, Dict, List


def strip_code_fences(content: str) -> str:
    """
    去除markdown代码块标记
    
    【处理内容】
    - ```json ... ```
    - ``` ... ```
    
    【参数】
    - content: 原始文本
    
    【返回值】
    清理后的文本
    """
    cleaned = content.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()


def normalize_list(items: Any) -> List[Dict[str, Any]]:
    """
    将单个对象或列表标准化为列表
    
    【参数】
    - items: 单个字典或字典列表
    
    【返回值】
    字典列表
    """
    if isinstance(items, dict):
        return [items]
    if not isinstance(items, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            out.append(item)
    return out


def _parse_jsonl_lines(content: str) -> List[Dict[str, Any]]:
    """
    按行解析JSONL格式
    
    【处理逻辑】
    逐行解析，跳过空行和解析失败的行
    """
    out: List[Dict[str, Any]] = []
    for line in content.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
            out.extend(normalize_list(parsed))
        except (json.JSONDecodeError, ValueError):
            continue
    return out


def _parse_balanced_objects(content: str) -> List[Dict[str, Any]]:
    """
    使用平衡括号算法提取JSON对象
    
    【功能说明】
    通过追踪大括号匹配状态，从混乱文本中提取完整的JSON对象
    支持字符串内的转义字符处理
    
    【算法逻辑】
    1. 逐字符遍历
    2. 追踪是否在字符串内(处理转义)
    3. 追踪大括号嵌套深度
    4. 当brace_count归零时尝试解析缓冲区内容
    """
    buffer = ""
    brace_count = 0
    in_string = False
    escape_next = False
    out: List[Dict[str, Any]] = []

    for char in content:
        if escape_next:
            escape_next = False
            buffer += char
            continue

        if char == "\\":
            escape_next = True
            buffer += char
            continue

        if char == '"':
            in_string = not in_string
            buffer += char
            continue

        if not in_string:
            if char == "{":
                brace_count += 1
            elif char == "}":
                brace_count -= 1

        buffer += char

        if brace_count == 0 and buffer.strip():
            candidate = buffer.strip()
            try:
                parsed = json.loads(candidate)
                out.extend(normalize_list(parsed))
                buffer = ""
            except (json.JSONDecodeError, ValueError):
                pass

    if buffer.strip():
        try:
            parsed = json.loads(buffer.strip())
            out.extend(normalize_list(parsed))
        except (json.JSONDecodeError, ValueError):
            pass

    return out


def parse_jsonl_or_array(content: str) -> List[Dict[str, Any]]:
    """
    解析JSONL或JSON数组
    
    【解析策略】
    1. 去除代码块标记
    2. 尝试标准json.loads解析整个内容
    3. 失败时尝试json_repair修复
    4. 再失败时按行解析JSONL
    5. 最后使用平衡括号算法
    
    【参数】
    - content: JSON文本
    
    【返回值】
    解析后的字典列表
    """
    cleaned = strip_code_fences(content)
    try:
        parsed = json.loads(cleaned)
        items = normalize_list(parsed)
        if items:
            return items
    except (json.JSONDecodeError, ValueError):
        pass

    try:
        import json_repair

        parsed = json_repair.loads(cleaned)
        items = normalize_list(parsed)
        if items:
            return items
    except (json.JSONDecodeError, ValueError, ImportError):
        pass

    items = _parse_jsonl_lines(cleaned)
    if items:
        return items

    return _parse_balanced_objects(cleaned)


def parse_json_list(content: str) -> List[Dict[str, Any]]:
    """parse_jsonl_or_array的别名"""
    return parse_jsonl_or_array(content)


def extract_json_lists(content: str) -> List[List[Dict[str, Any]]]:
    """
    从文本中提取所有JSON列表
    
    【功能说明】
    从复杂文本中提取多个JSON列表，支持多种格式
    
    【提取策略】
    1. 提取markdown代码块中的JSON
    2. 尝试将整个文本解析为列表
    3. 从字典值中提取列表
    4. 使用正则表达式匹配列表模式
    
    【参数】
    - content: 包含JSON列表的文本
    
    【返回值】
    提取到的JSON列表的列表
    """
    text = content.strip()
    found: List[List[Dict[str, Any]]] = []

    # 提取代码块
    code_blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    for block in code_blocks:
        try:
            import json_repair

            parsed = json_repair.loads(block)
            items = normalize_list(parsed)
            if items:
                found.append(items)
        except (json.JSONDecodeError, ValueError, ImportError):
            continue

    if found:
        return found

    # 尝试整体解析
    try:
        import json_repair

        parsed = json_repair.loads(text)
        if isinstance(parsed, list):
            items = normalize_list(parsed)
            if items:
                return [items]
        if isinstance(parsed, dict):
            lists_in_dict = []
            for v in parsed.values():
                if isinstance(v, list):
                    items = normalize_list(v)
                    if items:
                        lists_in_dict.append(items)
            if lists_in_dict:
                return lists_in_dict
    except (json.JSONDecodeError, ValueError, ImportError):
        pass

    # 正则匹配列表
    candidates = re.findall(r"(\[\s*\{[\s\S]*?\}\s*\])", text)
    for cand in candidates:
        try:
            import json_repair

            parsed = json_repair.loads(cand)
            items = normalize_list(parsed)
            if items:
                found.append(items)
        except (json.JSONDecodeError, ValueError, ImportError):
            continue

    return found
