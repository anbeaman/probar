"""东方财富响应 -> 统一 schema 的纯函数解析器。

刻意做成"无网络、纯函数":输入是已解析的 JSON dict,输出是 DataFrame / dict。
这样可以用冻结样本做确定性离线单测(测 parser,不测网络)。
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from ...core import symbols
from ...core.errors import NoData, SchemaChanged
from ...core.models import KLINE_COLUMNS, QUOTE_COLUMNS, SECURITIES_COLUMNS
from . import endpoints as ep
from .endpoints import KLINE_FIELDS


def parse_kline(payload: dict[str, Any], *, symbol: str) -> pd.DataFrame:
    """解析 K 线接口返回,产出含 :data:`KLINE_COLUMNS` 的 DataFrame。"""
    data = payload.get("data")
    if data is None:
        # rc 非 0 或 data 为 null:东财对停牌/无数据/错误代码都可能返回 data=null
        raise NoData(f"东财 kline 无数据: {symbol}")
    klines = data.get("klines")
    if klines is None:
        raise SchemaChanged(f"东财 kline 响应缺少 'klines' 字段: keys={list(data)}")
    if not klines:
        raise NoData(f"东财 kline 区间无数据: {symbol}")

    rows = []
    for line in klines:
        parts = line.split(",")
        if len(parts) < len(KLINE_FIELDS):
            raise SchemaChanged(
                f"东财 kline 单行字段数={len(parts)},期望>={len(KLINE_FIELDS)}: {line!r}"
            )
        rows.append(dict(zip(KLINE_FIELDS, parts, strict=False)))

    df = pd.DataFrame(rows)
    df["symbol"] = symbol
    df["date"] = pd.to_datetime(df["date"])
    num_cols = ["open", "high", "low", "close", "volume", "amount", "pct_chg", "turnover"]
    for col in num_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    # 收盘价是 K 线最核心字段;若解析后为 NaN,说明上游字段顺序/格式变了,别静默返回脏数据
    if df["close"].isna().any():
        raise SchemaChanged(f"东财 kline 收盘价解析为 NaN,字段格式可能已变更: {symbol}")
    return df[KLINE_COLUMNS]


def parse_quote(payload: dict[str, Any], *, symbol: str) -> dict[str, Any]:
    """解析单只实时快照。东财价格字段为放大整数,按 f59(小数位)还原。"""
    data = payload.get("data")
    if data is None:
        raise NoData(f"东财 quote 无数据: {symbol}")

    decimals = data.get("f59")
    try:
        scale = 10 ** int(decimals)  # 兼容 int / float / 数字字符串
    except (TypeError, ValueError):
        scale = 100

    def price(code: str) -> float | None:
        v = data.get(code)
        if v is None or v == "-":
            return None
        try:
            return round(float(v) / scale, 4)
        except (TypeError, ValueError):
            return None

    name = data.get("f58")
    latest = price("f43")
    if name is None and latest is None:
        raise NoData(f"东财 quote 空响应(无价无名,可能是无效代码): {symbol}")

    return {
        "symbol": symbol,
        "name": name,
        "price": latest,
        "open": price("f46"),
        "high": price("f44"),
        "low": price("f45"),
        "prev_close": price("f60"),
        "volume": data.get("f47"),
        "amount": data.get("f48"),
        "pct_chg": (data.get("f170") / 100 if isinstance(data.get("f170"), (int, float)) else None),
    }


def parse_quotes_batch(payload: dict[str, Any]) -> pd.DataFrame:
    """解析 ulist 批量实时快照(fltt=2,字段已是浮点)-> 含 :data:`QUOTE_COLUMNS` 的 DataFrame。

    字段:f2 现价 / f17 开 / f15 高 / f16 低 / f18 昨收 / f5 量(手)/ f6 额(元)/ f3 涨跌幅(%)。
    data 为 None -> NoData;缺 diff -> SchemaChanged;f12 非数字 -> SchemaChanged。
    """
    data = payload.get("data")
    if data is None:
        raise NoData("东财 quotes 无数据")
    diff = data.get("diff")
    if diff is None:
        raise SchemaChanged(f"东财 quotes 响应缺少 'diff' 字段: keys={list(data)}")
    items = list(diff.values()) if isinstance(diff, dict) else diff
    if not items:
        raise NoData("东财 quotes 无数据(请求的代码均无返回)")

    def _num(v: Any) -> float | None:
        if v is None or v == "-":
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    rows = []
    for r in items:
        if not isinstance(r, dict):
            raise SchemaChanged(f"东财 quotes diff 元素非对象: {r!r}")
        code = r.get("f12")
        if not code or not str(code).isdigit():
            raise SchemaChanged(f"东财 quotes 行 f12(代码)非法: {r}")
        sym = symbols.normalize(str(code))
        rows.append(
            {
                "symbol": sym.ts_code,
                "name": r.get("f14"),
                "price": _num(r.get("f2")),
                "open": _num(r.get("f17")),
                "high": _num(r.get("f15")),
                "low": _num(r.get("f16")),
                "prev_close": _num(r.get("f18")),
                "volume": _num(r.get("f5")),
                "amount": _num(r.get("f6")),
                "pct_chg": _num(r.get("f3")),
            }
        )
    return pd.DataFrame(rows, columns=QUOTE_COLUMNS)


def _klines_to_df(
    payload: dict[str, Any],
    *,
    key: str,
    fields: list[str],
    numeric: list[str],
    symbol: str,
    interface: str,
) -> pd.DataFrame:
    """通用:东财 ``data[key]`` 里逗号分隔的字符串数组 -> DataFrame。"""
    data = payload.get("data")
    if data is None:
        raise NoData(f"东财 {interface} 无数据: {symbol}")
    lines = data.get(key)
    if lines is None:
        raise SchemaChanged(f"东财 {interface} 响应缺少 '{key}' 字段: keys={list(data)}")
    if not lines:
        raise NoData(f"东财 {interface} 区间无数据: {symbol}")

    rows = []
    for line in lines:
        parts = line.split(",")
        if len(parts) < len(fields):
            raise SchemaChanged(
                f"东财 {interface} 单行字段数={len(parts)},期望>={len(fields)}: {line!r}"
            )
        rows.append(dict(zip(fields, parts, strict=False)))

    df = pd.DataFrame(rows)
    df["symbol"] = symbol
    for col in numeric:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def parse_fflow(payload: dict[str, Any], *, symbol: str) -> pd.DataFrame:
    """解析个股资金流(daykline)。"""
    df = _klines_to_df(
        payload, key="klines", fields=ep.FFLOW_FIELDS, numeric=ep.FFLOW_NUMERIC,
        symbol=symbol, interface="fund_flow",
    )
    df["date"] = pd.to_datetime(df["date"])
    bad = [c for c in ("main", "close", "pct_chg") if df[c].isna().any()]
    if bad:
        raise SchemaChanged(f"东财 fund_flow 字段 {bad} 解析为 NaN,字段格式可能已变更: {symbol}")
    return df[["symbol", "date", *ep.FFLOW_NUMERIC]]


def parse_trends(payload: dict[str, Any], *, symbol: str) -> pd.DataFrame:
    """解析当日分时(trends2)。"""
    df = _klines_to_df(
        payload, key="trends", fields=ep.TRENDS_FIELDS, numeric=ep.TRENDS_NUMERIC,
        symbol=symbol, interface="intraday",
    )
    df["time"] = pd.to_datetime(df["time"])
    return df[["symbol", "time", "open", "high", "low", "close", "volume", "amount", "avg"]]


def parse_datacenter(
    payload: dict[str, Any], *, mapping: dict[str, str], interface: str
) -> pd.DataFrame:
    """解析数据中心(datacenter-web v1)结构化 JSON,按 ``mapping`` 选列重命名。"""
    result = payload.get("result")
    if result is None:
        # datacenter 对"无匹配数据"返回 result=null:或 success=true,或 success=false + code 9201
        # ("查询数据为空")—— 都是**合法无数据**(NoData),不是字段变更。
        msg = str(payload.get("message") or "")
        success = payload.get("success")
        # 合法无数据:success 为真(空结果),或 success 假 + code 9201 + 消息明示"数据为空"
        empty = bool(success) or (
            not success
            and payload.get("code") == 9201
            and ("数据为空" in msg or "无数据" in msg)
        )
        if empty:
            raise NoData(f"东财 {interface} 无数据" + (f": {msg}" if msg else ""))
        raise SchemaChanged(
            f"东财 {interface} 响应异常:result=null 且非已知空数据"
            f"(code={payload.get('code')}, msg={msg})"
        )
    if not isinstance(result, dict) or "data" not in result:
        raise SchemaChanged(f"东财 {interface} 响应缺少 result.data 结构")
    data = result["data"]
    if not data:
        raise NoData(f"东财 {interface} 无数据")
    # 检查**所有行**都含 mapping 字段,避免部分行缺字段被 pandas 静默补 NaN
    missing = [k for k in mapping if not all(k in row for row in data)]
    if missing:
        raise SchemaChanged(f"东财 {interface} 缺少字段 {missing}")
    return pd.DataFrame(data)[list(mapping)].rename(columns=mapping)


def parse_securities(payload: dict[str, Any]) -> pd.DataFrame:
    """解析 clist 全市场列表的**一页** -> [symbol, code, name](只留接口真实字段)。

    交易所已隐含在 symbol 后缀(".SH"/".SZ"/".BJ");首版只含股票,故不再单列 market/asset_type。
    """
    data = payload.get("data")
    if data is None:
        raise NoData("东财 securities 无数据")
    diff = data.get("diff")
    if diff is None:
        raise SchemaChanged(f"东财 securities 响应缺少 'diff' 字段: keys={list(data)}")

    rows = []
    for r in diff:
        code = r.get("f12")
        if not code or not str(code).isdigit():
            raise SchemaChanged(f"东财 securities 行 f12(代码)非法: {r}")
        sym = symbols.normalize(str(code))
        rows.append(
            {
                "symbol": sym.ts_code,
                "code": str(code),
                "name": r.get("f14"),
            }
        )
    return pd.DataFrame(rows, columns=SECURITIES_COLUMNS)


def parse_sector_fund_flow(payload: dict[str, Any], *, kind: str) -> pd.DataFrame:
    """板块资金流榜(clist ``data.diff``)-> DataFrame(按主力净额降序)。

    返回 :data:`endpoints.SECTOR_FFLOW_COLUMNS`:name 板块名 / code 板块代码(BK..)/ pct_chg 涨跌幅% /
    main 主力净额(元)/ super/large/mid/small 各档净额 / main_pct 主力净占比% / lead_stock 领涨股。
    """
    data = payload.get("data")
    if data is None:
        raise NoData(f"东财 sector_fund_flow 无数据: {kind}")
    diff = data.get("diff")
    if diff is None:
        raise SchemaChanged(f"东财 sector_fund_flow 响应缺少 'diff' 字段: keys={list(data)}")
    items = list(diff.values()) if isinstance(diff, dict) else diff
    if not items:
        raise NoData(f"东财 sector_fund_flow 无数据: {kind}")
    rows = []
    for r in items:
        if not isinstance(r, dict) or "f62" not in r:
            raise SchemaChanged(f"东财 sector_fund_flow 行缺主力净额(f62): {r}")
        rows.append({col: r.get(f) for f, col in ep.SECTOR_FFLOW_MAP.items()})
    df = pd.DataFrame(rows, columns=ep.SECTOR_FFLOW_COLUMNS)
    for c in ep.SECTOR_FFLOW_NUMERIC:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if df["main"].isna().all():
        raise SchemaChanged("东财 sector_fund_flow 主力净额全为 NaN,字段可能已变更")
    return df.sort_values("main", ascending=False).reset_index(drop=True)
