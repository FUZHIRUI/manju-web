"""Visual Audio Assets 重构测试

测试 visual_audio_assets.py 使用新的公共 API 后的功能:
- 使用 get_image_concurrency()
- 使用 with_concurrency_limit()
- extract_and_fix_fenjing_prompts 函数修复
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, Any, List
from unittest.mock import AsyncMock, MagicMock, patch, Mock

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from manju_web.backend.services.workflow_runtime import visual_audio_assets
from manju_web.backend.services.workflow_runtime import provider_runtime


class TestExtractAndFixFenjingPrompts:
    """测试 extract_and_fix_fenjing_prompts 函数"""

    def test_extract_and_fix_fenjing_prompts_with_valid_data(self, tmp_path, monkeypatch):
        """测试使用有效的分镜提示词数据"""
        monkeypatch.setattr(
            visual_audio_assets.runtime_config,
            "PROJECT_NAME",
            "test_project"
        )
        
        valid_prompts = [
            {"fenjing_id": 1, "prompt": "A beautiful scene"},
            {"fenjing_id": 2, "prompt": "Another scene"},
        ]
        content = json.dumps(valid_prompts, ensure_ascii=False)
        
        result = visual_audio_assets.extract_and_fix_fenjing_prompts(content, expected_count=2)
        
        assert len(result) == 2
        assert result[0]["fenjing_id"] == 1
        assert result[0]["prompt"] == "A beautiful scene"

    def test_extract_and_fix_fenjing_prompts_count_mismatch(self, tmp_path, monkeypatch):
        """测试分镜数量不匹配时返回空列表"""
        monkeypatch.setattr(
            visual_audio_assets.runtime_config,
            "PROJECT_NAME",
            "test_project"
        )
        
        valid_prompts = [
            {"fenjing_id": 1, "prompt": "A beautiful scene"},
        ]
        content = json.dumps(valid_prompts, ensure_ascii=False)
        
        result = visual_audio_assets.extract_and_fix_fenjing_prompts(content, expected_count=2)
        
        assert result == []

    def test_extract_and_fix_fenjing_prompts_empty_list(self, tmp_path, monkeypatch):
        """测试空列表时返回空列表"""
        monkeypatch.setattr(
            visual_audio_assets.runtime_config,
            "PROJECT_NAME",
            "test_project"
        )
        
        content = json.dumps([], ensure_ascii=False)
        
        result = visual_audio_assets.extract_and_fix_fenjing_prompts(content, expected_count=0)
        
        assert result == []

    def test_extract_and_fix_fenjing_prompts_missing_prompt_field(self, tmp_path, monkeypatch):
        """测试缺少 prompt 字段时返回空列表"""
        monkeypatch.setattr(
            visual_audio_assets.runtime_config,
            "PROJECT_NAME",
            "test_project"
        )
        
        invalid_prompts = [
            {"fenjing_id": 1},  # 缺少 prompt
        ]
        content = json.dumps(invalid_prompts, ensure_ascii=False)
        
        result = visual_audio_assets.extract_and_fix_fenjing_prompts(content, expected_count=1)
        
        assert result == []

    def test_extract_and_fix_fenjing_prompts_missing_fenjing_id(self, tmp_path, monkeypatch):
        """测试缺少 fenjing_id 字段时返回空列表"""
        monkeypatch.setattr(
            visual_audio_assets.runtime_config,
            "PROJECT_NAME",
            "test_project"
        )
        
        invalid_prompts = [
            {"prompt": "A scene"},  # 缺少 fenjing_id
        ]
        content = json.dumps(invalid_prompts, ensure_ascii=False)
        
        result = visual_audio_assets.extract_and_fix_fenjing_prompts(content, expected_count=1)
        
        assert result == []

    def test_extract_and_fix_fenjing_prompts_not_dict_entry(self, tmp_path, monkeypatch):
        """测试条目不是字典时返回空列表"""
        monkeypatch.setattr(
            visual_audio_assets.runtime_config,
            "PROJECT_NAME",
            "test_project"
        )
        
        invalid_prompts = ["not a dict"]
        content = json.dumps(invalid_prompts, ensure_ascii=False)
        
        result = visual_audio_assets.extract_and_fix_fenjing_prompts(content, expected_count=1)
        
        assert result == []


class TestGenerateImagesWithQps:
    """测试 generate_images_with_qps 函数使用新的并发 API"""

    @pytest.mark.asyncio
    async def test_generate_images_with_qps_uses_concurrency_limit(self, tmp_path, monkeypatch):
        """测试使用并发限制"""
        monkeypatch.setattr(
            visual_audio_assets.runtime_config,
            "IMAGE_MODEL_CONCURRENCY",
            2
        )
        monkeypatch.setattr(
            visual_audio_assets.runtime_config,
            "PROJECT_NAME",
            "test_project"
        )
        
        # 创建测试用的 prompts jsonl 文件
        prompts_jsonl = tmp_path / "prompts.jsonl"
        prompts = [
            {"location_id": "loc1", "prompt_standing": "scene 1 standing", "prompt_sitting": "scene 1 sitting"},
            {"location_id": "loc2", "prompt_standing": "scene 2 standing", "prompt_sitting": "scene 2 sitting"},
        ]
        with open(prompts_jsonl, "w", encoding="utf-8") as f:
            for p in prompts:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")
        
        # Mock generate_image 函数 (在 visual_audio_assets 模块中导入的)
        mock_generate = AsyncMock(return_value=tmp_path / "test.png")
        monkeypatch.setattr(
            visual_audio_assets,
            "generate_image",
            mock_generate
        )
        
        # Mock emit_event
        monkeypatch.setattr(
            visual_audio_assets,
            "emit_event",
            MagicMock()
        )
        
        results = await visual_audio_assets.generate_images_with_qps(
            prompts_jsonl_path=prompts_jsonl,
            name_key="location_id",
            out_subdir="images"
        )
        
        # 验证 generate_image 被调用
        assert mock_generate.called

    @pytest.mark.asyncio
    async def test_generate_images_with_qps_with_callback(self, tmp_path, monkeypatch):
        """测试带回调函数的图像生成"""
        monkeypatch.setattr(
            visual_audio_assets.runtime_config,
            "IMAGE_MODEL_CONCURRENCY",
            1
        )
        monkeypatch.setattr(
            visual_audio_assets.runtime_config,
            "PROJECT_NAME",
            "test_project"
        )
        
        prompts_jsonl = tmp_path / "prompts.jsonl"
        prompts = [
            {"Character_Id": "char1", "st_prompt": "character 1"},
        ]
        with open(prompts_jsonl, "w", encoding="utf-8") as f:
            for p in prompts:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")
        
        mock_generate = AsyncMock(return_value=tmp_path / "test.png")
        monkeypatch.setattr(
            visual_audio_assets,
            "generate_image",
            mock_generate
        )

        monkeypatch.setattr(
            visual_audio_assets,
            "emit_event",
            MagicMock()
        )

        callback_called = False

        async def on_image_callback(path, item, idx):
            nonlocal callback_called
            callback_called = True

        results = await visual_audio_assets.generate_images_with_qps(
            prompts_jsonl_path=prompts_jsonl,
            name_key="Character_Id",
            out_subdir="images",
            on_image_callback=on_image_callback
        )

        assert callback_called


class TestGenerateLocationImagesShared:
    """测试 generate_location_images_shared 函数"""

    @pytest.mark.asyncio
    async def test_generate_location_images_uses_concurrency_limit(self, tmp_path, monkeypatch):
        """测试场景图像生成使用并发限制"""
        monkeypatch.setattr(
            visual_audio_assets.runtime_config,
            "IMAGE_MODEL_CONCURRENCY",
            2
        )
        monkeypatch.setattr(
            visual_audio_assets.runtime_config,
            "PROJECT_NAME",
            "test_project"
        )
        
        mock_generate = AsyncMock(return_value=tmp_path / "test.png")
        monkeypatch.setattr(
            visual_audio_assets,
            "generate_image",
            mock_generate
        )

        monkeypatch.setattr(
            visual_audio_assets,
            "emit_event",
            MagicMock()
        )

        location_prompt_map = {
            "loc1": {"standing": "standing prompt", "sitting": "sitting prompt"}
        }

        out_dir = tmp_path / "location_images"

        results = await visual_audio_assets.generate_location_images_shared(
            location_prompt_map=location_prompt_map,
            out_dir=out_dir
        )

        # 验证 generate_image 被调用
        assert mock_generate.called


class TestImportCompatibility:
    """测试导入兼容性"""

    def test_new_api_imports_from_provider_runtime(self):
        """测试从 provider_runtime 导入新 API"""
        from manju_web.backend.services.workflow_runtime.provider_runtime import (
            get_image_concurrency,
            with_concurrency_limit,
            with_thread_pool_limit,
            generate_image,
        )
        
        assert callable(get_image_concurrency)
        assert callable(with_concurrency_limit)
        assert callable(with_thread_pool_limit)
        assert callable(generate_image)

    def test_visual_audio_assets_imports_new_apis(self):
        """测试 visual_audio_assets 导入新 API"""
        # 验证 visual_audio_assets 中使用了新 API
        import inspect
        
        source = inspect.getsource(visual_audio_assets)
        assert "get_image_concurrency" in source
        assert "with_concurrency_limit" in source


class TestConcurrencyIntegrationInVisualAudioAssets:
    """测试 visual_audio_assets 中的并发集成"""

    @pytest.mark.asyncio
    async def test_concurrency_limit_applied_in_generate_images(self, tmp_path, monkeypatch):
        """测试图像生成中应用了并发限制"""
        monkeypatch.setattr(
            visual_audio_assets.runtime_config,
            "IMAGE_MODEL_CONCURRENCY",
            1
        )
        monkeypatch.setattr(
            visual_audio_assets.runtime_config,
            "PROJECT_NAME",
            "test_project"
        )
        
        prompts_jsonl = tmp_path / "prompts.jsonl"
        prompts = [
            {"location_id": "loc1", "prompt_standing": "scene 1 standing", "prompt_sitting": "scene 1 sitting"},
            {"location_id": "loc2", "prompt_standing": "scene 2 standing", "prompt_sitting": "scene 2 sitting"},
        ]
        with open(prompts_jsonl, "w", encoding="utf-8") as f:
            for p in prompts:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")

        execution_order = []

        async def mock_generate(prompt_text, out_dir, name_prefix, size=None):
            execution_order.append(f"start_{name_prefix}")
            await asyncio.sleep(0.01)
            execution_order.append(f"end_{name_prefix}")
            return out_dir / f"{name_prefix}.png"

        monkeypatch.setattr(
            visual_audio_assets,
            "generate_image",
            mock_generate
        )
        
        monkeypatch.setattr(
            visual_audio_assets,
            "emit_event",
            MagicMock()
        )
        
        await visual_audio_assets.generate_images_with_qps(
            prompts_jsonl_path=prompts_jsonl,
            name_key="location_id",
            out_subdir="images"
        )
        
        # 验证并发限制被应用
        # 注意：对于 location_id，每个位置会生成 standing 和 sitting 两个图像
        # 并发限制为1意味着每个 location 内部的图像是顺序生成的
        # 但不同 location 之间是并发的（因为每个 location 是一个独立的 task）
        # 所以验证每个 location 内部的 standing 和 sitting 是顺序的
        assert len(execution_order) == 8
        # loc1 的 standing 和 sitting 应该是顺序的
        assert execution_order.index("start_loc1_standing") < execution_order.index("end_loc1_standing")
        assert execution_order.index("end_loc1_standing") < execution_order.index("start_loc1_sitting")
        assert execution_order.index("start_loc1_sitting") < execution_order.index("end_loc1_sitting")
        # loc2 的 standing 和 sitting 应该是顺序的
        assert execution_order.index("start_loc2_standing") < execution_order.index("end_loc2_standing")
        assert execution_order.index("end_loc2_standing") < execution_order.index("start_loc2_sitting")
        assert execution_order.index("start_loc2_sitting") < execution_order.index("end_loc2_sitting")
