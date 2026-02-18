import json
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Dict


def read_json_body(handler: BaseHTTPRequestHandler) -> Dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}


def send_json(handler: BaseHTTPRequestHandler, status: int, payload: Dict[str, Any]) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET,POST,PATCH,OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.end_headers()
    handler.wfile.write(data)


def send_file(handler: BaseHTTPRequestHandler, file_path: Path, content_type: str) -> None:
    if not file_path.exists() or not file_path.is_file():
        send_json(handler, HTTPStatus.NOT_FOUND, {"error": "file_not_found"})
        return
    file_size = file_path.stat().st_size
    range_header = handler.headers.get("Range")
    if range_header:
        match = re.match(r"bytes=(\d*)-(\d*)", range_header)
        if match:
            start_text, end_text = match.groups()
            if start_text or end_text:
                if not start_text:
                    length = int(end_text)
                    length = min(length, file_size)
                    start = max(file_size - length, 0)
                    end = file_size - 1
                else:
                    start = int(start_text)
                    end = int(end_text) if end_text else file_size - 1
                if start >= file_size or end < start:
                    handler.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    handler.send_header("Content-Range", f"bytes */{file_size}")
                    handler.send_header("Access-Control-Allow-Origin", "*")
                    handler.end_headers()
                    return
                end = min(end, file_size - 1)
                length = end - start + 1
                handler.send_response(HTTPStatus.PARTIAL_CONTENT)
                handler.send_header("Content-Type", content_type)
                handler.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                handler.send_header("Accept-Ranges", "bytes")
                handler.send_header("Content-Length", str(length))
                handler.send_header("Access-Control-Allow-Origin", "*")
                handler.end_headers()
                with file_path.open("rb") as f:
                    f.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk = f.read(min(64 * 1024, remaining))
                        if not chunk:
                            break
                        handler.wfile.write(chunk)
                        remaining -= len(chunk)
                return
    data = file_path.read_bytes()
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Accept-Ranges", "bytes")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(data)


def send_file_safe(handler: BaseHTTPRequestHandler, file_path: Path, content_type: str) -> None:
    """安全发送文件，捕获客户端断开异常，防止服务崩溃"""
    try:
        send_file(handler, file_path, content_type)
    except (BrokenPipeError, ConnectionResetError):
        # 客户端断开连接，静默处理不抛出异常
        pass
    except Exception:
        # 其他异常继续抛出
        raise
