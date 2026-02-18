from pathlib import Path
from typing import Dict

from manju_web.backend.repositories import config_repo


def test_config_repo_roundtrip(config_paths: Dict[str, Path]) -> None:
    payload = {"items": {"auto_storyboard.batch_size": 5}}
    config_repo.save_global_config(payload)
    loaded = config_repo.load_global_config()
    # 边界：全局配置应可完整读写
    assert loaded == payload


def test_project_config_roundtrip(config_paths: Dict[str, Path]) -> None:
    payload = {"items": {"video.video_task_qps": 2}}
    config_repo.save_project_config("demo", payload)
    loaded = config_repo.load_project_config("demo")
    # 边界：项目配置应可完整读写
    assert loaded == payload


def test_auth_config_roundtrip(config_paths: Dict[str, Path]) -> None:
    payload = {"items": {"auth.tts_app_id": "app_1"}}
    config_repo.save_global_auth_config(payload)
    loaded = config_repo.load_global_auth_config()
    # 边界：鉴权配置应可完整读写
    assert loaded == payload
