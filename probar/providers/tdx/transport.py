"""通达信 TCP 传输层 —— 在自写协议客户端(:class:`._protocol.TdxClient`)之上做服务器池与容错。

职责:
  - **服务器池 + 业务探针**:连上后真拉固定标的行情校验"数据可信",坏服务器跳过;
  - **失败降级换服务器**:请求失败把当前服务器降到队尾、换一台重试;
  - **统一错误**:连接/全部不可用 -> :class:`NetworkError`;判空交给上层 parser;
  - **限流**:复用 :class:`TokenBucket`;请求串行化(线程锁)。

零第三方依赖(纯 stdlib 协议实现)。
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from ...core.errors import NetworkError
from ...core.rate_limit import TokenBucket
from ._protocol import TdxClient, TdxProtocolError
from .servers import DEFAULT_SERVERS

# 业务探针标的:连上服务器后真拉这两只校验"能返回有效行情"(而非仅 ping 通)
_PROBE: list[tuple[int, str]] = [(0, "000001"), (1, "600519")]
MAX_PER_REQUEST = 80  # 单请求最多约 80 只,超过自动分批


class TdxTransport:
    """持有一条到某台行情服务器的连接;失效时按服务器池降级换台。请求串行化(线程安全)。"""

    def __init__(
        self,
        *,
        timeout: float = 5.0,
        rate: float = 10.0,
        servers: list[tuple[str, int]] | None = None,
    ) -> None:
        self._timeout = timeout
        self._bucket = TokenBucket(rate)
        self._servers = list(servers) if servers else list(DEFAULT_SERVERS)
        self._client: TdxClient | None = None
        self._addr: tuple[str, int] | None = None
        self._lock = threading.Lock()

    # ---- 连接管理 ----
    @staticmethod
    def _safe_disconnect(client: TdxClient) -> None:
        try:
            client.disconnect()
        except Exception:  # noqa: BLE001 —— 关闭尽力而为,异常无所谓
            pass

    def _connect_one(self, host: str, port: int) -> TdxClient | None:
        """连一台并做业务探针;通过返回 client,否则断开并返回 None(调用方继续试下一台)。"""
        client = TdxClient(timeout=self._timeout)
        try:
            if not client.connect(host, port):
                return None
            rows = client.get_security_quotes(_PROBE)  # 业务探针:挡掉"端口通但数据坏"
            # 两只探针都返回且为正价才算可信
            ok = len(rows) >= len(_PROBE) and all(float(r.get("price") or 0) > 0 for r in rows)
        except (OSError, TdxProtocolError):
            self._safe_disconnect(client)  # 连接/帧异常:这台坏,换下一台
            return None
        except Exception:
            self._safe_disconnect(client)  # 解码/schema 等确定性错误:先关连接,再如实上抛(不掩盖)
            raise
        if not ok:
            self._safe_disconnect(client)
            return None
        return client

    def _ensure(self) -> TdxClient:
        if self._client is not None:
            return self._client
        tried: list[str] = []
        for host, port in self._servers:
            client = self._connect_one(host, port)
            if client is not None:
                self._client, self._addr = client, (host, port)
                return client
            tried.append(f"{host}:{port}")
        raise NetworkError(
            f"通达信:{len(self._servers)} 台服务器均不可用(已试 {', '.join(tried[:5])} …)"
        )

    def _reset(self) -> None:
        if self._client is not None:
            self._safe_disconnect(self._client)
        self._client, self._addr = None, None

    def _demote_current(self) -> None:
        """把当前服务器降级到队尾并断开,使下次 _ensure 选到不同的一台。"""
        addr = self._addr
        if addr is not None and addr in self._servers:
            self._servers.remove(addr)
            self._servers.append(addr)
        self._reset()

    # ---- 请求 ----
    def get_security_quotes(self, market_code: list[tuple[int, str]]) -> list[dict[str, Any]]:
        """限流 + 失败换服务器地拉批量行情;超上限自动分批;全部失败抛 :class:`NetworkError`。"""
        if not market_code:
            return []
        with self._lock:
            out: list[dict[str, Any]] = []
            for start in range(0, len(market_code), MAX_PER_REQUEST):
                out.extend(self._fetch_quotes(market_code[start : start + MAX_PER_REQUEST]))
            return out

    def _fetch_quotes(self, chunk: list[tuple[int, str]]) -> list[dict[str, Any]]:
        return self._with_retry(lambda c: c.get_security_quotes(chunk))

    def get_security_count(self, market: int) -> int:
        """拉某市场证券数量(失败换服务器)。"""
        with self._lock:
            return self._with_retry(lambda c: c.get_security_count(market))

    def get_security_list(self, market: int, start: int) -> list[dict[str, Any]]:
        """拉某市场证券列表的一页(失败换服务器)。"""
        with self._lock:
            return self._with_retry(lambda c: c.get_security_list(market, start))

    def get_security_bars(
        self, category: int, market: int, code: str, start: int, count: int
    ) -> list[dict[str, Any]]:
        """拉一页 K 线 bar(失败换服务器)。"""
        with self._lock:
            return self._with_retry(
                lambda c: c.get_security_bars(category, market, code, start, count)
            )

    def get_xdxr_info(self, market: int, code: str) -> list[dict[str, Any]]:
        """拉除权除息信息(失败换服务器)。"""
        with self._lock:
            return self._with_retry(lambda c: c.get_xdxr_info(market, code))

    def get_transaction_data(
        self, market: int, code: str, start: int, count: int
    ) -> list[dict[str, Any]]:
        """拉一页当日逐笔成交(失败换服务器)。"""
        with self._lock:
            return self._with_retry(
                lambda c: c.get_transaction_data(market, code, start, count)
            )

    def get_history_transaction_data(
        self, market: int, code: str, date: int, start: int, count: int
    ) -> list[dict[str, Any]]:
        """拉一页历史逐笔成交(失败换服务器)。"""
        with self._lock:
            return self._with_retry(
                lambda c: c.get_history_transaction_data(market, code, date, start, count)
            )

    def _with_retry(self, call: Callable[[TdxClient], Any]) -> Any:
        """执行一次请求;仅连接/帧异常时降级换服务器重试(最多几台);解码/Schema 类如实上抛。

        每次失败把当前服务器降到队尾,确保下次 _ensure 真换一台;底层异常细节不外泄(走 cause 链)。
        """
        last: Exception | None = None
        for _ in range(min(3, len(self._servers))):
            client = self._ensure()
            self._bucket.acquire()
            try:
                return call(client)
            except (OSError, TdxProtocolError) as e:
                last = e
                self._demote_current()
        raise NetworkError("通达信请求失败(已换多台服务器重试)") from last

    @property
    def server(self) -> tuple[str, int] | None:
        """当前所用服务器 ``(host, port)``;未连接为 None。"""
        return self._addr

    def close(self) -> None:
        with self._lock:
            self._reset()
