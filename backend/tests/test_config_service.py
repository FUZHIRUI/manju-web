from typing import Any, Dict

import pytest

from manju_web.backend.repositories import config_repo
from manju_web.backend.services import config_service


def test_update_config_global(config_paths: Dict[str, Any]) -> None:
    items = config_service.update_config("demo", "global", {"auto_storyboard.batch_size": 5})
    matched = [item for item in items if item["id"] == "auto_storyboard.batch_size"]
    # 边界：配置更新后的值必须可回读并标记来源
    assert matched and matched[0]["value"] == 5
    assert matched[0]["source"] == "global"


def test_project_override_model_limit_blocked(config_paths: Dict[str, Any]) -> None:
    # 边界：模型级限流仅允许全局配置
    with pytest.raises(ValueError):
        config_service.update_config("demo", "project", {"model.ark.ark_qps": 1})


def test_project_override_stage_concurrency_blocked(config_paths: Dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        config_service.update_config("demo", "project", {"auto_storyboard.stage_concurrency": 1})


def test_update_auth_config_mask(config_paths: Dict[str, Any]) -> None:
    items = config_service.update_auth_config("demo", "global", {"auth.tts_access_key": "secret"})
    matched = [item for item in items if item["id"] == "auth.tts_access_key"]
    # 边界：敏感字段必须被遮蔽，避免明文透出
    assert matched and matched[0]["value"] == ""
    assert matched[0]["stored"] is True
    saved = config_repo.load_global_auth_config()
    assert saved["items"]["auth.tts_access_key"] == "secret"


def test_auth_runtime_env_override(config_paths: Dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TTS_APP_ID", "runtime_app")
    items = config_service.get_effective_auth_config("demo")
    matched = [item for item in items if item["id"] == "auth.tts_app_id"]
    # 边界：运行时环境变量优先级最高
    assert matched and matched[0]["value"] == "runtime_app"
    assert matched[0]["source"] == "runtime"


def test_update_config_clamp_range(
    config_paths: Dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # 边界：小于最小值时应被截断到最小值
    items = config_service.update_config("demo", "global", {"model.ark.ark_qps": -1})
    matched = [item for item in items if item["id"] == "model.ark.ark_qps"]
    assert matched and matched[0]["value"] == 0
    # 边界：无最大值限制时应保留用户设置值
    items = config_service.update_config("demo", "global", {"auto_storyboard.batch_size": 999})
    matched = [item for item in items if item["id"] == "auto_storyboard.batch_size"]
    assert matched and matched[0]["value"] == 999


def test_update_config_invalid_value_ignored(config_paths: Dict[str, Any]) -> None:
    # 边界：非法数值应被忽略，保持默认值
    defaults = {item["id"]: item["default"] for item in config_service.list_config_items()}
    items = config_service.update_config("demo", "global", {"auto_storyboard.batch_size": "bad"})
    matched = [item for item in items if item["id"] == "auto_storyboard.batch_size"]
    assert matched and matched[0]["value"] == defaults["auto_storyboard.batch_size"]
