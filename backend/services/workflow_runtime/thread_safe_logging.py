"""
线程安全日志系统

解决多线程环境下 redirect_stdout 导致的 "I/O operation on closed file" 错误
"""
import sys
import threading
from pathlib import Path
from typing import Any, Dict, Optional


# 线程本地存储，用于保存每个线程的日志路径
_thread_local = threading.local()


class ThreadSafeLogManager:
    """线程安全的日志管理器
    
    为每个线程维护独立的日志文件句柄，避免多线程竞争导致的文件关闭问题。
    """
    
    def __init__(self):
        self._handles: Dict[int, Dict[str, Any]] = {}
        self._lock = threading.Lock()
    
    def get_handle(self, log_path: Path) -> Any:
        """获取当前线程的日志文件句柄"""
        thread_id = threading.current_thread().ident
        key = str(log_path)
        
        with self._lock:
            if thread_id not in self._handles:
                self._handles[thread_id] = {}
            
            if key not in self._handles[thread_id]:
                # 以追加模式打开文件
                f = log_path.open("a", encoding="utf-8")
                self._handles[thread_id][key] = f
            
            return self._handles[thread_id][key]
    
    def write(self, log_path: Path, message: str) -> None:
        """写入日志消息"""
        try:
            f = self.get_handle(log_path)
            f.write(message + "\n")
            f.flush()
        except Exception:
            # 如果写入失败，回退到原始stdout
            try:
                sys.__stdout__.write(message + "\n")
                sys.__stdout__.flush()
            except (IOError, OSError, ValueError):
                pass
    
    def close_thread_handles(self) -> None:
        """关闭当前线程的所有日志句柄"""
        thread_id = threading.current_thread().ident
        with self._lock:
            if thread_id in self._handles:
                for f in self._handles[thread_id].values():
                    try:
                        f.close()
                    except Exception:
                        pass
                del self._handles[thread_id]
    
    def close_all(self) -> None:
        """关闭所有日志句柄（服务器关闭时调用）"""
        with self._lock:
            for handles in self._handles.values():
                for f in handles.values():
                    try:
                        f.close()
                    except Exception:
                        pass
            self._handles.clear()


# 全局日志管理器实例
_log_manager = ThreadSafeLogManager()


class ThreadAwareStdout:
    """线程感知的 stdout 包装器
    
    根据当前线程的日志路径，自动将输出写入到对应的日志文件。
    这个类替代 sys.stdout，所有 print() 调用都会经过这里。
    """
    
    def __init__(self, manager: ThreadSafeLogManager):
        self.manager = manager
        self._original_stdout = sys.__stdout__
    
    def write(self, data: str) -> None:
        """写入数据
        
        如果有设置日志路径，则写入日志文件；否则写入原始 stdout。
        """
        if not data:
            return
        
        # 获取当前线程的日志路径
        log_path = getattr(_thread_local, 'log_path', None)
        
        if log_path:
            # 有日志路径，写入日志文件
            # 按行分割，确保每行都完整写入
            lines = data.split('\n')
            for line in lines:
                if line.strip():  # 只写入非空行
                    self.manager.write(Path(log_path), line)
        else:
            # 没有日志路径，回退到原始 stdout
            self._original_stdout.write(data)
            self._original_stdout.flush()
    
    def flush(self) -> None:
        """刷新缓冲区"""
    
    def isatty(self) -> bool:
        """是否为终端"""
        return False


# 全局线程感知的 stdout 实例
_thread_aware_stdout = ThreadAwareStdout(_log_manager)


class ThreadLogRedirector:
    """线程安全的日志重定向器
    
    使用 threading.local() 来隔离不同线程的日志输出。
    不需要修改 sys.stdout，而是通过线程本地存储来传递日志路径。
    """
    
    def __init__(self, log_path: Path):
        self.log_path = log_path
        self._previous_path: Optional[str] = None
    
    def __enter__(self):
        # 保存之前的日志路径（如果有）
        self._previous_path = getattr(_thread_local, 'log_path', None)
        # 设置当前线程的日志路径
        _thread_local.log_path = str(self.log_path)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # 恢复之前的日志路径
        if self._previous_path is not None:
            _thread_local.log_path = self._previous_path
        else:
            # 如果没有之前的日志路径，删除属性
            if hasattr(_thread_local, 'log_path'):
                delattr(_thread_local, 'log_path')
        return False


def install_thread_aware_stdout() -> None:
    """安装线程感知的 stdout
    
    在应用启动时调用一次，替换 sys.stdout。
    """
    sys.stdout = _thread_aware_stdout
    sys.stderr = _thread_aware_stdout


def uninstall_thread_aware_stdout() -> None:
    """卸载线程感知的 stdout，恢复原始 stdout"""
    sys.stdout = sys.__stdout__
    sys.stderr = sys.__stderr__


def set_thread_log_path(log_path: Path) -> None:
    """设置当前线程的日志路径"""
    _thread_local.log_path = str(log_path)


def clear_thread_log_path() -> None:
    """清除当前线程的日志路径"""
    if hasattr(_thread_local, 'log_path'):
        delattr(_thread_local, 'log_path')


def get_thread_log_path() -> Optional[str]:
    """获取当前线程的日志路径"""
    return getattr(_thread_local, 'log_path', None)


def close_thread_handles() -> None:
    """关闭当前线程的所有日志句柄"""
    _log_manager.close_thread_handles()
