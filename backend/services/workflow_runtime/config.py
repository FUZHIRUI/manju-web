"""
Thread-safe runtime configuration management module.

This module provides a singleton RuntimeConfig class that manages all workflow
runtime configuration parameters in a thread-safe manner.
"""

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .. import config_defaults
from ...repositories import config_repo


def _get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    """Get string value from environment variable."""
    return os.environ.get(name, default)


def _get_int(name: str, default: int) -> int:
    """Get integer value from environment variable."""
    value = _get_env(name)
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _get_float(name: str, default: float) -> float:
    """Get float value from environment variable."""
    value = _get_env(name)
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _get_bool(name: str, default: bool) -> bool:
    """Get boolean value from environment variable."""
    value = _get_env(name)
    if value is None:
        return default
    return str(value).lower() in {"1", "true", "yes", "y"}


@dataclass
class ArkConfig:
    """ARK API configuration."""
    base_url: str = ""
    api_key: str = ""
    chat_model: str = ""
    vlm_model: str = ""
    seedream_model: str = ""
    timeout: int = 300

    def update_from_env(self) -> None:
        """Update configuration from environment variables."""
        self.base_url = _get_env("ARK_BASE_URL", config_defaults.DEFAULT_ARK_BASE_URL) or ""
        self.api_key = _get_env("ARK_API_KEY", config_defaults.DEFAULT_ARK_API_KEY) or ""
        self.chat_model = _get_env("ARK_CHAT_MODEL", config_defaults.DEFAULT_ARK_CHAT_MODEL) or ""
        self.vlm_model = _get_env("ARK_VLM_MODEL", config_defaults.DEFAULT_ARK_VLM_MODEL) or ""
        self.seedream_model = _get_env("SEEDREAM_MODEL", config_defaults.DEFAULT_SEEDREAM_MODEL) or ""
        self.timeout = _get_int("ARK_TIMEOUT", config_defaults.DEFAULT_ARK_TIMEOUT)


@dataclass
class TosConfig:
    """TOS object storage configuration."""
    endpoint: str = ""
    access_key: str = ""
    secret_key: str = ""
    region: str = ""
    bucket: str = ""
    assets_prefix: str = ""
    character_prefix: str = ""
    location_prefix: str = ""
    cloth_prefix: str = ""
    crop_role_prefix: str = ""
    fenjing_prefix: str = ""
    tts_prefix: str = ""
    video_prefix: str = ""

    def update_from_env(self, project_name: str = "") -> None:
        """Update configuration from environment variables."""
        self.endpoint = _get_env("TOS_ENDPOINT", config_defaults.DEFAULT_TOS_ENDPOINT) or ""
        self.access_key = _get_env("TOS_ACCESS_KEY", config_defaults.DEFAULT_TOS_ACCESS_KEY) or ""
        self.secret_key = _get_env("TOS_SECRET_KEY", config_defaults.DEFAULT_TOS_SECRET_KEY) or ""
        self.region = _get_env("TOS_REGION", config_defaults.DEFAULT_TOS_REGION) or ""
        self.bucket = _get_env("TOS_BUCKET", config_defaults.DEFAULT_TOS_BUCKET) or ""

        # Prefixes based on project name
        name = project_name or config_defaults.DEFAULT_TOS_PROJECT_NAME
        self.assets_prefix = _get_env(
            "TOS_ASSETS_PREFIX",
            config_defaults.DEFAULT_TOS_ASSETS_PREFIX_TEMPLATE.format(project_name=name),
        ) or ""
        self.character_prefix = _get_env(
            "TOS_CHARACTER_PREFIX",
            config_defaults.DEFAULT_TOS_CHARACTER_PREFIX_TEMPLATE.format(project_name=name),
        ) or ""
        self.location_prefix = _get_env(
            "TOS_LOCATION_PREFIX",
            config_defaults.DEFAULT_TOS_LOCATION_PREFIX_TEMPLATE.format(project_name=name),
        ) or ""
        self.cloth_prefix = _get_env(
            "TOS_CLOTH_PREFIX",
            config_defaults.DEFAULT_TOS_CLOTH_PREFIX_TEMPLATE.format(project_name=name),
        ) or ""
        self.crop_role_prefix = _get_env(
            "TOS_CROP_ROLE_PREFIX",
            config_defaults.DEFAULT_TOS_CROP_ROLE_PREFIX_TEMPLATE.format(project_name=name),
        ) or ""
        self.fenjing_prefix = _get_env(
            "TOS_FENJING_PREFIX",
            config_defaults.DEFAULT_TOS_FENJING_PREFIX_TEMPLATE.format(project_name=name),
        ) or ""
        self.tts_prefix = _get_env(
            "TOS_TTS_PREFIX",
            config_defaults.DEFAULT_TOS_TTS_PREFIX_TEMPLATE.format(project_name=name),
        ) or ""
        self.video_prefix = _get_env(
            "TOS_VIDEO_PREFIX",
            config_defaults.DEFAULT_TOS_VIDEO_PREFIX_TEMPLATE.format(project_name=name),
        ) or ""


