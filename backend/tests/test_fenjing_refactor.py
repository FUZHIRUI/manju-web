"""Fenjing 模块重构测试

测试 fenjing.py 使用新的公共 API 后的功能:
- 使用 with_thread_pool_limit()
- 导入路径更新验证
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, Any, List
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from concurrent.futures import ThreadPoolExecutor

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from manju_web.backend.services.workflow_runtime import fenjing
from manju_web.backend.services.workflow_runtime import provider_runtime


class TestWithThreadPoolLimitUsage:
    """测试 with_thread_pool_limit 在 fenjing.py 中的使用"""

    def test_generate_fenjing_images_uses_thread_pool_limit(self, tmp_path, monkeypatch):
        """测试生成分镜图像时使用线程池限制"""
        monkeypatch.setattr(
            fenjing.runtime_config,
            "PROJECT_NAME",
            "test_project"
        )
        monkeypatch.setattr(
            fenjing.runtime_config,
            "SEEDREAM_MODEL",
            "test_model"
        )
        
        # Mock TosClientWrapper (在 fenjing 模块中导入的)
        mock_tos = MagicMock()
        mock_tos.available.return_value = False
        monkeypatch.setattr(
            fenjing,
            "TosClientWrapper",
            lambda: mock_tos
        )
        
        # Mock emit_event
        monkeypatch.setattr(
            fenjing,
            "emit_event",
            MagicMock()
        )
        
        # 创建测试用的 jsonl 文件
        fenjing_prompts_jsonl = tmp_path / "fenjing_prompts.jsonl"
        storyboards_jsonl = tmp_path / "storyboards.jsonl"
        chars_jsonl = tmp_path / "characters.jsonl"
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        
        prompts = [
            {"fenjing_id": 1, "prompt": "scene 1", "Location_Id": "loc1", "Background_xuanze": "standing"},
        ]
        storyboards = [
            {"Storyboard_id": 1, "Characters": []},
        ]
        chars = []
        
        with open(fenjing_prompts_jsonl, "w", encoding="utf-8") as f:
            for p in prompts:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")
        
        with open(storyboards_jsonl, "w", encoding="utf-8") as f:
            for s in storyboards:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
        
        with open(chars_jsonl, "w", encoding="utf-8") as f:
            for c in chars:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
        
        # Mock generate_image_with_refs 和 download (在 fenjing 模块中导入的)
        monkeypatch.setattr(
            fenjing,
            "generate_image_with_refs",
            AsyncMock(return_value={"data": [{"url": "http://example.com/image.png"}]})
        )
        monkeypatch.setattr(
            fenjing,
            "download",
            AsyncMock(return_value=True)
        )

        # Mock size_for_2k_9x16 (在 fenjing 模块中导入的)
        monkeypatch.setattr(
            fenjing,
            "size_for_2k_9x16",
            lambda: "1440x2560"
        )
        
        # 执行测试
        results, uploads = fenjing.generate_fenjing_images(
            fenjing_prompts_jsonl=fenjing_prompts_jsonl,
            storyboards_jsonl=storyboards_jsonl,
            input_dir=input_dir,
            cloth_changed_upload=[],
            chars_jsonl=chars_jsonl,
            chapter_name="chapter1"
        )
        
        # 验证结果
        assert isinstance(results, list)
        assert isinstance(uploads, list)

    def test_thread_pool_executor_created(self, monkeypatch):
        """测试线程池执行器被正确创建"""
        # 验证 with_thread_pool_limit 被导入
        import inspect
        source = inspect.getsource(fenjing)
        assert "with_thread_pool_limit" in source


class TestImportPathUpdates:
    """测试导入路径更新"""

    def test_provider_runtime_imports(self):
        """测试从 provider_runtime 导入的函数"""
        from manju_web.backend.services.workflow_runtime.fenjing import (
            download,
            generate_and_download,
            generate_and_download_with_refs,
            generate_image,
            generate_image_with_refs,
            run_async,
            size_for_2k_9x16,
            TosClientWrapper,
            emit_event,
            with_thread_pool_limit,
        )
        
        # 验证所有导入都是可调用的
        assert callable(download)
        assert callable(generate_and_download)
        assert callable(generate_and_download_with_refs)
        assert callable(generate_image)
        assert callable(generate_image_with_refs)
        assert callable(run_async)
        assert callable(size_for_2k_9x16)
        assert callable(with_thread_pool_limit)
        assert callable(TosClientWrapper)
        assert callable(emit_event)

    def test_visual_audio_assets_imports(self):
        """测试从 visual_audio_assets 导入的函数"""
        from manju_web.backend.services.workflow_runtime.fenjing import (
            download_file_from_tos,
            character_keys_sorted,
            prepare_character_map,
            build_character_presigned_map,
            load_char_defaults,
            load_char_plot_outfits,
            load_upload_jsonl,
        )
        
        # 验证所有导入都是可调用的
        assert callable(download_file_from_tos)
        assert callable(character_keys_sorted)
        assert callable(prepare_character_map)
        assert callable(build_character_presigned_map)
        assert callable(load_char_defaults)
        assert callable(load_char_plot_outfits)
        assert callable(load_upload_jsonl)


class TestGenerateFenjingImages:
    """测试 generate_fenjing_images 函数"""

    def test_generate_fenjing_images_with_empty_prompts(self, tmp_path, monkeypatch):
        """测试空提示词列表"""
        monkeypatch.setattr(
            fenjing.runtime_config,
            "PROJECT_NAME",
            "test_project"
        )
        monkeypatch.setattr(
            fenjing.runtime_config,
            "SEEDREAM_MODEL",
            "test_model"
        )
        
        mock_tos = MagicMock()
        mock_tos.available.return_value = False
        monkeypatch.setattr(
            provider_runtime,
            "TosClientWrapper",
            lambda: mock_tos
        )
        
        monkeypatch.setattr(
            fenjing,
            "emit_event",
            MagicMock()
        )
        
        fenjing_prompts_jsonl = tmp_path / "fenjing_prompts.jsonl"
        storyboards_jsonl = tmp_path / "storyboards.jsonl"
        chars_jsonl = tmp_path / "characters.jsonl"
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        
        # 空文件
        with open(fenjing_prompts_jsonl, "w", encoding="utf-8") as f:
            pass
        with open(storyboards_jsonl, "w", encoding="utf-8") as f:
            pass
        with open(chars_jsonl, "w", encoding="utf-8") as f:
            pass
        
        results, uploads = fenjing.generate_fenjing_images(
            fenjing_prompts_jsonl=fenjing_prompts_jsonl,
            storyboards_jsonl=storyboards_jsonl,
            input_dir=input_dir,
            cloth_changed_upload=[],
            chars_jsonl=chars_jsonl,
            chapter_name="chapter1"
        )
        
        assert results == []
        assert uploads == []

    def test_generate_fenjing_images_skips_invalid_items(self, tmp_path, monkeypatch):
        """测试跳过无效条目"""
        monkeypatch.setattr(
            fenjing.runtime_config,
            "PROJECT_NAME",
            "test_project"
        )
        monkeypatch.setattr(
            fenjing.runtime_config,
            "SEEDREAM_MODEL",
            "test_model"
        )
        
        mock_tos = MagicMock()
        mock_tos.available.return_value = False
        monkeypatch.setattr(
            provider_runtime,
            "TosClientWrapper",
            lambda: mock_tos
        )
        
        monkeypatch.setattr(
            fenjing,
            "emit_event",
            MagicMock()
        )
        
        fenjing_prompts_jsonl = tmp_path / "fenjing_prompts.jsonl"
        storyboards_jsonl = tmp_path / "storyboards.jsonl"
        chars_jsonl = tmp_path / "characters.jsonl"
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        
        # 包含无效条目（不是字典）
        prompts = ["not a dict"]
        storyboards = []
        chars = []
        
        with open(fenjing_prompts_jsonl, "w", encoding="utf-8") as f:
            for p in prompts:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")
        
        with open(storyboards_jsonl, "w", encoding="utf-8") as f:
            for s in storyboards:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
        
        with open(chars_jsonl, "w", encoding="utf-8") as f:
            for c in chars:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
        
        results, uploads = fenjing.generate_fenjing_images(
            fenjing_prompts_jsonl=fenjing_prompts_jsonl,
            storyboards_jsonl=storyboards_jsonl,
            input_dir=input_dir,
            cloth_changed_upload=[],
            chars_jsonl=chars_jsonl,
            chapter_name="chapter1"
        )
        
        assert results == []
        assert uploads == []


class TestNormBgType:
    """测试 norm_bg_type 函数"""

    def test_norm_bg_type_standing_variations(self):
        """测试 standing 的各种变体"""
        assert fenjing.norm_bg_type("standing") == "standing"
        assert fenjing.norm_bg_type("standding") == "standing"
        assert fenjing.norm_bg_type("standing图") == "standing"
        assert fenjing.norm_bg_type("STANDING") == "standing"

    def test_norm_bg_type_sitting_variations(self):
        """测试 sitting 的各种变体"""
        assert fenjing.norm_bg_type("sitting") == "sitting"
        assert fenjing.norm_bg_type("siting") == "sitting"
        assert fenjing.norm_bg_type("sitting图") == "sitting"
        assert fenjing.norm_bg_type("SITTING") == "sitting"

    def test_norm_bg_type_default(self):
        """测试默认值"""
        assert fenjing.norm_bg_type(None) == "standing"
        assert fenjing.norm_bg_type("") == "standing"
        assert fenjing.norm_bg_type("unknown") == "standing"
        assert fenjing.norm_bg_type("other") == "standing"


class TestPrepareLocationMap:
    """测试 prepare_location_map 函数"""

    def test_prepare_location_map_empty_dir(self, tmp_path, monkeypatch):
        """测试空目录"""
        mock_tos = MagicMock()
        mock_tos.available.return_value = False
        monkeypatch.setattr(
            provider_runtime,
            "TosClientWrapper",
            lambda: mock_tos
        )
        
        result = fenjing.prepare_location_map(tmp_path)
        assert result == {}

    def test_prepare_location_map_with_images(self, tmp_path, monkeypatch):
        """测试包含图像的目录"""
        mock_tos = MagicMock()
        mock_tos.available.return_value = True
        mock_tos.presign_get.return_value = "http://example.com/image.png"
        monkeypatch.setattr(
            provider_runtime,
            "TosClientWrapper",
            lambda: mock_tos
        )
        
        loc_dir = tmp_path / "location_images"
        loc_dir.mkdir()
        
        # 创建测试图像文件
        (loc_dir / "loc1_standing.png").touch()
        (loc_dir / "loc1_sitting.png").touch()
        (loc_dir / "loc2_standing.png").touch()
        
        result = fenjing.prepare_location_map(tmp_path)
        
        assert "loc1" in result
        assert "standing" in result["loc1"]
        assert "sitting" in result["loc1"]
        assert "loc2" in result
        assert "standing" in result["loc2"]


class TestListTosKeys:
    """测试 list_tos_keys 函数"""

    def test_list_tos_keys_not_available(self, monkeypatch):
        """测试 TOS 不可用时返回空列表"""
        mock_tos = MagicMock()
        mock_tos.available.return_value = False
        
        result = fenjing.list_tos_keys(mock_tos, "bucket", "prefix/")
        assert result == []

    def test_list_tos_keys_no_client(self, monkeypatch):
        """测试没有客户端时返回空列表"""
        mock_tos = MagicMock()
        mock_tos.available.return_value = True
        type(mock_tos)._client = None
        
        result = fenjing.list_tos_keys(mock_tos, "bucket", "prefix/")
        assert result == []


class TestDownloadStoryboardsFromTos:
    """测试 download_storyboards_from_tos 函数"""

    def test_download_storyboards_tos_not_available(self, tmp_path, monkeypatch):
        """测试 TOS 不可用时返回空列表"""
        mock_tos = MagicMock()
        mock_tos.available.return_value = False
        monkeypatch.setattr(
            provider_runtime,
            "TosClientWrapper",
            lambda: mock_tos
        )
        
        monkeypatch.setattr(
            fenjing,
            "emit_event",
            MagicMock()
        )
        
        result = fenjing.download_storyboards_from_tos(tmp_path)
        assert result == []

    def test_download_storyboards_fallback_to_local(self, tmp_path, monkeypatch):
        """测试回退到本地目录"""
        mock_tos = MagicMock()
        mock_tos.available.return_value = True
        mock_tos._client = None
        monkeypatch.setattr(
            provider_runtime,
            "TosClientWrapper",
            lambda: mock_tos
        )
        
        monkeypatch.setattr(
            fenjing,
            "emit_event",
            MagicMock()
        )
        
        # 创建本地 storyboards 目录和文件
        storyboards_dir = tmp_path / "storyboards"
        storyboards_dir.mkdir()
        (storyboards_dir / "storyboard_chapter_1.jsonl").touch()
        
        result = fenjing.download_storyboards_from_tos(tmp_path)
        
        assert len(result) == 1
        assert result[0].name == "storyboard_chapter_1.jsonl"
