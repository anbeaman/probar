# 通达信标准行情协议（probar clean-room 实现说明）

`probar.providers.tdx` 的 [`_protocol.py`](./_protocol.py) / [`_codec.py`](./_codec.py) 是对
**通达信标准行情(TDX Hq,默认端口 7709)二进制 TCP 协议**的独立实现,只用 Python 标准库
`socket` / `struct` / `zlib`,**不引入任何第三方依赖**。

## clean-room 边界

- 本实现只复刻**协议事实**:字节布局、长度字段、压缩标志、整数/价格/成交额的编码算法。
  这些互操作所必需的 wire format 属事实,不构成受版权保护的表达。
- 实现代码为**独立编写**,未照搬任何参考实现的代码结构、命名、注释或表达。
- 开发期曾用一个公开参考实现对**同一段真实响应字节**做解码对照(oracle 验证),确认本实现解码一致;
  该参考实现**不进入运行时依赖、也不随包分发**。冻结的对照样本见 `tests/fixtures/tdx_quotes_raw.json` 与 `tdx_securities_raw.json`。

## 连接与握手

TCP 连接后,先顺序发送三个固定握手包(版本/能力协商,wire 常量),各自按下述帧格式收一帧、丢弃响应:

| 包 | 字节(hex) |
|---|---|
| Setup1 | `0c0218930001030003000d0001` |
| Setup2 | `0c0218940001030003000d0002` |
| Setup3 | `0c031899000120002000db0fd5d0c9ccd6a4a8af0000008fc22540130000d500c9ccbdf0d7ea00000002` |

## 帧格式（小端）

**请求** —— `get_security_quotes` 请求头 `<HIHHIIHH` =
`(0x10c, 0x02006320, body_len, body_len, 0x5053e, 0, 0, n)`,其中 `body_len = n*7 + 12`、`n` 为查询只数;
随后每只 7 字节 `<B6s`(1 字节 market + 6 位 ASCII code)。market:`0=深 1=沪 2=北`。

**响应** —— 先收 16 字节头 `<IIIHH`,末两个 `uint16` 为 `zip_size` / `unzip_size`;按 `zip_size`
**收满**响应体;若 `zip_size != unzip_size` 则体经 `zlib` 压缩,解压后长度应为 `unzip_size`。

## 行情体解码（get_security_quotes）

体首跳过 2 字节,`<H` 读只数;每只 `<B6sH`(market / code / active1)后,用**变长有符号整数(vint)**
读基准价与各差分:

- **vint**:首字节低 6 位为数值低位,`0x40` 为符号位,`0x80` 表示"还有后续字节";后续字节取低 7 位,
  依次左移 6、13、20… 拼接。
- **价格**:开/高/低/收与五档均以"相对基准价 `base` 的差分"存储,最终价 = `(base + diff) / 100`。
- **成交额**:`<I` 读 32 位整数后,用 TDX 私有压缩浮点解码(高字节为指数,低 3 字节为尾数)。
- **服务器时间**:由一个整数按固定算法还原为 `HH:MM:SS.mmm`。

每只字段顺序:`base, last_close_diff, open_diff, high_diff, low_diff, 时间源, 保留, vol, cur_vol,
amount<I>, s_vol, b_vol, 保留×2, 五档×(bid_diff, ask_diff, bid_vol, ask_vol), 保留<H>, 保留×4, 保留<hH>`。

## 证券数量 / 列表解码(get_security_count / get_security_list)

**get_security_count** —— 请求:固定前缀 `0c0c186c0001080008004e04` + `<H market` + 固定尾 `75c73301`(命令 `0x044e`);
响应体偏移 0 的 `<H` 即该市场证券数量。

**get_security_list** —— 请求:固定前缀 `0c0118640101060006005004` + `<HH (market, start)`(命令 `0x0450`,每页最多 1000 条);
响应体偏移 0 的 `<H` 为本页条数,随后每条 **29 字节** `<6sH8s4sBI4s`:
`code(6 位 ASCII)/ volunit / name(8 字节 **GBK**)/ 保留 / 小数位 / 昨收(私有压缩浮点)/ 保留`。
体长应精确为 `2 + 29 * count`。

## K 线解码(get_security_bars)

**请求** —— `struct.pack("<HIHHHH6sHHHHIIH", 0x10c, 0x01016408, 0x1c, 0x1c, 0x052d, market, code,
category, 1, start, count, 0, 0, 0)`(命令 `0x052d`)。`category` 为周期(1m=8 / 5m=0 / 15m=1 / 30m=2 /
60m=3 / 日=4 / 周=5 / 月=6);`start` 为距最新的偏移、`count<=800`。

