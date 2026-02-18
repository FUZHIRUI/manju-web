"""
线程安全日志系统测试

验证修复后的代码是否解决了多线程环境下的 "I/O operation on closed file" 问题
"""
import sys
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

# 添加项目根目录到路径
ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "manju_web"))

from backend.services.workflow_runtime.thread_safe_logging import (
    ThreadLogRedirector,
    _log_manager,
)


class TestThreadSafeLogManager:
    """测试 ThreadSafeLogManager"""
    
    def test_single_thread_write(self):
        """测试单线程写入"""
        with TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "test.log"
            _log_manager.write(log_path, "test message")
            
            # 验证写入成功
            assert log_path.exists()
            content = log_path.read_text()
            assert "test message" in content
    
    def test_multi_thread_write(self):
        """测试多线程并发写入不同日志文件"""
        with TemporaryDirectory() as tmpdir:
            log_paths = [Path(tmpdir) / f"test_{i}.log" for i in range(5)]
            messages = [f"message from thread {i}" for i in range(5)]
            
            def write_log(log_path, message):
                for _ in range(10):
                    _log_manager.write(log_path, message)
                    time.sleep(0.01)
            
            threads = []
            for log_path, message in zip(log_paths, messages):
                t = threading.Thread(target=write_log, args=(log_path, message))
                threads.append(t)
                t.start()
            
            for t in threads:
                t.join()
            
            # 验证每个日志文件内容正确
            for log_path, message in zip(log_paths, messages):
                assert log_path.exists()
                content = log_path.read_text()
                assert message in content
                # 确保只有该线程的消息
                assert content.count(message) == 10


class TestThreadLogRedirector:
    """测试 ThreadLogRedirector"""
    
    def test_basic_redirect(self):
        """测试基本的日志重定向"""
        with TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "test.log"
            
            with ThreadLogRedirector(log_path):
                print("test message 1")
                print("test message 2")
            
            # 验证写入成功
            assert log_path.exists()
            content = log_path.read_text()
            assert "test message 1" in content
            assert "test message 2" in content
    
    def test_multi_thread_redirect(self):
        """测试多线程并发重定向"""
        with TemporaryDirectory() as tmpdir:
            log_paths = [Path(tmpdir) / f"test_{i}.log" for i in range(5)]
            
            def redirect_and_print(log_path, thread_id):
                with ThreadLogRedirector(log_path):
                    for i in range(10):
                        print(f"Thread {thread_id} message {i}")
                        time.sleep(0.01)
            
            threads = []
            for i, log_path in enumerate(log_paths):
                t = threading.Thread(target=redirect_and_print, args=(log_path, i))
                threads.append(t)
                t.start()
            
            for t in threads:
                t.join()
            
            # 验证每个日志文件内容正确
            for i, log_path in enumerate(log_paths):
                assert log_path.exists(), f"Log file {log_path} should exist"
                content = log_path.read_text()
                # 确保有该线程的消息
                assert f"Thread {i}" in content
                # 确保只有该线程的消息（10条）
                assert content.count(f"Thread {i}") == 10
    
    def test_nested_redirect(self):
        """测试嵌套重定向不会导致问题"""
        with TemporaryDirectory() as tmpdir:
            log_path1 = Path(tmpdir) / "test1.log"
            log_path2 = Path(tmpdir) / "test2.log"
            
            with ThreadLogRedirector(log_path1):
                print("outer message")
                with ThreadLogRedirector(log_path2):
                    print("inner message")
                print("outer message after inner")
            
            # 验证外层日志
            content1 = log_path1.read_text()
            assert "outer message" in content1
            assert "outer message after inner" in content1
            
            # 验证内层日志
            content2 = log_path2.read_text()
            assert "inner message" in content2
    
    def test_exception_handling(self):
        """测试异常情况下不会导致stdout无法恢复"""
        with TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "test.log"
            original_stdout = sys.stdout
            
            try:
                with ThreadLogRedirector(log_path):
                    print("before exception")
                    raise ValueError("test exception")
            except ValueError:
                pass
            
            # 验证stdout已恢复
            assert sys.stdout is original_stdout
            
            # 验证可以继续使用print
            print("after exception", file=sys.__stdout__)


class TestPrintProtection:
    """测试所有print语句都有保护"""
    
    def test_emit_event_print_protected(self):
        """测试 emit_event 中的 print 有保护"""
        from backend.services.workflow_runtime.provider_runtime import emit_event
        
        # 验证函数存在且可以调用
        try:
            emit_event("INFO", "test", "test_event", "test message")
        except Exception as e:
            pytest.fail(f"emit_event should not raise exception: {e}")
    
    def test_job_repo_print_protected(self):
        """测试 job_repo 中的 print 有保护"""
        from backend.repositories import job_repo
        
        # 验证 log_event 可以调用
        try:
            job_repo.log_event("INFO", "test_event")
        except Exception as e:
            pytest.fail(f"log_event should not raise exception: {e}")


class TestNoRedirectStdoutUsage:
    """测试没有使用 redirect_stdout"""
    
    def test_no_redirect_stdout_in_workflow_service(self):
        """测试 workflow_service.py 中没有 redirect_stdout"""
        workflow_service_path = Path(__file__).resolve().parents[1] / "services" / "workflow_service.py"
        content = workflow_service_path.read_text()
        
        # 不应该有 redirect_stdout 或 redirect_stderr
        assert "redirect_stdout" not in content, "workflow_service.py should not use redirect_stdout"
        assert "redirect_stderr" not in content, "workflow_service.py should not use redirect_stderr"
        
        # 应该使用 ThreadLogRedirector
        assert "ThreadLogRedirector" in content, "workflow_service.py should use ThreadLogRedirector"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
