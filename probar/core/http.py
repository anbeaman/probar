"""基于 httpx 的同步 HTTP 传输层:统一超时、限流、退避重试、默认请求头。

只负责"把请求安全地发出去、把 JSON 拿回来",不关心字段语义(解析交给各 provider)。
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from .errors import NetworkError, RateLimited
from .rate_limit import TokenBucket

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "*/*",
}


class HttpClient:
    def __init__(
        self,
        *,
        timeout: float = 8.0,
        rate: float = 10.0,
        proxy: str | None = None,
        headers: dict[str, str] | None = None,
        retries: int = 3,
    ) -> None:
        self._bucket = TokenBucket(rate)
        self._retries = max(1, retries)
        client_kwargs: dict[str, Any] = {
            "timeout": timeout,
            "headers": {**DEFAULT_HEADERS, **(headers or {})},
            "follow_redirects": True,
        }
        if proxy:  # 仅在显式传入时才加,避免老版 httpx 不识别 proxy/proxies 之别
            client_kwargs["proxy"] = proxy
        self._client = httpx.Client(**client_kwargs)

    def get_json(
        self, url: str, params: dict[str, Any] | None = None, *, referer: str | None = None
    ) -> Any:
        """限流 + 重试地发起 GET 并解析 JSON。失败穷尽重试后抛 :class:`NetworkError`。"""
        headers = {"Referer": referer} if referer else None
        last_err: Exception | None = None
        for attempt in range(self._retries):
            self._bucket.acquire()
            try:
                resp = self._client.get(url, params=params, headers=headers)
                if resp.status_code == 429:
                    raise RateLimited(f"429 Too Many Requests: {url}")
                resp.raise_for_status()
                # 非 JSON(被 WAF 拦截返回 HTML 等)时 .json() 抛 ValueError,纳入重试与分类
                return resp.json()
            except RateLimited:
                raise
            except (httpx.TransportError, httpx.HTTPStatusError, ValueError) as err:
                last_err = err
                time.sleep(0.3 * (attempt + 1))
        raise NetworkError(f"GET {url} 失败(已重试 {self._retries} 次): {last_err!r}")

    def close(self) -> None:
        self._client.close()
