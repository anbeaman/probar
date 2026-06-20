# 数据列与单位

跨源**同名接口返回统一的核心列**;源特有的稳定字段会作为额外列(文档登记)。
通用单位约定:**金额=元,成交量=手(1 手 = 100 股),涨跌幅/换手/占比=百分数**(`-2.11` 即 -2.11%)。

## kline / 历史 K 线

| 列 | 含义 | 单位 |
|---|---|---|
| `symbol` | 证券代码(规范化,如 `600519.SH`) | — |
| `date` | 日期/时间 | `datetime` |
| `open/high/low/close` | 开/高/低/收 | 元 |
| `volume` | 成交量 | 手 |
| `amount` | 成交额 | 元 |
| `pct_chg` | 涨跌幅 | % |
| `turnover` | 换手率 | % |

## quote / quotes / 实时快照

`symbol, name, price, open, high, low, prev_close, volume(手), amount(元), pct_chg(%)`。

### pb.tdx.quotes / quote 额外列(L1 五档)

通达信在上述核心列外,额外提供 L1 盘口五档与内外盘(`schema_version = tdx.quote/1`):

| 列 | 含义 | 单位 |
|---|---|---|
| `bid1..bid5` / `ask1..ask5` | 买一~五 / 卖一~五 价 | 元 |
| `bid_vol1..bid_vol5` / `ask_vol1..ask_vol5` | 各档挂单量 | 手 |
| `cur_vol` | 现手(最新一笔) | 手 |
| `inner_vol` / `outer_vol` | 内盘(主动卖) / 外盘(主动买) | 手 |
| `servertime` | 服务器时间,如 `14:59:58.376` | 字符串 |

注:`name` 在通达信侧**恒为 None**(协议不返回名称),需要名称用 `pb.dc` 或 `tdx.securities` 映射。

## intraday / 当日分时

`symbol, time, open, high, low, close, volume(手), amount(元), avg(当日均价, 元)`。

## fund_flow / 资金流

`symbol, date, main, small, mid, large, super`(净额,**元**)、对应 `*_pct`(净占比,**%**)、`close(元), pct_chg(%)`。
口径:`main(主力) = large(大单) + super(超大单)`。

## lhb / 龙虎榜

`date, code, name, close, change_rate(%), net_buy(元), buy(元), sell(元), deal_amt(元), turnover(%), amount(元), reason`。

## financials / 主要财务指标

`symbol, report_date, eps(元), eps_deduct(元), bps(元), revenue(元), net_profit(元), revenue_yoy(%), profit_yoy(%), roe(%)`。

## 溯源 `df.attrs`

`df.attrs` 含 `source`(来源,如 `dc`)等;`pb.tdx.quotes` 还写 `schema_version`、`server`(实际所用服务器 `(host, port)`)。
⚠️ `df.attrs` 不是稳定公共 API(pandas 运算/保存中易丢),仅作调试/溯源,**别用它承载业务必需字段**。
