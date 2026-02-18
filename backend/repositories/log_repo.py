from pathlib import Path
from typing import Dict, List, Optional


def tail_log(path: Path, max_lines: int = 200) -> List[str]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    return lines[-max_lines:]


def read_log_page(path: Path, offset: Optional[int], limit: int) -> Dict[str, object]:
    if not path.exists():
        return {"lines": [], "offset": 0, "next_offset": 0, "prev_offset": 0, "total": 0, "has_more": False}
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    total = len(lines)
    safe_limit = max(int(limit), 1)
    if offset is None:
        start = max(total - safe_limit, 0)
    else:
        start = max(min(int(offset), total), 0)
    end = min(start + safe_limit, total)
    page_lines = lines[start:end]
    next_offset = end
    prev_offset = max(start - safe_limit, 0)
    has_more = start > 0
    return {
        "lines": page_lines,
        "offset": start,
        "next_offset": next_offset,
        "prev_offset": prev_offset,
        "total": total,
        "has_more": has_more,
    }