**响应** —— 体偏移 0 的 `<H` 为 bar 数;每 bar:`datetime`(按 category:分钟级 4 字节 `<HH` 含时分,
日及以上 4 字节 `<I` 仅日期)+ 开/收/高/低 4 个 **vint 跨 bar 差分** + vol/amount 各 `<I`(私有压缩浮点)。
价格 `/1000`:开 = (开差 + 上一 bar 收基准)/1000,收/高/低 = (绝对开 + 各自差分)/1000,下一 bar 基准 =
绝对开 + 收差。bar 内成交量为**股数**(上层 /100 转手)。

**指数 K 线**(`get_index_bars`)—— **请求与 `get_security_bars` 完全相同**(同 cmd `0x052d`),但响应里
每 bar 末尾**多 4 字节** `<HH`(up_count 上涨家数 / down_count 下跌家数)。故个股解码器读指数响应会
`pos` 不足而判 `SchemaChanged`;指数走 `decode_index_kline`、对外用 `pb.tdx.index_kline`。

## 除权除息解码(get_xdxr_info)

**请求** —— 固定前缀 `0c1f187600010b000b000f000100` + `<B6s (market, code)`。

**响应** —— skip 9 字节后 `<H` 为事件数;每事件 29 字节:market/code/保留(8,跳过)+ 日期(4,日级 `<I`)+
`<B category` + 16 字节类别数据。**category=1 除权除息** = `<ffff`(fenhong 分红 / peigujia 配股价 /
songzhuangu 送转股 / peigu 配股,均每 10 股口径);category 11/12 缩股 = `<IIfI` 取第 3 个 float(suogu)。
体长应精确为 `11 + 29 * count`。

## 当日逐笔解码(get_transaction_data)

**请求** —— 固定前缀 `0c1708010101 0e000e00c50f`(命令 `0x0fc5`)+ `<H6sHH (market, code, start, count)`;
`start` 为距最新的偏移、`count` 每页约 2000 笔(上层自动翻页拼成当日全量)。

**响应** —— 体偏移 0 的 `<H` 为逐笔数;每笔顺序:`<H` 分钟戳(自 0 点的分钟数,`HH:MM`)+ 5 个 **vint**:
价差(跨笔累加,`(累计 base)/100` 得成交价)、vol(手)、num(笔数)、buyorsell(方向)、保留。
体长应被全部 vint 精确消费(`pos == len(body)`,否则判 `SchemaChanged`)。`buyorsell` 取通达信原值:
常见 `0` 买 / `1` 卖 / `2` 中性,集合竞价等为特殊值,不强行归一。

## 历史逐笔解码(get_history_transaction_data)

**请求** —— 固定前缀 `0c0130010001120012 00b50f`(命令 `0x0fb5`)+ `<IH6sHH (date, market, code, start, count)`;
`date` 为 `YYYYMMDD` 整数(如 `20260618`),`start`/`count` 同当日逐笔。

**响应** —— 与当日逐笔**布局不同**:`<H` 笔数后**另跳 4 字节保留**(`pos` 从 6 起),每笔 `<H` 分钟戳 +
**4 个 vint**(价差跨笔累加 `/100`、vol、buyorsell、保留)——**无 `num` 字段**。同样要求 `pos == len(body)`。

## 财务快照解码(get_finance_info)

**请求** —— 固定前缀 `0c1f187600010b000b00 10000100`(命令 `0x0010`)+ `<B6s (market, code)`。

**响应** —— `<H` 计数后 `<B6s`(market/code)+ **定长 136 字节** `<fHHIIf×30`:`liutongguben`(流通股本,
万股)、省份 / 行业(`<H`,内部编码)、财务更新日 / 上市日(`<I` YYYYMMDD)、`zongguben`(总股本)、
各类股 / 资产 / 负债 / 营收 / 利润(`<f`,均万元口径)、股东人数、每股净资产等。体长须精确为
`9 + 136`。**注意**:本接口的资产 / 营收 / 利润字段口径混乱(常与公告差约 10 倍),probar 只外泄经核验
可靠的股本 / 股东人数 / 每股净资产 / 日期,金额报表交 `pb.dc.financials`。

> 已实现:`get_security_quotes`(实时五档)、`get_security_count` / `get_security_list`(证券列表)、
> `get_security_bars`(K 线)、`get_xdxr_info`(除权除息)、`get_transaction_data`(当日逐笔)、
> `get_history_transaction_data`(历史逐笔)、`get_finance_info`(财务快照)。其余命令按同一框架后续接入。
