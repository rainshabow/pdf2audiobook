import asyncio
import time

import pytest

from app.services.ratelimit import AsyncRateLimiter


@pytest.mark.asyncio
async def test_rpm_zero_is_unlimited():
    limiter = AsyncRateLimiter(rpm=0)
    t0 = time.monotonic()
    for _ in range(200):
        await limiter.acquire()
    assert time.monotonic() - t0 < 0.5


@pytest.mark.asyncio
async def test_rate_limiter_paces_sequentially():
    # 1200 RPM = 20 请求/秒 → 两次请求间隔约 0.05s
    limiter = AsyncRateLimiter(rpm=1200)
    await limiter.acquire()  # 首个立即放行
    t0 = time.monotonic()
    await limiter.acquire()
    waited = time.monotonic() - t0
    assert waited >= 0.04


@pytest.mark.asyncio
async def test_concurrent_acquires_share_token_gate():
    limiter = AsyncRateLimiter(rpm=1200)
    t0 = time.monotonic()
    await asyncio.gather(limiter.acquire(), limiter.acquire())
    # 两个并发请求共享 1 个令牌：整体至少等待一个令牌间隔
    assert time.monotonic() - t0 >= 0.04
