"""异步请求频率（RPM）限速器。

实现为“匀速令牌闸门”：rpm>0 时令牌容量固定为 1，令牌按 rpm/60 的速度
补充。任何时刻最多放行一个即时请求，其余请求按速率均匀排队，因此在任意
60 秒窗口内的请求数不会超过 rpm（对 MiMo 这类“100 请求/分钟”的滚动窗口
限流最安全，不会因瞬时突发触发 429）。

rpm <= 0 表示不限制（acquire 立即返回）。
"""

import asyncio
import time


class AsyncRateLimiter:
    """每分钟最多 rpm 次 acquire 通过的匀速限速器。"""

    def __init__(self, rpm: int = 0):
        self._rpm = max(0, int(rpm or 0))
        self._rate = self._rpm / 60.0  # 每秒补充的令牌数
        self._capacity = 1.0  # 匀速闸门：不允许突发，避免超出滚动窗口配额
        self._tokens = self._capacity
        self._updated = time.monotonic()
        self._lock = asyncio.Lock()

    @property
    def rpm(self) -> int:
        return self._rpm

    async def acquire(self) -> None:
        if self._rpm <= 0:
            return
        while True:
            async with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                wait = (1.0 - self._tokens) / self._rate
            await asyncio.sleep(wait)

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._updated
        if elapsed > 0:
            self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
            self._updated = now
