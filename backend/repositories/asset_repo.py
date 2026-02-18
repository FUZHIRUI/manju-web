import json
import re
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from ..services.workflow_runtime import runtime_config
from ..services.workflow_runtime.io_jsonl import read_jsonl, write_jsonl
from ..services.workflow_runtime.provider_runtime import TosClientWrapper
from ..services.workflow_runtime.visual_audio_assets import character_keys_sorted, load_char_defaults
from ..services.workflow_runtime.fenjing import load_char_plot_outfits

from .media_repo import resolve_media_path
from .project_repo import (
    CHAPTER_PATTERN,
    list_files,
    project_base_dir,
    safe_read_jsonl,
    storyboard_assets_dir,
    visual_audio_assets_dir,
    to_project_relative,
)
from . import job_repo


def build_character_table(assets: Path) -> List[Dict[str, Any]]:
    path = assets / "characters.jsonl"
    rows: List[Dict[str, Any]] = []
    for item in safe_read_jsonl(path):
        if not isinstance(item, dict):
            continue
        outfit = item.get("Default_Outfit (Clothing)") or {}
        if not isinstance(outfit, dict):
            outfit = {}
        rows.append(
            {
                "Character_Id": item.get("Character_Id", ""),
                "Character_name": item.get("Character_name", ""),
                "Alias": item.get("Alias", ""),
                "attribute": item.get("attribute", ""),
                "Age_group": item.get("Age_group", ""),
                "Sex": item.get("Sex", ""),
                "Appearance": item.get("Appearance Description", ""),
                "Default_Outfit_id": outfit.get("Outfit_id", ""),
                "Default_Outfit_Description": outfit.get("Outfit_Description", ""),
                "Default_Shoes": item.get("Default_Shoes", ""),
            }
        )
    return rows


def build_location_table(assets: Path) -> List[Dict[str, Any]]:
    path = assets / "locations.jsonl"
    rows: List[Dict[str, Any]] = []
    for item in safe_read_jsonl(path):
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "Location_ID": item.get("Location_ID", ""),
                "Location": item.get("Location", ""),
                "Location_description": item.get("Location_description", ""),
            }
        )
    return rows


def build_expected_locations(project: str, assets: Path) -> List[Dict[str, Any]]:
    """
    构建期望的场景列表，包含场景ID、名称和是否有图片。
    只返回被分镜引用的场景，未引用的场景不显示占位符。
    """
    location_table = build_location_table(assets)
    existing_paths = [
        to_project_relative(project, Path(p))
        for p in list_files(assets / "location_images", (".png", ".jpg", ".jpeg"))
    ]
    existing_ids: Set[str] = set()
    for path in existing_paths:
        name = Path(path).stem
        match = re.match(r"^(.+?)_(standing|sitting)$", name, re.IGNORECASE)
        loc_id = match.group(1) if match else name
        existing_ids.add(loc_id)
    name_map: Dict[str, str] = {}
    for row in location_table:
        loc_id = str(row.get("Location_ID") or "").strip()
        loc_name = str(row.get("Location") or "").strip()
        if loc_id and loc_name:
            name_map[loc_id] = loc_name
    prompts_path = assets / "location_prompts.jsonl"
    for item in safe_read_jsonl(prompts_path):
        if not isinstance(item, dict):
            continue
        loc_id = str(item.get("Location_Id") or item.get("Location_ID") or "").strip()
        loc_name = str(item.get("Location") or "").strip()
        if loc_id and loc_name and loc_id not in name_map:
            name_map[loc_id] = loc_name
    referenced_ids = _collect_referenced_location_ids(assets)
    failed_results = list_asset_results(project, status="failed")
    failed_location_ids: Set[str] = set()
    failed_reasons: Dict[str, str] = {}
    for item in failed_results:
        if item.get("asset_type") == "location":
            loc_id = str(item.get("asset_id") or "")
            if loc_id:
                failed_location_ids.add(loc_id)
                reason = str(item.get("reason") or "")
                if reason and loc_id not in failed_reasons:
                    failed_reasons[loc_id] = reason
    all_ids = sorted((referenced_ids & set(name_map.keys())) | existing_ids)
    result: List[Dict[str, Any]] = []
    for loc_id in all_ids:
        result.append(
            {
                "location_id": loc_id,
                "location_name": name_map.get(loc_id, ""),
                "has_image": loc_id in existing_ids,
                "is_failed": loc_id in failed_location_ids,
                "fail_reason": failed_reasons.get(loc_id, ""),
            }
        )
    return result


def stringify_characters(chars: Any) -> str:
    if not chars:
        return ""
    if isinstance(chars, list):
        names: List[str] = []
        for c in chars:
            if isinstance(c, dict):
                name = c.get("Character_Name") or c.get("Character_name") or c.get("Character_Id")
                if isinstance(name, str) and name:
                    names.append(name)
        return "、".join(names)
    if isinstance(chars, dict):
        name = chars.get("Character_Name") or chars.get("Character_name") or chars.get("Character_Id")
        return name if isinstance(name, str) else ""
    return ""


def extract_fenjing_id(value: str) -> str:
    if not isinstance(value, str):
        return ""
    match = re.search(r"fenjing[_-]?(\d+)", value, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r"(\d+)", value)
    return match.group(1) if match else ""


def resolve_character_size_by_attribute(attribute: Optional[str]) -> Optional[str]:
    if isinstance(attribute, str):
        attr = attribute.strip()
        if attr == "人类":
            return runtime_config.CHARACTER_HUMAN_IMAGE_SIZE
        if attr == "兽类":
            return runtime_config.CHARACTER_BEAST_IMAGE_SIZE
    return None


def build_storyboard_table(assets: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    storyboards_dir = assets / "storyboards"
    if not storyboards_dir.exists():
        return rows
    files = sorted(storyboards_dir.glob("storyboard_chapter_*.jsonl"))
    for file in files:
        chapter_name = file.stem
        for item in safe_read_jsonl(file):
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "chapter": chapter_name,
                    "zhangjie_id": item.get("zhangjie_id", ""),
                    "Storyboard_id": item.get("Storyboard_id", ""),
                    "Era": item.get("Era", ""),
                    "Time": item.get("Time", ""),
                    "Location": item.get("Location", ""),
                    "Location_Id": item.get("Location_Id") or item.get("Location_id", ""),
                    "Characters": stringify_characters(item.get("Characters")),
                    "Action": item.get("Action", ""),
                }
            )
    return rows


def resolve_character_image(assets: Path, character_id: str, visual_assets: Optional[Path] = None) -> str:
    if not character_id:
        return ""
    path = assets / "character_images" / f"{character_id}.png"
    if path.exists():
        return str(path)
    if visual_assets:
        visual_path = visual_assets / "character_images" / f"{character_id}.png"
        if visual_path.exists():
            return str(visual_path)
    return ""


def resolve_cloth_image(assets: Path, outfit_id: str, visual_assets: Optional[Path] = None) -> str:
    if not outfit_id:
        return ""
    path = assets / "cloth_images" / f"{outfit_id}.png"
    if path.exists():
        return str(path)
    if visual_assets:
        visual_path = visual_assets / "cloth_images" / f"{outfit_id}.png"
        if visual_path.exists():
            return str(visual_path)
    return ""


def resolve_cloth_changed_image(assets: Path, character_id: str, outfit_id: str, visual_assets: Optional[Path] = None) -> str:
    if not character_id or not outfit_id:
        return ""
    path = assets / "cloth_changed_images" / f"{character_id}_{outfit_id}.png"
    if path.exists():
        return str(path)
    if visual_assets:
        visual_path = visual_assets / "cloth_changed_images" / f"{character_id}_{outfit_id}.png"
        if visual_path.exists():
            return str(visual_path)
    return ""


def resolve_location_image(assets: Path, loc_id: str, background_hint: str, visual_assets: Optional[Path] = None) -> str:
    if not loc_id:
        return ""
    suffix = "standing"
    if isinstance(background_hint, str):
        hint = background_hint.lower()
        if "sitting" in hint or "坐" in background_hint:
            suffix = "sitting"
    path = assets / "location_images" / f"{loc_id}_{suffix}.png"
    if path.exists():
        return str(path)
    fallback = assets / "location_images" / f"{loc_id}.png"
    if fallback.exists():
        return str(fallback)
    if visual_assets:
        visual_path = visual_assets / "location_images" / f"{loc_id}_{suffix}.png"
        if visual_path.exists():
            return str(visual_path)
        visual_fallback = visual_assets / "location_images" / f"{loc_id}.png"
        if visual_fallback.exists():
            return str(visual_fallback)
    return ""


