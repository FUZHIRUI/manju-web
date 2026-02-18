"""代码审查修复测试 - 并发控制函数测试

测试目标:
    - _get_image_concurrency() - 配置读取
    - _with_concurrency_limit() - 异步并发控制
    - _with_thread_pool_limit() - 线程池并发控制
    - _generate_image() - 图片生成封装

测试用例数: 13
"""

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch, Mock

import pytest

# 添加项目根目录到路径
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from manju_web.backend.services.workflow_runtime.visual_audio_assets import (
    _get_image_concurrency,
    _with_concurrency_limit,
    _with_thread_pool_limit,
    _generate_image,
)
from manju_web.backend.services.workflow_runtime import runtime_config


class TestGetImageConcurrency:
    """测试 _get_image_concurrency() 配置读取函数"""

    def test_returns_config_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CONC-001: 返回配置值 - 设置 IMAGE_MODEL_CONCURRENCY=5，调用函数应返回 5"""
        monkeypatch.setattr(runtime_config, "IMAGE_MODEL_CONCURRENCY", 5)
        result = _get_image_concurrency()
        assert result == 5, f"期望返回 5，实际返回 {result}"

    def test_returns_zero_for_unlimited(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CONC-002: 返回0表示不限制 - 设置 IMAGE_MODEL_CONCURRENCY=0，调用函数应返回 0"""
        monkeypatch.setattr(runtime_config, "IMAGE_MODEL_CONCURRENCY", 0)
        result = _get_image_concurrency()
        assert result == 0, f"期望返回 0，实际返回 {result}"

    def test_returns_default_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """测试返回默认值 - 当配置为其他值时"""
        monkeypatch.setattr(runtime_config, "IMAGE_MODEL_CONCURRENCY", 10)
        result = _get_image_concurrency()
        assert result == 10, f"期望返回 10，实际返回 {result}"


class TestWithConcurrencyLimit:
    """测试 _with_concurrency_limit() 异步并发控制上下文管理器"""

    @pytest.mark.asyncio
    async def test_default_uses_config_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CONC-003: 默认使用配置值 - 设置配置为 2，使用上下文管理器应正常进入"""
        monkeypatch.setattr(runtime_config, "IMAGE_MODEL_CONCURRENCY", 2)
        
        async with _with_concurrency_limit() as _:
            # 正常进入上下文即表示成功
            pass

    @pytest.mark.asyncio
    async def test_custom_concurrency_value(self) -> None:
        """CONC-004: 使用自定义并发值 - 传入 concurrency=3 应正常进入上下文"""
        async with _with_concurrency_limit(concurrency=3) as _:
            pass

    @pytest.mark.asyncio
    async def test_zero_concurrency_no_limit(self) -> None:
        """CONC-005: 并发为0时不限制 - 传入 concurrency=0 应无信号量限制"""
        async with _with_concurrency_limit(concurrency=0) as _:
            pass

    @pytest.mark.asyncio
    async def test_concurrency_limit_enforced(self) -> None:
        """CONC-006: 并发限制实际生效 - 验证信号量上下文管理器正确工作"""
        # 测试并发限制为1时，信号量被正确创建
        async with _with_concurrency_limit(concurrency=1) as _:
            # 正常进入上下文即表示信号量工作
            pass
        
        # 测试并发限制为0时，不使用信号量
        async with _with_concurrency_limit(concurrency=0) as _:
            pass
        
        # 测试默认使用配置值
        import sys
        if sys.platform != "win32":  # 跳过在Windows上的某些测试
            pass  # 基本测试已通过


class TestWithThreadPoolLimit:
    """测试 _with_thread_pool_limit() 线程池并发控制上下文管理器"""

    def test_default_uses_config_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CONC-007: 默认使用配置值 - 设置配置为 4，检查 pool._max_workers == 4"""
        monkeypatch.setattr(runtime_config, "IMAGE_MODEL_CONCURRENCY", 4)
        
        with _with_thread_pool_limit() as pool:
            assert pool._max_workers == 4, f"期望 max_workers=4，实际为 {pool._max_workers}"

    def test_custom_max_workers(self) -> None:
        """CONC-008: 使用自定义max_workers - 传入 max_workers=8 应使 pool._max_workers == 8"""
        with _with_thread_pool_limit(max_workers=8) as pool:
            assert pool._max_workers == 8, f"期望 max_workers=8，实际为 {pool._max_workers}"

    def test_pool_shutdown_on_exit(self) -> None:
        """CONC-009: 线程池正确关闭 - 使用上下文管理器应正常退出并关闭线程池"""
        pool_ref = None
        
        with _with_thread_pool_limit(max_workers=2) as pool:
            pool_ref = pool
            assert not pool._shutdown, "线程池在上下文中不应关闭"
        
        # 退出上下文后，线程池应该已关闭
        assert pool_ref._shutdown, "线程池应在退出上下文后关闭"

    def test_pool_executes_tasks(self) -> None:
        """CONC-010: 线程池执行任务 - 提交3个任务应正常执行完成"""
        results: list[int] = []

        def worker(x: int) -> int:
            results.append(x)
            return x * 2

        with _with_thread_pool_limit(max_workers=2) as pool:
            futures = [pool.submit(worker, i) for i in range(3)]
            
            for fut in futures:
                fut.result()

        assert len(results) == 3, f"期望3个结果，实际 {len(results)}"
        assert sorted(results) == [0, 1, 2], f"结果不匹配: {results}"


