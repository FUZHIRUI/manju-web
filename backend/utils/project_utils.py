"""Project related utility functions."""

import json
import re
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional


def safe_project_name(name: str) -> Optional[str]:
    """
    Convert project name to a safe directory name.

    Replaces non-alphanumeric characters with underscores to ensure directory safety.

    Args:
        name: Original project name

    Returns:
        Safe directory name or None if invalid
    """
    if not isinstance(name, str):
        return None
    name = name.strip()
    if not name or not re.match(r"^[a-zA-Z0-9_-]{1,64}$", name):
        return None
    return name


def project_base_dir(project: str, output_dir: Optional[Path] = None) -> Path:
    """
    Get the project's base directory.

    Args:
        project: Project name
        output_dir: Root output directory (defaults to environment or current dir)

    Returns:
        Project base directory path
    """
    if output_dir is None:
        import os
        from backend.services.workflow_runtime import runtime_config

        output_dir = Path(os.environ.get("MANJU_OUTPUT_DIR", str(runtime_config.OUTPUT_DIR)))
    return output_dir / project


def safe_read_jsonl(path: Path) -> List[Dict[str, Any]]:
    """
    Safely read a JSONL file.

    Returns an empty list if the file doesn't exist or is empty.
    Skips invalid JSON lines.

    Args:
        path: JSONL file path

    Returns:
        List of JSON objects
    """
    results = []
    if not path.exists():
        return results

    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass

    return results


def read_jsonl_lazy(path: Path) -> Generator[Dict[str, Any], None, None]:
    """
    Lazily read a JSONL file (generator version).

    Suitable for processing large files without loading everything into memory.

    Args:
        path: JSONL file path

    Yields:
        JSON objects
    """
    if not path.exists():
        return

    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass
