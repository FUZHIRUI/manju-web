import os
from typing import Any, Callable, Dict, List, Optional

from ..repositories import config_repo
from . import config_defaults
from . import throttle_service
from .workflow_runtime import retry_runtime, runtime_config

DEFAULT_STORYBOARD_BATCH_SIZE = int(config_defaults.DEFAULT_STORYBOARD_BATCH_SIZE)
DEFAULT_TTS_TOTAL_CONCURRENCY = int(config_defaults.DEFAULT_TTS_TOTAL_CONCURRENCY)
DEFAULT_VIDEO_TASK_QPS = float(config_defaults.DEFAULT_VIDEO_TASK_QPS)
DEFAULT_VIDEO_AUDIO_DURATION_QPS = float(config_defaults.DEFAULT_VIDEO_AUDIO_DURATION_QPS)
DEFAULT_IMAGE_MODEL_QPS = float(config_defaults.DEFAULT_IMAGE_MODEL_QPS)
DEFAULT_IMAGE_MODEL_CONCURRENCY = int(config_defaults.DEFAULT_IMAGE_MODEL_CONCURRENCY)
DEFAULT_ARK_MODEL_QPS = float(config_defaults.DEFAULT_ARK_MODEL_QPS)
DEFAULT_ARK_MODEL_CONCURRENCY = int(config_defaults.DEFAULT_ARK_MODEL_CONCURRENCY)
DEFAULT_VIDEO_MODEL_1_5_QPS = float(config_defaults.DEFAULT_VIDEO_MODEL_1_5_QPS)
DEFAULT_VIDEO_MODEL_1_5_CONCURRENCY = int(config_defaults.DEFAULT_VIDEO_MODEL_1_5_CONCURRENCY)
DEFAULT_VIDEO_MODEL_1_0_QPS = float(config_defaults.DEFAULT_VIDEO_MODEL_1_0_QPS)
DEFAULT_VIDEO_MODEL_1_0_CONCURRENCY = int(config_defaults.DEFAULT_VIDEO_MODEL_1_0_CONCURRENCY)


def _float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except Exception:
        return None


def _int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except Exception:
        return None


