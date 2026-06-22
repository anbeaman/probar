# 东方财富 `pb.dc`

数据最全(HTTP/JSON),已实现 8 个接口(含 `securities`)。所有 `symbol` 接受 `600519.SH` / `000001.SZ` / `600519` / `SH600519` 等写法;
表格返回 `pandas.DataFrame`,`df.attrs` 带来源等溯源信息。

!!! note "通用注意事项"
    - 非官方接口,已内置限流(默认 **5 req/s**)。该限流是 probar 的**友好访问保护,不是数据源的官方配额/SLA**;
      批量历史 / 财务 / 龙虎榜建议放慢到 **1–3 req/s**,**请勿高频轮询**,以免被限频(`RateLimited`)。
    - 金额单位为**元**,成交量为**手**(1 手 = 100 股),涨跌幅/换手/占比为**百分数**(如 `-2.11` 表示 -2.11%)。
    - 合法但无数据 → 抛 `NoData`;上游字段变更 → 抛 `SchemaChanged`(见 [错误模型](../reference/errors.md))。

!!! warning "东财反爬与取数稳定性(实测)"
    东财 `push2.eastmoney.com`(实时快照 / 批量 / 全市场扫描 `clist`)**对突发请求会 IP 级封禁数分钟**——
    期间该域所有端点直接断连(`Server disconnected`);`push2his`(K 线)/ `datacenter`(龙虎榜、财务)不受影响。
    probar 的应对(`pb.core.http`)是**稳健 + 友好访问**,而非"绕过":

    - **指数退避 + 随机抖动重试**,riding out 单次瞬时断连;
    - **按 host 熔断**:某域连续断连后短时熔断(冷却 ~60s),熔断窗口内对该域调用**快速失败**而非继续捶打
      (硬刚只会空耗重试并延长封禁);
    - 浏览器级请求头、默认放缓到 5 req/s。

    **没有客户端魔法绕过**:编号镜像(`1..N.push2`)同 IP 同封;延迟镜像 `push2delay` 虽可连但**不尊重 `fs` 过滤**
    (查股票却返回板块/基金),数据错配、已否决。**稳定取数的正确姿势**:控制频率、复用缓存
    (`securities()` 自带 TTL 缓存)、被封后等冷却,而不是高频硬刚。

---

## quote — 实时快照

```python
pb.dc.quote(symbol)            # 单只 -> dict
pb.dc.quotes([s1, s2, ...])    # 多只 -> DataFrame(见 quotes)
```

- **参数**:`symbol` 单只代码。
- **返回**(dict):`symbol, name, price(元), open, high, low, prev_close, volume(手), amount(元), pct_chg(%)`。

```python
>>> pb.dc.quote("600519.SH")
{'symbol': '600519.SH', 'name': '贵州茅台', 'price': 1648.0, 'open': 1685.01,
 'high': 1695.0, 'low': 1640.0, 'prev_close': 1683.51, 'volume': 38421,
 'amount': 6398000000.0, 'pct_chg': -2.11}
```

!!! warning "注意"
    停牌时 `price` 可能为 `None`(仍返回昨收等);无效代码会抛 `NoData` 或 `ValueError`。

---

## quotes — 批量快照

```python
pb.dc.quotes(symbol_list)      # -> DataFrame
```

- **参数**:`symbol_list` 代码列表。
- **返回列**:`symbol, name, price, open, high, low, prev_close, volume, amount, pct_chg`。

```python
>>> pb.dc.quotes(["000001.SZ", "600519.SH"])[["symbol", "name", "price", "pct_chg"]]
      symbol  name   price  pct_chg
0  000001.SZ  平安银行   10.52    -2.41
1  600519.SH  贵州茅台 1215.00    -2.02
```

!!! tip "批量端点(抗限频)"
    走 push2 `ulist` **批量端点**,一次请求多只、自动分批(每批 ≤ 100):N 只仅发 ⌈N/100⌉ 次请求,
    远少于逐只循环,**显著降低被限频概率**。取全市场快照可先用 `securities()` 拿代码,再分批 `quotes()`。

---

## kline — 历史 K 线

```python
pb.dc.kline(symbol, freq="1d", adjust="qfq", start=None, end=None, limit=1000)  # -> DataFrame
```

- **参数**:
  - `freq`:`1m / 5m / 15m / 30m / 60m / 1d / 1w / 1M`。
  - `adjust`:`"qfq"` 前复权 / `"hfq"` 后复权 / `None` 不复权。
  - `start` / `end`:`"YYYY-MM-DD"`(或 `"YYYYMMDD"`),省略则取最近 `limit` 根。
  - `limit`:最多根数,默认 1000。
- **返回列**:`symbol, date, open, high, low, close, volume(手), amount(元), pct_chg(%), turnover(%)`。

```python
>>> pb.dc.kline("600519.SH", freq="1d", adjust="qfq", limit=2)
      symbol       date    open   close  volume  pct_chg  turnover
0  600519.SH 2024-01-02  1685.0  1648.0   38421    -2.11      0.31
1  600519.SH 2024-01-03  1650.0  1660.5   29110     0.76      0.23

pb.dc.kline("000001.SZ", freq="5m", limit=240)   # 分钟线
```

!!! warning "注意"
    - **1 分钟历史深度有限**(东财侧限制),要长历史分钟请用 5m 及以上,或用通达信 `pb.tdx.kline`(历史分钟更深)。
    - 复权由东财直接给(一个参数);`pb.tdx` 的复权是 probar 自算——**两源复权口径可能略有差异**,各源数据独立、不互相替换。

---

## intraday — 当日分时

```python
pb.dc.intraday(symbol)         # -> DataFrame
```

