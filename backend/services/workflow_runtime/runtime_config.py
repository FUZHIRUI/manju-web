"""
runtime_config.py - 运行时配置管理模块

【模块职责】
管理工作流运行时的所有配置参数，支持从环境变量和配置存储加载

【配置来源】
1. 环境变量：优先级最高，用于容器化部署
2. 配置存储：通过config_repo从数据库加载
3. 默认值：config_defaults中定义的默认值

【配置分类】
1. ARK模型配置：API地址、密钥、模型名称、超时时间
2. TOS存储配置：对象存储的认证和路径配置
3. TTS语音配置：语音合成的认证和参数
4. 视频生成配置：视频模型的端点和参数
5. 思考模式配置：各阶段的思考预算和推理努力程度
6. QPS/并发配置：各模型的限流参数

【使用方式】
```python
from backend.services.workflow_runtime import runtime_config

# 直接使用配置项
api_key = runtime_config.ARK_API_KEY

# 重新加载配置(如配置更新后)
runtime_config.load()
```

【重要说明】
模块导入时会自动调用load()加载配置
"""

import os
from typing import Optional

from .. import config_defaults


def _get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    """从环境变量获取字符串值"""
    return os.environ.get(name, default)


def _get_int(name: str, default: int) -> int:
    """从环境变量获取整数值"""
    value = _get_env(name)
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _get_float(name: str, default: float) -> float:
    """从环境变量获取浮点数值"""
    value = _get_env(name)
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _get_bool(name: str, default: bool) -> bool:
    """从环境变量获取布尔值"""
    value = _get_env(name)
    if value is None:
        return default
    return str(value).lower() in {"1", "true", "yes", "y"}


ARK_BASE_URL: str
ARK_API_KEY: str
ARK_CHAT_MODEL: str
ARK_VLM_MODEL: str
SEEDREAM_MODEL: str
ARK_TIMEOUT: int
OUTPUT_DIR: str
PROJECT_NAME: str
TOS_ENDPOINT: str
TOS_ACCESS_KEY: str
TOS_SECRET_KEY: str
TOS_REGION: str
TOS_BUCKET: str
TOS_ASSETS_PREFIX: str
TOS_CHARACTER_PREFIX: str
TOS_LOCATION_PREFIX: str
TOS_CLOTH_PREFIX: str
TOS_CROP_ROLE_PREFIX: str
TOS_FENJING_PREFIX: str
TOS_TTS_PREFIX: str
TOS_VIDEO_PREFIX: str
PHASE1_THINKING: str
PHASE1_REASONING_EFFORT: str
STORYBOARD_THINKING: str
STORYBOARD_REASONING_EFFORT: str
STORYBOARD_BATCH_SIZE: int
CHARACTER_PROMPT_THINKING: str
CHARACTER_PROMPT_REASONING_EFFORT: str
LOCATION_PROMPT_THINKING: str
LOCATION_PROMPT_REASONING_EFFORT: str
TTS_PROMPT_THINKING: str
TTS_PROMPT_REASONING_EFFORT: str
FENJING_THINKING: str
FENJING_REASONING_EFFORT: str
FENJING_RECHECK_THINKING: str
FENJING_RECHECK_REASONING_EFFORT: str
BBOX_DETECTION_MODEL: str
BBOX_DETECTION_THINKING: str
TTS_APP_ID: str
TTS_ACCESS_KEY: str
TTS_RESOURCE_ID: str
TTS_URL: str
TTS_SPEAKER: str
TTS_TOTAL_CONCURRENCY: int
CHARACTER_HUMAN_IMAGE_SIZE: str
CHARACTER_BEAST_IMAGE_SIZE: str
VIDEO_PROMPT_THINKING: str
VIDEO_PROMPT_REASONING_EFFORT: str
VIDEO_MODEL_1_5_EP: str
VIDEO_MODEL_1_0_EP: str
VIDEO_RESOLUTION: str
VIDEO_RATIO: str
VIDEO_MIN_DURATION_1_5: float
VIDEO_MIN_DURATION_1_0: float
VIDEO_TASK_QPS: float
VIDEO_AUDIO_DURATION_QPS: float
IMAGE_MODEL_QPS: float
IMAGE_MODEL_CONCURRENCY: int
VIDEO_MODEL_1_5_QPS: float
VIDEO_MODEL_1_5_CONCURRENCY: int
VIDEO_MODEL_1_0_QPS: float
VIDEO_MODEL_1_0_CONCURRENCY: int
VIDEO_GENERATE_AUDIO: bool