def _config_definitions() -> List[Dict[str, Any]]:
    return [
        {
            "id": "auto_storyboard.stage_concurrency",
            "stage": "auto_storyboard",
            "key": "stage_concurrency",
            "type": "int",
            "default": 0,
            "min": 0,
            "max": 10,
            "scope": "global",
            "description": "自动分镜流程全局共享并发上限（所有项目总和，0表示不限制）",
            "enforce_global": True,
        },
        {
            "id": "auto_storyboard.batch_size",
            "stage": "auto_storyboard",
            "key": "batch_size",
            "type": "int",
            "env": "STORYBOARD_BATCH_SIZE",
            "default": int(DEFAULT_STORYBOARD_BATCH_SIZE),
            "min": 1,
            "scope": "global",
            "description": "单次生成章节的数量",
            "enforce_global": False,
        },
        {
            "id": "visual_audio_assets.stage_concurrency",
            "stage": "visual_audio_assets",
            "key": "stage_concurrency",
            "type": "int",
            "default": 0,
            "min": 0,
            "max": 10,
            "scope": "global",
            "description": "视觉与音频资产流程全局共享并发上限（所有项目总和，0表示不限制）",
            "enforce_global": True,
        },
        {
            "id": "visual_audio_assets.tts_total_concurrency",
            "stage": "visual_audio_assets",
            "key": "tts_total_concurrency",
            "type": "int",
            "env": "TTS_TOTAL_CONCURRENCY",
            "default": int(DEFAULT_TTS_TOTAL_CONCURRENCY),
            "min": 1,
            "max": 10,
            "scope": "global",
            "description": "TTS生成全局并发上限",
            "enforce_global": True,
        },
        {
            "id": "fenjing.stage_concurrency",
            "stage": "fenjing",
            "key": "stage_concurrency",
            "type": "int",
            "default": 0,
            "min": 0,
            "max": 20,
            "scope": "global",
            "description": "分镜细化流程全局共享并发上限（所有项目总和，0表示不限制）",
            "enforce_global": True,
        },
        {
            "id": "video.stage_concurrency",
            "stage": "video",
            "key": "stage_concurrency",
            "type": "int",
            "default": 0,
            "min": 0,
            "max": 10,
            "scope": "global",
            "description": "视频生成流程全局共享并发上限（所有项目总和，0表示不限制）",
            "enforce_global": True,
        },
        {
            "id": "video.video_task_qps",
            "stage": "video",
            "key": "video_task_qps",
            "type": "float",
            "env": "VIDEO_TASK_QPS",
            "default": float(DEFAULT_VIDEO_TASK_QPS),
            "min": 0,
            "max": 20,
            "scope": "global",
            "description": "视频生成任务创建QPS",
            "enforce_global": True,
        },
        {
            "id": "video.audio_duration_qps",
            "stage": "video",
            "key": "audio_duration_qps",
            "type": "float",
            "env": "VIDEO_AUDIO_DURATION_QPS",
            "default": float(DEFAULT_VIDEO_AUDIO_DURATION_QPS),
            "min": 0,
            "max": 20,
            "scope": "global",
            "description": "音频时长解析QPS",
            "enforce_global": True,
        },
        # 关系说明：同一 model_key 的 QPS 与并发成对出现，合并后用于模型级限流；
        # 同时 env 指向统一的环境变量，作为默认值与运行时覆盖来源。
        {
            "id": "model.image.seedream_4_5_qps",
            "stage": "model.image",
            "key": "seedream_4_5_qps",
            "model_key": "seedream_4_5",
            "type": "float",
            "env": "IMAGE_MODEL_QPS",
            "default": float(DEFAULT_IMAGE_MODEL_QPS),
            "min": 0,
            "max": 10,
            "scope": "global",
            "description": "生图模型QPS上限",
            "enforce_global": True,
        },
        {
            "id": "model.image.seedream_4_5_concurrency",
            "stage": "model.image",
            "key": "seedream_4_5_concurrency",
            "model_key": "seedream_4_5",
            "type": "int",
            "env": "IMAGE_MODEL_CONCURRENCY",
            "default": int(DEFAULT_IMAGE_MODEL_CONCURRENCY),
            "min": 0,
            "max": 100,
            "scope": "global",
            "description": "生图模型并发上限",
            "enforce_global": True,
        },
        {
            "id": "model.ark.ark_qps",
            "stage": "model.ark",
            "key": "ark_qps",
            "model_key": "ark",
            "type": "float",
            "env": "ARK_MODEL_QPS",
            "default": float(DEFAULT_ARK_MODEL_QPS),
            "min": 0,
            "max": 20,
            "scope": "global",
            "description": "LLM/VLM统一模型QPS上限",
            "enforce_global": True,
        },
        {
            "id": "model.ark.ark_concurrency",
            "stage": "model.ark",
            "key": "ark_concurrency",
            "model_key": "ark",
            "type": "int",
            "env": "ARK_MODEL_CONCURRENCY",
            "default": int(DEFAULT_ARK_MODEL_CONCURRENCY),
            "min": 0,
            "max": 100,
            "scope": "global",
            "description": "LLM/VLM统一模型并发上限",
            "enforce_global": True,
        },
        {
            "id": "model.video.video_1_5_qps",
            "stage": "model.video",
            "key": "video_1_5_qps",
            "model_key": "video_1_5",
            "type": "float",
            "env": "VIDEO_MODEL_1_5_QPS",
            "default": float(DEFAULT_VIDEO_MODEL_1_5_QPS),
            "min": 0,
            "max": 10,
            "scope": "global",
            "description": "生视频模型1.5 QPS上限",
            "enforce_global": True,
        },
        {
            "id": "model.video.video_1_5_concurrency",
            "stage": "model.video",
            "key": "video_1_5_concurrency",
            "model_key": "video_1_5",
            "type": "int",
            "env": "VIDEO_MODEL_1_5_CONCURRENCY",
            "default": int(DEFAULT_VIDEO_MODEL_1_5_CONCURRENCY),
            "min": 0,
            "max": 10,
            "scope": "global",
            "description": "生视频模型1.5 并发上限",
            "enforce_global": True,
        },
        {
            "id": "model.video.video_1_0_qps",
            "stage": "model.video",
            "key": "video_1_0_qps",
            "model_key": "video_1_0",
            "type": "float",
            "env": "VIDEO_MODEL_1_0_QPS",
            "default": float(DEFAULT_VIDEO_MODEL_1_0_QPS),
            "min": 0,
            "max": 10,
            "scope": "global",
            "description": "生视频模型1.0 QPS上限",
            "enforce_global": True,
        },
        {
            "id": "model.video.video_1_0_concurrency",
            "stage": "model.video",
            "key": "video_1_0_concurrency",
            "model_key": "video_1_0",
            "type": "int",
            "env": "VIDEO_MODEL_1_0_CONCURRENCY",
            "default": int(DEFAULT_VIDEO_MODEL_1_0_CONCURRENCY),
            "min": 0,
            "max": 10,
            "scope": "global",
            "description": "生视频模型1.0 并发上限",
            "enforce_global": True,
        },
    ]


