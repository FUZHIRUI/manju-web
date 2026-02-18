from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from typing import Dict
from urllib.parse import parse_qs, urlparse

from .http_utils import send_json
from ..repositories import project_repo
from ..services import config_service


def _extract_project(path: str) -> str:
    """从请求路径中解析并规范化项目名。"""
    parsed = urlparse(path)
    params = parse_qs(parsed.query)
    project = params.get("project", [""])[0]
    return project_repo.safe_project_name(project) if project else ""


def handle_get(handler: BaseHTTPRequestHandler, path: str) -> bool:
    """处理并发配置查询请求，返回当前项目生效的配置。"""
    if path.startswith("/api/config/auth"):
        project = _extract_project(path)
        try:
            items = config_service.get_auth_config(project)
        except Exception as exc:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return True
        send_json(handler, HTTPStatus.OK, {"items": items})
        return True
    if path.startswith("/api/config/retry"):
        try:
            config = config_service.get_retry_config()
        except Exception as exc:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return True
        send_json(handler, HTTPStatus.OK, {"config": config})
        return True
    if not path.startswith("/api/config/concurrency"):
        return False
    project = _extract_project(path)
    try:
        items = config_service.get_effective_config(project)
    except Exception as exc:
        send_json(handler, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        return True
    send_json(handler, HTTPStatus.OK, {"items": items})
    return True


def handle_patch(handler: BaseHTTPRequestHandler, path: str, body: Dict[str, object]) -> bool:
    """处理并发配置更新请求，更新后返回生效配置。"""
    if path.startswith("/api/config/auth"):
        project = _extract_project(path)
        scope = str(body.get("scope", "global"))
        updates = body.get("items")
        if scope not in {"global", "project"}:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_scope"})
            return True
        if not isinstance(updates, dict) or not updates:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_items"})
            return True
        try:
            items = config_service.update_auth_config(project, scope, updates)
        except Exception as exc:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return True
        send_json(handler, HTTPStatus.OK, {"items": items})
        return True
    if path.startswith("/api/config/retry"):
        updates = body.get("config")
        if not isinstance(updates, dict):
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_retry_config"})
            return True
        try:
            config = config_service.update_retry_config(updates)
        except Exception as exc:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return True
        send_json(handler, HTTPStatus.OK, {"config": config})
        return True
    if not path.startswith("/api/config/concurrency"):
        return False
    project = _extract_project(path)
    scope = str(body.get("scope", "global"))
    updates = body.get("items")
    if scope not in {"global", "project"}:
        send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_scope"})
        return True
    if not isinstance(updates, dict) or not updates:
        send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_items"})
        return True
    try:
        items = config_service.update_config(project, scope, updates)
    except Exception as exc:
        send_json(handler, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        return True
    send_json(handler, HTTPStatus.OK, {"items": items})
    return True