# HTTP服务器配置
SERVER_MAX_THREADS: int
SERVER_HOST: str
SERVER_PORT: int


def load() -> None:
    """
    加载所有运行时配置

    【加载顺序】
    1. 从环境变量加载基础配置
    2. 计算TOS路径前缀(基于项目名称)
    3. 加载各阶段的思考模式配置
    4. 加载QPS和并发配置
    5. 从配置存储同步认证信息(覆盖环境变量)

    【重要说明】
    此函数在模块导入时自动执行，也可手动调用以重新加载配置
    """
    global ARK_BASE_URL
    global ARK_API_KEY
    global ARK_CHAT_MODEL
    global ARK_VLM_MODEL
    global SEEDREAM_MODEL
    global ARK_TIMEOUT
    global OUTPUT_DIR
    global PROJECT_NAME
    global TOS_ENDPOINT
    global TOS_ACCESS_KEY
    global TOS_SECRET_KEY
    global TOS_REGION
    global TOS_BUCKET
    global TOS_ASSETS_PREFIX
    global TOS_CHARACTER_PREFIX
    global TOS_LOCATION_PREFIX
    global TOS_CLOTH_PREFIX
    global TOS_CROP_ROLE_PREFIX
    global TOS_FENJING_PREFIX
    global TOS_TTS_PREFIX
    global TOS_VIDEO_PREFIX
    global PHASE1_THINKING
    global PHASE1_REASONING_EFFORT
    global STORYBOARD_THINKING
    global STORYBOARD_REASONING_EFFORT
    global STORYBOARD_BATCH_SIZE
    global CHARACTER_PROMPT_THINKING
    global CHARACTER_PROMPT_REASONING_EFFORT
    global LOCATION_PROMPT_THINKING
    global LOCATION_PROMPT_REASONING_EFFORT
    global TTS_PROMPT_THINKING
    global TTS_PROMPT_REASONING_EFFORT
    global FENJING_THINKING
    global FENJING_REASONING_EFFORT
    global FENJING_RECHECK_THINKING
    global FENJING_RECHECK_REASONING_EFFORT
    global BBOX_DETECTION_MODEL
    global BBOX_DETECTION_THINKING
    global TTS_APP_ID
    global TTS_ACCESS_KEY
    global TTS_RESOURCE_ID
    global TTS_URL
    global TTS_SPEAKER
    global TTS_TOTAL_CONCURRENCY
    global CHARACTER_HUMAN_IMAGE_SIZE
    global CHARACTER_BEAST_IMAGE_SIZE
    global VIDEO_PROMPT_THINKING
    global VIDEO_PROMPT_REASONING_EFFORT
    global VIDEO_MODEL_1_5_EP
    global VIDEO_MODEL_1_0_EP
    global VIDEO_RESOLUTION
    global VIDEO_RATIO
    global VIDEO_MIN_DURATION_1_5
    global VIDEO_MIN_DURATION_1_0
    global VIDEO_TASK_QPS
    global VIDEO_AUDIO_DURATION_QPS
    global IMAGE_MODEL_QPS
    global IMAGE_MODEL_CONCURRENCY
    global VIDEO_MODEL_1_5_QPS
    global VIDEO_MODEL_1_5_CONCURRENCY
    global VIDEO_MODEL_1_0_QPS
    global VIDEO_MODEL_1_0_CONCURRENCY
    global VIDEO_GENERATE_AUDIO
    global SERVER_MAX_THREADS
    global SERVER_HOST
    global SERVER_PORT
    
    # HTTP服务器配置
    SERVER_MAX_THREADS = _get_int("MANJU_WEB_MAX_THREADS", config_defaults.DEFAULT_SERVER_MAX_THREADS)
    SERVER_HOST = _get_env("MANJU_WEB_HOST", config_defaults.DEFAULT_SERVER_HOST) or "127.0.0.1"
    SERVER_PORT = _get_int("MANJU_WEB_PORT", config_defaults.DEFAULT_SERVER_PORT)
    
    #模型相关的鉴权
    ARK_BASE_URL = _get_env("ARK_BASE_URL", config_defaults.DEFAULT_ARK_BASE_URL) or ""
    ARK_API_KEY = _get_env("ARK_API_KEY", config_defaults.DEFAULT_ARK_API_KEY) or ""
    ARK_CHAT_MODEL = _get_env("ARK_CHAT_MODEL", config_defaults.DEFAULT_ARK_CHAT_MODEL) or ""
    ARK_VLM_MODEL = _get_env("ARK_VLM_MODEL", config_defaults.DEFAULT_ARK_VLM_MODEL) or ""
    SEEDREAM_MODEL = _get_env("SEEDREAM_MODEL", config_defaults.DEFAULT_SEEDREAM_MODEL) or ""
    ARK_TIMEOUT = _get_int("ARK_TIMEOUT", config_defaults.DEFAULT_ARK_TIMEOUT)

    #输出路径，使用的是相对路径，本地先会保存
    OUTPUT_DIR = _get_env("MANJU_OUTPUT_DIR", config_defaults.DEFAULT_OUTPUT_DIR) or ""
    PROJECT_NAME = _get_env("PROJECT_NAME", config_defaults.DEFAULT_PROJECT_NAME) or ""

   #tos基础配置
    TOS_ENDPOINT = _get_env("TOS_ENDPOINT", config_defaults.DEFAULT_TOS_ENDPOINT) or ""
    TOS_ACCESS_KEY = _get_env("TOS_ACCESS_KEY", config_defaults.DEFAULT_TOS_ACCESS_KEY) or ""
    TOS_SECRET_KEY = _get_env("TOS_SECRET_KEY", config_defaults.DEFAULT_TOS_SECRET_KEY) or ""
    TOS_REGION = _get_env("TOS_REGION", config_defaults.DEFAULT_TOS_REGION) or ""
    TOS_BUCKET = _get_env("TOS_BUCKET", config_defaults.DEFAULT_TOS_BUCKET) or ""

    #tos输出路径配置
    project_name = PROJECT_NAME or config_defaults.DEFAULT_TOS_PROJECT_NAME
    TOS_ASSETS_PREFIX = _get_env(
        "TOS_ASSETS_PREFIX",
        config_defaults.DEFAULT_TOS_ASSETS_PREFIX_TEMPLATE.format(project_name=project_name),
    ) or ""
    TOS_CHARACTER_PREFIX = _get_env(
        "TOS_CHARACTER_PREFIX",
        config_defaults.DEFAULT_TOS_CHARACTER_PREFIX_TEMPLATE.format(project_name=project_name),
    ) or ""
    TOS_LOCATION_PREFIX = _get_env(
        "TOS_LOCATION_PREFIX",
        config_defaults.DEFAULT_TOS_LOCATION_PREFIX_TEMPLATE.format(project_name=project_name),
    ) or ""
    TOS_CLOTH_PREFIX = _get_env(
        "TOS_CLOTH_PREFIX",
        config_defaults.DEFAULT_TOS_CLOTH_PREFIX_TEMPLATE.format(project_name=project_name),
    ) or ""
    TOS_FENJING_PREFIX = _get_env(
        "TOS_FENJING_PREFIX",
        config_defaults.DEFAULT_TOS_FENJING_PREFIX_TEMPLATE.format(project_name=project_name),
    ) or ""
    TOS_CROP_ROLE_PREFIX = _get_env(
        "TOS_CROP_ROLE_PREFIX",
        config_defaults.DEFAULT_TOS_CROP_ROLE_PREFIX_TEMPLATE.format(project_name=project_name),
    ) or ""
    TOS_TTS_PREFIX = _get_env(
        "TOS_TTS_PREFIX",
        config_defaults.DEFAULT_TOS_TTS_PREFIX_TEMPLATE.format(project_name=project_name),
    ) or ""
    TOS_VIDEO_PREFIX = _get_env(
        "TOS_VIDEO_PREFIX",
        config_defaults.DEFAULT_TOS_VIDEO_PREFIX_TEMPLATE.format(project_name=project_name),
    ) or ""

    #TTS相关
    TTS_APP_ID = _get_env("TTS_APP_ID", config_defaults.DEFAULT_TTS_APP_ID) or ""
    TTS_ACCESS_KEY = _get_env("TTS_ACCESS_KEY", config_defaults.DEFAULT_TTS_ACCESS_KEY) or ""
    TTS_RESOURCE_ID = _get_env("TTS_RESOURCE_ID", config_defaults.DEFAULT_TTS_RESOURCE_ID) or ""
    TTS_URL = _get_env("TTS_URL", config_defaults.DEFAULT_TTS_URL) or ""
    TTS_SPEAKER = _get_env("TTS_SPEAKER", config_defaults.DEFAULT_TTS_SPEAKER) or ""
    TTS_TOTAL_CONCURRENCY = _get_int("TTS_TOTAL_CONCURRENCY", config_defaults.DEFAULT_TTS_TOTAL_CONCURRENCY)

    STORYBOARD_BATCH_SIZE = _get_int("STORYBOARD_BATCH_SIZE", config_defaults.DEFAULT_STORYBOARD_BATCH_SIZE)


    PHASE1_THINKING = _get_env("PHASE1_THINKING", config_defaults.DEFAULT_PHASE1_THINKING) or ""
    PHASE1_REASONING_EFFORT = _get_env("PHASE1_REASONING_EFFORT", config_defaults.DEFAULT_PHASE1_REASONING_EFFORT) or ""
    STORYBOARD_THINKING = _get_env("STORYBOARD_THINKING", config_defaults.DEFAULT_STORYBOARD_THINKING) or ""
    STORYBOARD_REASONING_EFFORT = _get_env(
        "STORYBOARD_REASONING_EFFORT",
        config_defaults.DEFAULT_STORYBOARD_REASONING_EFFORT,
    ) or ""
    CHARACTER_PROMPT_THINKING = _get_env(
        "CHARACTER_PROMPT_THINKING",
        config_defaults.DEFAULT_CHARACTER_PROMPT_THINKING,
    ) or ""
    CHARACTER_PROMPT_REASONING_EFFORT = _get_env(
        "CHARACTER_PROMPT_REASONING_EFFORT",
        config_defaults.DEFAULT_CHARACTER_PROMPT_REASONING_EFFORT,
    ) or ""
    LOCATION_PROMPT_THINKING = _get_env(
        "LOCATION_PROMPT_THINKING",
        config_defaults.DEFAULT_LOCATION_PROMPT_THINKING,
    ) or ""
    LOCATION_PROMPT_REASONING_EFFORT = _get_env(
        "LOCATION_PROMPT_REASONING_EFFORT",
        config_defaults.DEFAULT_LOCATION_PROMPT_REASONING_EFFORT,
    ) or ""
    TTS_PROMPT_THINKING = _get_env("TTS_PROMPT_THINKING", config_defaults.DEFAULT_TTS_PROMPT_THINKING) or ""
    TTS_PROMPT_REASONING_EFFORT = _get_env(
        "TTS_PROMPT_REASONING_EFFORT",
        config_defaults.DEFAULT_TTS_PROMPT_REASONING_EFFORT,
    ) or ""
    FENJING_THINKING = _get_env("FENJING_THINKING", config_defaults.DEFAULT_FENJING_THINKING) or ""
    FENJING_REASONING_EFFORT = _get_env(
        "FENJING_REASONING_EFFORT",
        config_defaults.DEFAULT_FENJING_REASONING_EFFORT,
    ) or ""

    CHARACTER_HUMAN_IMAGE_SIZE = _get_env(
        "CHARACTER_HUMAN_IMAGE_SIZE",
        config_defaults.DEFAULT_CHARACTER_HUMAN_IMAGE_SIZE,
    ) or ""
    CHARACTER_BEAST_IMAGE_SIZE = _get_env(
        "CHARACTER_BEAST_IMAGE_SIZE",
        config_defaults.DEFAULT_CHARACTER_BEAST_IMAGE_SIZE,
    ) or ""

    VIDEO_PROMPT_THINKING = _get_env("VIDEO_PROMPT_THINKING", config_defaults.DEFAULT_VIDEO_PROMPT_THINKING) or ""
    VIDEO_PROMPT_REASONING_EFFORT = _get_env(
        "VIDEO_PROMPT_REASONING_EFFORT",
        config_defaults.DEFAULT_VIDEO_PROMPT_REASONING_EFFORT,
    ) or ""
    VIDEO_MODEL_1_5_EP = _get_env("VIDEO_MODEL_1_5_EP", config_defaults.DEFAULT_VIDEO_MODEL_1_5_EP) or ""
    VIDEO_MODEL_1_0_EP = _get_env("VIDEO_MODEL_1_0_EP", config_defaults.DEFAULT_VIDEO_MODEL_1_0_EP) or ""
    VIDEO_RESOLUTION = _get_env("VIDEO_RESOLUTION", config_defaults.DEFAULT_VIDEO_RESOLUTION) or ""
    VIDEO_RATIO = _get_env("VIDEO_RATIO", config_defaults.DEFAULT_VIDEO_RATIO) or ""
    VIDEO_MIN_DURATION_1_5 = _get_float(
        "VIDEO_MIN_DURATION_1_5",
        config_defaults.DEFAULT_VIDEO_MIN_DURATION_1_5,
    )
    VIDEO_MIN_DURATION_1_0 = _get_float(
        "VIDEO_MIN_DURATION_1_0",
        config_defaults.DEFAULT_VIDEO_MIN_DURATION_1_0,
    )

 
    IMAGE_MODEL_QPS = _get_float("IMAGE_MODEL_QPS", config_defaults.DEFAULT_IMAGE_MODEL_QPS)
    IMAGE_MODEL_CONCURRENCY = _get_int("IMAGE_MODEL_CONCURRENCY", config_defaults.DEFAULT_IMAGE_MODEL_CONCURRENCY)
    VIDEO_TASK_QPS = _get_float("VIDEO_TASK_QPS", config_defaults.DEFAULT_VIDEO_TASK_QPS)
    VIDEO_AUDIO_DURATION_QPS = _get_float(
        "VIDEO_AUDIO_DURATION_QPS",
        config_defaults.DEFAULT_VIDEO_AUDIO_DURATION_QPS,
    )
    VIDEO_MODEL_1_5_QPS = _get_float("VIDEO_MODEL_1_5_QPS", config_defaults.DEFAULT_VIDEO_MODEL_1_5_QPS)
    VIDEO_MODEL_1_5_CONCURRENCY = _get_int(
        "VIDEO_MODEL_1_5_CONCURRENCY",
        config_defaults.DEFAULT_VIDEO_MODEL_1_5_CONCURRENCY,
    )
    VIDEO_MODEL_1_0_QPS = _get_float("VIDEO_MODEL_1_0_QPS", config_defaults.DEFAULT_VIDEO_MODEL_1_0_QPS)
    VIDEO_MODEL_1_0_CONCURRENCY = _get_int(
        "VIDEO_MODEL_1_0_CONCURRENCY",
        config_defaults.DEFAULT_VIDEO_MODEL_1_0_CONCURRENCY,
    )
    VIDEO_GENERATE_AUDIO = _get_bool("VIDEO_GENERATE_AUDIO", config_defaults.DEFAULT_VIDEO_GENERATE_AUDIO)

    # 从配置存储同步所有鉴权配置（覆盖环境变量默认值）
    _sync_auth_config_from_storage()


