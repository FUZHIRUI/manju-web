"""代码审查修复测试 - 异常处理细化测试

测试目标:
    - 自定义异常类
    - 异常继承关系

测试用例数: 10
"""

import sys
from pathlib import Path
from typing import Any, Optional

import pytest

# 添加项目根目录到路径
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from manju_web.backend.services.workflow_runtime.provider_runtime import (
    WorkflowRuntimeError,
    ImageGenerationError,
    FenjingPromptError,
    RetryExceededError,
)


class TestWorkflowRuntimeError:
    """测试 WorkflowRuntimeError 异常类"""

    def test_is_exception_subclass(self) -> None:
        """EXC-001: 是Exception子类 - 检查继承关系"""
        assert issubclass(WorkflowRuntimeError, Exception), \
            "WorkflowRuntimeError 应该是 Exception 的子类"

    def test_can_be_raised_and_caught(self) -> None:
        """EXC-002: 可抛出和捕获 - raise/catch 应正常捕获"""
        with pytest.raises(WorkflowRuntimeError) as exc_info:
            raise WorkflowRuntimeError("test error message")
        
        assert str(exc_info.value) == "test error message", "异常消息应匹配"

    def test_can_catch_as_exception(self) -> None:
        """测试可以作为 Exception 捕获"""
        try:
            raise WorkflowRuntimeError("test")
        except Exception as e:
            assert isinstance(e, WorkflowRuntimeError), "应能作为 Exception 捕获"


class TestImageGenerationError:
    """测试 ImageGenerationError 异常类"""

    def test_is_workflow_runtime_error_subclass(self) -> None:
        """EXC-003: 是WorkflowRuntimeError子类 - 检查继承关系"""
        assert issubclass(ImageGenerationError, WorkflowRuntimeError), \
            "ImageGenerationError 应该是 WorkflowRuntimeError 的子类"
        assert issubclass(ImageGenerationError, Exception), \
            "ImageGenerationError 应该是 Exception 的子类"

    def test_stores_error_message(self) -> None:
        """EXC-004: 存储错误消息 - 创建异常验证消息"""
        error = ImageGenerationError("generation failed")
        assert str(error) == "generation failed", "错误消息应匹配"

    def test_stores_prompt_text(self) -> None:
        """EXC-005: 存储提示词文本 - 传入prompt_text验证"""
        error = ImageGenerationError(
            "generation failed",
            prompt_text="test prompt"
        )
        assert error.prompt_text == "test prompt", "prompt_text 应匹配"

    def test_stores_cause_exception(self) -> None:
        """EXC-006: 存储原始异常 - 传入cause验证"""
        original_error = ValueError("original error")
        error = ImageGenerationError(
            "generation failed",
            prompt_text="test prompt",
            cause=original_error
        )
        assert error.cause is original_error, "cause 应指向原始异常"
        assert str(error.cause) == "original error", "原始异常消息应匹配"

    def test_optional_parameters(self) -> None:
        """测试可选参数"""
        # 只传消息
        error1 = ImageGenerationError("error")
        assert error1.prompt_text is None
        assert error1.cause is None

        # 传消息和 prompt_text
        error2 = ImageGenerationError("error", prompt_text="prompt")
        assert error2.prompt_text == "prompt"
        assert error2.cause is None


class TestFenjingPromptError:
    """测试 FenjingPromptError 异常类"""

    def test_is_workflow_runtime_error_subclass(self) -> None:
        """EXC-007: 是WorkflowRuntimeError子类 - 检查继承关系"""
        assert issubclass(FenjingPromptError, WorkflowRuntimeError), \
            "FenjingPromptError 应该是 WorkflowRuntimeError 的子类"

    def test_stores_chapter_info(self) -> None:
        """EXC-008: 存储章节信息 - 传入chapter验证"""
        error = FenjingPromptError(
            "prompt generation failed",
            chapter="chapter_1"
        )
        assert error.chapter == "chapter_1", "chapter 应匹配"

    def test_stores_cause_exception(self) -> None:
        """测试存储原始异常"""
        original_error = RuntimeError("original")
        error = FenjingPromptError(
            "prompt generation failed",
            chapter="chapter_1",
            cause=original_error
        )
        assert error.cause is original_error, "cause 应指向原始异常"