def build_character_details(project: str, assets: Path) -> List[Dict[str, Any]]:
    prompt_map: Dict[str, str] = {}
    prompt_name_map: Dict[str, str] = {}
    prompts_path = assets / "character_prompts.jsonl"
    for item in safe_read_jsonl(prompts_path):
        if not isinstance(item, dict):
            continue
        cid = item.get("Character_Id") or item.get("Character_id") or item.get("character_id")
        if not isinstance(cid, str) or not cid:
            continue
        prompt_text = item.get("st_prompt") or item.get("prompt") or ""
        prompt_map[cid] = prompt_text if isinstance(prompt_text, str) else ""
        prompt_name = item.get("name") or item.get("Character_name") or item.get("Character_Name")
        if isinstance(prompt_name, str) and prompt_name.strip():
            prompt_name_map[cid] = prompt_name
    name_map: Dict[str, str] = {}
    chars_path = assets / "characters.jsonl"
    for item in safe_read_jsonl(chars_path):
        if not isinstance(item, dict):
            continue
        cid = item.get("Character_Id") or item.get("Character_id") or item.get("character_id")
        if not isinstance(cid, str) or not cid:
            continue
        name = item.get("Character_name") or item.get("Character_Name") or item.get("character_name")
        if isinstance(name, str) and name.strip():
            name_map[cid] = name
    main_map: Dict[str, Path] = {}
    main_dir = assets / "character_images"
    if main_dir.exists():
        for p in sorted(main_dir.iterdir()):
            if not p.is_file():
                continue
            if p.suffix.lower() not in (".png", ".jpg", ".jpeg"):
                continue
            main_map[p.stem] = p
    candidate_map: Dict[str, List[str]] = {}
    candidate_dir = assets / "character_candidates"
    if candidate_dir.exists():
        for p in sorted(candidate_dir.iterdir()):
            if not p.is_file():
                continue
            if p.suffix.lower() not in (".png", ".jpg", ".jpeg"):
                continue
            match = re.match(r"(.+)_\d+$", p.stem)
            cid = match.group(1) if match else p.stem
            candidate_map.setdefault(cid, []).append(to_project_relative(project, p))
    qc_map = _load_character_qc_map(project)
    ids = sorted(set(prompt_map.keys()) | set(main_map.keys()) | set(candidate_map.keys()))
    rows: List[Dict[str, Any]] = []
    for cid in ids:
        image_path = to_project_relative(project, main_map[cid]) if cid in main_map else ""
        qc_info = qc_map.get(cid, {})
        rows.append(
            {
                "character_id": cid,
                "character_name": name_map.get(cid) or prompt_name_map.get(cid, ""),
                "prompt": prompt_map.get(cid, ""),
                "image_path": image_path,
                "candidate_images": candidate_map.get(cid, []),
                "qc_pass": qc_info.get("qc_pass"),
                "qc_attempts": qc_info.get("qc_attempts", 0),
                "qc_reason": qc_info.get("reason", ""),
            }
        )
    return rows


def build_cloth_changed_prompt(outfit_desc: Any) -> str:
    base = "高质量真人摄影，正面及侧面形象拍摄，纯白色背景，采用影视级渲染效果。参考图中的人物站立，全身拍摄。给参考图中的人物换上服装参考图的衣服，穿的鞋不变，并在水平方向展示角色的正视、侧视图形象，保持人物形象不得改变。"
    if isinstance(outfit_desc, str) and outfit_desc.strip():
        return f"{base}服装描述：{outfit_desc}"
    return base


def build_cloth_changed_details(project: str, assets: Path) -> List[Dict[str, Any]]:
    chars_path = assets / "characters.jsonl"
    rows: List[Dict[str, Any]] = []
    candidate_map: Dict[str, List[str]] = {}
    candidate_dir = assets / "cloth_changed_candidates"
    if candidate_dir.exists():
        for p in sorted(candidate_dir.iterdir()):
            if not p.is_file():
                continue
            if p.suffix.lower() not in (".png", ".jpg", ".jpeg"):
                continue
            match = re.match(r"(.+)_\d+$", p.stem)
            key = match.group(1) if match else p.stem
            candidate_map.setdefault(key, []).append(to_project_relative(project, p))
    seen: Set[str] = set()
    for item in safe_read_jsonl(chars_path):
        if not isinstance(item, dict):
            continue
        cid = item.get("Character_Id") or item.get("Character_id") or item.get("character_id")
        if not isinstance(cid, str) or not cid:
            continue
        name = item.get("Character_name") or item.get("Character_Name") or ""
        changes = item.get("Plot_Costume_Change") or []
        if not isinstance(changes, list):
            continue
        for ch in changes:
            if not isinstance(ch, dict):
                continue
            outfit_id = ch.get("Outfit_id")
            if not isinstance(outfit_id, str) or not outfit_id:
                continue
            key = f"{cid}_{outfit_id}"
            if key in seen:
                continue
            seen.add(key)
            prompt_text = ch.get("st_prompt") or ch.get("prompt") or build_cloth_changed_prompt(ch.get("Outfit_Description"))
            image_path = assets / "cloth_changed_images" / f"{key}.png"
            rows.append(
                {
                    "cloth_changed_id": key,
                    "character_id": cid,
                    "outfit_id": outfit_id,
                    "character_name": name if isinstance(name, str) else "",
                    "prompt": prompt_text if isinstance(prompt_text, str) else "",
                    "image_path": to_project_relative(project, image_path) if image_path.exists() else "",
                    "candidate_images": candidate_map.get(key, []),
                }
            )
    return rows


def build_outfit_map_from_storyboard(assets_dir: Path, chapter_name: str, fenjing_id: str) -> Dict[str, str]:
    storyboards_path = assets_dir / "storyboards" / f"{chapter_name}.jsonl"
    if not storyboards_path.exists():
        return {}
    try:
        target_id = int(fenjing_id)
    except Exception:
        target_id = None
    for sb in read_jsonl(str(storyboards_path)):
        if not isinstance(sb, dict):
            continue
        sb_id = sb.get("Storyboard_id")
        try:
            sb_id = int(sb_id)
        except Exception:
            sb_id = None
        if target_id is None or sb_id != target_id:
            continue
        chars = sb.get("Characters") or sb.get("characters") or []
        if not isinstance(chars, list):
            continue
        outfit_map: Dict[str, str] = {}
        for c in chars:
            if not isinstance(c, dict):
                continue
            cid = c.get("Character_Id") or c.get("character_id")
            outf = c.get("Outfit") or c.get("outfit")
            if isinstance(cid, str) and isinstance(outf, str):
                outfit_map[cid] = outf
        return outfit_map
    return {}


def build_fenjing_details(project: str, assets: Path, visual_assets: Optional[Path] = None) -> Dict[str, List[Dict[str, Any]]]:
    result: Dict[str, List[Dict[str, Any]]] = {}
    storyboards_dir = assets / "storyboards"
    if not storyboards_dir.exists():
        return result
    chars_jsonl = assets / "characters.jsonl"
    defaults = load_char_defaults(chars_jsonl) if chars_jsonl.exists() else {}
    plot_outfits = load_char_plot_outfits(chars_jsonl) if chars_jsonl.exists() else {}
    failed_results = list_asset_results(project, status="failed")
    failed_fenjing_map: Dict[str, Dict[str, str]] = {}
    for item in failed_results:
        if item.get("asset_type") == "fenjing":
            chapter = str(item.get("chapter") or "")
            fid = str(item.get("asset_id") or "")
            reason = str(item.get("reason") or "")
            if chapter and fid:
                key = f"{chapter}:{fid}"
                if key not in failed_fenjing_map:
                    failed_fenjing_map[key] = reason
    chapters = sorted([p for p in storyboards_dir.iterdir() if p.is_dir() and CHAPTER_PATTERN.match(p.name)])
    for chapter_dir in chapters:
        candidate_dir = chapter_dir / "fenjing_candidates"
        candidate_map: Dict[str, List[str]] = {}
        if candidate_dir.exists():
            for p in sorted(candidate_dir.iterdir()):
                if not p.is_file():
                    continue
                match = re.match(r"fenjing(\d+)", p.stem, re.IGNORECASE)
                if not match:
                    continue
                fid = match.group(1)
                candidate_map.setdefault(fid, []).append(to_project_relative(project, p))
        prompts_path = chapter_dir / "fenjing_prompts.jsonl"
        rows: List[Dict[str, Any]] = []
        if prompts_path.exists():
            for item in safe_read_jsonl(prompts_path):
                if not isinstance(item, dict):
                    continue
                fenjing_id = str(item.get("fenjing_id", "")).strip()
                outfit_map = build_outfit_map_from_storyboard(assets, chapter_dir.name, fenjing_id)
                bg_hint = item.get("Background_xuanze", "")
                loc_id = str(item.get("Background_pic", "")).strip()
                ref_images: List[Dict[str, Any]] = []
                location_path = resolve_location_image(assets, loc_id, str(bg_hint), visual_assets)
                if location_path:
                    ref_images.append({"type": "location", "id": loc_id, "path": to_project_relative(project, Path(location_path))})
                for idx in range(1, 6):
                    char_key = f"Character_{idx}"
                    outfit_key = f"Character_{idx}_outfit"
                    char_id = str(item.get(char_key, "")).strip()
                    outfit_id = str(item.get(outfit_key, "")).strip()
                    if not outfit_id:
                        outfit_id = outfit_map.get(char_id, "")
                    if char_id:
                        ref_path = ""
                        default_outfit = defaults.get(char_id)
                        if outfit_id and outfit_id != default_outfit:
                            plot_set = plot_outfits.get(char_id)
                            if isinstance(plot_set, set) and outfit_id in plot_set:
                                ref_path = resolve_cloth_changed_image(assets, char_id, outfit_id, visual_assets)
                        if not ref_path:
                            ref_path = resolve_character_image(assets, char_id, visual_assets)
                        if ref_path:
                            ref_images.append({"type": "character", "id": char_id, "path": to_project_relative(project, Path(ref_path))})
                image_path = chapter_dir / "fenjing_images" / f"fenjing{fenjing_id}.png"
                fail_key = f"{chapter_dir.name}:{fenjing_id}"
                rows.append(
                    {
                        "fenjing_id": fenjing_id,
                        "prompt": item.get("prompt", ""),
                        "duration": item.get("duration", ""),
                        "background": bg_hint,
                        "image_path": to_project_relative(project, image_path) if image_path.exists() else "",
                        "ref_images": ref_images,
                        "candidate_images": candidate_map.get(fenjing_id, []),
                        "is_failed": fail_key in failed_fenjing_map,
                        "fail_reason": failed_fenjing_map.get(fail_key, ""),
                    }
                )
        if not rows:
            storyboard_jsonl = chapter_dir / f"{chapter_dir.name}.jsonl"
            if not storyboard_jsonl.exists():
                storyboard_jsonl = storyboards_dir / f"{chapter_dir.name}.jsonl"
            for idx, item in enumerate(safe_read_jsonl(storyboard_jsonl), start=1):
                if not isinstance(item, dict):
                    continue
                fenjing_id = str(item.get("Storyboard_id", idx)).strip()
                image_path = chapter_dir / "fenjing_images" / f"fenjing{fenjing_id}.png"
                fail_key = f"{chapter_dir.name}:{fenjing_id}"
                rows.append(
                    {
                        "fenjing_id": fenjing_id,
                        "prompt": item.get("Action", ""),
                        "duration": "",
                        "background": item.get("Time", ""),
                        "image_path": to_project_relative(project, image_path) if image_path.exists() else "",
                        "ref_images": [],
                        "candidate_images": candidate_map.get(fenjing_id, []),
                        "is_failed": fail_key in failed_fenjing_map,
                        "fail_reason": failed_fenjing_map.get(fail_key, ""),
                    }
                )
        result[chapter_dir.name] = rows
    return result


