"""
资产统计配置模块。

通过配置驱动的方式定义各资产类型的统计规则，
支持灵活启用/禁用特定类型，便于后续节点调整。
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class AssetTypeConfig:
    """
    单个资产类型的统计配置。

    Attributes:
        type_id: 类型唯一标识符，用于API和前端交互
        label: 显示标签（中文）
        enabled: 是否启用统计
        has_chapter: 是否按章节维度统计
        priority: 显示优先级（数值越小越靠前）
        source_type: 数据来源类型: "details" 表示从details列表提取, "paths" 表示从路径列表提取
        details_key: 当 source_type="details" 时，在 assets 数据中的键名
        paths_key: 当 source_type="paths" 时，在 assets 数据中的键名
        id_field: 当 source_type="details" 时，用于提取ID的字段名
        path_id_pattern: 当 source_type="paths" 时，从路径提取ID的正则表达式
    """
    type_id: str
    label: str
    enabled: bool = True
    has_chapter: bool = False
    priority: int = 100
    source_type: str = "details"
    details_key: str = ""
    paths_key: str = ""
    id_field: str = ""
    path_id_pattern: str = ""
    extra_fields: Dict[str, Any] = field(default_factory=dict)


ASSET_TYPE_REGISTRY: Dict[str, AssetTypeConfig] = {
    "character": AssetTypeConfig(
        type_id="character",
        label="角色图",
        enabled=True,
        has_chapter=False,
        priority=10,
        source_type="details",
        details_key="character_details",
        id_field="character_id",
    ),
    "location": AssetTypeConfig(
        type_id="location",
        label="场景图",
        enabled=True,
        has_chapter=False,
        priority=20,
        source_type="paths",
        paths_key="locations",
        path_id_pattern=r"location[_-]?(\d+)",
    ),
    "fenjing": AssetTypeConfig(
        type_id="fenjing",
        label="分镜图",
        enabled=True,
        has_chapter=True,
        priority=30,
        source_type="details_by_chapter",
        details_key="fenjing_details",
        id_field="fenjing_id",
    ),
    "video": AssetTypeConfig(
        type_id="video",
        label="视频",
        enabled=True,
        has_chapter=True,
        priority=40,
        source_type="video_chapter",
    ),
    "cloth": AssetTypeConfig(
        type_id="cloth",
        label="服装图",
        enabled=True,
        has_chapter=False,
        priority=50,
        source_type="paths",
        paths_key="cloth",
        path_id_pattern=r"cloth[_-]?(\d+)",
    ),
    "cloth_changed": AssetTypeConfig(
        type_id="cloth_changed",
        label="换装图",
        enabled=True,
        has_chapter=False,
        priority=60,
        source_type="details",
        details_key="cloth_changed_details",
        id_field="outfit_id",
    ),
}


def get_enabled_asset_types() -> List[AssetTypeConfig]:
    """获取所有启用的资产类型配置，按优先级排序。"""
    return sorted(
        [cfg for cfg in ASSET_TYPE_REGISTRY.values() if cfg.enabled],
        key=lambda x: x.priority,
    )


def get_asset_type_config(type_id: str) -> Optional[AssetTypeConfig]:
    """根据类型ID获取配置。"""
    return ASSET_TYPE_REGISTRY.get(type_id)


def register_asset_type(config: AssetTypeConfig) -> None:
    """
    注册新的资产类型配置。

    用于扩展新的资产类型，无需修改现有代码。
    """
    ASSET_TYPE_REGISTRY[config.type_id] = config


def disable_asset_type(type_id: str) -> None:
    """
    禁用指定资产类型的统计。

    用于后续移除某些节点时，只需调用此方法即可。
    """
    if type_id in ASSET_TYPE_REGISTRY:
        ASSET_TYPE_REGISTRY[type_id].enabled = False