def _sync_auth_config_from_storage() -> None:
    """
    从全局配置存储同步所有鉴权配置到运行时

    【功能说明】
    从数据库配置存储中加载认证信息，覆盖环境变量的默认值
    用于在Web界面中配置API密钥后同步到运行时

    【配置映射表】
    - ARK: ark_base_url, ark_api_key, ark_chat_model, ark_vlm_model, seedream_model
    - TTS: tts_app_id, tts_access_key, tts_resource_id, tts_url, tts_speaker
    - Video: video_model_1_5_ep, video_model_1_0_ep
    - TOS: tos_access_key, tos_secret_key, tos_endpoint, tos_region, tos_bucket

    【异常处理】
    配置存储读取失败时保持环境变量值，不抛出异常
    """
    try:
        # 延迟导入避免循环依赖
        from ...repositories import config_repo
        
        global_config = config_repo.load_global_auth_config()
        if not isinstance(global_config, dict):
            return
            
        items = global_config.get("items", {})
        if not isinstance(items, dict):
            return
            
        # 声明所有全局变量
        global ARK_BASE_URL, ARK_API_KEY, ARK_CHAT_MODEL, ARK_VLM_MODEL, SEEDREAM_MODEL
        global TTS_APP_ID, TTS_ACCESS_KEY, TTS_RESOURCE_ID, TTS_URL, TTS_SPEAKER
        global VIDEO_MODEL_1_5_EP, VIDEO_MODEL_1_0_EP
        global TOS_ACCESS_KEY, TOS_SECRET_KEY, TOS_ENDPOINT, TOS_REGION, TOS_BUCKET
        
        # ARK 配置
        if "auth.ark_base_url" in items and items["auth.ark_base_url"]:
            ARK_BASE_URL = str(items["auth.ark_base_url"])
        if "auth.ark_api_key" in items and items["auth.ark_api_key"]:
            ARK_API_KEY = str(items["auth.ark_api_key"])
        if "auth.ark_chat_model" in items and items["auth.ark_chat_model"]:
            ARK_CHAT_MODEL = str(items["auth.ark_chat_model"])
        if "auth.ark_vlm_model" in items and items["auth.ark_vlm_model"]:
            ARK_VLM_MODEL = str(items["auth.ark_vlm_model"])
        if "auth.seedream_model" in items and items["auth.seedream_model"]:
            SEEDREAM_MODEL = str(items["auth.seedream_model"])
        
        # TTS 配置
        if "auth.tts_app_id" in items and items["auth.tts_app_id"]:
            TTS_APP_ID = str(items["auth.tts_app_id"])
        if "auth.tts_access_key" in items and items["auth.tts_access_key"]:
            TTS_ACCESS_KEY = str(items["auth.tts_access_key"])
        if "auth.tts_resource_id" in items and items["auth.tts_resource_id"]:
            TTS_RESOURCE_ID = str(items["auth.tts_resource_id"])
        if "auth.tts_url" in items and items["auth.tts_url"]:
            TTS_URL = str(items["auth.tts_url"])
        if "auth.tts_speaker" in items and items["auth.tts_speaker"]:
            TTS_SPEAKER = str(items["auth.tts_speaker"])
        
        # 视频模型配置
        if "auth.video_model_1_5_ep" in items and items["auth.video_model_1_5_ep"] is not None:
            VIDEO_MODEL_1_5_EP = str(items["auth.video_model_1_5_ep"])
        if "auth.video_model_1_0_ep" in items and items["auth.video_model_1_0_ep"] is not None:
            VIDEO_MODEL_1_0_EP = str(items["auth.video_model_1_0_ep"])
        
        # TOS 配置
        if "auth.tos_access_key" in items and items["auth.tos_access_key"]:
            TOS_ACCESS_KEY = str(items["auth.tos_access_key"])
        if "auth.tos_secret_key" in items and items["auth.tos_secret_key"]:
            TOS_SECRET_KEY = str(items["auth.tos_secret_key"])
        if "auth.tos_endpoint" in items and items["auth.tos_endpoint"]:
            TOS_ENDPOINT = str(items["auth.tos_endpoint"])
        if "auth.tos_region" in items and items["auth.tos_region"]:
            TOS_REGION = str(items["auth.tos_region"])
        if "auth.tos_bucket" in items and items["auth.tos_bucket"]:
            TOS_BUCKET = str(items["auth.tos_bucket"])

    except (ImportError, AttributeError, ValueError):
        # 配置存储读取失败时保持环境变量值
        pass


