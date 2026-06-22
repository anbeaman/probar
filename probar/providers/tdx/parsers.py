"""通达信响应(经协议层 :mod:`._codec` 解码后的 ``list[dict]``)-> 统一 schema 的纯函数解析器。

刻意做成纯函数:输入是协议层 ``get_security_quotes`` 解出的 ``list[dict]``,输出是统一 schema
的 DataFrame。这样可用冻结的真实 fixture 做确定性离线单测(测 parser、不测网络)。TDX 的原始
字段名 / 数字 market 编码只在本层归一,不外泄到公共 API。
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from ...core import symbols
from ...core.errors import NoData, SchemaChanged
from ...core.models import SECURITIES_COLUMNS, TDX_QUOTE_COLUMNS

# 解析必需的关键字段:缺失即视为协议/字段变更(SchemaChanged)。
# 含 bid1/ask1 —— 这是五档接口,缺盘口即说明协议层已变,不该静默返回 None。
_REQUIRED = ("market", "code", "price", "last_close", "bid1", "ask1")
_LEVELS = range(1, 6)


def _num(v: Any) -> float | None:
    """宽松转 float;无法转换(None / '-' / 异常)时返回 None,不抛。"""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_quotes(raw: list[dict[str, Any]]) -> pd.DataFrame:
    """解析批量实时五档快照 -> 含 :data:`TDX_QUOTE_COLUMNS` 的 DataFrame。

    - 空列表 -> :class:`NoData`(请求的代码均无返回);
    - 缺关键字段 -> :class:`SchemaChanged`;
    - market(0/1/2)经 :func:`symbols.from_tdx` 还原为规范 symbol;
    - **只返回协议真实字段**:不含 name(TDX 不返回名称)/ pct_chg(可由 price、prev_close 自算)。
    """
    if not raw:
        raise NoData("通达信 quote 无数据(请求的代码均无返回)")

    rows = []
    for r in raw:
        missing = [k for k in _REQUIRED if k not in r]
        if missing:
            raise SchemaChanged(f"通达信 quote 响应缺少字段 {missing}: 实得 keys={list(r)[:8]}")
        code = r.get("code")
        if code is None or not str(code).isdigit():
            raise SchemaChanged(f"通达信 quote 行 code 非法: {code!r}")
        try:
            sym = symbols.from_tdx(r["market"], str(code))
        except ValueError as e:
            # market 非 0/1/2:归为协议变更,且不把 TDX 的 market 编码语义外泄
            raise SchemaChanged(f"通达信 quote 行 market 非法: {r.get('market')!r}") from e
        row: dict[str, Any] = {
            "symbol": sym.ts_code,
            "price": _num(r.get("price")),
            "open": _num(r.get("open")),
            "high": _num(r.get("high")),
            "low": _num(r.get("low")),
            "prev_close": _num(r.get("last_close")),
            "volume": r.get("vol"),       # 累计成交量(手)
            "amount": r.get("amount"),    # 累计成交额(元)
            "cur_vol": r.get("cur_vol"),  # 现手
            "inner_vol": r.get("s_vol"),  # 内盘(主动卖)
            "outer_vol": r.get("b_vol"),  # 外盘(主动买)
            "servertime": r.get("servertime"),
        }
        for i in _LEVELS:
            row[f"bid{i}"] = _num(r.get(f"bid{i}"))
            row[f"bid_vol{i}"] = r.get(f"bid_vol{i}")
            row[f"ask{i}"] = _num(r.get(f"ask{i}"))
            row[f"ask_vol{i}"] = r.get(f"ask_vol{i}")
        rows.append(row)

    return pd.DataFrame(rows, columns=TDX_QUOTE_COLUMNS)


# A 股股票代码前缀(按 TDX market):用于从全品种列表里筛出股票,排除指数/ETF/债券/回购等
_STOCK_PREFIX: dict[int, tuple[str, ...]] = {
    0: ("000", "001", "002", "003", "300", "301"),   # 深:主板 / 中小 / 创业
    1: ("600", "601", "603", "605", "688", "689"),   # 沪:主板 / 科创(含 689 CDR)
    2: ("43", "83", "87", "88", "92"),               # 北
}


def is_a_share_stock(market: int, code: str) -> bool:
    """该 (market, code) 是否 A 股股票(按代码前缀;排除指数/ETF/债券/回购等)。"""
    return code.startswith(_STOCK_PREFIX.get(market, ()))


def parse_securities(raw: list[dict[str, Any]]) -> pd.DataFrame:
    """全品种列表(已解码)-> 仅 A 股股票的 ``[symbol, code, name, market, asset_type]``。

    TDX ``get_security_list`` 返回市场内**所有品种**(含指数/ETF/债),此处按代码前缀筛出股票;
    market 数字编码经 :func:`symbols.from_tdx` 还原为规范市场,不外泄;按 symbol 去重。
    空列表 / 全被过滤 -> :class:`NoData`。
    """
    rows = []
    seen: set[str] = set()
    for r in raw:
        market, code = r.get("market"), r.get("code")
        if not isinstance(market, int) or not isinstance(code, str) or not code.isdigit():
            raise SchemaChanged(f"通达信 securities 行非法: market={market!r} code={code!r}")
        if not is_a_share_stock(market, code):
            continue
        try:
            sym = symbols.from_tdx(market, code)
        except ValueError as e:
            raise SchemaChanged(f"通达信 securities 行 market 非法: {market!r}") from e
        if sym.ts_code in seen:
            continue
        seen.add(sym.ts_code)
        rows.append(
            {
                "symbol": sym.ts_code,
                "code": code,
                "name": r.get("name"),
                "market": sym.market,
                "asset_type": "stock",
            }
        )
    if not rows:
        raise NoData("通达信 securities 无 A 股股票(品种列表为空或全被过滤)")
    return pd.DataFrame(rows, columns=SECURITIES_COLUMNS)


_MINUTE_FREQS = {"1m", "5m", "15m", "30m", "60m"}

# 通达信 K 线**只返回协议真实字段**:不含 pct_chg(probar 自算,可由 close 自行计算)、
# 也不含 turnover(通达信 K 线协议不提供换手率)。东财 pb.dc.kline 另含这两列(其源数据真有)。
_TDX_KLINE_COLUMNS = ["symbol", "date", "open", "high", "low", "close", "volume", "amount"]


def parse_kline(raw: list[dict[str, Any]], *, symbol: str, freq: str) -> pd.DataFrame:
    """K 线 bar(已解码)-> 含 :data:`_TDX_KLINE_COLUMNS` 的 DataFrame(**原始价**,未复权)。

    - 空 -> :class:`NoData`;
    - volume 由通达信原始**股数**换算为**手**(/100,对齐东财);amount 为元;
    - 日/周/月的 date 归一到零点,分钟级保留时分;
    - **只返回协议真实字段**:不含 pct_chg(可由 close 自算)/ turnover(通达信 K 线不提供)。
    """
    if not raw:
        raise NoData(f"通达信 kline 无数据: {symbol}")
    rows = [
        {
            "symbol": symbol,
            "date": b["datetime"],
            "open": b["open"],
            "high": b["high"],
            "low": b["low"],
            "close": b["close"],
            "volume": b["vol"] / 100.0,   # 股 -> 手
            "amount": b["amount"],
        }
        for b in raw
    ]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    if freq not in _MINUTE_FREQS:
        df["date"] = df["date"].dt.normalize()
    return df[_TDX_KLINE_COLUMNS]


# 指数 K 线:比个股多 up_count/down_count(上涨/下跌家数,指数协议真实返回的市场宽度)
_TDX_INDEX_KLINE_COLUMNS = [
    "symbol", "date", "open", "high", "low", "close", "volume", "amount", "up_count", "down_count",
]


def parse_index_kline(raw: list[dict[str, Any]], *, symbol: str, freq: str) -> pd.DataFrame:
    """指数 K 线 bar(已解码)-> 含 :data:`_TDX_INDEX_KLINE_COLUMNS` 的 DataFrame。

    比个股 kline 多 up_count(上涨家数)/ down_count(下跌家数)——指数协议真实返回的市场宽度;
    同样**只含协议真实字段**(无自算 pct_chg / 恒空 turnover)。日/周/月 date 归零点。
    **注意**:指数成交量协议**已是手**(不同于个股给的是股),故 volume 不再 /100。
    """
    if not raw:
        raise NoData(f"通达信 index_kline 无数据: {symbol}")
    rows = [
        {
            "symbol": symbol,
            "date": b["datetime"],
            "open": b["open"],
            "high": b["high"],
            "low": b["low"],
            "close": b["close"],
            "volume": b["vol"],           # 指数协议成交量已是手,不同于个股的股,不再 /100
            "amount": b["amount"],
            "up_count": b["up_count"],
            "down_count": b["down_count"],
        }
        for b in raw
    ]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    if freq not in _MINUTE_FREQS:
        df["date"] = df["date"].dt.normalize()
    return df[_TDX_INDEX_KLINE_COLUMNS]


_XDXR_COLUMNS = [
    "symbol", "date", "category", "name", "fenhong", "songzhuangu", "peigu", "peigujia", "suogu",
]


def parse_xdxr(raw: list[dict[str, Any]], *, symbol: str) -> pd.DataFrame:
    """除权除息事件(已解码)-> DataFrame。**无任何事件是合法空集 -> 固定列空表**(非 NoData)。

    fenhong 分红(元/10股)、songzhuangu 送转股(股/10股)、peigu 配股(股/10股)、
    peigujia 配股价(元/股)仅 category=1 填充;suogu 缩股比例(category 11/12)。用于复权。
    """
    if not raw:
        return pd.DataFrame(columns=_XDXR_COLUMNS)   # 新股/不分红股无事件,合法空集
    df = pd.DataFrame(raw)
    df.insert(0, "symbol", symbol)
    df["date"] = pd.to_datetime(df["date"])
    return df.reindex(columns=_XDXR_COLUMNS)


def apply_adjust(df: pd.DataFrame, events: list[dict[str, Any]], adjust: str) -> pd.DataFrame:
    """对**原始价** K 线 df 应用前(qfq)/后(hfq)复权;``events`` 为 get_xdxr_info 解码结果。

    除权参考价 = (前收盘×10 - 分红 + 配股×配股价) / (10 + 送转 + 配股),每事件因子 = 前收盘/参考价;
    后复权(hfq)锚定最早、前复权(qfq)锚定最新。仅调 OHLC(量额不动)。
    仅用窗口内、且能取到前收盘的除权除息(category=1)事件。
    """
    df = df.copy()
    factor = pd.Series(1.0, index=df.index)
    cat1 = sorted((e for e in events if e.get("category") == 1), key=lambda e: e["date"])
    for e in cat1:
        ex = pd.Timestamp(e["date"])
        prev = df.loc[df["date"] < ex, "close"]
        if prev.empty:
            continue                                 # 事件在窗口之前,取不到前收盘
        p_prev = float(prev.iloc[-1])
        fenhong = e.get("fenhong") or 0.0
        songzhuangu = e.get("songzhuangu") or 0.0
        peigu = e.get("peigu") or 0.0
        peigujia = e.get("peigujia") or 0.0
        denom = 10.0 + songzhuangu + peigu
        if denom <= 0:
            continue
        ref = (p_prev * 10.0 - fenhong + peigu * peigujia) / denom
        if ref <= 0:
            continue
        factor.loc[df["date"] >= ex] *= p_prev / ref
    if adjust == "qfq":
        factor = factor / factor.iloc[-1]            # 前复权:锚定最新一根 = 原始价
    else:
        factor = factor / factor.iloc[0]             # 后复权:锚定窗口最早一根 = 原始价
    for col in ("open", "high", "low", "close"):
        df[col] = (df[col] * factor).round(3)
    return df


_TICKS_COLUMNS = ["symbol", "time", "price", "vol", "num", "buyorsell"]
_TICKS_HIST_COLUMNS = ["symbol", "date", "time", "price", "vol", "buyorsell"]


def parse_ticks(raw: list[dict[str, Any]], *, symbol: str) -> pd.DataFrame:
    """当日逐笔(已解码)-> DataFrame。空 -> :class:`NoData`。

    time 为分钟级(HH:MM,同分钟可多笔);price 元、vol 手、num 笔数、
    buyorsell(买卖方向,通达信原值:常见 0 买 / 1 卖 / 2 中性,集合竞价等为特殊值)。
    """
    if not raw:
        raise NoData(f"通达信 ticks 无数据: {symbol}")
    df = pd.DataFrame(raw)
    df.insert(0, "symbol", symbol)
    return df.reindex(columns=_TICKS_COLUMNS)


def parse_ticks_hist(raw: list[dict[str, Any]], *, symbol: str, date: str) -> pd.DataFrame:
    """历史逐笔(已解码)-> DataFrame。空 -> :class:`NoData`。

    与当日逐笔同形,但**多 date 列、无 num**(历史协议不返回笔数);date 为查询日(规范化 YYYY-MM-DD)。
    """
    if not raw:
        raise NoData(f"通达信 ticks_hist 无数据: {symbol} {date}")
    df = pd.DataFrame(raw)
    df.insert(0, "date", date)
    df.insert(0, "symbol", symbol)
    return df.reindex(columns=_TICKS_HIST_COLUMNS)


def parse_finance_info(raw: dict[str, Any], *, symbol: str) -> dict[str, Any]:
    """财务快照(已解码)-> dict(前置 symbol)。总股本 <=0(无效/退市/无数据)-> :class:`NoData`。"""
    if not raw or (raw.get("total_shares") or 0) <= 0:
        raise NoData(f"通达信 finance_info 无数据: {symbol}")
    return {"symbol": symbol, **raw}