def _sync_default_storage(
    definitions: List[Dict[str, Any]],
    current: Dict[str, Any],
    save_func: Callable[[Dict[str, Any]], None],
) -> Dict[str, Any]:
    data = current if isinstance(current, dict) else {}
    defaults = data.get("defaults")
    if not isinstance(defaults, dict):
        defaults = {}
    next_defaults = dict(defaults)
    updated = False
    for item in definitions:
        item_id = item["id"]
        if item_id in next_defaults:
            continue
        next_defaults[item_id] = item["default"]
        updated = True
    if updated:
        payload = dict(data)
        payload["defaults"] = next_defaults
        if "items" in payload and not isinstance(payload.get("items"), dict):
            payload["items"] = {}
        save_func(payload)
    return next_defaults


def list_config_items() -> List[Dict[str, Any]]:
    items = _config_definitions()
    default_map = _sync_default_storage(
        items,
        config_repo.load_global_config(),
        config_repo.save_global_config,
    )
    for item in items:
        item_id = item["id"]
        if item_id not in default_map:
            continue
        merged = _apply_value(item, default_map.get(item_id))
        if merged is None:
            continue
        item["default"] = merged
    for item in items:
        item["source"] = "default"
        item["value"] = item["default"]
    return items


def _auth_definitions() -> List[Dict[str, Any]]:
    return [
        {
            "id": "auth.ark_base_url",
            "stage": "ark",
            "key": "ark_base_url",
            "type": "string",
            "env": "ARK_BASE_URL",
            "default": config_defaults.DEFAULT_ARK_BASE_URL,
            "scope": "global",
            "description": "ARK服务地址",
            "sensitive": False,
        },
        {
            "id": "auth.ark_api_key",
            "stage": "ark",
            "key": "ark_api_key",
            "type": "string",
            "env": "ARK_API_KEY",
            "default": config_defaults.DEFAULT_ARK_API_KEY,
            "scope": "global",
            "description": "ARK鉴权API Key",
            "sensitive": True,
        },
        {
            "id": "auth.ark_chat_model",
            "stage": "ark",
            "key": "ark_chat_model",
            "type": "string",
            "env": "ARK_CHAT_MODEL",
            "default": config_defaults.DEFAULT_ARK_CHAT_MODEL,
            "scope": "global",
            "description": "ARK对话模型",
            "sensitive": False,
        },
        {
            "id": "auth.ark_vlm_model",
            "stage": "ark",
            "key": "ark_vlm_model",
            "type": "string",
            "env": "ARK_VLM_MODEL",
            "default": config_defaults.DEFAULT_ARK_VLM_MODEL,
            "scope": "global",
            "description": "ARK多模态模型",
            "sensitive": False,
        },
        {
            "id": "auth.seedream_model",
            "stage": "ark",
            "key": "seedream_model",
            "type": "string",
            "env": "SEEDREAM_MODEL",
            "default": config_defaults.DEFAULT_SEEDREAM_MODEL,
            "scope": "global",
            "description": "Seedream模型",
            "sensitive": False,
        },
        {
            "id": "auth.ark_timeout",
            "stage": "ark",
            "key": "ark_timeout",
            "type": "string",
            "env": "ARK_TIMEOUT",
            "default": config_defaults.DEFAULT_ARK_TIMEOUT,
            "scope": "global",
            "description": "ARK请求超时(秒)",
            "sensitive": False,
        },
        {
            "id": "auth.tos_endpoint",
            "stage": "tos",
            "key": "tos_endpoint",
            "type": "string",
            "env": "TOS_ENDPOINT",
            "default": config_defaults.DEFAULT_TOS_ENDPOINT,
            "scope": "global",
            "description": "TOS服务地址",
            "sensitive": False,
        },
        {
            "id": "auth.tos_access_key",
            "stage": "tos",
            "key": "tos_access_key",
            "type": "string",
            "env": "TOS_ACCESS_KEY",
            "default": config_defaults.DEFAULT_TOS_ACCESS_KEY,
            "scope": "global",
            "description": "TOS鉴权AccessKey",
            "sensitive": True,
        },
        {
            "id": "auth.tos_secret_key",
            "stage": "tos",
            "key": "tos_secret_key",
            "type": "string",
            "env": "TOS_SECRET_KEY",
            "default": config_defaults.DEFAULT_TOS_SECRET_KEY,
            "scope": "global",
            "description": "TOS鉴权SecretKey",
            "sensitive": True,
        },
        {
            "id": "auth.tos_region",
            "stage": "tos",
            "key": "tos_region",
            "type": "string",
            "env": "TOS_REGION",
            "default": config_defaults.DEFAULT_TOS_REGION,
            "scope": "global",
            "description": "TOS区域",
            "sensitive": False,
        },
        {
            "id": "auth.tos_bucket",
            "stage": "tos",
            "key": "tos_bucket",
            "type": "string",
            "env": "TOS_BUCKET",
            "default": config_defaults.DEFAULT_TOS_BUCKET,
            "scope": "global",
            "description": "TOS桶名",
            "sensitive": False,
        },
        {
            "id": "auth.tts_app_id",
            "stage": "tts",
            "key": "tts_app_id",
            "type": "string",
            "env": "TTS_APP_ID",
            "default": config_defaults.DEFAULT_TTS_APP_ID,
            "scope": "global",
            "description": "TTS鉴权AppId",
            "sensitive": False,
        },
        {
            "id": "auth.tts_access_key",
            "stage": "tts",
            "key": "tts_access_key",
            "type": "string",
            "env": "TTS_ACCESS_KEY",
            "default": config_defaults.DEFAULT_TTS_ACCESS_KEY,
            "scope": "global",
            "description": "TTS鉴权AccessKey",
            "sensitive": True,
        },
        {
            "id": "auth.tts_resource_id",
            "stage": "tts",
            "key": "tts_resource_id",
            "type": "string",
            "env": "TTS_RESOURCE_ID",
            "default": config_defaults.DEFAULT_TTS_RESOURCE_ID,
            "scope": "global",
            "description": "TTS鉴权ResourceId",
            "sensitive": False,
        },
        {
            "id": "auth.tts_url",
            "stage": "tts",
            "key": "tts_url",
            "type": "string",
            "env": "TTS_URL",
            "default": config_defaults.DEFAULT_TTS_URL,
            "scope": "global",
            "description": "TTS服务地址",
            "sensitive": False,
        },
        {
            "id": "auth.tts_speaker",
            "stage": "tts",
            "key": "tts_speaker",
            "type": "string",
            "env": "TTS_SPEAKER",
            "default": config_defaults.DEFAULT_TTS_SPEAKER,
            "scope": "global",
            "description": "TTS默认发音人",
            "sensitive": False,
        },
        {
            "id": "auth.video_model_1_5_ep",
            "stage": "video",
            "key": "video_model_1_5_ep",
            "type": "string",
            "env": "VIDEO_MODEL_1_5_EP",
            "default": config_defaults.DEFAULT_VIDEO_MODEL_1_5_EP,
            "scope": "global",
            "description": "视频生成模型1.5端点ID (如: ep-20250101-xxxxx)",
            "sensitive": False,
        },
        {
            "id": "auth.video_model_1_0_ep",
            "stage": "video",
            "key": "video_model_1_0_ep",
            "type": "string",
            "env": "VIDEO_MODEL_1_0_EP",
            "default": config_defaults.DEFAULT_VIDEO_MODEL_1_0_EP,
            "scope": "global",
            "description": "视频生成模型1.0端点ID (如: ep-20250101-xxxxx)",
            "sensitive": False,
        },
    ]


