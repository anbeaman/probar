"""通达信 Provider —— 绑定到 ``pb.tdx``。

通达信走**二进制 TCP 协议**(默认 7709 标准行情),不复用 HTTP 传输层:底层经
:class:`~probar.providers.tdx.transport.TdxTransport` + 自写协议客户端(clean-room,纯标准库
socket/struct/zlib,**零第三方依赖**)+ 服务器池业务探针。

已实现:``quotes`` / ``quote``(批量实时五档,全链路:服务器池 -> 协议 ->
解析 -> 归一)。其余接口已在命名空间中声明(诚实反映能力矩阵),按路线图分批落地,未实现者
抛 :class:`NotImplementedError` 并注明计划版本。

命名空间里**刻意不提供** fund_flow / lhb / hsgt —— 通达信协议无此数据域,访问应得到
AttributeError 而非运行时"不支持"。复权说明:K 线返回原始价,前/后复权由 probar 用
:meth:`xdxr` 自算;逐笔为分笔成交明细,**非交易所 L2 逐笔委托**。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...core import symbols
from ...core.cache import TTLCache
from ...core.errors import NoData, SchemaChanged
from ...core.models import QUOTE_COLUMNS, SECURITIES_COLUMNS, ensure_columns, stamp
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
        timeout: float = 8.0,
        rate: float = 10.0,
        servers: list[tuple[str, int]] | None = None,
        cache_ttl: float = 3600.0,
    ) -> None:
        self.timeout = timeout
        self.rate = rate
        self.servers = servers  # None -> 内置已验证服务器池(由 canary 定期业务探针刷新)
        self._transport: TdxTransport | None = None
        self._cache: TTLCache = TTLCache(ttl=cache_ttl)  # securities 等慢变全量数据

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

    def securities(self, *, use_cache: bool = True) -> pd.DataFrame:
        """**沪深** A 股代码表,返回 DataFrame(从通达信全品种列表筛出股票)。

        参数: use_cache 是否走 TTL 缓存(默认 True,默认缓存 1h,见 Tdx(cache_ttl=))。
        返回列: symbol, code, name, market(SH/SZ), asset_type(固定 "stock")。
        说明: 通达信按市场分页拉**全品种**(每页 1000)再按代码前缀筛股票,故默认整表缓存;
            `use_cache=False` 强制刷新。名称来自通达信(GBK 解码),与东财可能略有出入(各源独立)。
            **不含北交所**:通达信行情服务器对北交所覆盖不稳定,北交所代码表请用 `pb.dc.securities`。
        示例:
            >>> df = pb.tdx.securities()
            >>> list(df.columns)
            ['symbol', 'code', 'name', 'market', 'asset_type']
        """
        if use_cache:
            cached = self._cache.get("securities")
            if cached is not None:
                return cached.copy(deep=True)  # 防用户原地改写污染缓存
        t = self._t()
        raw: list[dict[str, Any]] = []
        for market in (0, 1):   # 深 / 沪(北交所 TDX 覆盖不稳,见 docstring,交给 pb.dc)
            count = t.get_security_count(market)
            start = 0
            while start < count:
                page = t.get_security_list(market, start)
                if not page:   # 还没到 count 却返回空页 = 异常,别静默返回残表
                    raise SchemaChanged(
                        f"通达信 securities: market {market} 在 {start}/{count} 处返回空页"
                    )
                raw.extend(page)
                start += len(page)
        df = parsers.parse_securities(raw)
        ensure_columns(df, SECURITIES_COLUMNS, source=self.name, interface="securities")
        if not {"SH", "SZ"} <= set(df["market"]):   # 缓存前校验沪深都在,不缓存残表
            raise SchemaChanged(f"通达信 securities 缺市场: 实得 {sorted(set(df['market']))}")
        result = stamp(df, source=self.name, schema_version="tdx.securities/1", coverage="SH+SZ")
        if use_cache:
            self._cache.set("securities", result.copy(deep=True))
        return result

    def block(self) -> pd.DataFrame:
        raise _todo("block")

    def finance_info(self, symbol: str) -> dict:
        raise _todo("finance_info")