@dataclass
class TtsConfig:
    """TTS voice synthesis configuration."""
    app_id: str = ""
    access_key: str = ""
    resource_id: str = ""
    url: str = ""
    speaker: str = ""
    total_concurrency: int = 1

    def update_from_env(self) -> None:
        """Update configuration from environment variables."""
        self.app_id = _get_env("TTS_APP_ID", config_defaults.DEFAULT_TTS_APP_ID) or ""
        self.access_key = _get_env("TTS_ACCESS_KEY", config_defaults.DEFAULT_TTS_ACCESS_KEY) or ""
        self.resource_id = _get_env("TTS_RESOURCE_ID", config_defaults.DEFAULT_TTS_RESOURCE_ID) or ""
        self.url = _get_env("TTS_URL", config_defaults.DEFAULT_TTS_URL) or ""
        self.speaker = _get_env("TTS_SPEAKER", config_defaults.DEFAULT_TTS_SPEAKER) or ""
        self.total_concurrency = _get_int("TTS_TOTAL_CONCURRENCY", config_defaults.DEFAULT_TTS_TOTAL_CONCURRENCY)


@dataclass
class VideoConfig:
    """Video generation configuration."""
    model_1_5_ep: str = ""
    model_1_0_ep: str = ""
    resolution: str = ""
    ratio: str = ""
    min_duration_1_5: float = 0.0
    min_duration_1_0: float = 0.0

    def update_from_env(self) -> None:
        """Update configuration from environment variables."""
        self.model_1_5_ep = _get_env("VIDEO_MODEL_1_5_EP", config_defaults.DEFAULT_VIDEO_MODEL_1_5_EP) or ""
        self.model_1_0_ep = _get_env("VIDEO_MODEL_1_0_EP", config_defaults.DEFAULT_VIDEO_MODEL_1_0_EP) or ""
        self.resolution = _get_env("VIDEO_RESOLUTION", config_defaults.DEFAULT_VIDEO_RESOLUTION) or ""
        self.ratio = _get_env("VIDEO_RATIO", config_defaults.DEFAULT_VIDEO_RATIO) or ""
        self.min_duration_1_5 = _get_float("VIDEO_MIN_DURATION_1_5", config_defaults.DEFAULT_VIDEO_MIN_DURATION_1_5)
        self.min_duration_1_0 = _get_float("VIDEO_MIN_DURATION_1_0", config_defaults.DEFAULT_VIDEO_MIN_DURATION_1_0)


