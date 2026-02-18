from pathlib import Path
from typing import List

from manju_web.backend.services.workflow_runtime import io_jsonl


def test_read_write_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "a.jsonl"
    data = [{"a": 1}, {"b": 2}]
    io_jsonl.write_jsonl(str(path), data)
    loaded = io_jsonl.read_jsonl(str(path))
    # 边界：多行 JSONL 读写顺序与内容应一致
    assert loaded == data