def list_auth_items() -> List[Dict[str, Any]]:
    items = _auth_definitions()
    default_map = _sync_default_storage(
        items,
        config_repo.load_global_auth_config(),
        config_repo.save_global_auth_config,
    )
    for item in items:
        item_id = item["id"]
        if item_id not in default_map:
            continue
        merged = _apply_auth_value(item, default_map.get(item_id))
        if merged is None:
            continue
        item["default"] = merged
    for item in items:
        item["source"] = "default"
        item["value"] = item["default"]
    return items


def _apply_auth_value(item: Dict[str, Any], value: Any) -> Optional[Any]:
    if value is None:
        return None
    if item["type"] == "string":
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()
    return None


def _merge_auth_overrides(base: List[Dict[str, Any]], overrides: Dict[str, Any], source: str) -> None:
    if not overrides:
        return
    override_items = overrides.get("items") if isinstance(overrides, dict) else overrides
    if not isinstance(override_items, dict):
        return
    for item in base:
        item_id = item["id"]
        if item_id not in override_items:
            continue
        merged = _apply_auth_value(item, override_items.get(item_id))
        if merged is None:
            continue
        item["value"] = merged
        item["source"] = source


def _merge_auth_runtime_env(base: List[Dict[str, Any]]) -> None:
    for item in base:
        env = item.get("env")
        if not env:
            continue
        if env not in os.environ:
            continue
        merged = _apply_auth_value(item, os.environ.get(env))
        if merged is None:
            continue
        item["value"] = merged
        item["source"] = "runtime"