@dataclass
class PhaseConfig:
    """Phase configuration."""
    phase1_thinking: str = ""
    phase1_reasoning_effort: str = ""
    storyboard_thinking: str = ""
    storyboard_reasoning_effort: str = ""
    storyboard_batch_size: int = 10
    character_prompt_thinking: str = ""
    character_prompt_reasoning_effort: str = ""
    location_prompt_thinking: str = ""
    location_prompt_reasoning_effort: str = ""
    tts_prompt_thinking: str = ""
    tts_prompt_reasoning_effort: str = ""
    fenjing_thinking: str = ""
    fenjing_reasoning_effort: str = ""

    def update_from_env(self) -> None:
        """Update configuration from environment variables."""
        self.phase1_thinking = _get_env("PHASE1_THINKING", config_defaults.DEFAULT_PHASE1_THINKING) or ""
        self.phase1_reasoning_effort = _get_env("PHASE1_REASONING_EFFORT", config_defaults.DEFAULT_PHASE1_REASONING_EFFORT) or ""
        self.storyboard_thinking = _get_env("STORYBOARD_THINKING", config_defaults.DEFAULT_STORYBOARD_THINKING) or ""
        self.storyboard_reasoning_effort = _get_env("STORYBOARD_REASONING_EFFORT", config_defaults.DEFAULT_STORYBOARD_REASONING_EFFORT) or ""
        self.storyboard_batch_size = _get_int("STORYBOARD_BATCH_SIZE", config_defaults.DEFAULT_STORYBOARD_BATCH_SIZE)
        self.character_prompt_thinking = _get_env("CHARACTER_PROMPT_THINKING", config_defaults.DEFAULT_CHARACTER_PROMPT_THINKING) or ""
        self.character_prompt_reasoning_effort = _get_env("CHARACTER_PROMPT_REASONING_EFFORT", config_defaults.DEFAULT_CHARACTER_PROMPT_REASONING_EFFORT) or ""
        self.location_prompt_thinking = _get_env("LOCATION_PROMPT_THINKING", config_defaults.DEFAULT_LOCATION_PROMPT_THINKING) or ""
        self.location_prompt_reasoning_effort = _get_env("LOCATION_PROMPT_REASONING_EFFORT", config_defaults.DEFAULT_LOCATION_PROMPT_REASONING_EFFORT) or ""
        self.tts_prompt_thinking = _get_env("TTS_PROMPT_THINKING", config_defaults.DEFAULT_TTS_PROMPT_THINKING) or ""
        self.tts_prompt_reasoning_effort = _get_env("TTS_PROMPT_REASONING_EFFORT", config_defaults.DEFAULT_TTS_PROMPT_REASONING_EFFORT) or ""
        self.fenjing_thinking = _get_env("FENJING_THINKING", config_defaults.DEFAULT_FENJING_THINKING) or ""
        self.fenjing_reasoning_effort = _get_env("FENJING_REASONING_EFFORT", config_defaults.DEFAULT_FENJING_REASONING_EFFORT) or ""


@dataclass
class QpsConfig:
    """QPS and concurrency configuration."""
    image_model_qps: float = 0.0
    image_model_concurrency: int = 1
    video_task_qps: float = 0.0
    video_audio_duration_qps: float = 0.0
    video_model_1_5_qps: float = 0.0
    video_model_1_5_concurrency: int = 1
    video_model_1_0_qps: float = 0.0
    video_model_1_0_concurrency: int = 1
    video_generate_audio: bool = True

    def update_from_env(self) -> None:
        """Update configuration from environment variables."""
        self.image_model_qps = _get_float("IMAGE_MODEL_QPS", config_defaults.DEFAULT_IMAGE_MODEL_QPS)
        self.image_model_concurrency = _get_int("IMAGE_MODEL_CONCURRENCY", config_defaults.DEFAULT_IMAGE_MODEL_CONCURRENCY)
        self.video_task_qps = _get_float("VIDEO_TASK_QPS", config_defaults.DEFAULT_VIDEO_TASK_QPS)
        self.video_audio_duration_qps = _get_float("VIDEO_AUDIO_DURATION_QPS", config_defaults.DEFAULT_VIDEO_AUDIO_DURATION_QPS)
        self.video_model_1_5_qps = _get_float("VIDEO_MODEL_1_5_QPS", config_defaults.DEFAULT_VIDEO_MODEL_1_5_QPS)
        self.video_model_1_5_concurrency = _get_int("VIDEO_MODEL_1_5_CONCURRENCY", config_defaults.DEFAULT_VIDEO_MODEL_1_5_CONCURRENCY)
        self.video_model_1_0_qps = _get_float("VIDEO_MODEL_1_0_QPS", config_defaults.DEFAULT_VIDEO_MODEL_1_0_QPS)
        self.video_model_1_0_concurrency = _get_int("VIDEO_MODEL_1_0_CONCURRENCY", config_defaults.DEFAULT_VIDEO_MODEL_1_0_CONCURRENCY)
        self.video_generate_audio = _get_bool("VIDEO_GENERATE_AUDIO", config_defaults.DEFAULT_VIDEO_GENERATE_AUDIO)