def get_project_prefixes(project_name: str) -> dict:
    """
    获取项目特定的TOS前缀配置（线程安全）
    
    【参数】
    - project_name: 项目名称
    
    【返回值】
    - 包含所有TOS前缀的字典
    
    【说明】
    此函数不依赖全局变量，可以安全地在多线程环境中使用
    """
    return {
        "TOS_ASSETS_PREFIX": config_defaults.DEFAULT_TOS_ASSETS_PREFIX_TEMPLATE.format(project_name=project_name),
        "TOS_CHARACTER_PREFIX": config_defaults.DEFAULT_TOS_CHARACTER_PREFIX_TEMPLATE.format(project_name=project_name),
        "TOS_LOCATION_PREFIX": config_defaults.DEFAULT_TOS_LOCATION_PREFIX_TEMPLATE.format(project_name=project_name),
        "TOS_CLOTH_PREFIX": config_defaults.DEFAULT_TOS_CLOTH_PREFIX_TEMPLATE.format(project_name=project_name),
        "TOS_CROP_ROLE_PREFIX": config_defaults.DEFAULT_TOS_CROP_ROLE_PREFIX_TEMPLATE.format(project_name=project_name),
        "TOS_FENJING_PREFIX": config_defaults.DEFAULT_TOS_FENJING_PREFIX_TEMPLATE.format(project_name=project_name),
        "TOS_TTS_PREFIX": config_defaults.DEFAULT_TOS_TTS_PREFIX_TEMPLATE.format(project_name=project_name),
        "TOS_VIDEO_PREFIX": config_defaults.DEFAULT_TOS_VIDEO_PREFIX_TEMPLATE.format(project_name=project_name),
    }


load()