def list_project_assets(project: str) -> Dict[str, Any]:
    assets = storyboard_assets_dir(project)
    # 同时从visual_audio_assets目录查找资产（多项目安全：只读操作，无并发冲突）
    visual_assets = visual_audio_assets_dir(project)
    data: Dict[str, Any] = {
        "project": project,
        "assets_root": str(assets),
        "characters": [],
        "character_details": [],
        "cloth_changed_details": [],
        "locations": [],
        "expected_locations": [],
        "cloth": [],
        "cloth_changed": [],
        "chapters": [],
        "videos": [],
        "tts_audio": {},
        "character_table": [],
        "location_table": [],
        "storyboard_table": [],
        "fenjing_details": {},
    }
    if not assets.exists() and not visual_assets.exists():
        return data
    
    # 从两个目录合并查找角色图片（优先使用visual_audio_assets中的）
    character_images_from_visual = list_files(visual_assets / "character_images", (".png", ".jpg", ".jpeg")) if visual_assets.exists() else []
    character_images_from_storyboard = list_files(assets / "character_images", (".png", ".jpg", ".jpeg")) if assets.exists() else []
    # 使用visual_assets中的图片优先
    all_character_images = character_images_from_visual + character_images_from_storyboard
    seen_chars = set()
    unique_character_images = []
    for p in all_character_images:
        stem = Path(p).stem
        if stem not in seen_chars:
            seen_chars.add(stem)
            unique_character_images.append(p)
    data["characters"] = [to_project_relative(project, Path(p)) for p in unique_character_images]
    
    # 从visual_assets构建character_details（如果存在）
    if visual_assets.exists():
        data["character_details"] = build_character_details(project, visual_assets)
    elif assets.exists():
        data["character_details"] = build_character_details(project, assets)
    
    data["cloth_changed_details"] = build_cloth_changed_details(project, assets)
    
    # 从两个目录合并查找场景图片
    location_images_from_visual = list_files(visual_assets / "location_images", (".png", ".jpg", ".jpeg")) if visual_assets.exists() else []
    location_images_from_storyboard = list_files(assets / "location_images", (".png", ".jpg", ".jpeg")) if assets.exists() else []
    all_location_images = location_images_from_visual + location_images_from_storyboard
    seen_locs = set()
    unique_location_images = []
    for p in all_location_images:
        stem = Path(p).stem
        if stem not in seen_locs:
            seen_locs.add(stem)
            unique_location_images.append(p)
    data["locations"] = [to_project_relative(project, Path(p)) for p in unique_location_images]
    
    # 优先从visual_assets构建expected_locations
    if visual_assets.exists():
        data["expected_locations"] = build_expected_locations(project, visual_assets)
    elif assets.exists():
        data["expected_locations"] = build_expected_locations(project, assets)
    
    data["cloth"] = [
        to_project_relative(project, Path(p))
        for p in list_files(assets / "cloth_images", (".png", ".jpg", ".jpeg"))
    ]
    data["cloth_changed"] = [
        to_project_relative(project, Path(p))
        for p in list_files(assets / "cloth_changed_images", (".png", ".jpg", ".jpeg"))
    ]
    chapters_dir = assets / "storyboards"
    if chapters_dir.exists():
        for chapter in sorted(chapters_dir.iterdir()):
            if not chapter.is_dir() or not CHAPTER_PATTERN.match(chapter.name):
                continue
            fenjing_dir = chapter / "fenjing_images"
            chapter_data = {
                "name": chapter.name,
                "fenjing_images": [
                    to_project_relative(project, Path(p))
                    for p in list_files(fenjing_dir, (".png", ".jpg", ".jpeg"))
                ],
                "storyboard_jsonl": to_project_relative(project, chapter / f"{chapter.name}.jsonl"),
                "fenjing_prompts": to_project_relative(project, chapter / "fenjing_prompts.jsonl"),
                "shipin_prompts": to_project_relative(project, chapter / "shipin_prompts.jsonl"),
            }
            data["chapters"].append(chapter_data)
    video_map: Dict[str, Dict[str, Any]] = {}
    video_dirs = [project_base_dir(project) / "video", assets / "video"]
    for base_dir in video_dirs:
        if not base_dir.exists():
            continue
        for chapter in sorted(base_dir.iterdir()):
            if not chapter.is_dir():
                continue
            videos = [
                to_project_relative(project, Path(p))
                for p in list_files(chapter, (".mp4", ".mov"))
            ]
            if not videos:
                continue
            entry = video_map.get(chapter.name)
            if entry:
                merged = list(dict.fromkeys(entry["videos"] + videos))
                entry["videos"] = merged
            else:
                video_map[chapter.name] = {"chapter": chapter.name, "videos": videos}
    data["videos"] = [video_map[name] for name in sorted(video_map.keys())]
    
    tts_audio_map: Dict[str, List[str]] = {}
    tts_audio_dirs = [project_base_dir(project) / "tts_audio", assets / "tts_audio"]
    for base_dir in tts_audio_dirs:
        if not base_dir.exists():
            continue
        if (base_dir / "tts_audios").exists():
            base_dir = base_dir / "tts_audios"
        for chapter in sorted(base_dir.iterdir()):
            if not chapter.is_dir():
                continue
            audio_files = [
                to_project_relative(project, Path(p))
                for p in list_files(chapter, (".mp3"))
            ]
            if not audio_files:
                continue
            entry = tts_audio_map.get(chapter.name)
            if entry:
                merged = list(dict.fromkeys(entry + audio_files))
                tts_audio_map[chapter.name] = merged
            else:
                tts_audio_map[chapter.name] = audio_files
    
    data["tts_audio"] = tts_audio_map
    
    data["character_table"] = build_character_table(assets)
    data["location_table"] = build_location_table(assets)
    data["storyboard_table"] = build_storyboard_table(assets)
    data["fenjing_details"] = build_fenjing_details(project, assets, visual_assets)
    return data


def asset_results_path(project: str) -> Path:
    return project_base_dir(project) / "asset_results.jsonl"


def read_asset_results(project: str) -> List[Dict[str, Any]]:
    return safe_read_jsonl(asset_results_path(project))


def append_asset_results(project: str, items: List[Dict[str, Any]]) -> None:
    if not items:
        return
    path = asset_results_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = safe_read_jsonl(path)
    existing.extend(items)
    write_jsonl(str(path), existing)


