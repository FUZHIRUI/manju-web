from pathlib import Path
from typing import Dict
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    # 边界：测试路径隔离时确保可正确导入项目模块
    sys.path.insert(0, str(ROOT))

from manju_web.backend.repositories import config_repo, job_repo, project_repo
from manju_web.backend.services.workflow_runtime import runtime_config


@pytest.fixture()
def config_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Dict[str, Path]:
    # 边界：使用临时目录隔离配置文件，避免污染真实配置
    base = tmp_path / "config"
    global_path = base / "global_concurrency.json"
    project_dir = base / "project_concurrency"
    auth_global_path = base / "global_auth.json"
    auth_project_dir = base / "project_auth"
    retry_global_path = base / "global_retry.json"
    monkeypatch.setattr(config_repo, "CONFIG_DIR", base)
    monkeypatch.setattr(config_repo, "GLOBAL_PATH", global_path)
    monkeypatch.setattr(config_repo, "PROJECT_DIR", project_dir)
    monkeypatch.setattr(config_repo, "AUTH_GLOBAL_PATH", auth_global_path)
    monkeypatch.setattr(config_repo, "AUTH_PROJECT_DIR", auth_project_dir)
    monkeypatch.setattr(config_repo, "RETRY_GLOBAL_PATH", retry_global_path)
    # 边界：清理相关环境变量，确保配置读取优先使用测试数据
    env_keys = [
        "STORYBOARD_BATCH_SIZE",
        "TTS_TOTAL_CONCURRENCY",
        "VIDEO_TASK_QPS",
        "VIDEO_AUDIO_DURATION_QPS",
        "IMAGE_MODEL_QPS",
        "IMAGE_MODEL_CONCURRENCY",
        "VIDEO_MODEL_1_5_QPS",
        "VIDEO_MODEL_1_5_CONCURRENCY",
        "VIDEO_MODEL_1_0_QPS",
        "VIDEO_MODEL_1_0_CONCURRENCY",
        "TTS_APP_ID",
        "TTS_ACCESS_KEY",
        "TTS_RESOURCE_ID",
        "TTS_URL",
        "TTS_SPEAKER",
    ]
    for key in env_keys:
        monkeypatch.delenv(key, raising=False)
    return {
        "base": base,
        "global": global_path,
        "project_dir": project_dir,
        "auth_global": auth_global_path,
        "auth_project_dir": auth_project_dir,
        "retry_global": retry_global_path,
    }


@pytest.fixture(autouse=True)
def isolate_output_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("MANJU_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(project_repo, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(runtime_config, "OUTPUT_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture()
def project_output_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # 边界：输出目录使用临时路径，确保测试互不影响
    monkeypatch.setattr(project_repo, "OUTPUT_DIR", tmp_path)
    return tmp_path


@pytest.fixture()
def job_repo_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "root"
    log_dir = root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(job_repo, "ROOT_DIR", root)
    monkeypatch.setattr(job_repo, "LOG_DIR", log_dir)
    return root
