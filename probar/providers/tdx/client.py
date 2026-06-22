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

import pandas as pd

from ...core import symbols
from ...core.cache import TTLCache
from ...core.errors import NoData, NotSupported, SchemaChanged
from ...core.models import SECURITIES_COLUMNS, TDX_QUOTE_COLUMNS, ensure_columns, stamp
from . import parsers

if TYPE_CHECKING:
    from .transport import TdxTransport

# freq -> 通达信 K 线周期 category
_FREQ_CATEGORY = {"1m": 8, "5m": 0, "15m": 1, "30m": 2, "60m": 3, "1d": 4, "1w": 5, "1M": 6}
_BARS_PER_PAGE = 800   # 单次 get_security_bars 上限
_MAX_OFFSET = 65000    # 通达信 start/offset 为 uint16(<65536);分钟线最深约 6.5 万根
_TICKS_PER_PAGE = 2000  # 单次 get_transaction_data 上限

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
        返回列(只含协议真实字段 + L1 盘口):
            symbol, price, open, high, low, prev_close, volume(手), amount(元),
            bid1..bid5 / bid_vol1..5 / ask1..ask5 / ask_vol1..5(五档价与量),
            cur_vol(现手), inner_vol(内盘), outer_vol(外盘), servertime(服务器时间)。
        注意:
            - 不含 name(TDX 不返回名称,用 pb.dc 或 tdx.securities 映射)、
              不含 pct_chg(可由 price/prev_close 自算);
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
        ensure_columns(df, TDX_QUOTE_COLUMNS, source=self.name, interface="quotes")
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
    def kline(
        self,
        symbol: str,
        *,
        freq: str = "1d",
        adjust: str | None = None,
        start: str | None = None,
        end: str | None = None,
        limit: int = 800,
    ) -> pd.DataFrame:
        """历史 K 线(**原始价**,未复权),返回 DataFrame。

        参数:
            freq:   1m/5m/15m/30m/60m/1d/1w/1M(默认 1d)。
            adjust: None/"none"原始价 / "qfq"前复权 / "hfq"后复权(用除权除息 xdxr 自算)。
            start, end: "YYYY-MM-DD";省略 start 时取最近 limit 根。
            limit:  未给 start 时的最多根数(默认 800)。
        返回列: symbol, date, open, high, low, close, volume(手), amount(元)。
        说明: **只返回协议真实字段**——不含 pct_chg(可由 close 自算)/ turnover(通达信 K 线不提供;
            东财 pb.dc.kline 才有真实换手率)。复权(qfq/hfq)用 xdxr 自算、仅调 OHLC;
            qfq 锚最新一根、hfq 锚窗口最早一根(窗口相对,各源口径不同)。
            面向 A 股**股票**(volume 股数 /100 转手);ETF/可转债"一手"未必 100 股,volume 仅供参考。
            分钟线受协议 offset(uint16)限制,最深约 6.5 万根。
        示例:
            >>> pb.tdx.kline("600519.SH", freq="1d", limit=3)[["date", "close", "volume"]]
        """
        if freq not in _FREQ_CATEGORY:
            raise ValueError(f"不支持的 freq={freq!r},可选: {list(_FREQ_CATEGORY)}")
        if adjust not in (None, "none", "qfq", "hfq"):
            raise ValueError(f"不支持的 adjust={adjust!r},可选: None/'none'/'qfq'/'hfq'")
        if adjust in ("qfq", "hfq") and freq in ("1w", "1M"):
            # 周/月 bar 跨除权日,整根乘一个因子会产出错误复权价 -> 暂不支持
            raise NotSupported("周/月线复权暂不支持(整根 bar 跨除权日);请对日线复权后自行重采样")
        category = _FREQ_CATEGORY[freq]
        if start is not None:
            start = pd.Timestamp(start).strftime("%Y-%m-%d")   # 归一日期,兼容未补零写法
        market, code = symbols.to_tdx(symbol)
        t = self._t()
        raw: list[dict[str, Any]] = []
        offset = 0
        while offset <= _MAX_OFFSET:   # offset 为 uint16,超限即停(分钟线深度上限)
            page = t.get_security_bars(category, market, code, offset, _BARS_PER_PAGE)
            if not page:
                break
            raw = page + raw          # offset 越大越旧,旧页拼前面 -> 整体按时间升序
            offset += len(page)
            if len(page) < _BARS_PER_PAGE:
                break                 # 没有更早的历史了
            # 多取一根前置 bar:保持复权窗口与历史一致(hfq 锚"拉取窗口最早一根");
            # 该前置 bar 在 tail/过滤后被丢弃,不影响 adjust=None 的最近 limit 根
            if start is None:
                if len(raw) > limit:
                    break
            elif raw[0]["datetime"][:10] < start:
                break
        df = parsers.parse_kline(raw, symbol=str(symbols.normalize(symbol)), freq=freq)
        if adjust in ("qfq", "hfq"):   # 用全窗口原始价 + 除权除息事件复权,再过滤
            df = parsers.apply_adjust(df, t.get_xdxr_info(market, code), adjust)
        if start:
            df = df[df["date"] >= pd.Timestamp(start)]
        if end:
            df = df[df["date"] < pd.Timestamp(end) + pd.Timedelta(days=1)]
        if start is None and len(df) > limit:
            df = df.tail(limit)
        if df.empty:
            raise NoData(f"通达信 kline 区间无数据: {symbol}")
        adj = adjust or "none"
        return stamp(df.reset_index(drop=True), source=self.name, freq=freq, adjust=adj)

    def intraday(self, symbol: str) -> pd.DataFrame:
        """**有意不提供**:通达信分时仅 price+vol,已被 `kline(freq="1m")`(含 OHLC+量额)完全覆盖。

        分时需求请用 `pb.tdx.kline(symbol, freq="1m")`,或要均价线用 `pb.dc.intraday`(各源独立)。
        """
        raise NotSupported(
            "pb.tdx.intraday 有意不提供:通达信分时仅 price+vol,"
            "请用 pb.tdx.kline(freq='1m')(含 OHLC+量额)或 pb.dc.intraday(含均价)"
        )

    def intraday_hist(self, symbol: str, *, date: str) -> pd.DataFrame:
        """**有意不提供**:同 :meth:`intraday`;历史分时用 `pb.tdx.kline(freq="1m", …)`。"""
        raise NotSupported(
            "pb.tdx.intraday_hist 有意不提供:请用 "
            "pb.tdx.kline(freq='1m', start=…, end=…) 或 pb.dc.intraday_hist"
        )

    def ticks(self, symbol: str, *, limit: int = 2000) -> pd.DataFrame:
        """当日逐笔成交,返回 DataFrame。

        参数: symbol 证券代码;limit 最多笔数(默认 2000,取最新的;自动分页)。
        返回列: symbol, time(HH:MM,分钟级), price(元), vol(手), num(笔数),
            buyorsell(买卖方向,通达信原值:常见 0 买 / 1 卖 / 2 中性)。
        说明: 当日数据(盘后为最近交易日);同一分钟可有多笔;全无数据抛 NoData。
        示例:
            >>> pb.tdx.ticks("600519.SH", limit=5)[["time", "price", "vol", "buyorsell"]]
        """
        market, code = symbols.to_tdx(symbol)
        t = self._t()
        raw: list[dict[str, Any]] = []
        offset = 0
        while offset <= _MAX_OFFSET:
            page = t.get_transaction_data(market, code, offset, _TICKS_PER_PAGE)
            if not page:
                break
            raw = page + raw          # offset 越大越早,旧页拼前 -> 整体时间升序
            offset += len(page)
            if len(page) < _TICKS_PER_PAGE:
                break
            if len(raw) >= limit:
                break
        df = parsers.parse_ticks(raw, symbol=str(symbols.normalize(symbol)))
        if len(df) > limit:
            df = df.tail(limit).reset_index(drop=True)
        return stamp(df, source=self.name)

    def ticks_hist(
        self, symbol: str, *, date: str, limit: int | None = None
    ) -> pd.DataFrame:
        """历史逐笔成交(指定交易日),返回 DataFrame。

        参数: symbol 证券代码;date 交易日("YYYY-MM-DD" 或 "YYYYMMDD");
            limit 最多笔数(默认 None 取全天;给值则取最新的;自动分页)。
        返回列: symbol, date, time(HH:MM,分钟级), price(元), vol(手),
            buyorsell(买卖方向,通达信原值)。**比当日逐笔少 num 列**(历史协议不返回笔数)。
        说明: 同一分钟可有多笔;该日无成交/非交易日抛 NoData。东财免费源无完整历史逐笔。
        示例:
            >>> pb.tdx.ticks_hist("600519.SH", date="2026-06-19", limit=50)
        """
        d = pd.Timestamp(date)
        date_int = d.year * 10000 + d.month * 100 + d.day
        date_norm = d.strftime("%Y-%m-%d")
        market, code = symbols.to_tdx(symbol)
        t = self._t()
        raw: list[dict[str, Any]] = []
        offset = 0
        while offset <= _MAX_OFFSET:
            page = t.get_history_transaction_data(market, code, date_int, offset, _TICKS_PER_PAGE)
            if not page:
                break
            raw = page + raw          # offset 越大越早,旧页拼前 -> 整体时间升序
            offset += len(page)
            if len(page) < _TICKS_PER_PAGE:
                break
            if limit is not None and len(raw) >= limit:
                break
        df = parsers.parse_ticks_hist(
            raw, symbol=str(symbols.normalize(symbol)), date=date_norm
        )
        if limit is not None and len(df) > limit:
            df = df.tail(limit).reset_index(drop=True)
        return stamp(df, source=self.name)

    # ---- 参考/元数据:待实现 ----
    def xdxr(self, symbol: str) -> pd.DataFrame:
        """除权除息事件(全历史),返回 DataFrame。

        参数: symbol 证券代码。
        返回列: symbol, date, category(类别码), name(类别名), fenhong(分红 元/10股),
            songzhuangu(送转股 股/10股), peigu(配股 股/10股), peigujia(配股价 元), suogu(缩股比)。
        说明: 仅 category=1(除权除息)填分红/送转/配股;无任何事件返回固定列空表。复权接入见路线图。
        示例:
            >>> pb.tdx.xdxr("600519.SH")[["date", "name", "fenhong", "songzhuangu"]].tail(1)
        """
        market, code = symbols.to_tdx(symbol)
        raw = self._t().get_xdxr_info(market, code)
        df = parsers.parse_xdxr(raw, symbol=str(symbols.normalize(symbol)))
        return stamp(df, source=self.name)

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

    def finance_info(self, symbol: str) -> dict[str, Any]:
        """财务快照(股本结构 + 基本面常用字段),返回 dict。

        参数: symbol 证券代码,如 "600519.SH"。
        返回 dict: symbol, float_shares(流通股本,股), total_shares(总股本,股),
            holders(股东人数), bvps(每股净资产,元/股), ipo_date(上市日), report_date(财务更新日)。
        说明: 通达信财务快照,**截至 report_date(非实时)**;份额单位股。
            **只外泄经核验可靠的字段**——通达信本接口的总资产/净资产/营收/利润等金额字段口径混乱
            (常与公告差约 10 倍),刻意不外泄;季度报表(EPS/营收等)请用 pb.dc.financials(各源独立)。
            无效/退市代码抛 NoData。
        示例:
            >>> pb.tdx.finance_info("600519.SH")["total_shares"]
        """
        market, code = symbols.to_tdx(symbol)
        raw = self._t().get_finance_info(market, code)
        info = parsers.parse_finance_info(raw, symbol=str(symbols.normalize(symbol)))
        return {k: _native(v) for k, v in info.items()}