- **返回列**:`symbol, time, open, high, low, close, volume(手), amount(元), avg(当日均价, 元)`。
- 每分钟一行,覆盖 9:30–15:00。

```python
>>> pb.dc.intraday("000001.SZ").tail(1)
        symbol                time  close  volume     avg
240  000001.SZ 2024-06-19 15:00  11.18    1788  11.205
```

!!! warning "注意"
    返回的是**最近一个交易日**的分时;盘中调用为当日实时累积。历史某日分时(`intraday_hist`)仍在规划中。

---

## fund_flow — 个股资金流

```python
pb.dc.fund_flow(symbol, days=100)   # -> DataFrame
```

- **参数**:`days` 取最近多少个交易日,默认 100。
- **返回列**(净额单位**元**,占比**%**):
  `symbol, date, main(主力净额), small, mid, large, super(超大单), main_pct, small_pct, mid_pct, large_pct, super_pct, close(元), pct_chg(%)`。
- 口径:`main(主力) = large(大单) + super(超大单)`。

```python
>>> pb.dc.fund_flow("000001.SZ", days=2)[["date", "main", "super", "pct_chg"]]
         date          main          super  pct_chg
0  2026-06-16  -544577072.0  -306740640.0    -1.21
1  2026-06-18  -869933072.0  -590207200.0    -2.02
```

---

## sector_fund_flow — 板块资金流榜(涨跌幅 + 主力资金)

```python
pb.dc.sector_fund_flow("industry")   # 行业板块榜 -> DataFrame
pb.dc.sector_fund_flow("concept")    # 概念板块榜
```

- **参数**:`kind` = `"industry"`(行业,~496 个)/ `"concept"`(概念,~494 个)。
- **返回列**(净额=**元**,涨跌幅/占比=**%**;按主力净额降序):
  `name(板块名), code(板块代码 BK..), pct_chg(涨跌幅), main(主力净额), super(超大单), large(大单), mid(中单), small(小单), main_pct(主力净占比), lead_stock(领涨股)`。
- **一接口给齐板块涨跌幅 + 主力资金分档** —— 这是东财服务端直接算好的。
  **通达信免费协议给不出板块涨跌幅/资金流**(无可报价的板块指数、无资金流域,且免费逐笔是抽样),
  所以板块行情/资金榜走东财(各源数据独立)。

```python
>>> pb.dc.sector_fund_flow("industry").head(2)[["name", "pct_chg", "main", "lead_stock"]]
     name  pct_chg          main lead_stock
0  非银金融     5.52  1.237701e+10       东方财富
1  有色金属     3.88  1.121023e+10       洛阳钼业
```

---

## lhb — 龙虎榜

```python
pb.dc.lhb(date="YYYY-MM-DD")    # -> DataFrame
```

- **参数**:`date` 交易日,**必须** `YYYY-MM-DD`(会严格校验,非法格式抛 `ValueError`)。
- **返回列**:`date, code, name, close, change_rate(%), net_buy(元), buy(元), sell(元), deal_amt(元), turnover(%), amount(元), reason(上榜原因)`。

```python
>>> pb.dc.lhb(date="2026-06-18")[["code", "name", "net_buy", "reason"]].head(1)
     code  name      net_buy        reason
0  301687  示例股A  50000000.0  日涨幅偏离值达7%
```

!!! warning "注意"
    非交易日 / 当日无龙虎榜 → 抛 `NoData`。单日榜单较多时 v0.1 取前 500 行。

---

## financials — 主要财务指标

```python
pb.dc.financials(symbol)       # -> DataFrame
```

- **返回列**(按报告期,一行一期):
  `symbol, report_date, eps(每股收益, 元), eps_deduct(扣非EPS, 元), bps(每股净资产, 元), revenue(营收, 元), net_profit(归母净利, 元), revenue_yoy(营收同比, %), profit_yoy(净利同比, %), roe(加权ROE, %)`。

```python
>>> pb.dc.financials("600519.SH")[["report_date", "eps", "revenue", "roe"]].head(1)
           report_date   eps       revenue   roe
0  2026-03-31 00:00:00  18.5  5.100000e+10   8.9
```

---

## securities — 全市场代码表

```python
pb.dc.securities(page_size=1000)   # -> DataFrame
```

- **参数**:`page_size` 每页条数(默认 1000,分页拉全)。
- **返回列**:`symbol`(规范化,如 `600519.SH`)、`code`(原始 6 位)、`name`。**只留接口真实字段**:交易所看 `symbol` 后缀(`.SH`/`.SZ`/`.BJ`),不另列 `market`;首版只含股票,无 `asset_type`。

```python
>>> df = pb.dc.securities()
>>> list(df.columns)
['symbol', 'code', 'name']
>>> df.head(2)
      symbol    code  name
0  000001.SZ  000001  平安银行
1  600519.SH  600519  贵州茅台
```

!!! warning "注意"
    - 首版**只含沪深京 A 股**(不含 ETF / 可转债 / 指数,留待后续小版本)。
    - 全市场约 5800+ 只,分页拉全后**整表缓存**(默认 1h,`EastMoney(cache_ttl=)` 可调):
      重复调用直接命中、不再分页,免反复被限频;传 `use_cache=False` 可强制刷新。

---

## 暂未实现(命名空间里已声明,调用抛 `NotImplementedError`)

`intraday_hist`(历史分时)、`ticks`(分笔)、`hsgt`(北向/沪深港通)、`holders/unlock/dividend`、
`industry/concept(_cons)`、`xdxr` —— 路线图项,尚未实现。

!!! note "北向资金"
    北向(沪深港通)**盘中实时**买卖/净流入自 2024 年起已停止披露,后续 `hsgt` 只会提供额度与盘后/EOD 数据。
