from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from urllib.parse import unquote

from .http_utils import send_file_safe, send_json
from ..repositories import project_repo
from ..services import project_service


def handle_get(handler: BaseHTTPRequestHandler, path: str) -> bool:
    if not path.startswith("/media/"):
        return False
    parts = path[len("/media/") :].split("/", 1)
    if len(parts) != 2:
        send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_media_path"})
        return True
    project = project_repo.safe_project_name(parts[0])
    if not project:
        send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_project"})
        return True
    rel_path = unquote(parts[1])
    resolved = project_service.resolve_media_path(project, rel_path)
    if not resolved:
        send_json(handler, HTTPStatus.NOT_FOUND, {"error": "file_not_found"})
        return True
    content_type = "application/octet-stream"
    if resolved.suffix.lower() in {".png", ".jpg", ".jpeg"}:
        content_type = "image/png" if resolved.suffix.lower() == ".png" else "image/jpeg"
    elif resolved.suffix.lower() in {".mp4", ".mov"}:
        content_type = "video/mp4"
    send_file_safe(handler, resolved, content_type)
    return True
