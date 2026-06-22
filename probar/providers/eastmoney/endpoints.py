"""东方财富 push2 接口的 URL 与参数常量。

字段编码(f51..f61 等)较多,集中放这里便于维护;接口一旦变更,canary 会先报警,
改动也集中在本文件 + parsers.py。
"""

from __future__ import annotations

KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
QUOTE_URL = "https://push2.eastmoney.com/api/qt/stock/get"

# 通用 ut 令牌(公开接口常用值)
UT = "fa5fd1943c7b386f172d6893dbfba10b"

# K 线频率 -> klt
KLT = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "60m": 60,
    "1d": 101,
    "1w": 102,
    "1M": 103,
}

# 复权 -> fqt
FQT = {None: 0, "none": 0, "qfq": 1, "hfq": 2}

# K 线返回的 klines 字符串字段顺序(对应 fields2=f51..f61)
KLINE_FIELDS = [
    "date",
    "open",
    "close",
    "high",
    "low",
    "volume",
    "amount",
    "amplitude",
    "pct_chg",
    "change",
    "turnover",
]
KLINE_FIELDS2 = "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
KLINE_FIELDS1 = "f1,f2,f3,f4,f5,f6"

# 实时快照所需字段(单只 stock/get)
QUOTE_FIELDS = "f43,f44,f45,f46,f47,f48,f57,f58,f60,f169,f170,f59"

# ---- 批量实时快照(ulist.np;一次多只,fltt=2 直接返回浮点、免缩放)----
ULIST_URL = "https://push2.eastmoney.com/api/qt/ulist.np/get"
# f12=代码 f13=市场 f14=名称 f2=现价 f3=涨跌幅 f5=成交量(手) f6=成交额(元)
# f15=最高 f16=最低 f17=开盘 f18=昨收
QUOTES_FIELDS = "f12,f13,f14,f2,f3,f5,f6,f15,f16,f17,f18"
QUOTES_MAX_PER_REQ = 100  # 单请求 secid 数上限(保守分批)

# ---- 资金流(个股历史 daykline)----
FFLOW_URL = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
FFLOW_UT = "b2884a393a59ad64002292a3e90d46a5"
FFLOW_FIELDS1 = "f1,f2,f3,f7"
FFLOW_FIELDS2 = "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65"
# 请求 f51..f65(共 15 段);f64/f65 为保留字段,FFLOW_FIELDS 只映射前 13 段(zip 自动截断)。
# klines 字符串字段顺序(净额单位:元;占比单位:%)
FFLOW_FIELDS = [
    "date",
    "main",        # 主力净流入(超大单+大单)
    "small",       # 小单净流入
    "mid",         # 中单净流入
    "large",       # 大单净流入
    "super",       # 超大单净流入
    "main_pct",
    "small_pct",
    "mid_pct",
    "large_pct",
    "super_pct",
    "close",
    "pct_chg",
]
FFLOW_NUMERIC = FFLOW_FIELDS[1:]  # 除 date 外都是数值

# ---- 当日分时(trends2)----
TRENDS_URL = "https://push2his.eastmoney.com/api/qt/stock/trends2/get"
TRENDS_FIELDS1 = "f1,f2,f3,f4,f5,f6,f7,f8"
TRENDS_FIELDS2 = "f51,f52,f53,f54,f55,f56,f57,f58"
TRENDS_FIELDS = ["time", "open", "close", "high", "low", "volume", "amount", "avg"]
TRENDS_NUMERIC = ["open", "close", "high", "low", "volume", "amount", "avg"]

# ---- 数据中心(龙虎榜 / 财务指标等结构化 JSON)----
DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"

# 龙虎榜每日明细字段映射(上游列名 -> 统一列名)
LHB_MAP = {
    "TRADE_DATE": "date",
    "SECURITY_CODE": "code",
    "SECURITY_NAME_ABBR": "name",
    "CLOSE_PRICE": "close",
    "CHANGE_RATE": "change_rate",
    "BILLBOARD_NET_AMT": "net_buy",
    "BILLBOARD_BUY_AMT": "buy",
    "BILLBOARD_SELL_AMT": "sell",
    "BILLBOARD_DEAL_AMT": "deal_amt",
    "TURNOVERRATE": "turnover",
    "ACCUM_AMOUNT": "amount",
    "EXPLANATION": "reason",
}

# 主要财务指标字段映射
FINANCIALS_MAP = {
    "REPORT_DATE": "report_date",
    "EPSJB": "eps",
    "EPSKCJB": "eps_deduct",
    "BPS": "bps",
    "TOTALOPERATEREVE": "revenue",
    "PARENTNETPROFIT": "net_profit",
    "TOTALOPERATEREVETZ": "revenue_yoy",
    "PARENTNETPROFITTZ": "profit_yoy",
    "ROEJQ": "roe",
}

# ---- 全市场证券列表(clist)----
CLIST_URL = "https://push2.eastmoney.com/api/qt/clist/get"
# 沪深京 A 股(不含 ETF / 可转债 / 指数;首版只含股票)
SECURITIES_FS = "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23,m:0 t:81 s:2048"
# f12=代码, f13=市场(0深/1沪), f14=名称(market 实际由代码前缀推断,更可靠)
SECURITIES_FIELDS = "f12,f13,f14"
