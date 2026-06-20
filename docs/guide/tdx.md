# 通达信 `pb.tdx`

通达信走**二进制 TCP 协议**(默认 7709 标准行情),不复用 HTTP 层。定位是 A 股**行情底座**:
批量实时五档、历史分钟、**历史逐笔**是它相对东财的强项;复权由 probar 用除权除息数据自算。

底层经 `TdxTransport`:**服务器池 + 业务探针**(连上后真拉固定标的校验五档,而非仅 ping);
pytdx 封在传输层之后、字段名与 market 编码不外泄,可随时替换。

## 安装

通达信为可选依赖:

```bash
pip install "probar[tdx]"
```

未安装时调用 `pb.tdx.*` 会抛 `NotSupported` 并给出安装指引。

## `quotes` / `quote` —— 批量实时五档(v0.3,已实现)

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

## 路线图(其余接口)

命名空间已声明完整接口面,未实现者调用抛 `NotImplementedError` 并注明计划版本:

| 接口 | 状态 | 说明 |
|---|---|---|
| `quotes` / `quote` | ✅ v0.3 | 批量实时五档(标杆) |
| `kline(freq=日/周/月/分钟, adjust=...)` | 规划 | K 线(复权自算) |
| `intraday` / `intraday_hist` | 规划 | 当日 / 历史分时 |
| `ticks` / `ticks_hist` | 规划 | 当日 / 历史逐笔(分笔成交明细,**非** L2 逐笔委托) |
| `xdxr` | 规划 | 除权除息(用于复权) |
| `securities` | 规划 | 全市场代码表 |
| `block` | 规划 | 本地板块 |
| `finance_info` | 规划 | 基础财务 |

!!! note "命名空间里没有什么"
    通达信协议**没有**资金流 / 龙虎榜 / 北向数据域,因此 `pb.tdx` 里**不存在** `fund_flow` / `lhb` / `hsgt`
    —— 访问会得到 `AttributeError`,而不是运行时"不支持"。这些请用 `pb.dc`。

!!! warning "服务器池与业务探针"
    内置服务器池在连接时做**业务探针**(拉固定标的校验五档合理),而非仅 ping —— 因为"能连 ≠ 数据完整"。
    坏服务器自动跳过;完整的延迟评分 / 熔断在后续小版本完善。
