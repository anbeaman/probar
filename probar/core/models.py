"""数据契约(统一核心 schema)。

设计取舍:大表行情**不做逐行 pydantic 校验**,只用轻量的
"列存在 + dtype" 断言;严格校验留给 canary / ``validate=True``。各源同名接口返回
同一套**核心列**,源特有的额外字段放进 ``df.attrs['extras']`` 或 ``raw``。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from .errors import SchemaChanged

if TYPE_CHECKING:
    import pandas as pd

# 同名接口的核心列契约(跨源一致)
KLINE_COLUMNS = [
    "symbol",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "pct_chg",
    "turnover",
]

QUOTE_COLUMNS = [
    "symbol",
    "name",
    "price",
    "open",
    "high",
    "low",
    "prev_close",
    "volume",
    "amount",
    "pct_chg",
]

# 全市场证券列表(securities)
SECURITIES_COLUMNS = ["symbol", "code", "name", "market", "asset_type"]

# 通达信实时五档快照(quote):核心列 + L1 盘口五档 + 内外盘/现手/服务器时间。
# name 恒为 None(TDX 行情协议不返回名称);inner_vol/outer_vol 为内盘/外盘。
TDX_QUOTE_COLUMNS = [
    *QUOTE_COLUMNS,  # symbol,name,price,open,high,low,prev_close,volume,amount,pct_chg
    "bid1", "bid_vol1", "ask1", "ask_vol1",
    "bid2", "bid_vol2", "ask2", "ask_vol2",
    "bid3", "bid_vol3", "ask3", "ask_vol3",
    "bid4", "bid_vol4", "ask4", "ask_vol4",
    "bid5", "bid_vol5", "ask5", "ask_vol5",
    "cur_vol", "inner_vol", "outer_vol", "servertime",
]


def ensure_columns(
    df: pd.DataFrame, required: Iterable[str], *, source: str, interface: str
) -> pd.DataFrame:
    """校验 DataFrame 至少包含 ``required`` 列,否则抛 :class:`SchemaChanged`。"""
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SchemaChanged(
            f"[{source}.{interface}] 响应缺少字段 {missing};上游接口可能已变更。"
            f" 实得列: {list(df.columns)}"
        )
    return df


def stamp(df: pd.DataFrame, *, source: str, **meta: object) -> pd.DataFrame:
    """在 ``df.attrs`` 写入来源等溯源信息(provenance)。"""
    df.attrs["source"] = source
    for k, v in meta.items():
        df.attrs[k] = v
    return df
