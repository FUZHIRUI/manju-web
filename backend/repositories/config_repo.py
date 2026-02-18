"""配置持久化仓库，封装全局与项目级并发配置的读写。"""

import json
from pathlib import Path
from typing import Any, Dict

ROOT_DIR = Path(__file__).resolve().parents[3]
CONFIG_DIR = ROOT_DIR / "manju_web" / "backend" / "config"
GLOBAL_PATH = CONFIG_DIR / "global_concurrency.json"
PROJECT_DIR = CONFIG_DIR / "project_concurrency"
AUTH_GLOBAL_PATH = CONFIG_DIR / "global_auth.json"
AUTH_PROJECT_DIR = CONFIG_DIR / "project_auth"
RETRY_GLOBAL_PATH = CONFIG_DIR / "global_retry.json"


def _read_json(path: Path) -> Dict[str, Any]:
    """读取配置文件并容错返回空对象，确保上层逻辑不因文件缺失中断。"""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    """写入配置文件并确保目录存在，保证配置更新可落盘。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_global_config() -> Dict[str, Any]:
    """读取全局并发配置，缺失时返回空对象以保持默认配置生效。"""
    return _read_json(GLOBAL_PATH)


def load_project_config(project: str) -> Dict[str, Any]:
    """读取指定项目并发配置，项目名为空时直接返回空对象。"""
    if not project:
        return {}
    return _read_json(PROJECT_DIR / f"{project}.json")


def save_global_config(data: Dict[str, Any]) -> None:
    """保存全局并发配置，便于统一控制全局限速策略。"""
    _write_json(GLOBAL_PATH, data)


def save_project_config(project: str, data: Dict[str, Any]) -> None:
    """保存项目级并发配置，项目名为空时跳过写入以避免误落盘。"""
    if not project:
        return
    _write_json(PROJECT_DIR / f"{project}.json", data)


def load_global_auth_config() -> Dict[str, Any]:
    return _read_json(AUTH_GLOBAL_PATH)


def load_project_auth_config(project: str) -> Dict[str, Any]:
    if not project:
        return {}
    return _read_json(AUTH_PROJECT_DIR / f"{project}.json")


def save_global_auth_config(data: Dict[str, Any]) -> None:
    _write_json(AUTH_GLOBAL_PATH, data)


def save_project_auth_config(project: str, data: Dict[str, Any]) -> None:
    if not project:
        return
    _write_json(AUTH_PROJECT_DIR / f"{project}.json", data)


def load_global_retry_config() -> Dict[str, Any]:
    return _read_json(RETRY_GLOBAL_PATH)


def save_global_retry_config(data: Dict[str, Any]) -> None:
    _write_json(RETRY_GLOBAL_PATH, data)
