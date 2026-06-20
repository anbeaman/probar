"""线程安全的令牌桶限流器,用于对每个数据源做"友好爬取",降低被限频/封 IP 的风险。"""

from __future__ import annotations

import threading
import time


class TokenBucket:
    """经典令牌桶。``rate`` 为每秒补充的令牌数,``capacity`` 为桶容量(默认等于 rate)。"""

    def __init__(self, rate: float, capacity: float | None = None) -> None:
        if rate <= 0:
            raise ValueError(f"rate 必须 > 0,得到 {rate!r}")
        self.rate = float(rate)
        # 容量至少为 1,否则低频限流(rate<1)下 acquire(1) 永远取不到令牌而死锁
        self.capacity = float(capacity if capacity is not None else max(rate, 1.0))
        self._tokens = self.capacity
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self, n: float = 1.0) -> None:
        """阻塞直到取到 ``n`` 个令牌。``n`` 超过桶容量会永远取不到,直接报错。"""
        if n > self.capacity:
            raise ValueError(f"单次请求 {n} 个令牌超过桶容量 {self.capacity}")
        while True:
            with self._lock:
                now = time.monotonic()
                self._tokens = min(self.capacity, self._tokens + (now - self._last) * self.rate)
                self._last = now
                if self._tokens >= n:
                    self._tokens -= n
                    return
                wait = (n - self._tokens) / self.rate
            time.sleep(wait)
