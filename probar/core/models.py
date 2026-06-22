"""数据契约(统一核心 schema)。

设计取舍:大表行情**不做逐行 pydantic 校验**,只用轻量的
"列存在 + dtype" 断言;严格校验留给 canary / ``validate=True``。各源同名接口**尽量**返回
同一套**核心列**;某源不提供 / probar 自算的字段会从该源删减(如通达信不外泄 name/pct_chg/turnover,
见 ``TDX_QUOTE_COLUMNS`` 与各 client 文档),源特有的额外字段放进 ``df.attrs['extras']`` 或 ``raw``。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from .errors import SchemaChanged

if TYPE_CHECKING:
    import pandas as pd

# 同名接口的列契约(此为**东财 dc 全集**;通达信 tdx 等源会删减自算/恒空列,用各自的 _TDX_* 列表)
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

# 全市场证券列表(securities):只留协议/接口真实字段。
# market(SH/SZ/BJ)已隐含在 symbol 后缀(".SH"/".SZ"/".BJ"),不另列;asset_type 此前恒 "stock"、已删。
SECURITIES_COLUMNS = ["symbol", "code", "name"]

# 通达信实时五档快照(quote):**只含协议真实字段** —— 不含 name(TDX 行情协议不返回名称、
# 恒 None)与 pct_chg(probar 自算,可由 price/prev_close 自行计算)。核心行情 + L1 盘口五档 +
# 内外盘/现手/服务器时间。需要名称用 pb.dc 或 pb.tdx.securities 映射。
TDX_QUOTE_COLUMNS = [
    "symbol", "price", "open", "high", "low", "prev_close", "volume", "amount",
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
