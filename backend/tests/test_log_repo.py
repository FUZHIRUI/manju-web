from pathlib import Path
from typing import List

from manju_web.backend.repositories import log_repo


def test_tail_log(tmp_path: Path) -> None:
    path = tmp_path / "a.log"
    path.write_text("\n".join([f"line{i}" for i in range(5)]), encoding="utf-8")
    tail = log_repo.tail_log(path, max_lines=2)
    # 边界：只返回指定行数的日志尾部
    assert tail == ["line3", "line4"]