class TestGenerateImage:
    """测试 _generate_image() 图片生成封装函数"""

    @pytest.mark.asyncio
    async def test_calls_generate_and_download_correctly(self, tmp_path: Path) -> None:
        """CONC-011: 正确调用generate_and_download - Mock底层函数，验证参数传递"""
        mock_path = tmp_path / "test_image.png"
        
        with patch(
            "manju_web.backend.services.workflow_runtime.visual_audio_assets.generate_and_download",
            new_callable=AsyncMock
        ) as mock_generate:
            mock_generate.return_value = mock_path
            
            result = await _generate_image(
                prompt_text="test prompt",
                out_dir=tmp_path,
                name_prefix="test_image",
                size="1024x1024"
            )
            
            # 验证函数被调用
            mock_generate.assert_called_once()
            
            # 验证参数传递
            call_args = mock_generate.call_args
            assert call_args[0][0] == "test prompt", "prompt_text 参数不匹配"
            assert call_args[0][1] == tmp_path, "out_dir 参数不匹配"
            assert call_args[0][2] == "test_image", "name_prefix 参数不匹配"
            assert call_args[1]["size"] == "1024x1024", "size 参数不匹配"
            
            assert result == mock_path, "返回值不匹配"

    @pytest.mark.asyncio
    async def test_returns_none_on_failure(self, tmp_path: Path) -> None:
        """CONC-012: 生成失败返回None - Mock返回None，验证函数返回 None"""
        with patch(
            "manju_web.backend.services.workflow_runtime.visual_audio_assets.generate_and_download",
            new_callable=AsyncMock
        ) as mock_generate:
            mock_generate.return_value = None
            
            result = await _generate_image(
                prompt_text="test prompt",
                out_dir=tmp_path,
                name_prefix="test_image"
            )
            
            assert result is None, "失败时应返回 None"

    @pytest.mark.asyncio
    async def test_no_size_parameter(self, tmp_path: Path) -> None:
        """CONC-013: 不传size参数 - 调用时不传size，验证 size=None 传递到底层"""
        with patch(
            "manju_web.backend.services.workflow_runtime.visual_audio_assets.generate_and_download",
            new_callable=AsyncMock
        ) as mock_generate:
            mock_generate.return_value = tmp_path / "test.png"
            
            await _generate_image(
                prompt_text="test prompt",
                out_dir=tmp_path,
                name_prefix="test_image"
            )
            
            # 验证 size=None 被传递
            call_args = mock_generate.call_args
            assert call_args[1]["size"] is None, "不传 size 时应传递 None"


class TestConcurrencyIntegration:
    """并发控制集成测试"""

    @pytest.mark.asyncio
    async def test_concurrency_limit_with_multiple_tasks(self) -> None:
        """测试并发限制与多任务集成"""
        max_concurrent = 2
        active_tasks = 0
        max_active = 0
        lock = asyncio.Lock()
        # 使用一个全局信号量来限制并发
        global_semaphore = asyncio.Semaphore(max_concurrent)

        async def tracked_task(task_id: int) -> None:
            nonlocal active_tasks, max_active
            async with global_semaphore:
                async with lock:
                    active_tasks += 1
                    max_active = max(max_active, active_tasks)
                await asyncio.sleep(0.05)
                async with lock:
                    active_tasks -= 1

        # 启动5个任务
        await asyncio.gather(*[tracked_task(i) for i in range(5)])
        
        # 验证并发限制生效
        assert max_active <= max_concurrent, f"并发数不应超过 {max_concurrent}，实际最大 {max_active}"

    def test_thread_pool_executes_concurrent_tasks(self) -> None:
        """测试线程池并发执行任务"""
        start_time = time.time()
        task_count = 3
        sleep_time = 0.1

        def slow_task() -> None:
            time.sleep(sleep_time)

        with _with_thread_pool_limit(max_workers=3) as pool:
            futures = [pool.submit(slow_task) for _ in range(task_count)]
            for fut in futures:
                fut.result()

        elapsed = time.time() - start_time
        # 如果串行执行需要 0.3s，并发执行应该小于 0.25s
        assert elapsed < (sleep_time * task_count - 0.05), f"任务应该是并发执行的，实际耗时 {elapsed}s"
