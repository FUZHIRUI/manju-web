"""
资产统计服务模块。

提供生图次数统计功能，支持按类型、章节、成功/失败维度统计。
所有统计逻辑基于配置驱动，便于扩展和维护。
结果记录（asset_results.jsonl）为唯一数据源。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .asset_stats_config import (
    AssetTypeConfig,
    get_enabled_asset_types,
    get_asset_type_config,
)


@dataclass
class AssetStatItem:
    """
    单个资产类型的统计结果。
    """
    type_id: str
    label: str
    total: int = 0
    success: int = 0
    failed: int = 0
    retry_count: int = 0
    has_chapter: bool = False
    chapters: Dict[str, Dict[str, int]] = field(default_factory=dict)


@dataclass
class AssetStatsResult:
    """
    完整的资产统计结果。
    """
    total_success: int = 0
    total_failed: int = 0
    total_retry: int = 0
    by_type: Dict[str, AssetStatItem] = field(default_factory=dict)
    by_chapter: Dict[str, Dict[str, int]] = field(default_factory=dict)


class AssetStatsCalculator:
    """
    资产统计计算器。

    根据配置驱动的方式计算各类型资产的统计数据，
    支持灵活扩展新的资产类型。
    """

    def __init__(self, assets_data: Dict[str, Any], results_data: List[Dict[str, Any]]):
        """
        初始化计算器。

        Args:
            assets_data: 项目资产数据（来自 list_project_assets）
            results_data: 结果条目数据（来自 asset_results.jsonl）
        """
        self.assets_data = assets_data
        self.results_data = results_data
        self._result_map = self._build_result_map()

    def _build_result_map(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        构建结果条目索引，按 asset_type 分组。
        """
        result_map: Dict[str, List[Dict[str, Any]]] = {}
        for item in self.results_data:
            asset_type = str(item.get("asset_type") or "")
            if not asset_type:
                continue
            result_map.setdefault(asset_type, []).append(item)
        return result_map

    def calculate(self) -> AssetStatsResult:
        """
        计算完整的统计数据。
        """
        result = AssetStatsResult()

        for config in get_enabled_asset_types():
            stat_item = self._calculate_type(config)
            result.by_type[config.type_id] = stat_item
            result.total_success += stat_item.success
            result.total_failed += stat_item.failed
            result.total_retry += stat_item.retry_count

            for chapter, chapter_stat in stat_item.chapters.items():
                if chapter not in result.by_chapter:
                    result.by_chapter[chapter] = {"success": 0, "failed": 0, "retry": 0}
                result.by_chapter[chapter]["success"] += chapter_stat.get("success", 0)
                result.by_chapter[chapter]["failed"] += chapter_stat.get("failed", 0)
                result.by_chapter[chapter]["retry"] += chapter_stat.get("retry", 0)

        return result

    def _calculate_type(self, config: AssetTypeConfig) -> AssetStatItem:
        """
        计算单个资产类型的统计数据。
        """
        stat = AssetStatItem(
            type_id=config.type_id,
            label=config.label,
            has_chapter=config.has_chapter,
        )

        if config.source_type == "details":
            self._calculate_from_details(config, stat)
        elif config.source_type == "paths":
            self._calculate_from_paths(config, stat)
        elif config.source_type == "details_by_chapter":
            self._calculate_from_details_by_chapter(config, stat)
        elif config.source_type == "video_chapter":
            self._calculate_video_chapter(config, stat)

        stat.total = stat.success + stat.failed
        return stat

    def _calculate_from_details(self, config: AssetTypeConfig, stat: AssetStatItem) -> None:
        """
        从结果记录计算统计（结果记录为唯一数据源）。
        """
        type_results = self._result_map.get(config.type_id, [])
        for result_item in type_results:
            self._apply_result(stat, result_item)

    def _calculate_from_paths(self, config: AssetTypeConfig, stat: AssetStatItem) -> None:
        """
        从结果记录计算统计（结果记录为唯一数据源）。
        """
        type_results = self._result_map.get(config.type_id, [])
        for result_item in type_results:
            self._apply_result(stat, result_item)

    def _calculate_from_details_by_chapter(self, config: AssetTypeConfig, stat: AssetStatItem) -> None:
        """
        从结果记录计算统计（结果记录为唯一数据源，按章节分组）。
        """
        type_results = self._result_map.get(config.type_id, [])

        chapter_stats: Dict[str, Dict[str, int]] = {}
        for result_item in type_results:
            chapter = str(result_item.get("chapter_id") or "")
            if chapter not in chapter_stats:
                chapter_stats[chapter] = {"success": 0, "failed": 0, "retry": 0}
            self._apply_result(stat, result_item, chapter_stats[chapter])

        for chapter, chapter_stat in chapter_stats.items():
            if chapter:
                stat.chapters[chapter] = chapter_stat

    def _calculate_video_chapter(self, config: AssetTypeConfig, stat: AssetStatItem) -> None:
        """
        从结果记录计算统计（结果记录为唯一数据源，按章节分组）。
        """
        type_results = self._result_map.get(config.type_id, [])

        chapter_stats: Dict[str, Dict[str, int]] = {}
        for result_item in type_results:
            chapter = str(result_item.get("chapter_id") or "")
            if chapter not in chapter_stats:
                chapter_stats[chapter] = {"success": 0, "failed": 0, "retry": 0}
            self._apply_result(stat, result_item, chapter_stats[chapter])

        for chapter, chapter_stat in chapter_stats.items():
            if chapter:
                stat.chapters[chapter] = chapter_stat

    def _apply_result(
        self,
        stat: AssetStatItem,
        result_item: Dict[str, Any],
        chapter_stat: Optional[Dict[str, int]] = None,
    ) -> None:
        """
        应用结果条目到统计。
        """
        status = result_item.get("status")
        retry = int(result_item.get("retry_count") or 0)
        source = str(result_item.get("source") or "")
        reason = str(result_item.get("reason") or "")

        if status == "success":
            stat.success += 1
            if chapter_stat is not None:
                chapter_stat["success"] += 1
        elif source == "qc_result" and status == "failed":
            stat.retry_count += max(1, retry)
            if chapter_stat is not None:
                chapter_stat["retry"] += max(1, retry)
            return
        elif reason == "missing_output":
            stat.failed += 1
            if chapter_stat is not None:
                chapter_stat["failed"] += 1
        else:
            stat.failed += 1
            if chapter_stat is not None:
                chapter_stat["failed"] += 1

        stat.retry_count += retry
        if chapter_stat is not None:
            chapter_stat["retry"] += retry


def calculate_asset_stats(
    assets_data: Dict[str, Any],
    results_data: List[Dict[str, Any]],
) -> AssetStatsResult:
    """
    计算资产统计的便捷函数。
    """
    calculator = AssetStatsCalculator(assets_data, results_data)
    return calculator.calculate()


def format_stats_for_api(result: AssetStatsResult) -> Dict[str, Any]:
    """
    将统计结果格式化为API响应格式。
    """
    by_type = {}
    for type_id, stat in result.by_type.items():
        by_type[type_id] = {
            "label": stat.label,
            "total": stat.total,
            "success": stat.success,
            "failed": stat.failed,
            "retry_count": stat.retry_count,
            "has_chapter": stat.has_chapter,
            "chapters": stat.chapters,
        }

    return {
        "summary": {
            "total_success": result.total_success,
            "total_failed": result.total_failed,
            "total_retry": result.total_retry,
        },
        "by_type": by_type,
        "by_chapter": result.by_chapter,
    }
