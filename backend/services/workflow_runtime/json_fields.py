"""
json_fields.py - JSON字段处理与映射模块

【模块职责】
处理JSON数据中的字段映射、标准化和校验，解决不同数据源字段命名不一致的问题

【主要功能】
1. 字段名标准化：处理大小写、下划线等差异
2. 角色/地点名称映射：构建名称到ID的映射表
3. 分镜字段补齐：确保分镜数据包含必要的角色和背景字段
4. 分镜提示词字段修复：同步storyboard和prompt之间的角色字段

【字段命名差异处理】
- Character_Id / Character_id / character_id
- Location_ID / Location_Id / location_id
- Character_name / Character_Name / name

【使用场景】
- Phase 2分镜生成后的字段标准化
- 分镜提示词生成时的字段同步
- 角色/地点引用校验时的名称映射
"""

import re
from typing import Any, Dict, List, Tuple


def normalize_keys(item: Dict[str, Any], key_map: Dict[str, str]) -> Dict[str, Any]:
    """
    根据key_map标准化字典的key
    
    【参数】
    - item: 原始字典
    - key_map: 字段名映射表 {原字段名: 目标字段名}
    
    【返回值】
    标准化后的新字典
    """
    out = dict(item)
    for key, value in item.items():
        target = key_map.get(key)
        if target and target not in out:
            out[target] = value
    return out


def normalize_list_keys(items: List[Dict[str, Any]], key_map: Dict[str, str]) -> List[Dict[str, Any]]:
    """对列表中的每个字典进行key标准化"""
    return [normalize_keys(item, key_map) for item in items if isinstance(item, dict)]


