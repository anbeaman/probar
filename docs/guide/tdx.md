# 通达信 `pb.tdx`

通达信走**二进制 TCP 协议**(默认 7709 标准行情),不复用 HTTP 层。定位是 A 股**行情底座**:
批量实时五档、历史分钟、**历史逐笔**是它相对东财的强项;复权由 probar 用除权除息数据自算。

底层经 `TdxTransport` + **自写协议客户端**(clean-room,纯标准库 `socket`/`struct`/`zlib`,**零第三方依赖**,
开箱即用):**服务器池 + 业务探针**(连上后真拉固定标的校验五档,而非仅 ping),失败自动降级换服务器。

## `quotes` / `quote` —— 批量实时五档(已实现)

`quotes(symbol_list)` 批量、`quote(symbol)` 单只。这是通达信相对东财的强项:一次请求多只、含 L1 五档盘口。

**参数**

| 参数 | 说明 |
|---|---|
| `symbol_list` / `symbol` | 代码或代码列表,如 `"600519.SH"` / `["000001.SZ", "600519.SH"]`;自动分批(每批 ≤ 80) |

**返回**(`quotes` 为 DataFrame,`quote` 为 dict;列一致):

| 列 | 含义 |
|---|---|
| `symbol` | 规范代码,如 `600519.SH` |
| `name` | **恒为 None**(TDX 行情协议不返回名称;名称用 `pb.dc` 或 `tdx.securities` 映射) |
| `price` / `open` / `high` / `low` / `prev_close` | 现价 / 开 / 高 / 低 / 昨收(元) |
| `volume` / `amount` | 累计成交量(手) / 成交额(元) |
| `pct_chg` | 涨跌幅(%,由 price 与 prev_close 计算) |
| `bid1..bid5` / `bid_vol1..bid_vol5` | 买一~买五 价 / 量 |
| `ask1..ask5` / `ask_vol1..ask_vol5` | 卖一~卖五 价 / 量 |
| `cur_vol` / `inner_vol` / `outer_vol` | 现手 / 内盘(主动卖) / 外盘(主动买) |
| `servertime` | 服务器时间(如 `14:59:58.376`) |

`df.attrs` 另含溯源:`source`、`schema_version`(`tdx.quote/1`)、`server`(实际所用服务器 `(host, port)`)。

**示例**

```python
import probar as pb

df = pb.tdx.quotes(["000001.SZ", "600519.SH"])
print(df[["symbol", "price", "prev_close", "pct_chg", "bid1", "ask1"]])
#       symbol    price  prev_close  pct_chg     bid1      ask1
#    000001.SZ    10.52       10.78  -2.4119    10.52     10.53
#    600519.SH  1215.00     1240.00  -2.0161  1215.00   1215.28

q = pb.tdx.quote("600519.SH")           # 单只 -> dict(含五档)
q["price"], q["bid1"], q["ask1"]        # (1215.0, 1215.0, 1215.28)

df.attrs["server"]          # 实际所用服务器,如 ('218.75.126.9', 7709)
df.attrs["schema_version"]  # 'tdx.quote/1'
```

**注意**

- 停牌 / 无效代码不会出现在返回里(只返回有数据的);全部无数据抛 `NoData`。
- `name` 恒为 `None` —— 需要名称用 `pb.dc.quote` 或后续的 `tdx.securities` 映射。
- 北交所(BJ)能否取到取决于具体服务器(部分标准行情站不含北交所);服务器池会自动挑能用的。

## `securities` —— 沪深 A 股代码表(v0.2,已实现)

```python
df = pb.tdx.securities()        # -> DataFrame,默认缓存 1h
```

- **返回列**:`symbol, code, name, market(SH/SZ), asset_type("stock")`。名称来自通达信(GBK 解码)。
- **机制**:通达信按市场分页拉**全品种**(每页 1000)再按代码前缀筛出股票,首次 ~5s、之后走缓存;
  `use_cache=False` 强制刷新,`Tdx(cache_ttl=...)` 调缓存时长。
- **不含北交所**:通达信行情服务器对北交所覆盖不稳定,**北交所代码表请用 `pb.dc.securities`**(各源独立)。
- 名称与东财可能略有出入(各源数据独立,不互相替换)。

## `kline` —— 历史 K 线(v0.3,已实现)

