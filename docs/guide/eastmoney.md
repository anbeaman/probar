# 东方财富 `pb.dc`

默认主源,v0.1 已实现 7 个接口。所有 `symbol` 接受 `600519.SH` / `000001.SZ` / `600519` / `SH600519` 等写法;
表格返回 `pandas.DataFrame`,`df.attrs` 带来源等溯源信息。

!!! note "通用注意事项"
    - 非官方接口,已内置限流;**请勿高频轮询**,以免被目标站点限频(`RateLimited`)。
    - 金额单位为**元**,成交量为**手**(1 手 = 100 股),涨跌幅/换手/占比为**百分数**(如 `-2.11` 表示 -2.11%)。
    - 合法但无数据 → 抛 `NoData`;上游字段变更 → 抛 `SchemaChanged`(见 [错误模型](../reference/errors.md))。

---

## quote — 实时快照

```python
pb.dc.quote(symbol)            # 单只 -> dict
pb.dc.quote([s1, s2, ...])     # 多只 -> 见 quotes
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
df = pb.dc.quotes(["000001.SZ", "600519.SH"])
```

!!! warning "注意"
    v0.1 为**串行**实现,几十只以内顺手;全市场批量请等 v0.2 的批量/异步接口,不要拿它循环打几千只。

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
df = pb.dc.kline("600519.SH", freq="1d", adjust="qfq", start="2024-01-01")
df = pb.dc.kline("000001.SZ", freq="5m", limit=240)   # 分钟线
```

!!! warning "注意"
    - **1 分钟历史深度有限**(东财侧限制),要长历史分钟请用 5m 及以上,或等 v0.2 通达信。
    - 复权由东财直接给(一个参数);跨源换到 `pb.tdx` 时复权是 probar 自算,数值口径可能略有差异。

---

## intraday — 当日分时

```python
pb.dc.intraday(symbol)         # -> DataFrame
```

- **返回列**:`symbol, time, open, high, low, close, volume(手), amount(元), avg(当日均价, 元)`。
- 每分钟一行,覆盖 9:30–15:00。

```python
df = pb.dc.intraday("000001.SZ")
df.tail()
```

!!! warning "注意"
    返回的是**最近一个交易日**的分时;盘中调用为当日实时累积。历史某日分时请等 v0.2(`intraday_hist`)。

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
df = pb.dc.fund_flow("000001.SZ", days=30)
df[["date", "main", "super", "pct_chg"]].tail()
```

---

## lhb — 龙虎榜

```python
pb.dc.lhb(date="YYYY-MM-DD")    # -> DataFrame
```

- **参数**:`date` 交易日,**必须** `YYYY-MM-DD`(会严格校验,非法格式抛 `ValueError`)。
- **返回列**:`date, code, name, close, change_rate(%), net_buy(元), buy(元), sell(元), deal_amt(元), turnover(%), amount(元), reason(上榜原因)`。

```python
df = pb.dc.lhb(date="2026-06-18")
df[["code", "name", "net_buy", "reason"]].head()
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
df = pb.dc.financials("600519.SH")
df[["report_date", "eps", "revenue", "roe"]].head()
```

---

## 暂未实现(命名空间里已声明,调用抛 `NotImplementedError`)

`intraday_hist`(历史分时)、`ticks`(分笔)、`hsgt`(北向/沪深港通)、`holders/unlock/dividend`、
`industry/concept(_cons)`、`securities`、`xdxr` —— 计划 v0.2 / v0.3 落地。

!!! note "北向资金"
    北向(沪深港通)**盘中实时**买卖/净流入自 2024 年起已停止披露,后续 `hsgt` 只会提供额度与盘后/EOD 数据。
