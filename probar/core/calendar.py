"""交易日历(占位实现)。

v0.1 仅按工作日粗判;接入交易所节假日表(以及午休/集合竞价时段判断)留待后续版本。
TODO(v0.2): 内置或拉取 SSE/SZSE 节假日数据,补 ``is_open_now`` / ``previous_trading_day``。
"""

from __future__ import annotations

from datetime import date, datetime


def is_trading_day(d: date | datetime | None = None) -> bool:
    """是否为交易日(当前仅排除周末,**未含法定节假日**)。"""
    d = d or date.today()
    if isinstance(d, datetime):
        d = d.date()
    return d.weekday() < 5