@dataclass
class ServerConfig:
    """HTTP server configuration."""
    max_threads: int = 10
    host: str = "127.0.0.1"
    port: int = 8080

    def update_from_env(self) -> None:
        """Update configuration from environment variables."""
        self.max_threads = _get_int("MANJU_WEB_MAX_THREADS", config_defaults.DEFAULT_SERVER_MAX_THREADS)
        self.host = _get_env("MANJU_WEB_HOST", config_defaults.DEFAULT_SERVER_HOST) or "127.0.0.1"
        self.port = _get_int("MANJU_WEB_PORT", config_defaults.DEFAULT_SERVER_PORT)


class RuntimeConfig:
    """Runtime configuration manager (thread-safe singleton)."""

    _instance: Optional['RuntimeConfig'] = None
    _lock: threading.Lock = threading.Lock()
    _initialized: bool = False

    def __new__(cls) -> 'RuntimeConfig':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            self._ark = ArkConfig()
            self._tos = TosConfig()
            self._tts = TtsConfig()
            self._video = VideoConfig()
            self._phase = PhaseConfig()
            self._qps = QpsConfig()
            self._server = ServerConfig()
            self._output_dir: Path = Path()
            self._project_name: str = ""
            self._instance_lock = threading.RLock()
            self._initialized = True

    @property
    def ark(self) -> ArkConfig:
        """ARK configuration."""
        return self._ark

    @property
    def tos(self) -> TosConfig:
        """TOS configuration."""
        return self._tos

    @property
    def tts(self) -> TtsConfig:
        """TTS configuration."""
        return self._tts

    @property
    def video(self) -> VideoConfig:
        """Video configuration."""
        return self._video

    @property
    def phase(self) -> PhaseConfig:
        """Phase configuration."""
        return self._phase

    @property
    def qps(self) -> QpsConfig:
        """QPS/Concurrency configuration."""
        return self._qps

    @property
    def server(self) -> ServerConfig:
        """Server configuration."""
        return self._server

    @property
    def OUTPUT_DIR(self) -> Path:
        """Output directory."""
        return self._output_dir

    @property
    def PROJECT_NAME(self) -> str:
        """Project name."""
        return self._project_name

    def load(self) -> None:
        """Load all runtime configuration."""
        with self._instance_lock:
            # Update all config sections from environment
            self._ark.update_from_env()
            self._server.update_from_env()
            self._output_dir = Path(
                _get_env("MANJU_OUTPUT_DIR", config_defaults.DEFAULT_OUTPUT_DIR) or ""
            )
            self._project_name = _get_env("PROJECT_NAME", config_defaults.DEFAULT_PROJECT_NAME) or ""
            self._tos.update_from_env(self._project_name)
            self._tts.update_from_env()
            self._video.update_from_env()
            self._phase.update_from_env()
            self._qps.update_from_env()

            # Sync auth config from storage
            self._sync_auth_config_from_storage()

    def _sync_auth_config_from_storage(self) -> None:
        """Sync auth config from storage, overriding environment defaults."""
        try:
            global_config = config_repo.load_global_auth_config()
            if not isinstance(global_config, dict):
                return

            items = global_config.get("items", {})
            if not isinstance(items, dict):
                return

            # ARK config
            if "auth.ark_base_url" in items and items["auth.ark_base_url"]:
                self._ark.base_url = str(items["auth.ark_base_url"])
            if "auth.ark_api_key" in items and items["auth.ark_api_key"]:
                self._ark.api_key = str(items["auth.ark_api_key"])
            if "auth.ark_chat_model" in items and items["auth.ark_chat_model"]:
                self._ark.chat_model = str(items["auth.ark_chat_model"])
            if "auth.ark_vlm_model" in items and items["auth.ark_vlm_model"]:
                self._ark.vlm_model = str(items["auth.ark_vlm_model"])
            if "auth.seedream_model" in items and items["auth.seedream_model"]:
                self._ark.seedream_model = str(items["auth.seedream_model"])

            # TTS config
            if "auth.tts_app_id" in items and items["auth.tts_app_id"]:
                self._tts.app_id = str(items["auth.tts_app_id"])
            if "auth.tts_access_key" in items and items["auth.tts_access_key"]:
                self._tts.access_key = str(items["auth.tts_access_key"])
            if "auth.tts_resource_id" in items and items["auth.tts_resource_id"]:
                self._tts.resource_id = str(items["auth.tts_resource_id"])
            if "auth.tts_url" in items and items["auth.tts_url"]:
                self._tts.url = str(items["auth.tts_url"])
            if "auth.tts_speaker" in items and items["auth.tts_speaker"]:
                self._tts.speaker = str(items["auth.tts_speaker"])

            # Video config
            if "auth.video_model_1_5_ep" in items and items["auth.video_model_1_5_ep"] is not None:
                self._video.model_1_5_ep = str(items["auth.video_model_1_5_ep"])
            if "auth.video_model_1_0_ep" in items and items["auth.video_model_1_0_ep"] is not None:
                self._video.model_1_0_ep = str(items["auth.video_model_1_0_ep"])

            # TOS config
            if "auth.tos_access_key" in items and items["auth.tos_access_key"]:
                self._tos.access_key = str(items["auth.tos_access_key"])
            if "auth.tos_secret_key" in items and items["auth.tos_secret_key"]:
                self._tos.secret_key = str(items["auth.tos_secret_key"])
            if "auth.tos_endpoint" in items and items["auth.tos_endpoint"]:
                self._tos.endpoint = str(items["auth.tos_endpoint"])
            if "auth.tos_region" in items and items["auth.tos_region"]:
                self._tos.region = str(items["auth.tos_region"])
            if "auth.tos_bucket" in items and items["auth.tos_bucket"]:
                self._tos.bucket = str(items["auth.tos_bucket"])

        except (ImportError, AttributeError, ValueError):
            # Keep environment variable values on failure
            pass


