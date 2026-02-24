"""Generic table building utilities."""

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from backend.utils.project_utils import safe_read_jsonl


def build_table(
    jsonl_path: Path,
    id_extractor: Callable[[Dict[str, Any]], Optional[str]],
    row_builder: Callable[[Dict[str, Any]], Dict[str, Any]],
    filter_fn: Optional[Callable[[Dict[str, Any]], bool]] = None
) -> Dict[str, Dict[str, Any]]:
    """
    Build a table from a JSONL file.

    Args:
        jsonl_path: Path to the JSONL file
        id_extractor: Function to extract ID from a record
        row_builder: Function to build row data from a record
        filter_fn: Optional filter function

    Returns:
        Mapping of ID to row data
    """
    result = {}
    for item in safe_read_jsonl(jsonl_path):
        if filter_fn and not filter_fn(item):
            continue

        id_val = id_extractor(item)
        if id_val:
            result[id_val] = row_builder(item)

    return result


def build_list_table(
    jsonl_path: Path,
    row_builder: Callable[[Dict[str, Any]], Optional[Dict[str, Any]]],
    filter_fn: Optional[Callable[[Dict[str, Any]], bool]] = None
) -> List[Dict[str, Any]]:
    """
    Build a list table from a JSONL file.

    Args:
        jsonl_path: Path to the JSONL file
        row_builder: Function to build row data from a record (returns None to skip)
        filter_fn: Optional filter function

    Returns:
        List of row data
    """
    result = []
    for item in safe_read_jsonl(jsonl_path):
        if filter_fn and not filter_fn(item):
            continue

        row = row_builder(item)
        if row is not None:
            result.append(row)

    return result


# Predefined ID extractors

def extract_character_id(item: Dict[str, Any]) -> Optional[str]:
    """Extract character ID from item."""
    for key in ["Character_Id", "Character_id", "character_id"]:
        cid = item.get(key)
        if isinstance(cid, str) and cid:
            return cid
    return None


def extract_location_id(item: Dict[str, Any]) -> Optional[str]:
    """Extract location ID from item."""
    for key in ["Location_Id", "Location_id", "location_id", "ID", "id"]:
        lid = item.get(key)
        if isinstance(lid, str) and lid:
            return lid
    return None


def extract_storyboard_id(item: Dict[str, Any]) -> Optional[str]:
    """Extract storyboard ID from item."""
    for key in ["Storyboard_Id", "Storyboard_id", "storyboard_id", "ID", "id"]:
        sid = item.get(key)
        if isinstance(sid, str) and sid:
            return sid
    return None


def extract_cloth_changed_id(item: Dict[str, Any]) -> Optional[str]:
    """Extract cloth changed ID from item."""
    for key in ["ClothChanged_Id", "ClothChanged_id", "clothchanged_id", "CharacterCloth_Id", "ID", "id"]:
        cid = item.get(key)
        if isinstance(cid, str) and cid:
            return cid
    return None
