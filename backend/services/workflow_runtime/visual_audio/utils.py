"""Utility functions for visual audio assets module."""

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .. import runtime_config


def ensure_dir(path: Path) -> None:
    """Ensure directory exists, creating parents if necessary."""
    path.mkdir(parents=True, exist_ok=True)


def read_text(path: Union[str, Path]) -> str:
    """Read text file contents."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def safe_get(
    data: Dict[str, Any],
    key: str,
    default: Any = None,
    alt_keys: Optional[List[str]] = None
) -> Any:
    """
    Safely get value from dict with fallback to alternative keys.

    Args:
        data: Dictionary to search
        key: Primary key to look for
        default: Default value if not found
        alt_keys: Alternative keys to try if primary not found

    Returns:
        Value from dict or default
    """
    if key in data:
        return data[key]

    if alt_keys:
        for alt_key in alt_keys:
            if alt_key in data:
                return data[alt_key]

    return default


def resolve_character_size_by_attribute(attribute: Optional[str]) -> Optional[str]:
    """
    Resolve image size based on character attribute.

    Args:
        attribute: Character attribute (人类/兽类/etc.)

    Returns:
        Image size string or None
    """
    if isinstance(attribute, str):
        attr = attribute.strip()
        if attr == "人类":
            return runtime_config.CHARACTER_HUMAN_IMAGE_SIZE
        if attr == "兽类":
            return runtime_config.CHARACTER_BEAST_IMAGE_SIZE
    return None


def merge_dicts(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deep merge two dictionaries.

    Args:
        base: Base dictionary
        override: Dictionary with values to override

    Returns:
        Merged dictionary
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_dicts(result[key], value)
        else:
            result[key] = value
    return result
