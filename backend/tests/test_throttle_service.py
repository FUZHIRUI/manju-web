import asyncio

from manju_web.backend.services import throttle_service


def test_configure_and_acquire_model_limiter() -> None:
    throttle_service.configure_model_limiters({"m1": {"qps": 0, "concurrency": 1}})

    async def run() -> None:
        limiter = await throttle_service.acquire_model_limit("m1")
        # 边界：QPS=0 时应退化为仅并发限制
        assert limiter is not None
        limiter.release()

    asyncio.run(run())


def test_stage_limiter() -> None:
    throttle_service.configure_stage_limiters({"s1": {"concurrency": 1}})
    limiter = throttle_service.acquire_stage_limit("s1")
    # 边界：未配置 QPS 也应能获取并发限流器
    assert limiter is not None
    limiter.release()
