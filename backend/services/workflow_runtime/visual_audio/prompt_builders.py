"""Prompt building utilities for visual audio assets module."""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .utils import read_text


def build_character_prompt(
    character_name: str,
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
    location_name: str,
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


def load_prompt_template(template_path: Path) -> str:
    """
    Load a prompt template from file.

    Args:
        template_path: Path to template file

    Returns:
        Template string
    """
    return read_text(template_path)


def format_prompt(template: str, variables: Dict[str, Any]) -> str:
    """
    Format a prompt template with variables.

    Args:
        template: Template string with {variable} placeholders
        variables: Dictionary of variables to substitute

    Returns:
        Formatted prompt string
    """
    try:
        return template.format(**variables)
    except KeyError as e:
        # Log missing variable and return template with available substitutions
        return template.format(**{k: v for k, v in variables.items() if f"{{{k}}}" in template})


def build_tts_prompt(
    text: str,
    character_name: Optional[str] = None,
    emotion: Optional[str] = None,
    speed: float = 1.0,
) -> Dict[str, Any]:
    """
    Build TTS (text-to-speech) configuration.

    Args:
        text: Text to speak
        character_name: Character name (for voice selection)
        emotion: Emotion hint
        speed: Speech speed multiplier

    Returns:
        TTS configuration dict
    """
    config: Dict[str, Any] = {
        "text": text,
        "speed": speed,
    }

    if character_name:
        config["voice_character"] = character_name

    if emotion:
        config["emotion"] = emotion

    return config


def merge_prompt_parts(base_parts: List[str], override_parts: Optional[List[str]] = None) -> str:
    """
    Merge multiple prompt parts into a single prompt.

    Args:
        base_parts: Base prompt parts
        override_parts: Additional parts to append

    Returns:
        Merged prompt string
    """
    all_parts = list(base_parts)
    if override_parts:
        all_parts.extend(override_parts)

    # Remove duplicates while preserving order
    seen = set()
    unique_parts = []
    for part in all_parts:
        part_clean = part.strip()
        if part_clean and part_clean not in seen:
            seen.add(part_clean)
            unique_parts.append(part_clean)

    return "; ".join(unique_parts)
