import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional


@dataclass(frozen=True)
class ApiRoute:
    method: str
    match: str
    pattern: str
    file: str
    line: int


def _iter_files(root: Path) -> Iterable[Path]:
    candidates = [
        root / "backend" / "server.py",
    ]
    handlers = root / "backend" / "handlers"
    if handlers.exists():
        candidates.extend(sorted(handlers.glob("*.py")))
    return [p for p in candidates if p.exists()]


def _detect_method(file_path: Path, line: str, current: Optional[str]) -> Optional[str]:
    if file_path.name == "server.py":
        if re.search(r"def\s+do_GET\b", line):
            return "GET"
        if re.search(r"def\s+do_POST\b", line):
            return "POST"
        if re.search(r"def\s+do_PATCH\b", line):
            return "PATCH"
        if re.search(r"def\s+do_\w+\b", line):
            return None
        return current
    match = re.search(r"def\s+handle_(get|post|patch)\b", line)
    if match:
        return match.group(1).upper()
    if re.search(r"def\s+\w+\b", line):
        return None
    return current


def _extract_patterns(line: str) -> List[tuple[str, str]]:
    patterns: List[tuple[str, str]] = []
    for func in ("startswith", "endswith"):
        match = re.findall(rf"\b(path|clean_path)\.{func}\((['\"])(/api/[^'\"]+)\2\)", line)
        for _, _, value in match:
            patterns.append((func, value))
    match_eq = re.findall(r"\b(path|clean_path)\s*==\s*(['\"])(/api/[^'\"]+)\2", line)
    for _, _, value in match_eq:
        patterns.append(("equals", value))
    match_in = re.findall(r"\b(path|clean_path)\s*in\s*\(([^\)]*)\)", line)
    for _, values in match_in:
        for literal in re.findall(r"(['\"])(/api/[^'\"]+)\1", values):
            patterns.append(("in", literal[1]))
    return patterns


def scan_routes(root: Path) -> List[ApiRoute]:
    routes: List[ApiRoute] = []
    for file_path in _iter_files(root):
        current_method: Optional[str] = None
        try:
            text = file_path.read_text(encoding="utf-8")
        except Exception:
            continue
        for index, raw_line in enumerate(text.splitlines(), start=1):
            current_method = _detect_method(file_path, raw_line, current_method)
            if not current_method:
                continue
            for match_type, pattern in _extract_patterns(raw_line):
                routes.append(
                    ApiRoute(
                        method=current_method,
                        match=match_type,
                        pattern=pattern,
                        file=str(file_path),
                        line=index,
                    )
                )
    return routes


def main() -> None:
    """扫描 manju_web 项目后端路由并输出 JSON。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default="/Users/bytedance/Desktop/常见python/manju_web")
    args = parser.parse_args()
    root = Path(args.root)
    routes = scan_routes(root)
    payload = [route.__dict__ for route in routes]
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