class TestRetryExceededError:
    """测试 RetryExceededError 异常类"""

    def test_is_workflow_runtime_error_subclass(self) -> None:
        """EXC-009: 是WorkflowRuntimeError子类 - 检查继承关系"""
        assert issubclass(RetryExceededError, WorkflowRuntimeError), \
            "RetryExceededError 应该是 WorkflowRuntimeError 的子类"

    def test_stores_attempts_count(self) -> None:
        """EXC-010: 存储尝试次数 - 传入attempts验证"""
        error = RetryExceededError(
            "max retries exceeded",
            attempts=3
        )
        assert error.attempts == 3, "attempts 应匹配"

    def test_stores_cause_exception(self) -> None:
        """测试存储原始异常"""
        original_error = ConnectionError("connection failed")
        error = RetryExceededError(
            "max retries exceeded",
            attempts=5,
            cause=original_error
        )
        assert error.cause is original_error, "cause 应指向原始异常"
        assert error.attempts == 5, "attempts 应匹配"


class TestExceptionHierarchy:
    """测试异常继承层次结构"""

    def test_all_inherit_from_workflow_runtime_error(self) -> None:
        """测试所有自定义异常都继承自 WorkflowRuntimeError"""
        exceptions = [
            ImageGenerationError,
            FenjingPromptError,
            RetryExceededError,
        ]
        
        for exc_class in exceptions:
            assert issubclass(exc_class, WorkflowRuntimeError), \
                f"{exc_class.__name__} 应该继承自 WorkflowRuntimeError"

    def test_all_inherit_from_exception(self) -> None:
        """测试所有自定义异常都继承自 Exception"""
        exceptions = [
            WorkflowRuntimeError,
            ImageGenerationError,
            FenjingPromptError,
            RetryExceededError,
        ]
        
        for exc_class in exceptions:
            assert issubclass(exc_class, Exception), \
                f"{exc_class.__name__} 应该继承自 Exception"

    def test_can_catch_all_workflow_errors(self) -> None:
        """测试可以用 WorkflowRuntimeError 捕获所有子类异常"""
        errors = [
            ImageGenerationError("test", prompt_text="p"),
            FenjingPromptError("test", chapter="c"),
            RetryExceededError("test", attempts=3),
        ]
        
        for error in errors:
            try:
                raise error
            except WorkflowRuntimeError as e:
                assert type(e) == type(error), "应正确捕获具体异常类型"


class TestExceptionUsage:
    """测试异常使用场景"""

    def test_image_generation_error_usage(self) -> None:
        """测试 ImageGenerationError 使用场景"""
        try:
            raise ImageGenerationError(
                "Failed to generate image",
                prompt_text="a beautiful landscape",
                cause=ValueError("API error")
            )
        except ImageGenerationError as e:
            assert "Failed to generate image" in str(e)
            assert e.prompt_text == "a beautiful landscape"
            assert isinstance(e.cause, ValueError)

    def test_fenjing_prompt_error_usage(self) -> None:
        """测试 FenjingPromptError 使用场景"""
        try:
            raise FenjingPromptError(
                "Failed to generate fenjing prompts",
                chapter="chapter_5",
                cause=RuntimeError("LLM error")
            )
        except FenjingPromptError as e:
            assert "Failed to generate fenjing prompts" in str(e)
            assert e.chapter == "chapter_5"
            assert isinstance(e.cause, RuntimeError)

    def test_retry_exceeded_error_usage(self) -> None:
        """测试 RetryExceededError 使用场景"""
        try:
            raise RetryExceededError(
                "Max retry attempts reached",
                attempts=5,
                cause=ConnectionError("Timeout")
            )
        except RetryExceededError as e:
            assert "Max retry attempts reached" in str(e)
            assert e.attempts == 5
            assert isinstance(e.cause, ConnectionError)


class TestExceptionAttributes:
    """测试异常属性"""

    def test_all_exceptions_have_required_attributes(self) -> None:
        """测试所有异常都有必需的属性"""
        # ImageGenerationError
        img_error = ImageGenerationError("test")
        assert hasattr(img_error, 'prompt_text')
        assert hasattr(img_error, 'cause')

        # FenjingPromptError
        fenjing_error = FenjingPromptError("test")
        assert hasattr(fenjing_error, 'chapter')
        assert hasattr(fenjing_error, 'cause')

        # RetryExceededError
        retry_error = RetryExceededError("test", attempts=3)
        assert hasattr(retry_error, 'attempts')
        assert hasattr(retry_error, 'cause')

    def test_exception_args(self) -> None:
        """测试异常参数"""
        error = WorkflowRuntimeError("test message")
        assert error.args == ("test message",)

        error2 = ImageGenerationError("test message")
        assert error2.args == ("test message",)