def get_effective_auth_config(project: str) -> List[Dict[str, Any]]:
    items = list_auth_items()
    global_overrides = config_repo.load_global_auth_config()
    _merge_auth_overrides(items, global_overrides, "global")
    project_overrides = config_repo.load_project_auth_config(project)
    _merge_auth_overrides(items, project_overrides, "project")
    # 配置直接从 JSON 文件加载，不受环境变量影响
    return items


def _mask_auth_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    masked_items: List[Dict[str, Any]] = []
    for item in items:
        next_item = dict(item)
        if next_item.get("sensitive") and next_item.get("value"):
            next_item["stored"] = True
            next_item["value"] = ""
        else:
            next_item["stored"] = bool(next_item.get("value"))
        masked_items.append(next_item)
    return masked_items


def _apply_value(item: Dict[str, Any], value: Any) -> Optional[Any]:
    if item["type"] == "int":
        parsed = _int(value)
    else:
        parsed = _float(value)
    if parsed is None:
        return None
    min_val = item.get("min")
    max_val = item.get("max")
    if min_val is not None and parsed < min_val:
        parsed = min_val
    if max_val is not None and parsed > max_val:
        parsed = max_val
    return parsed


def _merge_overrides(base: List[Dict[str, Any]], overrides: Dict[str, Any], source: str) -> None:
    if not overrides:
        return
    override_items = overrides.get("items") or overrides
    if not isinstance(override_items, dict):
        return
    for item in base:
        item_id = item["id"]
        if item_id not in override_items:
            continue
        merged = _apply_value(item, override_items.get(item_id))
        if merged is None:
            continue
        item["value"] = merged
        item["source"] = source


def _merge_runtime_env(base: List[Dict[str, Any]]) -> None:
    for item in base:
        env = item.get("env")
        if not env:
            continue
        if env not in os.environ:
            continue
        merged = _apply_value(item, os.environ.get(env))
        if merged is None:
            continue
        item["value"] = merged
        item["source"] = "runtime"


def _validate_project_limits(global_items: Dict[str, Dict[str, Any]], project_items: List[Dict[str, Any]]) -> Optional[str]:
    for item in project_items:
        if not item.get("enforce_global"):
            continue
        global_item = global_items.get(item["id"])
        if not global_item:
            continue
        global_value = global_item.get("value")
        if global_value is None:
            continue
        if item["value"] > global_value and global_value > 0:
            return item["id"]
    return None


def _get_effective_global_config() -> List[Dict[str, Any]]:
    items = list_config_items()
    global_overrides = config_repo.load_global_config()
    _merge_overrides(items, global_overrides, "global")
    _merge_runtime_env(items)
    return items