def build_character_name_map(characters: List[Dict[str, Any]]) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    构建角色名称映射表
    
    【功能说明】
    构建角色名称到ID、ID到名称的双向映射，支持别名处理
    
    【处理逻辑】
    1. 提取Character_Id和Character_name建立映射
    2. 处理Alias字段(支持列表和逗号分隔字符串)
    3. 去除名称前后空格
    
    【参数】
    - characters: 角色列表
    
    【返回值】
    - name_to_id: 名称到ID的映射
    - id_to_name: ID到名称的映射
    
    【示例】
    >>> chars = [{"Character_Id": "c1", "Character_name": "张三", "Alias": ["小张", "阿三"]}]
    >>> name_to_id, id_to_name = build_character_name_map(chars)
    >>> name_to_id["张三"], name_to_id["小张"]
    ("c1", "c1")
    """
    name_to_id: Dict[str, str] = {}
    id_to_name: Dict[str, str] = {}
    for c in characters:
        if not isinstance(c, dict):
            continue
        cid = c.get("Character_Id") or c.get("Character_id") or c.get("character_id")
        name = c.get("Character_name") or c.get("Character_Name") or c.get("name")
        if isinstance(cid, str) and cid and isinstance(name, str) and name:
            id_to_name[cid] = name
            name_to_id[name] = cid
            name_to_id[name.strip()] = cid
        alias = c.get("Alias")
        if alias:
            if isinstance(alias, list):
                for a in alias:
                    if isinstance(a, str) and a.strip():
                        name_to_id[a.strip()] = cid
            elif isinstance(alias, str):
                for a in alias.replace("，", ",").split(","):
                    if a.strip():
                        name_to_id[a.strip()] = cid
    return name_to_id, id_to_name


def build_location_name_map(locations: List[Dict[str, Any]]) -> Dict[str, str]:
    """
    构建地点名称映射表
    
    【参数】
    - locations: 地点列表
    
    【返回值】
    地点名称到ID的映射表
    """
    name_to_id: Dict[str, str] = {}
    for l in locations:
        if not isinstance(l, dict):
            continue
        lid = l.get("Location_ID") or l.get("Location_Id") or l.get("location_id")
        name = l.get("Location") or l.get("Location_Name") or l.get("name")
        if isinstance(lid, str) and lid and isinstance(name, str) and name:
            name_to_id[name] = lid
            name_to_id[name.strip()] = lid
    return name_to_id


def build_storyboard_character_fields(shot: Dict[str, Any]) -> Dict[str, str]:
    """
    从分镜数据中提取角色字段
    
    【功能说明】
    从分镜的Characters/Character_List/characters字段中提取角色ID
    生成标准化的Character_1, Character_2等字段
    
    【参数】
    - shot: 单个分镜数据
    
    【返回值】
    标准化的角色字段字典，如 {"Character_1": "c1", "Character_1_outfit": "o1"}
    """
    existing = {}
    for key, value in shot.items():
        if not isinstance(key, str):
            continue
        if key.startswith("Character_") and isinstance(value, str) and value:
            existing[key] = value
    if existing:
        return existing

    characters = shot.get("Characters")
    if not isinstance(characters, list):
        characters = shot.get("Character_List")
    if not isinstance(characters, list):
        characters = shot.get("characters")
    if not isinstance(characters, list):
        return {}

    out: Dict[str, str] = {}
    idx = 1
    for c in characters:
        if not isinstance(c, dict):
            continue
        cid = c.get("Character_Id") or c.get("Character_id") or c.get("character_id")
        outfit = c.get("Outfit") or c.get("outfit")
        if isinstance(cid, str) and cid:
            out[f"Character_{idx}"] = cid
            if isinstance(outfit, str) and outfit:
                out[f"Character_{idx}_outfit"] = outfit
            idx += 1
    return out


def enforce_storyboard_fields(shot: Dict[str, Any], location_id: str) -> Dict[str, Any]:
    """
    确保分镜包含必要的字段
    
    【功能说明】
    补齐分镜数据中缺失的Background_pic和角色字段
    
    【处理逻辑】
    1. 如果缺少Background_pic，使用location_id填充
    2. 调用build_storyboard_character_fields提取并添加角色字段
    
    【参数】
    - shot: 单个分镜数据
    - location_id: 地点ID，用于填充Background_pic
    
    【返回值】
    补齐字段后的分镜数据
    """
    out = dict(shot)
    if "Background_pic" not in out:
        if isinstance(location_id, str) and location_id:
            out["Background_pic"] = location_id
    fields = build_storyboard_character_fields(out)
    for key, value in fields.items():
        out[key] = value
    return out


def enforce_prompt_fields(prompt: Dict[str, Any], storyboard: Dict[str, Any]) -> Dict[str, Any]:
    """
    确保分镜提示词包含必要的字段
    
    【功能说明】
    将storyboard中的Background_pic和角色字段同步到prompt中
    用于保持分镜和提示词之间的一致性
    
    【参数】
    - prompt: 分镜提示词数据
    - storyboard: 对应的分镜数据
    
    【返回值】
    补齐字段后的提示词数据
    """
    out = dict(prompt)
    background_pic = storyboard.get("Background_pic")
    if not isinstance(background_pic, str) or not background_pic:
        background_pic = storyboard.get("Location_Id") or storyboard.get("Location_ID") or storyboard.get("location_id")
    if isinstance(background_pic, str) and background_pic:
        out["Background_pic"] = background_pic

    fields = build_storyboard_character_fields(storyboard)
    for key, value in fields.items():
        out[key] = value
    return out


def _extract_character_fields(item: Dict[str, Any]) -> Dict[str, Any]:
    """提取字典中的角色字段(Character_*)"""
    out: Dict[str, Any] = {}
    for key, value in item.items():
        if isinstance(key, str) and re.match(r"^Character_\d+(_outfit)?$", key):
            if isinstance(value, str) and value:
                out[key] = value
    return out


def fix_fenjing_character_fields(
    storyboards: List[Dict[str, Any]],
    prompts: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    修复分镜提示词中的角色字段
    
    【功能说明】
    确保prompt中的角色字段与storyboard保持一致
    用于fenjing生成前的数据校验
    
    【处理逻辑】
    1. 遍历每个prompt和对应的storyboard
    2. 比较两者的角色字段差异
    3. 修复缺失、错误、多余的角色字段
    4. 统计修复情况
    
    【参数】
    - storyboards: 分镜列表
    - prompts: 分镜提示词列表
    
    【返回值】
    - updated: 修复后的提示词列表
    - stats: 修复统计信息(fixed_count/filled_count/removed_count/updated_count/affected_fenjing_ids)
    """
    updated: List[Dict[str, Any]] = []
    fixed_count = 0
    filled_count = 0
    removed_count = 0
    updated_count = 0
    affected_fenjing_ids: List[str] = []

    for idx, prompt in enumerate(prompts):
        if not isinstance(prompt, dict):
            updated.append(prompt)
            continue
        storyboard = storyboards[idx] if idx < len(storyboards) and isinstance(storyboards[idx], dict) else None
        if storyboard is None:
            updated.append(prompt)
            continue
        desired = build_storyboard_character_fields(storyboard)
        current = _extract_character_fields(prompt)
        changed = False

        for key, value in desired.items():
            if key not in current:
                filled_count += 1
                changed = True
            elif current.get(key) != value:
                updated_count += 1
                changed = True

        for key in current.keys():
            if key not in desired:
                removed_count += 1
                changed = True

        if changed:
            new_prompt = dict(prompt)
            for key in list(current.keys()):
                if key not in desired and key in new_prompt:
                    new_prompt.pop(key, None)
            for key, value in desired.items():
                new_prompt[key] = value
            updated.append(new_prompt)
            fixed_count += 1
            fenjing_id = new_prompt.get("fenjing_id")
            if isinstance(fenjing_id, str) and fenjing_id:
                affected_fenjing_ids.append(fenjing_id)
        else:
            updated.append(prompt)

    stats = {
        "fixed_count": fixed_count,
        "filled_count": filled_count,
        "removed_count": removed_count,
        "updated_count": updated_count,
        "affected_fenjing_ids": affected_fenjing_ids,
    }
    return updated, stats
