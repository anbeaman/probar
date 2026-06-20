"""通达信 Provider —— 绑定到 ``pb.tdx``。

通达信走**二进制 TCP 协议**(默认 7709 标准行情),不复用 HTTP 传输层:底层经
:class:`~probar.providers.tdx.transport.TdxTransport` + 自写协议客户端(clean-room,纯标准库
socket/struct/zlib,**零第三方依赖**)+ 服务器池业务探针。

v0.3 已实现:``quotes`` / ``quote``(批量实时五档,**标杆**,全链路:服务器池 -> 协议 ->
解析 -> 归一)。其余接口已在命名空间中声明(诚实反映能力矩阵),按路线图分批落地,未实现者
抛 :class:`NotImplementedError` 并注明计划版本。

命名空间里**刻意不提供** fund_flow / lhb / hsgt —— 通达信协议无此数据域,访问应得到
AttributeError 而非运行时"不支持"。复权说明:K 线返回原始价,前/后复权由 probar 用
:meth:`xdxr` 自算;逐笔为分笔成交明细,**非交易所 L2 逐笔委托**。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...core import symbols
from ...core.errors import NoData
from ...core.models import QUOTE_COLUMNS, ensure_columns, stamp
from . import parsers

if TYPE_CHECKING:
    import pandas as pd

    from .transport import TdxTransport

_V = "v0.3"
_SCHEMA = "tdx.quote/1"


def _todo(interface: str) -> NotImplementedError:
    return NotImplementedError(f"pb.tdx.{interface} 计划在 {_V} 接入(通达信 TCP 协议 + 服务器池)")


def _native(v: Any) -> Any:
    """把 numpy 标量还原成 Python 原生类型,让单只 quote 的 dict 干净。"""
    return v.item() if hasattr(v, "item") else v


class Tdx:
    name = "tdx"

    def __init__(
        self,
        *,
        timeout: float = 5.0,
        rate: float = 10.0,
        servers: list[tuple[str, int]] | None = None,
    ) -> None:
        self.timeout = timeout
        self.rate = rate
        self.servers = servers  # None -> 内置已验证服务器池(由 canary 定期业务探针刷新)
        self._transport: TdxTransport | None = None

    def __repr__(self) -> str:  # noqa: D105
        return f"<Tdx source='tdx' servers={'auto' if not self.servers else len(self.servers)}>"

    def _t(self) -> TdxTransport:
        """惰性建传输层:``import probar`` / 构造 ``Tdx`` 时不连接、不占用 socket。"""
        if self._transport is None:
            from .transport import TdxTransport

            self._transport = TdxTransport(
                timeout=self.timeout, rate=self.rate, servers=self.servers
            )
        return self._transport

    def close(self) -> None:
        if self._transport is not None:
            self._transport.close()
            self._transport = None

    def __enter__(self):  # noqa: D105
        return self

    def __exit__(self, *exc: object) -> None:  # noqa: D105
        self.close()

    # ---- 行情:已实现(标杆) ----
    def quotes(self, symbol_list: list[str]) -> pd.DataFrame:
        """批量实时五档快照,返回 DataFrame(**标杆接口**)。

        参数:
            symbol_list: 代码列表,如 ["000001.SZ", "600519.SH"];自动分批(每批<=80)。
        返回列(核心 + L1 盘口):
            symbol, name(恒 None,TDX 不返回名称), price, open, high, low,
            prev_close, volume(手), amount(元), pct_chg(%, 由 price/prev_close 算),
            bid1..bid5 / bid_vol1..5 / ask1..ask5 / ask_vol1..5(五档价与量),
            cur_vol(现手), inner_vol(内盘), outer_vol(外盘), servertime(服务器时间)。
        注意:
            - 名称需另用 pb.dc 或 tdx.securities 映射;
            - 停牌/无效代码不会出现在返回里(只返回有数据的);全部无数据抛 NoData。
        示例:
            >>> pb.tdx.quotes(["000001.SZ", "600519.SH"])[["symbol", "price", "bid1", "ask1"]]
                  symbol    price    bid1     ask1
            0  000001.SZ   10.52   10.52    10.53
            1  600519.SH  1215.0  1215.0  1215.28
        """
        if not symbol_list:
            raise ValueError("symbol_list 不能为空")
        req = [symbols.to_tdx(s) for s in symbol_list]
        raw = self._t().get_security_quotes(req)
        df = parsers.parse_quotes(raw)
        ensure_columns(df, QUOTE_COLUMNS, source=self.name, interface="quotes")
        return stamp(df, source=self.name, schema_version=_SCHEMA, server=self._t().server)

    def quote(self, symbol: str) -> dict[str, Any]:
        """单只实时五档快照,返回 dict。批量见 :meth:`quotes`。

        参数: symbol 证券代码,如 "600519.SH"。
        返回 dict: 同 :meth:`quotes` 的列(含五档);无效代码/停牌无数据时抛 NoData。
        示例:
            >>> q = pb.tdx.quote("600519.SH")
            >>> q["price"], q["bid1"], q["ask1"]
            (1215.0, 1215.0, 1215.28)
        """
        sym = str(symbols.normalize(symbol))
        df = self.quotes([symbol])
        row = df[df["symbol"] == sym]   # 按请求的 symbol 取,不盲取首行
        if row.empty:
            raise NoData(f"通达信 quote 无数据: {symbol}")
        return {k: _native(v) for k, v in row.iloc[0].to_dict().items()}

    # ---- 行情:待实现(占位,调用抛 NotImplementedError) ----
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

    # ---- 参考/元数据:待实现 ----
    def xdxr(self, symbol: str) -> pd.DataFrame:
        raise _todo("xdxr")

    def securities(self) -> pd.DataFrame:
        raise _todo("securities")

    def block(self) -> pd.DataFrame:
        raise _todo("block")

    def finance_info(self, symbol: str) -> dict:
        raise _todo("finance_info")