def get_effective_config(project: str) -> List[Dict[str, Any]]:
    items = list_config_items()
    global_overrides = config_repo.load_global_config()
    _merge_overrides(items, global_overrides, "global")
    project_overrides = config_repo.load_project_config(project)
    model_ids = {item["id"] for item in items if item.get("model_key")}
    stage_ids = {item["id"] for item in items if item.get("key") == "stage_concurrency"}
    if isinstance(project_overrides, dict) and isinstance(project_overrides.get("items"), dict):
        filtered = {
            k: v
            for k, v in project_overrides["items"].items()
            if k not in model_ids and k not in stage_ids
        }
        project_overrides = {**project_overrides, "items": filtered}
    _merge_overrides(items, project_overrides, "project")
    _merge_runtime_env(items)
    global_map = {item["id"]: item for item in list_config_items()}
    _merge_overrides(list(global_map.values()), global_overrides, "global")
    invalid_id = _validate_project_limits(global_map, items)
    if invalid_id:
        raise ValueError(f"project_override_exceeds_global:{invalid_id}")
    return items


def apply_runtime(project: str) -> List[Dict[str, Any]]:
    items = get_effective_config(project)
    global_items = _get_effective_global_config()
    auth_items = get_effective_auth_config(project)
    for item in items:
        env = item.get("env")
        if env and not item.get("model_key"):
            os.environ[env] = str(item["value"])
    for item in global_items:
        env = item.get("env")
        if env and item.get("model_key"):
            os.environ[env] = str(item["value"])
    for item in auth_items:
        env = item.get("env")
        if env:
            os.environ[env] = str(item["value"])
    runtime_config.load()
    model_limits: Dict[str, Dict[str, float]] = {}
    stage_limits: Dict[str, Dict[str, float]] = {}
    for item in global_items:
        model_key = item.get("model_key")
        if model_key:
            if item["key"].endswith("_qps"):
                model_limits.setdefault(model_key, {})["qps"] = float(item["value"])
            elif item["key"].endswith("_concurrency"):
                model_limits.setdefault(model_key, {})["concurrency"] = float(item["value"])
    for item in global_items:
        if item["key"] == "stage_concurrency":
            stage_limits.setdefault(item["stage"], {})["concurrency"] = float(item["value"])
    throttle_service.configure_model_limiters(model_limits)
    throttle_service.configure_stage_limiters(stage_limits)
    return items


def apply_auth_runtime(project: str) -> List[Dict[str, Any]]:
    items = get_effective_auth_config(project)
    # 配置直接通过 _sync_updates_to_runtime() 同步到 runtime_config
    # 不再经过环境变量中转
    runtime_config.load()
    return items


def update_config(project: str, scope: str, updates: Dict[str, Any]) -> List[Dict[str, Any]]:
    allowed = {item["id"] for item in list_config_items()}
    invalid = [key for key in updates.keys() if key not in allowed]
    if invalid:
        raise ValueError(f"invalid_config_items:{','.join(invalid)}")
    items = list_config_items()
    item_map = {item["id"]: item for item in items}
    model_ids = {item["id"] for item in items if item.get("model_key")}
    stage_ids = {item["id"] for item in items if item.get("key") == "stage_concurrency"}
    if scope == "project":
        blocked = [key for key in updates.keys() if key in model_ids]
        if blocked:
            raise ValueError(f"model_limits_global:{','.join(blocked)}")
        stage_blocked = [key for key in updates.keys() if key in stage_ids]
        if stage_blocked:
            raise ValueError(f"stage_limits_global:{','.join(stage_blocked)}")
    if scope == "project":
        current = config_repo.load_project_config(project)
        data = current.get("items") if isinstance(current, dict) else {}
        if not isinstance(data, dict):
            data = {}
        for key, value in updates.items():
            if value is None:
                data.pop(key, None)
            else:
                data[key] = value
        config_repo.save_project_config(project, {"items": data})
    else:
        current = config_repo.load_global_config()
        data = current.get("items") if isinstance(current, dict) else {}
        defaults = current.get("defaults") if isinstance(current, dict) else {}
        if not isinstance(data, dict):
            data = {}
        if not isinstance(defaults, dict):
            defaults = {}
        for key, value in updates.items():
            if value is None:
                data.pop(key, None)
            else:
                data[key] = value
        config_repo.save_global_config({"items": data, "defaults": defaults})
    for key in updates.keys():
        item = item_map.get(key)
        if not item:
            continue
        env = item.get("env")
        if not env:
            continue
        os.environ.pop(env, None)
    return apply_runtime(project)


