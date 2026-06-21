"""三源能力矩阵 —— 定稿。

这是对三个**数据源本身**能力的参考记录(某源能不能提供某类数据),不是方法清单:
各命名空间(pb.dc/tdx/ths)按路线图暴露其中**已实现或计划实现**的方法子集;
真实可调用的方法以 ``dir(pb.dc)`` / IDE 自动补全为准。


档位:
    FULL ✅   强,可做主实现
    PART 🔸   部分/弱/需二次计算
    SOFT ⚠️   反爬脆,best-effort(同花顺多数能力)
    NONE ❌   无,命名空间里不提供该接口
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

FULL, PART, SOFT, NONE = "✅", "🔸", "⚠️", "❌"

# capability -> {dc, tdx, ths}
CAPABILITIES: dict[str, dict[str, str]] = {
    "实时快照 quote":           {"dc": FULL, "tdx": FULL, "ths": SOFT},
    "五档盘口(仅L1)":           {"dc": FULL, "tdx": FULL, "ths": SOFT},
    "当日分时 intraday":         {"dc": FULL, "tdx": FULL, "ths": SOFT},
    "历史分时 intraday_hist":    {"dc": PART, "tdx": FULL, "ths": SOFT},
    "当日逐笔 ticks":            {"dc": PART, "tdx": FULL, "ths": SOFT},
    "历史逐笔 ticks_hist":       {"dc": NONE, "tdx": FULL, "ths": NONE},
    "K线 日/周/月":              {"dc": FULL, "tdx": FULL, "ths": SOFT},
    "K线 分钟":                  {"dc": PART, "tdx": FULL, "ths": SOFT},
    "前/后复权 adjust":          {"dc": FULL, "tdx": PART, "ths": SOFT},
    "资金流 fund_flow":          {"dc": FULL, "tdx": NONE, "ths": SOFT},
    "龙虎榜 lhb":                {"dc": FULL, "tdx": NONE, "ths": SOFT},
    "北向/沪深港通 hsgt":        {"dc": PART, "tdx": NONE, "ths": SOFT},
    "财务报表/业绩 financials":  {"dc": FULL, "tdx": PART, "ths": SOFT},
    "股东/解禁/分红":            {"dc": FULL, "tdx": PART, "ths": SOFT},
    "板块/概念成分":             {"dc": FULL, "tdx": PART, "ths": SOFT},
    "细粒度概念题材":            {"dc": PART, "tdx": PART, "ths": SOFT},
    "自然语言选股 wencai":       {"dc": NONE, "tdx": NONE, "ths": SOFT},
    "证券代码表 securities":     {"dc": FULL, "tdx": FULL, "ths": PART},
    "除权除息 xdxr":             {"dc": FULL, "tdx": FULL, "ths": SOFT},
    "多市场(港美/期货/基金/转债)": {"dc": FULL, "tdx": PART, "ths": SOFT},
}

# 同花顺整体为反爬 best-effort:内容(题材/问财)是三源最强,但抓取可靠性最低。
NOTES = {
    "ths": "全程反爬(hexin-v),best-effort;问财与细粒度概念题材为其独有价值。",
    "tdx": "无资金流/龙虎榜/北向(协议无此数据域);复权需用 xdxr 自算;逐笔为分笔明细非 L2;"
           "分时数据用 kline(freq='1m')取(未单列 intraday);"
           "financials 仅股本/每股净资产快照(金额报表用 dc)。",
    "dc": "数据最全(实时/复权/资金流/龙虎榜/财报);北向实时盘中已停披露,仅 EOD/额度。",
}


def capabilities() -> pd.DataFrame:
    """返回能力矩阵(行=能力,列=dc/tdx/ths)。"""
    import pandas as pd

    df = pd.DataFrame(CAPABILITIES).T
    df = df[["dc", "tdx", "ths"]]
    df.index.name = "capability"
    return df
