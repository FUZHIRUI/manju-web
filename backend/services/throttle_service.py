import asyncio
import time
from dataclasses import dataclass
from threading import BoundedSemaphore
from typing import Dict, Optional


class TokenBucket:
    def __init__(self, rate: float, capacity: int) -> None:
        self.rate = max(0.0, float(rate))
        self.capacity = max(1, int(capacity))
        self.tokens = float(self.capacity)
        self.last_ts = time.monotonic()
        # 使用线程锁，避免不同事件循环下的 asyncio.Lock 造成跨 loop 问题
        from threading import Lock
        self._thread_lock: Optional[Lock] = Lock()

    async def take(self, tokens: int = 1) -> None:
        if self.rate <= 0:
            return
        needed = max(1, int(tokens))
        missing = 0.0
        # 线程安全地更新令牌状态
        if self._thread_lock:
            self._thread_lock.acquire()
        try:
            now = time.monotonic()
            elapsed = max(0.0, now - self.last_ts)
            if elapsed > 0:
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
                self.last_ts = now
            if self.tokens >= needed:
                self.tokens -= needed
                return
            missing = needed - self.tokens
            self.tokens = 0
        finally:
            if self._thread_lock:
                self._thread_lock.release()
        wait = missing / self.rate if self.rate > 0 else 0
        if wait > 0:
            await asyncio.sleep(wait)


@dataclass
class AsyncLimiter:
    bucket: Optional[TokenBucket]
    semaphore_size: Optional[int]
    # 使用线程信号量实现跨线程并发限制，避免 asyncio.Semaphore 的事件循环绑定问题
    thread_semaphore: Optional[BoundedSemaphore] = None

    async def acquire(self) -> None:
        if self.bucket:
            await self.bucket.take(1)
        if self.thread_semaphore is None and self.semaphore_size and self.semaphore_size > 0:
            self.thread_semaphore = BoundedSemaphore(int(self.semaphore_size))
        if self.thread_semaphore:
            # 线程信号量是同步的，这里放在异步函数中调用没有问题
            self.thread_semaphore.acquire()

    def release(self) -> None:
        if self.thread_semaphore:
            self.thread_semaphore.release()


@dataclass
class StageLimiter:
    semaphore: Optional[BoundedSemaphore]

    def acquire(self) -> None:
        if self.semaphore:
            self.semaphore.acquire()

    def release(self) -> None:
        if self.semaphore:
            self.semaphore.release()


_model_limiters: Dict[str, AsyncLimiter] = {}
_stage_limiters: Dict[str, StageLimiter] = {}


def _build_async_limiter(qps: float, concurrency: int) -> Optional[AsyncLimiter]:
    bucket = None
    if qps and qps > 0:
        bucket = TokenBucket(qps, max(1, int(qps)))
    semaphore_size = int(concurrency) if concurrency and concurrency > 0 else None
    if not bucket and not semaphore_size:
        return None
    return AsyncLimiter(bucket=bucket, semaphore_size=semaphore_size)


def _build_stage_limiter(concurrency: int) -> Optional[StageLimiter]:
    if concurrency and concurrency > 0:
        return StageLimiter(semaphore=BoundedSemaphore(int(concurrency)))
    return None


def configure_model_limiters(model_limits: Dict[str, Dict[str, float]]) -> None:
    _model_limiters.clear()
    for key, values in model_limits.items():
        limiter = _build_async_limiter(values.get("qps", 0), int(values.get("concurrency", 0)))
        if limiter:
            _model_limiters[key] = limiter


def configure_stage_limiters(stage_limits: Dict[str, Dict[str, float]]) -> None:
    _stage_limiters.clear()
    for key, values in stage_limits.items():
        limiter = _build_stage_limiter(int(values.get("concurrency", 0)))
        if limiter:
            _stage_limiters[key] = limiter


def get_model_limiter(model_key: str) -> Optional[AsyncLimiter]:
    return _model_limiters.get(model_key)


def get_stage_limiter(stage_key: str) -> Optional[StageLimiter]:
    return _stage_limiters.get(stage_key)


async def acquire_model_limit(model_key: str) -> Optional[AsyncLimiter]:
    limiter = _model_limiters.get(model_key)
    if limiter:
        await limiter.acquire()
        return limiter
    return None


def acquire_stage_limit(stage_key: str) -> Optional[StageLimiter]:
    limiter = _stage_limiters.get(stage_key)
    if limiter:
        limiter.acquire()
        return limiter
    return None
