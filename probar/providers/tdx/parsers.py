"""通达信响应(经 pytdx 解码后的 ``list[dict]``)-> 统一 schema 的纯函数解析器。

刻意做成纯函数:输入是 transport 层拿到的 ``list[dict]``(pytdx ``get_security_quotes``
的输出形态),输出是统一 schema 的 DataFrame。这样可用冻结的真实 fixture 做确定性离线
单测(测 parser、不测网络)。pytdx 的字段名 / market 数字编码只在本层出现,不外泄。
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from ...core import symbols
from ...core.errors import NoData, SchemaChanged
from ...core.models import TDX_QUOTE_COLUMNS

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
    - pct_chg 由 price / last_close 计算(TDX 协议不直接返回涨跌幅)。
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
        price = _num(r.get("price"))
        prev_close = _num(r.get("last_close"))
        pct_chg: float | None = None
        if price is not None and prev_close is not None and prev_close != 0:
            pct_chg = round((price - prev_close) / prev_close * 100, 4)
        row: dict[str, Any] = {
            "symbol": sym.ts_code,
            "name": None,  # TDX 行情协议不返回名称;需要名称用 pb.dc 或 tdx.securities 映射
            "price": price,
            "open": _num(r.get("open")),
            "high": _num(r.get("high")),
            "low": _num(r.get("low")),
            "prev_close": prev_close,
            "volume": r.get("vol"),       # 累计成交量(手)
            "amount": r.get("amount"),    # 累计成交额(元)
            "pct_chg": pct_chg,
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
