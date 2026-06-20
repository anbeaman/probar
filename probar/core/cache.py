"""极简 TTL 内存缓存。

盘中快照走短 TTL,避免重复请求打爆数据源;历史数据的落盘缓存留待后续版本
(diskcache / sqlite)。
"""

from __future__ import annotations

import threading
import time
from typing import Any


class TTLCache:
    def __init__(self, ttl: float = 2.0, maxsize: int = 4096) -> None:
        self.ttl = ttl
        self.maxsize = maxsize
        self._d: dict[Any, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: Any) -> Any | None:
        with self._lock:
            item = self._d.get(key)
            if item is None:
                return None
            expire, value = item
            if expire < time.monotonic():
                self._d.pop(key, None)
                return None
            return value

    def set(self, key: Any, value: Any, ttl: float | None = None) -> None:
        with self._lock:
            if len(self._d) >= self.maxsize:
                self._d.clear()  # 简单粗暴的逐出策略,scaffold 够用
            self._d[key] = (time.monotonic() + (ttl if ttl is not None else self.ttl), value)