```python
df = pb.tdx.kline("600519.SH", freq="1d", limit=300)           # 最近 300 根日线(原始价)
df = pb.tdx.kline("600519.SH", freq="1d", adjust="qfq")        # 前复权(用 xdxr 自算)
df = pb.tdx.kline("000001.SZ", freq="5m", start="2026-06-01")  # 区间分钟线
```

- **参数**:`freq` = `1m/5m/15m/30m/60m/1d/1w/1M`;`start`/`end` = `"YYYY-MM-DD"`(省略 start 取最近 `limit` 根);
  `adjust` = `None`原始价 / `qfq`前复权 / `hfq`后复权(用除权除息 xdxr 自算)。
- **返回列**:`symbol, date, open, high, low, close, volume(手), amount(元), pct_chg(%), turnover`。
- **注意**:`turnover` 恒为 `NaN`(协议不提供);复权仅调 OHLC、`pct_chg` 重算;
  **qfq 锚最新、hfq 锚拉取窗口最早**(窗口相对,不与东财逐值相等)。分钟历史比东财更深,是通达信的强项。
- **复权限制**:仅日线/分钟线(`1w`/`1M` 复权抛 `NotSupported`);给 `end` 时 qfq 锚"拉取到的最新"而非 end;缩股暂不参与复权。

## `xdxr` —— 除权除息事件(v0.4,已实现)

```python
df = pb.tdx.xdxr("600519.SH")        # -> DataFrame,全历史除权除息等事件
```

- **返回列**:`symbol, date, category(类别码), name(类别名), fenhong(分红 元/10股),
  songzhuangu(送转股 股/10股), peigu(配股 股/10股), peigujia(配股价 元/股), suogu(缩股比例)`。
- 仅 `category=1`(除权除息)填分红/送转/配股;无任何事件返回固定列空表。
- **复权基石**:已接入 `kline` 的 `adjust=qfq/hfq` 自算复权。

## `ticks` —— 当日逐笔成交(v0.6,已实现)

```python
df = pb.tdx.ticks("600519.SH")             # -> DataFrame,当日全部逐笔(自动翻页)
df = pb.tdx.ticks("600519.SH", limit=50)   # 只要最新 50 笔
```

- **返回列**:`symbol, time(HH:MM), price(元), vol(手), num(笔数), buyorsell`。
- **方向 `buyorsell`**:通达信原值,常见 `0` 买 / `1` 卖 / `2` 中性;集合竞价等为特殊值(不强行归一,保留原义)。
- **机制**:协议按页拉(每页约 2000 笔),自动翻页拼成当日全量;`limit` 截最新 N 笔。
  逐笔是通达信相对东财的强项(东财免费源不提供完整当日逐笔)。
- **注意**:`time` 为分钟级(同一分钟可多笔,通达信不返回秒);这是**分笔成交明细**,
  **非** L2 逐笔委托(L2 需授权数据源,不在本库范围)。

## 路线图(其余接口)

命名空间已声明完整接口面,未实现者调用抛 `NotImplementedError` 并注明计划版本:

| 接口 | 状态 | 说明 |
|---|---|---|
| `quotes` / `quote` | ✅ v0.1 | 批量实时五档 |
| `securities` | ✅ v0.2 | 沪深 A 股代码表(北交所用 `pb.dc`) |
| `kline` | ✅ v0.3 | 历史 K 线(原始价;复权需 xdxr) |
| `intraday` / `intraday_hist` | 规划 | 当日 / 历史分时 |
| `ticks` | ✅ v0.6 | 当日逐笔成交(分笔成交明细,**非** L2 逐笔委托) |
| `ticks_hist` | 规划 | 历史逐笔(往日分笔) |
| `xdxr` | ✅ v0.4 | 除权除息事件(复权基石) |
| `block` | 规划 | 本地板块 |
| `finance_info` | 规划 | 基础财务 |

!!! note "命名空间里没有什么"
    通达信协议**没有**资金流 / 龙虎榜 / 北向数据域,因此 `pb.tdx` 里**不存在** `fund_flow` / `lhb` / `hsgt`
    —— 访问会得到 `AttributeError`,而不是运行时"不支持"。这些请用 `pb.dc`。

!!! warning "服务器池与业务探针"
    内置服务器池在连接时做**业务探针**(拉固定标的校验五档合理),而非仅 ping —— 因为"能连 ≠ 数据完整"。
    坏服务器自动跳过;完整的延迟评分 / 熔断在后续小版本完善。
