"""Provider 基类:持有共享的 HTTP 传输层与统一配置。

注意:通达信走二进制 TCP 协议,不复用 HTTP 传输层,其 Provider 见 ``tdx`` 子包。
"""

from __future__ import annotations

from ..core.http import HttpClient


class HttpProvider:
    """基于 HTTP/JSON 的数据源基类(东方财富、同花顺)。"""

    name = "base"

    def __init__(
        self,
        *,
        timeout: float = 8.0,
        rate: float = 5.0,  # 默认放缓(友好访问 + 预防东财 push2 突发 IP 封禁;可调高)
        proxy: str | None = None,
    ) -> None:
        self._http = HttpClient(timeout=timeout, rate=rate, proxy=proxy)

    def close(self) -> None:
        self._http.close()

    def __enter__(self):  # noqa: D105
        return self

    def __exit__(self, *exc: object) -> None:  # noqa: D105
        self.close()

    def __repr__(self) -> str:  # noqa: D105
        return f"<{type(self).__name__} source={self.name!r}>"
