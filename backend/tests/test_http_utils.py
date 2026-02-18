from io import BytesIO
from pathlib import Path
from typing import Dict, Optional

from manju_web.backend.handlers import http_utils


# 边界：用最小化 Handler 模拟读写与头部行为，避免引入真实网络依赖
class FakeHandler:
    def __init__(self, body: bytes = b"", headers: Optional[Dict[str, str]] = None) -> None:
        self.headers = headers or {}
        self.rfile = BytesIO(body)
        self.wfile = BytesIO()
        self.status = None
        self.sent_headers: Dict[str, str] = {}

    def send_response(self, status: int) -> None:
        self.status = status

    def send_header(self, key: str, value: str) -> None:
        self.sent_headers[key] = value

    def end_headers(self) -> None:
        return None


def test_read_json_body() -> None:
    body = b'{"a": 1}'
    handler = FakeHandler(body=body, headers={"Content-Length": str(len(body))})
    data = http_utils.read_json_body(handler)
    # 边界：正常 JSON body 应解析成功
    assert data == {"a": 1}


def test_read_json_body_invalid() -> None:
    body = b"not-json"
    handler = FakeHandler(body=body, headers={"Content-Length": str(len(body))})
    data = http_utils.read_json_body(handler)
    # 边界：非法 JSON 返回空对象
    assert data == {}


def test_send_json() -> None:
    handler = FakeHandler()
    http_utils.send_json(handler, 200, {"ok": True})
    # 边界：输出 JSON 响应应带正确状态码与内容类型
    assert handler.status == 200
    assert handler.sent_headers.get("Content-Type") == "application/json; charset=utf-8"
    payload = handler.wfile.getvalue().decode("utf-8")
    assert '"ok": true' in payload


def test_send_file_ranges(tmp_path: Path) -> None:
    file_path = tmp_path / "a.txt"
    file_path.write_text("abcdef", encoding="utf-8")
    handler = FakeHandler(headers={"Range": "bytes=1-3"})
    http_utils.send_file(handler, file_path, "text/plain")
    # 边界：合法 Range 请求返回 206 且内容截取正确
    assert handler.status == 206
    assert handler.sent_headers.get("Content-Range") == "bytes 1-3/6"
    assert handler.wfile.getvalue() == b"bcd"


def test_send_file_not_found(tmp_path: Path) -> None:
    handler = FakeHandler()
    http_utils.send_file(handler, tmp_path / "missing.txt", "text/plain")
    # 边界：文件不存在返回 404
    assert handler.status == 404


def test_send_file_range_unsatisfiable(tmp_path: Path) -> None:
    file_path = tmp_path / "a.txt"
    file_path.write_text("abcdef", encoding="utf-8")
    handler = FakeHandler(headers={"Range": "bytes=99-100"})
    http_utils.send_file(handler, file_path, "text/plain")
    # 边界：Range 超出文件范围返回 416
    assert handler.status == 416
