"""通达信 Provider —— 绑定到 ``pb.tdx``。

通达信走**二进制 TCP 协议**(默认 7709 标准行情 / 7727 扩展行情),不复用 HTTP 传输层。
v0.2 接入,重点是服务器池 + 业务探针(拉固定股票校验返回长度/时间/价格区间)而非仅 ping。

本类在 v0.1 仅声明**该源真实支持**的接口面(命名空间形态正确),实现抛
:class:`NotImplementedError`。命名空间里**刻意不提供** fund_flow / lhb / hsgt
—— 通达信协议无此数据域,访问应得到 AttributeError 而非运行时"不支持"。

复权说明:K 线返回原始价,前/后复权由 probar 用 :meth:`xdxr`(除权除息)自算。
逐笔为分笔成交明细,**非交易所 L2 逐笔委托**。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

_V = "v0.2"


def _todo(interface: str) -> NotImplementedError:
    return NotImplementedError(f"pb.tdx.{interface} 计划在 {_V} 接入(通达信 TCP 协议 + 服务器池)")


class Tdx:
    name = "tdx"

    def __init__(
        self, *, timeout: float = 5.0, servers: list[tuple[str, int]] | None = None
    ) -> None:
        self.timeout = timeout
        self.servers = servers  # None -> v0.2 使用内置服务器池(由 CI 定期业务探针刷新)

    def __repr__(self) -> str:  # noqa: D105
        return f"<Tdx source='tdx' servers={'auto' if not self.servers else len(self.servers)}>"

    # ---- 行情 ----
    def quote(self, symbol: str) -> dict:
        raise _todo("quote")

    def quotes(self, symbol_list: list[str]) -> pd.DataFrame:
        raise _todo("quotes")

    def kline(self, symbol: str, *, freq: str = "1d", adjust: str | None = None) -> pd.DataFrame:
        raise _todo("kline")

    def intraday(self, symbol: str) -> pd.DataFrame:
        raise _todo("intraday")

    def intraday_hist(self, symbol: str, *, date: str) -> pd.DataFrame:
        raise _todo("intraday_hist")

    def ticks(self, symbol: str) -> pd.DataFrame:
        raise _todo("ticks")

    def ticks_hist(self, symbol: str, *, date: str) -> pd.DataFrame:
        raise _todo("ticks_hist")

    # ---- 参考/元数据 ----
    def xdxr(self, symbol: str) -> pd.DataFrame:
        raise _todo("xdxr")

    def securities(self) -> pd.DataFrame:
        raise _todo("securities")

    def block(self) -> pd.DataFrame:
        raise _todo("block")

    def finance_info(self, symbol: str) -> dict:
        raise _todo("finance_info")