def get_config() -> RuntimeConfig:
    """Get the runtime configuration instance (singleton)."""
    return RuntimeConfig()


# Backward compatibility: Create global config instance
_config = get_config()
_config.load()

# Expose configuration properties for backward compatibility
ARK_BASE_URL = _config.ark.base_url
ARK_API_KEY = _config.ark.api_key
ARK_CHAT_MODEL = _config.ark.chat_model
ARK_VLM_MODEL = _config.ark.vlm_model
SEEDREAM_MODEL = _config.ark.seedream_model
ARK_TIMEOUT = _config.ark.timeout
OUTPUT_DIR = _config.OUTPUT_DIR
PROJECT_NAME = _config.PROJECT_NAME
TOS_ENDPOINT = _config.tos.endpoint
TOS_ACCESS_KEY = _config.tos.access_key
TOS_SECRET_KEY = _config.tos.secret_key
TOS_REGION = _config.tos.region
TOS_BUCKET = _config.tos.bucket
TOS_ASSETS_PREFIX = _config.tos.assets_prefix
TOS_CHARACTER_PREFIX = _config.tos.character_prefix
TOS_LOCATION_PREFIX = _config.tos.location_prefix
TOS_CLOTH_PREFIX = _config.tos.cloth_prefix
TOS_CROP_ROLE_PREFIX = _config.tos.crop_role_prefix
TOS_FENJING_PREFIX = _config.tos.fenjing_prefix
TOS_TTS_PREFIX = _config.tos.tts_prefix
TOS_VIDEO_PREFIX = _config.tos.video_prefix
