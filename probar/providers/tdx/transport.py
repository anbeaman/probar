"""通达信 TCP 传输层 —— 把 pytdx 封在身后,只暴露 probar 自己的接口与错误模型。

设计要点(与 Codex 评审一致):
  - **lazy import pytdx**:没装 ``probar[tdx]`` 时给清晰安装指引(NotSupported),
    而不是在 ``import probar`` 时就炸;
  - **服务器池 + 业务探针**:连上后真拉一笔固定标的行情校验"数据可信",坏服务器自动跳过;
  - **统一错误**:连接/超时/全部不可用 -> :class:`NetworkError`;判空交给上层 parser;
  - **限流**:复用 :class:`TokenBucket`,对 TDX 友好访问;
  - **隔离**:pytdx 的对象 / 异常 / market 数字编码不外泄,domain 层只见 ``list[dict]``;
    pytdx 可随时被替换(vendor / clean-room)而不动上层。
"""

from __future__ import annotations

import threading
from typing import Any

from ...core.errors import NetworkError, NotSupported
from ...core.rate_limit import TokenBucket
from .servers import DEFAULT_SERVERS

# 业务探针标的:连上服务器后真拉这两只校验"能返回有效行情"(而非仅 ping 通)
_PROBE: list[tuple[int, str]] = [(0, "000001"), (1, "600519")]
# pytdx 单次 get_security_quotes 上限约 80 只
MAX_PER_REQUEST = 80


def _load_pytdx() -> Any:
    """延迟加载 pytdx;未安装时给出清晰的 extra 安装指引。"""
    try:
        from pytdx.hq import TdxHq_API
    except ImportError as e:
        raise NotSupported(
            "通达信接口需要可选依赖 pytdx:请执行 `pip install probar[tdx]`"
        ) from e
    return TdxHq_API


class TdxTransport:
    """持有一条到某台行情服务器的连接;失效时按服务器池重连。请求串行化(线程安全)。"""

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
        self._api: Any = None
        self._addr: tuple[str, int] | None = None
        self._lock = threading.Lock()

    # ---- 连接管理 ----
    @staticmethod
    def _safe_disconnect(api: Any) -> None:
        try:
            api.disconnect()
        except Exception:  # noqa: BLE001 —— 关闭尽力而为,异常无所谓
            pass

    def _connect_one(self, api_cls: Any, host: str, port: int) -> Any | None:
        """连一台并做业务探针;通过返回 api,否则断开并返回 None(调用方继续试下一台)。"""
        api = api_cls()
        try:
            if not api.connect(host, port, time_out=self._timeout):
                self._safe_disconnect(api)
                return None
            q = api.get_security_quotes(_PROBE)  # 业务探针:挡掉"端口通但数据坏"
            rows = [dict(r) for r in (q or [])]
            # 两只探针都返回且为正价才算可信;任何异常值(非数值/None)都按坏服务器跳过
            ok = len(rows) >= len(_PROBE) and all(float(r.get("price") or 0) > 0 for r in rows)
        except Exception:  # noqa: BLE001 —— pytdx 异常类型不稳定 / 探针值异常,均换下一台
            self._safe_disconnect(api)
            return None
        if not ok:
            self._safe_disconnect(api)
            return None
        return api

    def _ensure(self) -> Any:
        if self._api is not None:
            return self._api
        api_cls = _load_pytdx()
        tried: list[str] = []
        for host, port in self._servers:
            api = self._connect_one(api_cls, host, port)
            if api is not None:
                self._api, self._addr = api, (host, port)
                return api
            tried.append(f"{host}:{port}")
        raise NetworkError(
            f"通达信:{len(self._servers)} 台服务器均不可用(已试 {', '.join(tried[:5])} …)"
        )

    def _reset(self) -> None:
        if self._api is not None:
            self._safe_disconnect(self._api)
        self._api, self._addr = None, None

    # ---- 请求 ----
    def get_security_quotes(self, market_code: list[tuple[int, str]]) -> list[dict[str, Any]]:
        """限流 + 失败换服务器地拉批量行情,返回 ``list[dict]``(pytdx 原始字段)。

        超过单请求上限的自动分批。全部服务器失败抛 :class:`NetworkError`。
        """
        if not market_code:
            return []
        with self._lock:
            out: list[dict[str, Any]] = []
            for start in range(0, len(market_code), MAX_PER_REQUEST):
                chunk = market_code[start : start + MAX_PER_REQUEST]
                out.extend(self._request_chunk(chunk))
            return out

    def _request_chunk(self, chunk: list[tuple[int, str]]) -> list[dict[str, Any]]:
        last: Exception | None = None
        # 最多试几台**不同**服务器:每次失败把当前服务器降级到队尾,确保下次 _ensure 真换一台
        for _ in range(min(3, len(self._servers))):
            api = self._ensure()
            self._bucket.acquire()
            try:
                q = api.get_security_quotes(chunk)
                return [dict(r) for r in (q or [])]
            except Exception as e:  # noqa: BLE001 —— pytdx 异常类型不稳定,降级换服务器重试
                last = e
                self._demote_current()
        # 不外泄 pytdx 异常细节:概括原因,底层 cause 走异常链(traceback 可见,str 干净)
        raise NetworkError("通达信 get_security_quotes 失败(已换多台服务器重试)") from last

    def _demote_current(self) -> None:
        """把当前服务器降级到队尾并断开,使下次 _ensure 选到不同的一台。"""
        addr = self._addr
        if addr is not None and addr in self._servers:
            self._servers.remove(addr)
            self._servers.append(addr)
        self._reset()

    @property
    def server(self) -> tuple[str, int] | None:
        """当前所用服务器 ``(host, port)``;未连接为 None。"""
        return self._addr

    def close(self) -> None:
        with self._lock:
            self._reset()