def list_asset_results(
    project: str,
    job_id: Optional[str] = None,
    flow: Optional[str] = None,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    items = read_asset_results(project)
    if job_id:
        items = [item for item in items if item.get("job_id") == job_id]
    if flow:
        items = [item for item in items if item.get("flow") == flow]
    if status:
        items = [item for item in items if item.get("status") == status]
    return items


def aggregate_results_by_job(project: str, job_id: str) -> Dict[str, Any]:
    items = list_asset_results(project, job_id=job_id)
    success = 0
    failed = 0
    retry_count = 0
    by_type: Dict[str, Dict[str, int]] = {}
    for item in items:
        asset_type = str(item.get("asset_type") or "unknown")
        if asset_type not in by_type:
            by_type[asset_type] = {"success": 0, "failed": 0, "retry": 0}
        if item.get("status") == "success":
            success += 1
            by_type[asset_type]["success"] += 1
        else:
            failed += 1
            by_type[asset_type]["failed"] += 1
        retry = int(item.get("retry_count") or 0)
        retry_count += retry
        by_type[asset_type]["retry"] += retry
    return {
        "job_id": job_id,
        "total": len(items),
        "success": success,
        "failed": failed,
        "retry_count": retry_count,
        "by_type": by_type,
    }


def aggregate_partial_failures(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    failed = [item for item in items if item.get("status") == "failed"]
    counts: Dict[str, int] = {}
    for item in failed:
        asset_type = str(item.get("asset_type") or "")
        if not asset_type:
            continue
        counts[asset_type] = counts.get(asset_type, 0) + 1
    return {
        "partial_failed": bool(failed),
        "partial_failed_count": sum(counts.values()),
        "partial_failed_types": sorted(counts.keys()),
        "counts": counts,
    }


def build_visual_audio_asset_results(
    job_id: str,
    project: str,
    allowed_missing_output_types: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    data = list_project_assets(project)
    now = time.time()
    results: List[Dict[str, Any]] = []
    qc_map = _load_character_qc_map(project)
    allowed_types = {"character", "location"} if allowed_missing_output_types is None else set(allowed_missing_output_types)
    if "character" in allowed_types:
        character_details = data.get("character_details") or []
        for item in character_details:
            char_id = str(item.get("character_id") or "")
            if not char_id:
                continue
            qc_info = qc_map.get(char_id)
            if qc_info:
                status = "success" if qc_info.get("qc_pass") else "failed"
                results.append(
                    _build_asset_result(
                        job_id=job_id,
                        project=project,
                        flow="visual_audio_assets",
                        asset_type="character",
                        asset_id=char_id,
                        file=item.get("image_path") or qc_info.get("file") or "",
                        status=status,
                        reason=qc_info.get("reason") or "",
                        retry_count=qc_info.get("retry_count") or 0,
                        qc_limit=qc_info.get("qc_limit") or 0,
                        source="qc_result",
                        created_at=now,
                    )
                )
                continue
            status = "success" if item.get("image_path") else "failed"
            reason = "" if status == "success" else "missing_output"
            results.append(
                _build_asset_result(
                    job_id=job_id,
                    project=project,
                    flow="visual_audio_assets",
                    asset_type="character",
                    asset_id=char_id,
                    file=item.get("image_path") or "",
                    status=status,
                    reason=reason,
                    retry_count=0,
                    qc_limit=0,
                    source="runtime",
                    created_at=now,
                )
            )
    if "location" in allowed_types:
        location_table = data.get("location_table") or []
        location_ids = _extract_location_ids(location_table)
        location_map = _build_location_path_map(data.get("locations") or [])
        assets = storyboard_assets_dir(project)
        referenced_ids = _collect_referenced_location_ids(assets)
        all_location_ids = sorted((set(location_ids) & referenced_ids) | set(location_map.keys()))
        for loc_id in all_location_ids:
            path = location_map.get(loc_id, "")
            status = "success" if path else "failed"
            reason = "" if status == "success" else "missing_output"
            results.append(
                _build_asset_result(
                    job_id=job_id,
                    project=project,
                    flow="visual_audio_assets",
                    asset_type="location",
                    asset_id=loc_id,
                    file=path,
                    status=status,
                    reason=reason,
                    retry_count=0,
                    qc_limit=0,
                    source="runtime",
                    created_at=now,
                )
            )
    return results


def build_fenjing_asset_results(job_id: str, project: str) -> List[Dict[str, Any]]:
    data = list_project_assets(project)
    now = time.time()
    results: List[Dict[str, Any]] = []
    details_by_chapter = data.get("fenjing_details") or {}
    for chapter, items in details_by_chapter.items():
        for item in items or []:
            fenjing_id = str(item.get("fenjing_id") or "")
            if not fenjing_id:
                continue
            status = "success" if item.get("image_path") else "failed"
            reason = "" if status == "success" else "missing_output"
            results.append(
                _build_asset_result(
                    job_id=job_id,
                    project=project,
                    flow="fenjing",
                    asset_type="fenjing",
                    asset_id=fenjing_id,
                    file=item.get("image_path") or "",
                    status=status,
                    reason=reason,
                    retry_count=0,
                    qc_limit=0,
                    source="runtime",
                    created_at=now,
                    chapter_id=str(chapter),
                    fenjing_id=fenjing_id,
                )
            )
    return results


def build_video_asset_results(job_id: str, project: str) -> List[Dict[str, Any]]:
    data = list_project_assets(project)
    now = time.time()
    results: List[Dict[str, Any]] = []
    expected = _build_expected_fenjing_ids(data.get("storyboard_table") or [])
    video_map = _build_video_path_map(data.get("videos") or [])
    for chapter, fenjing_ids in expected.items():
        for fenjing_id in fenjing_ids:
            path = video_map.get(chapter, {}).get(fenjing_id, "")
            status = "success" if path else "failed"
            reason = "" if status == "success" else "missing_output"
            results.append(
                _build_asset_result(
                    job_id=job_id,
                    project=project,
                    flow="video",
                    asset_type="video",
                    asset_id=fenjing_id,
                    file=path,
                    status=status,
                    reason=reason,
                    retry_count=0,
                    qc_limit=0,
                    source="runtime",
                    created_at=now,
                    chapter_id=chapter,
                    fenjing_id=fenjing_id,
                )
            )
    for chapter, fenjing_map in video_map.items():
        for fenjing_id, path in fenjing_map.items():
            if chapter in expected and fenjing_id in expected[chapter]:
                continue
            results.append(
                _build_asset_result(
                    job_id=job_id,
                    project=project,
                    flow="video",
                    asset_type="video",
                    asset_id=fenjing_id,
                    file=path,
                    status="success",
                    reason="",
                    retry_count=0,
                    qc_limit=0,
                    source="runtime",
                    created_at=now,
                    chapter_id=chapter,
                    fenjing_id=fenjing_id,
                )
            )
    return results


def build_partial_failures_from_qc(job_id: str, project: str) -> List[Dict[str, Any]]:
    qc_map = _load_character_qc_map(project)
    if not qc_map:
        return []
    now = time.time()
    failed: List[Dict[str, Any]] = []
    for char_id, qc_info in qc_map.items():
        if qc_info.get("qc_pass"):
            continue
        failed.append(
            _build_asset_result(
                job_id=job_id,
                project=project,
                flow="visual_audio_assets",
                asset_type="character",
                asset_id=char_id,
                file=qc_info.get("file") or "",
                status="failed",
                reason=qc_info.get("reason") or "qc_failed",
                retry_count=qc_info.get("retry_count") or 0,
                qc_limit=qc_info.get("qc_limit") or 0,
                source="qc_result",
                created_at=now,
            )
        )
    return failed


def _build_asset_result(
    job_id: str,
    project: str,
    flow: str,
    asset_type: str,
    asset_id: str,
    file: str,
    status: str,
    reason: str,
    retry_count: int,
    qc_limit: int,
    source: str,
    created_at: float,
    chapter_id: str = "",
    fenjing_id: str = "",
) -> Dict[str, Any]:
    return {
        "id": f"{job_id}_{asset_type}_{asset_id}",
        "job_id": job_id,
        "project": project,
        "flow": flow,
        "asset_type": asset_type,
        "asset_id": asset_id,
        "file": file,
        "status": status,
        "reason": reason,
        "retry_count": retry_count,
        "qc_limit": qc_limit,
        "source": source,
        "created_at": created_at,
        "chapter_id": chapter_id,
        "fenjing_id": fenjing_id,
    }


def _load_character_qc_map(project: str) -> Dict[str, Dict[str, Any]]:
    qc_path = storyboard_assets_dir(project) / "character_qc_results.jsonl"
    items = safe_read_jsonl(qc_path)
    result: Dict[str, Dict[str, Any]] = {}
    for item in items:
        file_path = str(item.get("file") or "")
        stem = Path(file_path).stem if file_path else ""
        if not stem:
            continue
        qc_pass = item.get("qc_pass")
        if qc_pass is None and isinstance(item.get("qc"), dict):
            qc_content = item.get("qc", {}).get("content") or ""
            qc_pass = _extract_qc_pass(qc_content)
        qc_attempts = item.get("qc_attempts")
        retry_count = max(int(qc_attempts) - 1, 0) if isinstance(qc_attempts, int) else 0
        qc_limit = int(qc_attempts) if isinstance(qc_attempts, int) else 0
        result[stem] = {
            "file": file_path,
            "qc_pass": bool(qc_pass),
            "reason": _extract_qc_reason(item),
            "retry_count": retry_count,
            "qc_limit": qc_limit,
        }
    return result


def _extract_qc_pass(content: str) -> bool:
    try:
        payload = json.loads(content)
        return bool(payload.get("check_result"))
    except Exception:
        return False


def _extract_qc_reason(item: Dict[str, Any]) -> str:
    if isinstance(item.get("check_ana"), str):
        return item.get("check_ana") or ""
    qc = item.get("qc")
    if isinstance(qc, dict):
        content = qc.get("content")
        if isinstance(content, str):
            try:
                payload = json.loads(content)
                return str(payload.get("check_ana") or "")
            except Exception:
                return ""
    return ""


def _extract_location_ids(location_table: List[Dict[str, Any]]) -> List[str]:
    ids: List[str] = []
    for row in location_table:
        if not isinstance(row, dict):
            continue
        loc_id = row.get("Location_ID") or row.get("Location_id") or row.get("location_id") or ""
        loc_id = str(loc_id).strip()
        if loc_id:
            ids.append(loc_id)
    return ids


def _collect_referenced_location_ids(assets: Path) -> Set[str]:
    referenced_ids: Set[str] = set()
    storyboards_dir = assets / "storyboards"
    if storyboards_dir.exists():
        for chapter_dir in storyboards_dir.iterdir():
            if not chapter_dir.is_dir():
                continue
            fenjing_prompts_path = chapter_dir / "fenjing_prompts.jsonl"
            if not fenjing_prompts_path.exists():
                continue
            for item in safe_read_jsonl(fenjing_prompts_path):
                if not isinstance(item, dict):
                    continue
                loc_id = item.get("Location_Id") or item.get("location_id") or item.get("Background_pic")
                if isinstance(loc_id, str) and loc_id.strip():
                    referenced_ids.add(loc_id.strip())
    return referenced_ids


def _build_location_path_map(paths: List[str]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for path in paths:
        name = Path(path).stem
        match = re.match(r"(.+?)_(standing|sitting)$", name, re.IGNORECASE)
        loc_id = match.group(1) if match else name
        if loc_id and loc_id not in result:
            result[loc_id] = path
    return result


def _build_expected_fenjing_ids(rows: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    expected: Dict[str, List[str]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        chapter = str(row.get("chapter_id") or row.get("chapter") or row.get("chapter_name") or "")
        fenjing_id = str(row.get("fenjing_id") or row.get("fenjingId") or row.get("fenjing") or "")
        if not chapter or not fenjing_id:
            continue
        expected.setdefault(chapter, [])
        if fenjing_id not in expected[chapter]:
            expected[chapter].append(fenjing_id)
    return expected


def _build_video_path_map(videos_by_chapter: Any) -> Dict[str, Dict[str, str]]:
    result: Dict[str, Dict[str, str]] = {}
    if isinstance(videos_by_chapter, list):
        for item in videos_by_chapter:
            if not isinstance(item, dict):
                continue
            chapter = str(item.get("chapter") or "")
            paths = item.get("videos")
            if not chapter or not isinstance(paths, list):
                continue
            result[chapter] = _build_video_fenjing_map(paths)
        return result
    if isinstance(videos_by_chapter, dict):
        for chapter, paths in videos_by_chapter.items():
            if not isinstance(paths, list):
                continue
            result[str(chapter)] = _build_video_fenjing_map(paths)
    return result


def _build_video_fenjing_map(paths: List[str]) -> Dict[str, str]:
    chapter_map: Dict[str, str] = {}
    for path in paths:
        name = Path(path).name
        match = re.match(r"fenjing_(\d+)(?:_video|_\d+)?\.mp4", name, re.IGNORECASE)
        if not match:
            continue
        fenjing_id = match.group(1)
        existing = chapter_map.get(fenjing_id)
        if not existing or "_video" in name:
            chapter_map[fenjing_id] = path
    return chapter_map


def update_fenjing_prompt(project: str, chapter_name: str, fenjing_id: str, prompt_text: str) -> Dict[str, Any]:
    chapter_dir = storyboard_assets_dir(project) / "storyboards" / chapter_name
    prompts_path = chapter_dir / "fenjing_prompts.jsonl"
    if not prompts_path.exists():
        job_repo.log_event(
            "ERROR",
            "fenjing_prompt_update_error",
            trace_id="",
            project=project,
            chapter=chapter_name,
            fenjing_id=fenjing_id,
            error="prompts_missing",
        )
        return {"ok": False, "error": "prompts_missing"}
    items = read_jsonl(str(prompts_path))
    updated = False
    for item in items:
        if str(item.get("fenjing_id", "")) == fenjing_id:
            item["prompt"] = prompt_text
            updated = True
            break
    if not updated:
        job_repo.log_event(
            "ERROR",
            "fenjing_prompt_update_error",
            trace_id="",
            project=project,
            chapter=chapter_name,
            fenjing_id=fenjing_id,
            error="fenjing_id_not_found",
        )
        return {"ok": False, "error": "fenjing_id_not_found"}
    write_jsonl(str(prompts_path), items)
    job_repo.log_event(
        "INFO",
        "fenjing_prompt_update_saved",
        trace_id="",
        project=project,
        chapter=chapter_name,
        fenjing_id=fenjing_id,
        prompt_length=len(prompt_text),
    )
    return {"ok": True}


def update_video_prompt(project: str, chapter_name: str, fenjing_id: str, prompt_text: str) -> Dict[str, Any]:
    chapter_dir = storyboard_assets_dir(project) / "storyboards" / chapter_name
    prompts_path = chapter_dir / "shipin_prompts.jsonl"
    if not prompts_path.exists():
        job_repo.log_event(
            "ERROR",
            "video_prompt_update_error",
            trace_id="",
            project=project,
            chapter=chapter_name,
            fenjing_id=fenjing_id,
            error="prompts_missing",
        )
        return {"ok": False, "error": "prompts_missing"}
    items = read_jsonl(str(prompts_path))
    updated = False
    for item in items:
        if str(item.get("fenjing_id", "")) == fenjing_id:
            item["prompt"] = prompt_text
            updated = True
            break
    if not updated:
        job_repo.log_event(
            "ERROR",
            "video_prompt_update_error",
            trace_id="",
            project=project,
            chapter=chapter_name,
            fenjing_id=fenjing_id,
            error="fenjing_id_not_found",
        )
        return {"ok": False, "error": "fenjing_id_not_found"}
    write_jsonl(str(prompts_path), items)
    job_repo.log_event(
        "INFO",
        "video_prompt_update_saved",
        trace_id="",
        project=project,
        chapter=chapter_name,
        fenjing_id=fenjing_id,
        prompt_length=len(prompt_text),
    )
    return {"ok": True}


def update_character_prompt(project: str, character_id: str, prompt_text: str) -> Dict[str, Any]:
    assets_dir = storyboard_assets_dir(project)
    prompts_path = assets_dir / "character_prompts.jsonl"
    if not prompts_path.exists():
        return {"ok": False, "error": "prompts_missing"}
    items = read_jsonl(str(prompts_path))
    updated = False
    for item in items:
        cid = item.get("Character_Id") or item.get("Character_id") or item.get("character_id")
        if str(cid) == character_id:
            item["prompt"] = prompt_text
            item["st_prompt"] = prompt_text
            updated = True
            break
    if not updated:
        return {"ok": False, "error": "character_id_not_found"}
    write_jsonl(str(prompts_path), items)
    return {"ok": True}


def update_cloth_changed_prompt(project: str, character_id: str, outfit_id: str, prompt_text: str) -> Dict[str, Any]:
    assets_dir = storyboard_assets_dir(project)
    chars_path = assets_dir / "characters.jsonl"
    if not chars_path.exists():
        return {"ok": False, "error": "prompts_missing"}
    items = read_jsonl(str(chars_path))
    updated = False
    for item in items:
        cid = item.get("Character_Id") or item.get("Character_id") or item.get("character_id")
        if str(cid) != character_id:
            continue
        changes = item.get("Plot_Costume_Change") or []
        if not isinstance(changes, list):
            continue
        for ch in changes:
            if not isinstance(ch, dict):
                continue
            oid = ch.get("Outfit_id")
            if str(oid) == outfit_id:
                ch["prompt"] = prompt_text
                ch["st_prompt"] = prompt_text
                updated = True
                break
        if updated:
            break
    if not updated:
        return {"ok": False, "error": "outfit_id_not_found"}
    write_jsonl(str(chars_path), items)
    return {"ok": True}


def publish_character_candidate(project: str, character_id: str, candidate_rel: str) -> Dict[str, Any]:
    if not candidate_rel:
        return {"ok": False, "error": "candidate_missing"}
    candidate_path = resolve_media_path(project, candidate_rel)
    if not candidate_path or not candidate_path.exists():
        return {"ok": False, "error": "candidate_not_found"}
    if "character_candidates" not in candidate_path.parts:
        return {"ok": False, "error": "candidate_invalid"}
    assets_dir = storyboard_assets_dir(project)
    target_dir = assets_dir / "character_images"
    target_dir.mkdir(parents=True, exist_ok=True)
    base_id = character_id if character_id.startswith("char_") else f"char_{character_id}"
    target_path = target_dir / f"{base_id}.png"
    shutil.copyfile(candidate_path, target_path)
    tos = TosClientWrapper()
    if not tos.available():
        return {"ok": False, "error": "tos_unavailable"}
    key = f"{runtime_config.TOS_CHARACTER_PREFIX}/{base_id}.png"
    uri = tos.upload_file(runtime_config.TOS_BUCKET, key, target_path)
    if not uri:
        return {"ok": False, "error": "tos_upload_failed"}
    return {"ok": True, "uri": uri, "path": str(target_path)}


def publish_cloth_changed_candidate(project: str, character_id: str, outfit_id: str, candidate_rel: str) -> Dict[str, Any]:
    if not candidate_rel:
        return {"ok": False, "error": "candidate_missing"}
    candidate_path = resolve_media_path(project, candidate_rel)
    if not candidate_path or not candidate_path.exists():
        return {"ok": False, "error": "candidate_not_found"}
    if "cloth_changed_candidates" not in candidate_path.parts:
        return {"ok": False, "error": "candidate_invalid"}
    assets_dir = storyboard_assets_dir(project)
    target_dir = assets_dir / "cloth_changed_images"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{character_id}_{outfit_id}.png"
    shutil.copyfile(candidate_path, target_path)
    tos = TosClientWrapper()
    if not tos.available():
        return {"ok": False, "error": "tos_unavailable"}
    key = f"{runtime_config.TOS_CLOTH_PREFIX}/{character_id}_{outfit_id}.png"
    uri = tos.upload_file(runtime_config.TOS_BUCKET, key, target_path)
    if not uri:
        return {"ok": False, "error": "tos_upload_failed"}
    return {"ok": True, "uri": uri, "path": str(target_path)}


def publish_fenjing_candidate(project: str, chapter_name: str, fenjing_id: str, candidate_rel: str) -> Dict[str, Any]:
    if not candidate_rel:
        job_repo.log_event(
            "ERROR",
            "fenjing_candidate_publish_error",
            trace_id="",
            project=project,
            chapter=chapter_name,
            fenjing_id=fenjing_id,
            error="candidate_missing",
        )
        return {"ok": False, "error": "candidate_missing"}
    candidate_path = resolve_media_path(project, candidate_rel)
    if not candidate_path or not candidate_path.exists():
        job_repo.log_event(
            "ERROR",
            "fenjing_candidate_publish_error",
            trace_id="",
            project=project,
            chapter=chapter_name,
            fenjing_id=fenjing_id,
            candidate_path=candidate_rel,
            error="candidate_not_found",
        )
        return {"ok": False, "error": "candidate_not_found"}
    if "fenjing_candidates" not in candidate_path.parts:
        job_repo.log_event(
            "ERROR",
            "fenjing_candidate_publish_error",
            trace_id="",
            project=project,
            chapter=chapter_name,
            fenjing_id=fenjing_id,
            candidate_path=candidate_rel,
            error="candidate_invalid",
        )
        return {"ok": False, "error": "candidate_invalid"}
    chapter_dir = storyboard_assets_dir(project) / "storyboards" / chapter_name
    target_dir = chapter_dir / "fenjing_images"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"fenjing{fenjing_id}.png"
    shutil.copyfile(candidate_path, target_path)
    job_repo.log_event(
        "INFO",
        "fenjing_candidate_copied",
        trace_id="",
        project=project,
        chapter=chapter_name,
        fenjing_id=fenjing_id,
        candidate_path=str(candidate_path),
        target_path=str(target_path),
    )
    tos = TosClientWrapper()
    if not tos.available():
        job_repo.log_event(
            "ERROR",
            "fenjing_candidate_publish_error",
            trace_id="",
            project=project,
            chapter=chapter_name,
            fenjing_id=fenjing_id,
            target_path=str(target_path),
            error="tos_unavailable",
        )
        return {"ok": False, "error": "tos_unavailable"}
    key = f"{runtime_config.TOS_FENJING_PREFIX}/{chapter_name}/fenjing{fenjing_id}.png"
    uri = tos.upload_file(runtime_config.TOS_BUCKET, key, target_path)
    if not uri:
        job_repo.log_event(
            "ERROR",
            "fenjing_candidate_publish_error",
            trace_id="",
            project=project,
            chapter=chapter_name,
            fenjing_id=fenjing_id,
            target_path=str(target_path),
            key=key,
            error="tos_upload_failed",
        )
        return {"ok": False, "error": "tos_upload_failed"}
    job_repo.log_event(
        "INFO",
        "fenjing_candidate_published",
        trace_id="",
        project=project,
        chapter=chapter_name,
        fenjing_id=fenjing_id,
        target_path=str(target_path),
        key=key,
        uri=uri,
    )
    return {"ok": True, "uri": uri, "path": str(target_path)}


def publish_video_candidate(project: str, chapter_name: str, candidate_rel: str) -> Dict[str, Any]:
    if not candidate_rel:
        job_repo.log_event(
            "ERROR",
            "video_candidate_publish_error",
            trace_id="",
            project=project,
            chapter=chapter_name,
            error="candidate_missing",
        )
        return {"ok": False, "error": "candidate_missing"}
    candidate_path = resolve_media_path(project, candidate_rel)
    if not candidate_path or not candidate_path.exists():
        job_repo.log_event(
            "ERROR",
            "video_candidate_publish_error",
            trace_id="",
            project=project,
            chapter=chapter_name,
            candidate_path=candidate_rel,
            error="candidate_not_found",
        )
        return {"ok": False, "error": "candidate_not_found"}
    rel_parts = Path(candidate_rel).parts
    if not rel_parts or rel_parts[0] != "video":
        job_repo.log_event(
            "ERROR",
            "video_candidate_publish_error",
            trace_id="",
            project=project,
            chapter=chapter_name,
            candidate_path=candidate_rel,
            error="candidate_invalid",
        )
        return {"ok": False, "error": "candidate_invalid"}
    if "assets" in candidate_path.parts:
        job_repo.log_event(
            "ERROR",
            "video_candidate_publish_error",
            trace_id="",
            project=project,
            chapter=chapter_name,
            candidate_path=candidate_rel,
            error="candidate_invalid",
        )
        return {"ok": False, "error": "candidate_invalid"}
    assets_dir = storyboard_assets_dir(project)
    target_dir = assets_dir / "video" / chapter_name
    target_dir.mkdir(parents=True, exist_ok=True)
    target_filename = candidate_path.name
    match = re.match(r"fenjing_(\d+)(?:_\d+)?\.mp4", candidate_path.name, re.IGNORECASE)
    fenjing_id = match.group(1) if match else extract_fenjing_id(candidate_path.name)
    if match:
        target_filename = f"fenjing_{match[1]}_video.mp4"
    target_path = target_dir / target_filename
    shutil.copyfile(candidate_path, target_path)
    job_repo.log_event(
        "INFO",
        "video_candidate_published",
        trace_id="",
        project=project,
        chapter=chapter_name,
        fenjing_id=fenjing_id,
        candidate_path=str(candidate_path),
        target_path=str(target_path),
    )
    return {"ok": True, "path": str(target_path)}


def delete_candidate_file(project: str, candidate_rel: str, required_dir: str) -> Dict[str, Any]:
    if not candidate_rel:
        job_repo.log_event(
            "ERROR",
            "candidate_delete_error",
            trace_id="",
            project=project,
            error="candidate_missing",
        )
        return {"ok": False, "error": "candidate_missing"}
    candidate_path = resolve_media_path(project, candidate_rel)
    if not candidate_path or not candidate_path.exists():
        job_repo.log_event(
            "ERROR",
            "candidate_delete_error",
            trace_id="",
            project=project,
            candidate_path=candidate_rel,
            error="candidate_not_found",
        )
        return {"ok": False, "error": "candidate_not_found"}
    if required_dir not in candidate_path.parts:
        job_repo.log_event(
            "ERROR",
            "candidate_delete_error",
            trace_id="",
            project=project,
            candidate_path=candidate_rel,
            error="candidate_invalid",
        )
        return {"ok": False, "error": "candidate_invalid"}
    try:
        candidate_path.unlink()
    except Exception as exc:
        job_repo.log_event(
            "ERROR",
            "candidate_delete_error",
            trace_id="",
            project=project,
            candidate_path=str(candidate_path),
            error=f"candidate_delete_failed:{exc}",
        )
        return {"ok": False, "error": f"candidate_delete_failed:{exc}"}
    job_repo.log_event(
        "INFO",
        "candidate_deleted",
        trace_id="",
        project=project,
        candidate_path=str(candidate_path),
        required_dir=required_dir,
    )
    return {"ok": True, "path": str(candidate_path)}


def delete_video_candidate(project: str, candidate_rel: str) -> Dict[str, Any]:
    if not candidate_rel:
        job_repo.log_event(
            "ERROR",
            "video_candidate_delete_error",
            trace_id="",
            project=project,
            error="candidate_missing",
        )
        return {"ok": False, "error": "candidate_missing"}
    candidate_path = resolve_media_path(project, candidate_rel)
    if not candidate_path or not candidate_path.exists():
        job_repo.log_event(
            "ERROR",
            "video_candidate_delete_error",
            trace_id="",
            project=project,
            candidate_path=candidate_rel,
            error="candidate_not_found",
        )
        return {"ok": False, "error": "candidate_not_found"}
    rel_parts = Path(candidate_rel).parts
    if not rel_parts or rel_parts[0] != "video":
        job_repo.log_event(
            "ERROR",
            "video_candidate_delete_error",
            trace_id="",
            project=project,
            candidate_path=candidate_rel,
            error="candidate_invalid",
        )
        return {"ok": False, "error": "candidate_invalid"}
    if "assets" in candidate_path.parts:
        job_repo.log_event(
            "ERROR",
            "video_candidate_delete_error",
            trace_id="",
            project=project,
            candidate_path=candidate_rel,
            error="candidate_invalid",
        )
        return {"ok": False, "error": "candidate_invalid"}
    fenjing_id = extract_fenjing_id(candidate_path.name)
    try:
        candidate_path.unlink()
    except Exception as exc:
        job_repo.log_event(
            "ERROR",
            "video_candidate_delete_error",
            trace_id="",
            project=project,
            candidate_path=str(candidate_path),
            fenjing_id=fenjing_id,
            error=f"candidate_delete_failed:{exc}",
        )
        return {"ok": False, "error": f"candidate_delete_failed:{exc}"}
    job_repo.log_event(
        "INFO",
        "video_candidate_deleted",
        trace_id="",
        project=project,
        candidate_path=str(candidate_path),
        fenjing_id=fenjing_id,
    )
    return {"ok": True, "path": str(candidate_path)}


def _remove_path(path: Path, removed: List[str], errors: List[str]) -> None:
    if not path.exists():
        return
    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        removed.append(str(path))
    except Exception as exc:
        errors.append(f"{path}:{exc}")


def _normalize_tos_prefix(prefix: Optional[str]) -> Optional[str]:
    if not isinstance(prefix, str):
        return None
    cleaned = prefix.strip().strip("/")
    return cleaned or None


def _list_tos_keys(tos: TosClientWrapper, bucket: str, prefix: str) -> List[str]:
    if not tos.available():
        return []
    client = tos._client if hasattr(tos, "_client") else None
    if not client:
        return []
    keys: List[str] = []
    try:
        continuation_token: Optional[str] = None
        is_truncated = True
        while is_truncated:
            resp = None
            if hasattr(client, "list_objects_type2"):
                kwargs = {"prefix": prefix}
                if continuation_token:
                    kwargs["continuation_token"] = continuation_token
                resp = client.list_objects_type2(bucket, **kwargs)
            elif hasattr(client, "list_objects"):
                kwargs = {"prefix": prefix}
                if continuation_token:
                    kwargs["marker"] = continuation_token
                resp = client.list_objects(bucket, **kwargs)
            if resp is None:
                break
            contents = getattr(resp, "contents", None) or getattr(resp, "contents_list", None) or getattr(resp, "Contents", None)
            if contents:
                for it in contents:
                    key = getattr(it, "key", None) or getattr(it, "Key", None) or it.get("Key") if isinstance(it, dict) else None
                    if isinstance(key, str) and key:
                        keys.append(key)
            else:
                if isinstance(resp, dict):
                    for it in resp.get("Contents", []) or []:
                        key = it.get("Key")
                        if isinstance(key, str) and key:
                            keys.append(key)
            is_truncated = bool(getattr(resp, "is_truncated", None) or getattr(resp, "IsTruncated", None) or (resp.get("IsTruncated") if isinstance(resp, dict) else False))
            next_token = (
                getattr(resp, "next_continuation_token", None)
                or getattr(resp, "NextContinuationToken", None)
                or (resp.get("NextContinuationToken") if isinstance(resp, dict) else None)
                or getattr(resp, "next_marker", None)
                or getattr(resp, "NextMarker", None)
                or (resp.get("NextMarker") if isinstance(resp, dict) else None)
            )
            if is_truncated and isinstance(next_token, str) and next_token:
                continuation_token = next_token
                continue
            break
    except Exception:
        return []
    return keys


def _delete_tos_keys(tos: TosClientWrapper, bucket: str, keys: List[str]) -> Tuple[int, List[str]]:
    if not keys:
        return 0, []
    errors: List[str] = []
    deleted = 0
    for key in keys:
        if tos.delete_object(bucket, key):
            deleted += 1
        else:
            errors.append(key)
    return deleted, errors


def _build_ignored_tos_result(reason: str) -> Dict[str, Any]:
    return {"ok": True, "deleted": 0, "errors": [], "ignored": True, "reason": reason}


def _delete_tos_prefix(tos: TosClientWrapper, bucket: str, prefix: Optional[str]) -> Dict[str, Any]:
    base_prefix = _normalize_tos_prefix(prefix)
    if not bucket or not base_prefix:
        return _build_ignored_tos_result("tos_config_missing")
    if not tos.available():
        return _build_ignored_tos_result("tos_unavailable")
    list_prefix = f"{base_prefix}/"
    keys = _list_tos_keys(tos, bucket, list_prefix)
    if not keys:
        return {"ok": True, "deleted": 0, "errors": []}
    deleted, errors = _delete_tos_keys(tos, bucket, keys)
    return {"ok": len(errors) == 0, "deleted": deleted, "errors": errors}


def _collect_auto_storyboard_tos_keys(assets_prefix: str, keys: List[str]) -> List[str]:
    base_prefix = _normalize_tos_prefix(assets_prefix)
    if not base_prefix:
        return []
    prefix = f"{base_prefix}/"
    target_names = {
        "characters.jsonl",
        "locations.jsonl",
        "summaries.jsonl",
        "raw_characters.jsonl",
        "raw_locations.jsonl",
        "raw_summaries.jsonl",
    }
    targets: List[str] = []
    for key in keys:
        if not key.startswith(prefix):
            continue
        tail = key[len(prefix):]
        if tail in target_names:
            targets.append(key)
            continue
        if tail.startswith("storyboards/"):
            sub = tail[len("storyboards/"):]
            if "/" not in sub and sub.endswith(".jsonl"):
                targets.append(key)
    return targets


def _collect_visual_audio_tos_keys(assets_prefix: str, keys: List[str], phases: Set[str]) -> List[str]:
    base_prefix = _normalize_tos_prefix(assets_prefix)
    if not base_prefix:
        return []
    prefix = f"{base_prefix}/"
    target_names: Set[str] = set()
    if "character" in phases:
        target_names |= {"character_prompts.jsonl", "character_prompts_from_tos.jsonl"}
    if "location_prompts" in phases:
        target_names |= {"location_prompts.jsonl", "location_prompts_from_tos.jsonl"}
    if "cloth_images" in phases or "cloth_changed" in phases:
        target_names |= {"cloth_upload.jsonl", "cloth_changed_upload.jsonl"}
    targets: List[str] = []
    for key in keys:
        if not key.startswith(prefix):
            continue
        tail = key[len(prefix):]
        if tail in target_names:
            targets.append(key)
            continue
        if "fenjing_prompts" in phases and tail.startswith("storyboards/") and tail.endswith("/fenjing_prompts.jsonl"):
            targets.append(key)
    return targets


def _merge_tos_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not results:
        return {"ok": True, "deleted": 0, "errors": []}
    deleted = 0
    errors: List[str] = []
    ok = True
    ignored = True
    reasons: List[str] = []
    for result in results:
        deleted += int(result.get("deleted", 0) or 0)
        errs = result.get("errors") or []
        if isinstance(errs, list):
            errors.extend([str(e) for e in errs])
        if not result.get("ok", True):
            ok = False
        if not result.get("ignored", False):
            ignored = False
        reason = result.get("reason")
        if isinstance(reason, str) and reason:
            reasons.append(reason)
    summary: Dict[str, Any] = {"ok": ok, "deleted": deleted, "errors": errors}
    if ignored:
        summary["ignored"] = True
        if reasons:
            summary["reasons"] = sorted(set(reasons))
    return summary


def _clean_tos_auto_storyboard(tos: TosClientWrapper, bucket: str) -> Dict[str, Any]:
    assets_prefix = runtime_config.TOS_ASSETS_PREFIX
    base_prefix = _normalize_tos_prefix(assets_prefix)
    if not bucket or not base_prefix:
        return _build_ignored_tos_result("tos_config_missing")
    if not tos.available():
        return _build_ignored_tos_result("tos_unavailable")
    list_prefix = f"{base_prefix}/"
    keys = _list_tos_keys(tos, bucket, list_prefix)
    if not keys:
        return {"ok": True, "deleted": 0, "errors": []}
    targets = _collect_auto_storyboard_tos_keys(base_prefix, keys)
    if not targets:
        return {"ok": True, "deleted": 0, "errors": []}
    deleted, errors = _delete_tos_keys(tos, bucket, targets)
    return {"ok": len(errors) == 0, "deleted": deleted, "errors": errors}


def _clean_tos_visual_audio_assets(tos: TosClientWrapper, bucket: str, phases: Set[str]) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    assets_prefix = runtime_config.TOS_ASSETS_PREFIX
    needs_assets_keys = any(item in phases for item in {"character", "location_prompts", "fenjing_prompts"})
    if needs_assets_keys:
        base_prefix = _normalize_tos_prefix(assets_prefix)
        if not bucket or not base_prefix:
            results.append(_build_ignored_tos_result("tos_config_missing"))
        elif not tos.available():
            results.append(_build_ignored_tos_result("tos_unavailable"))
        else:
            list_prefix = f"{base_prefix}/"
            keys = _list_tos_keys(tos, bucket, list_prefix)
            if keys:
                targets = _collect_visual_audio_tos_keys(base_prefix, keys, phases)
                if targets:
                    deleted, errors = _delete_tos_keys(tos, bucket, targets)
                    results.append({"ok": len(errors) == 0, "deleted": deleted, "errors": errors})
    if "character" in phases:
        results.append(_delete_tos_prefix(tos, bucket, runtime_config.TOS_CHARACTER_PREFIX))
    if "location_images" in phases:
        results.append(_delete_tos_prefix(tos, bucket, runtime_config.TOS_LOCATION_PREFIX))
    if "cloth_images" in phases or "cloth_changed" in phases:
        results.append(_delete_tos_prefix(tos, bucket, runtime_config.TOS_CLOTH_PREFIX))
    if "tts" in phases:
        results.append(_delete_tos_prefix(tos, bucket, runtime_config.TOS_TTS_PREFIX))
    return _merge_tos_results(results)


def _clean_tos_for_flow(flow: str) -> Dict[str, Any]:
    tos = TosClientWrapper()
    bucket = runtime_config.TOS_BUCKET
    if flow == "auto_storyboard":
        return _clean_tos_auto_storyboard(tos, bucket)
    if flow == "visual_audio_assets":
        phases = {
            "character",
            "location_prompts",
            "fenjing_prompts",
            "location_images",
            "tts",
            "cloth_images",
            "cloth_changed",
        }
        return _clean_tos_visual_audio_assets(tos, bucket, phases)
    if flow in {"fenjing", "fenjing_generate"}:
        return _delete_tos_prefix(tos, bucket, runtime_config.TOS_FENJING_PREFIX)
    if flow == "fenjing_upload":
        return _delete_tos_prefix(tos, bucket, runtime_config.TOS_FENJING_PREFIX)
    if flow == "video":
        return _delete_tos_prefix(tos, bucket, runtime_config.TOS_VIDEO_PREFIX)
    return _build_ignored_tos_result("invalid_flow")


def clean_stage_assets(project: str, flow: str) -> Dict[str, Any]:
    if flow not in {"auto_storyboard", "visual_audio_assets", "fenjing", "fenjing_generate", "fenjing_upload", "video"}:
        return {"ok": False, "error": "invalid_flow"}
    assets = storyboard_assets_dir(project)
    base = project_base_dir(project)
    removed: List[str] = []
    errors: List[str] = []
    if flow == "auto_storyboard":
        targets = [
            assets / "characters.jsonl",
            assets / "locations.jsonl",
            assets / "summaries.jsonl",
            assets / "raw_characters.jsonl",
            assets / "raw_locations.jsonl",
            assets / "raw_summaries.jsonl",
        ]
        for target in targets:
            _remove_path(target, removed, errors)
        storyboards_dir = assets / "storyboards"
        if storyboards_dir.exists():
            for item in sorted(storyboards_dir.iterdir()):
                if item.is_file() and item.suffix.lower() == ".jsonl":
                    _remove_path(item, removed, errors)
    elif flow == "visual_audio_assets":
        dir_targets = [
            assets / "character_images",
            assets / "location_images",
            assets / "cloth_images",
            assets / "cloth_changed_images",
            assets / "character_candidates",
            assets / "cloth_changed_candidates",
            assets / "tts_audio",
        ]
        for target in dir_targets:
            _remove_path(target, removed, errors)
        file_targets = [
            assets / "character_prompts.jsonl",
            assets / "location_prompts.jsonl",
            assets / "character_prompts_from_tos.jsonl",
            assets / "location_prompts_from_tos.jsonl",
            assets / "character_qc_results.jsonl",
            assets / "cloth_upload.jsonl",
            assets / "cloth_changed_upload.jsonl",
        ]
        for target in file_targets:
            _remove_path(target, removed, errors)
        _remove_path(base / "tts_audio", removed, errors)
        storyboards_dir = assets / "storyboards"
        if storyboards_dir.exists():
            for item in sorted(storyboards_dir.iterdir()):
                if item.is_file() and item.name.startswith("tts_prompts_") and item.suffix.lower() == ".jsonl":
                    _remove_path(item, removed, errors)
                if item.is_dir() and CHAPTER_PATTERN.match(item.name):
                    for sub_item in sorted(item.iterdir()):
                        if sub_item.is_file() and sub_item.name.startswith("tts_prompts_") and sub_item.suffix.lower() == ".jsonl":
                            _remove_path(sub_item, removed, errors)
                        if sub_item.is_file() and sub_item.name == "fenjing_prompts.jsonl":
                            _remove_path(sub_item, removed, errors)
    elif flow in {"fenjing", "fenjing_generate"}:
        storyboards_dir = assets / "storyboards"
        if storyboards_dir.exists():
            for item in sorted(storyboards_dir.iterdir()):
                if item.is_dir() and CHAPTER_PATTERN.match(item.name):
                    _remove_path(item / "fenjing_images", removed, errors)
                    _remove_path(item / "fenjing_candidates", removed, errors)
    elif flow == "fenjing_upload":
        pass
    elif flow == "video":
        _remove_path(assets / "video", removed, errors)
        _remove_path(base / "video", removed, errors)
    result = {"ok": len(errors) == 0, "removed": removed, "errors": errors}
    result["tos"] = _clean_tos_for_flow(flow)
    return result


def _resolve_visual_audio_phases(phase: str) -> Set[str]:
    phases_raw = str(phase or "all")
    phases = {p.strip().lower() for p in phases_raw.split(",") if p.strip()}
    if not phases or "all" in phases:
        return {"all"}
    if "location" in phases:
        phases |= {"location_prompts", "location_images"}
        phases.discard("location")
    if "fenjing" in phases:
        phases.add("fenjing_prompts")
        phases.discard("fenjing")
    if "cloth" in phases:
        phases |= {"cloth_images", "cloth_changed"}
        phases.discard("cloth")
    if "cloth_changed_images" in phases:
        phases.add("cloth_changed")
        phases.discard("cloth_changed_images")
    return phases


def _remove_tts_prompt_files(storyboards_dir: Path, removed: List[str], errors: List[str]) -> None:
    if not storyboards_dir.exists():
        return
    for item in sorted(storyboards_dir.iterdir()):
        if item.is_file() and item.name.startswith("tts_prompts_") and item.suffix.lower() == ".jsonl":
            _remove_path(item, removed, errors)
        if item.is_dir() and CHAPTER_PATTERN.match(item.name):
            for sub_item in sorted(item.iterdir()):
                if sub_item.is_file() and sub_item.name.startswith("tts_prompts_") and sub_item.suffix.lower() == ".jsonl":
                    _remove_path(sub_item, removed, errors)


def _remove_fenjing_prompt_files(storyboards_dir: Path, removed: List[str], errors: List[str]) -> None:
    if not storyboards_dir.exists():
        return
    for item in sorted(storyboards_dir.iterdir()):
        if item.is_dir() and CHAPTER_PATTERN.match(item.name):
            _remove_path(item / "fenjing_prompts.jsonl", removed, errors)


def clean_visual_audio_assets_by_phase(project: str, phase: str) -> Dict[str, Any]:
    assets = storyboard_assets_dir(project)
    base = project_base_dir(project)
    removed: List[str] = []
    errors: List[str] = []
    phases = _resolve_visual_audio_phases(phase)
    if "all" in phases:
        phases = {
            "character",
            "location_prompts",
            "fenjing_prompts",
            "location_images",
            "tts",
            "cloth_images",
            "cloth_changed",
        }
    if "character" in phases:
        phases |= {"cloth_images", "cloth_changed"}
    if "location_prompts" in phases or "fenjing_prompts" in phases:
        phases.add("location_images")

    targets: List[Path] = []
    if "character" in phases:
        targets += [
            assets / "character_prompts.jsonl",
            assets / "character_prompts_from_tos.jsonl",
            assets / "character_images",
            assets / "character_candidates",
            assets / "character_qc_results.jsonl",
        ]
    if "location_prompts" in phases:
        targets += [
            assets / "location_prompts.jsonl",
            assets / "location_prompts_from_tos.jsonl",
        ]
    if "location_images" in phases:
        targets.append(assets / "location_images")
    if "cloth_images" in phases or "cloth_changed" in phases:
        targets += [
            assets / "cloth_images",
            assets / "cloth_changed_images",
            assets / "cloth_changed_candidates",
            assets / "cloth_upload.jsonl",
            assets / "cloth_changed_upload.jsonl",
        ]
    if "tts" in phases:
        targets += [
            assets / "tts_audio",
            base / "tts_audio",
        ]

    for target in targets:
        _remove_path(target, removed, errors)

    storyboards_dir = assets / "storyboards"
    if "tts" in phases:
        _remove_tts_prompt_files(storyboards_dir, removed, errors)
    if "fenjing_prompts" in phases:
        _remove_fenjing_prompt_files(storyboards_dir, removed, errors)
    result = {"ok": len(errors) == 0, "removed": removed, "errors": errors}
    result["tos"] = _clean_tos_visual_audio_assets(TosClientWrapper(), runtime_config.TOS_BUCKET, phases)
    return result


def build_fenjing_ref_urls(project: str, chapter_name: str, fenjing_id: str, item: Dict[str, Any]) -> List[str]:
    refs: List[str] = []
    assets_dir = storyboard_assets_dir(project)
    chars_jsonl = assets_dir / "characters.jsonl"
    defaults = load_char_defaults(chars_jsonl) if chars_jsonl.exists() else {}
    plot_outfits = load_char_plot_outfits(chars_jsonl) if chars_jsonl.exists() else {}
    outfit_map = build_outfit_map_from_storyboard(assets_dir, chapter_name, fenjing_id)
    tos = TosClientWrapper()
    for pk in character_keys_sorted(item):
        cid = item.get(pk)
        if not isinstance(cid, str) or not cid:
            continue
        num = pk.split("_")[1] if "_" in pk else ""
        prefix = "Character" if pk.startswith("Character_") else "person"
        current_outfit = item.get(f"{prefix}_{num}_outfit") or outfit_map.get(cid)
        default_outfit = defaults.get(cid)
        ref_url = None
        if isinstance(current_outfit, str) and current_outfit and current_outfit != default_outfit:
            plot_set = plot_outfits.get(cid)
            if isinstance(plot_set, set) and current_outfit in plot_set:
                changed_key = f"{runtime_config.TOS_CLOTH_PREFIX}/{cid}_{current_outfit}.png"
                changed_presigned = tos.presign_get(runtime_config.TOS_BUCKET, changed_key) if tos.available() else None
                if isinstance(changed_presigned, str) and changed_presigned:
                    ref_url = changed_presigned
        if not ref_url:
            char_key = f"{runtime_config.TOS_CHARACTER_PREFIX}/{cid}.png"
            ref_url = tos.presign_get(runtime_config.TOS_BUCKET, char_key) if tos.available() else None
        if isinstance(ref_url, str) and ref_url:
            refs.append(ref_url)
    loc_id = str(item.get("Background_pic", "")).strip()
    bg_hint = str(item.get("Background_xuanze", "")).strip()
    typ = "sitting" if ("sitting" in bg_hint.lower() or "坐" in bg_hint) else "standing"
    if loc_id:
        loc_key = f"{runtime_config.TOS_LOCATION_PREFIX}/{loc_id}_{typ}.png"
        url = tos.presign_get(runtime_config.TOS_BUCKET, loc_key) if tos.available() else None
        if isinstance(url, str) and url:
            refs.append(url)
    return refs