def _sync_updates_to_runtime(updates: Dict[str, Any]) -> None:
    """同步配置更新到运行时配置
    
    支持所有鉴权配置的实时同步，无需重启服务
    """
    # 配置映射表：配置ID -> runtime_config 变量名
    config_mapping = {
        # ARK 配置
        "auth.ark_base_url": "ARK_BASE_URL",
        "auth.ark_api_key": "ARK_API_KEY",
        "auth.ark_chat_model": "ARK_CHAT_MODEL",
        "auth.ark_vlm_model": "ARK_VLM_MODEL",
        "auth.seedream_model": "SEEDREAM_MODEL",
        # TTS 配置
        "auth.tts_app_id": "TTS_APP_ID",
        "auth.tts_access_key": "TTS_ACCESS_KEY",
        "auth.tts_resource_id": "TTS_RESOURCE_ID",
        "auth.tts_url": "TTS_URL",
        "auth.tts_speaker": "TTS_SPEAKER",
        # 视频模型配置
        "auth.video_model_1_5_ep": "VIDEO_MODEL_1_5_EP",
        "auth.video_model_1_0_ep": "VIDEO_MODEL_1_0_EP",
        # TOS 配置
        "auth.tos_access_key": "TOS_ACCESS_KEY",
        "auth.tos_secret_key": "TOS_SECRET_KEY",
        "auth.tos_endpoint": "TOS_ENDPOINT",
        "auth.tos_region": "TOS_REGION",
        "auth.tos_bucket": "TOS_BUCKET",
    }
    
    for key, value in updates.items():
        if key in config_mapping:
            runtime_var = config_mapping[key]
            # 处理 None 值（重置操作）
            safe_value = value if value is not None else ""
            setattr(runtime_config, runtime_var, str(safe_value))


def update_auth_config(project: str, scope: str, updates: Dict[str, Any]) -> List[Dict[str, Any]]:
    allowed = {item["id"] for item in list_auth_items()}
    invalid = [key for key in updates.keys() if key not in allowed]
    if invalid:
        raise ValueError(f"invalid_auth_items:{','.join(invalid)}")
    definitions = {item["id"]: item for item in list_auth_items()}
    if scope == "project":
        current = config_repo.load_project_auth_config(project)
        data = current.get("items") if isinstance(current, dict) else {}
        if not isinstance(data, dict):
            data = {}
        for key, value in updates.items():
            if value is None:
                data.pop(key, None)
                continue
            merged = _apply_auth_value(definitions[key], value)
            if merged is None:
                continue
            data[key] = merged
        config_repo.save_project_auth_config(project, {"items": data})
    else:
        current = config_repo.load_global_auth_config()
        data = current.get("items") if isinstance(current, dict) else {}
        defaults = current.get("defaults") if isinstance(current, dict) else {}
        if not isinstance(data, dict):
            data = {}
        if not isinstance(defaults, dict):
            defaults = {}
        for key, value in updates.items():
            if value is None:
                data.pop(key, None)
                continue
            merged = _apply_auth_value(definitions[key], value)
            if merged is None:
                continue
            data[key] = merged
        config_repo.save_global_auth_config({"items": data, "defaults": defaults})
    
    # 同步配置更新到运行时（实时生效，无需重启服务）
    _sync_updates_to_runtime(updates)
    
    items = apply_auth_runtime(project)
    return _mask_auth_items(items)


def get_auth_config(project: str) -> List[Dict[str, Any]]:
    return _mask_auth_items(get_effective_auth_config(project))


def get_retry_config() -> Dict[str, Any]:
    return retry_runtime.load_retry_config()


def update_retry_config(config: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(config, dict):
        raise ValueError("invalid_retry_config")
    config_repo.save_global_retry_config(config)
    return retry_runtime.load_retry_config()
