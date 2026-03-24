"""Prompt building utilities for visual audio assets module."""

from typing import Any, Dict, List, Optional


def build_character_prompt(
    _character_name: str,
    base_prompt: str,
    attribute: Optional[str] = None,
    outfit_desc: Optional[str] = None,
) -> str:
    """
    Build character image generation prompt.

    Args:
        character_name: Character name
        base_prompt: Base character description
        attribute: Character attribute (人类/兽类)
        outfit_desc: Outfit description

    Returns:
        Complete prompt string
    """
    prompt_parts = [base_prompt]

    # Add outfit description if provided
    if outfit_desc:
        prompt_parts.append(f"穿着: {outfit_desc}")

    # Add style hints based on attribute
    if attribute:
        if attribute.strip() == "人类":
            prompt_parts.append("高质量真人摄影风格，写实")
        elif attribute.strip() == "兽类":
            prompt_parts.append("奇幻生物风格，精致细节")

    return "; ".join(prompt_parts)


def build_location_prompt(
    _location_name: str,
    location_desc: str,
    scene_type: Optional[str] = None,
    time_of_day: Optional[str] = None,
) -> str:
    """
    Build location/background image generation prompt.

    Args:
        location_name: Location name
        location_desc: Location description
        scene_type: Type of scene (室内/室外)
        time_of_day: Time of day (白天/夜晚/黄昏)

    Returns:
        Complete prompt string
    """
    prompt_parts = [location_desc]

    if scene_type:
        prompt_parts.append(scene_type)

    if time_of_day:
        prompt_parts.append(f"{time_of_day}的光线")

    prompt_parts.append("高质量，电影级画面，宽屏比例")

    return "; ".join(prompt_parts)


def build_fenjing_prompt(
    action: str,
    characters: List[Dict[str, Any]],
    location: Optional[str] = None,
    time: Optional[str] = None,
    style_hints: Optional[List[str]] = None,
) -> str:
    """
    Build fenjing (storyboard frame) image generation prompt.

    Args:
        action: Action description
        characters: List of character dicts with name, outfit, pose
        location: Location description
        time: Time of day
        style_hints: Additional style hints

    Returns:
        Complete prompt string
    """
    prompt_parts = []

    # Add action
    prompt_parts.append(f"场景: {action}")

    # Add characters
    if characters:
        char_descs = []
        for char in characters:
            char_parts = [char.get("name", "")]
            if char.get("outfit"):
                char_parts.append(f"穿着{char['outfit']}")
            if char.get("pose"):
                char_parts.append(char["pose"])
            char_descs.append("，".join(char_parts))
        prompt_parts.append("角色: " + "; ".join(char_descs))

    # Add location and time
    if location:
        prompt_parts.append(f"地点: {location}")
    if time:
        prompt_parts.append(f"时间: {time}")

    # Add style hints
    if style_hints:
        prompt_parts.extend(style_hints)
    else:
        prompt_parts.append("电影级画面，高质量，精致细节")

    return "; ".join(prompt_parts)
