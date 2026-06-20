# 通达信标准行情协议（probar clean-room 实现说明）

`probar.providers.tdx` 的 [`_protocol.py`](./_protocol.py) / [`_codec.py`](./_codec.py) 是对
**通达信标准行情(TDX Hq,默认端口 7709)二进制 TCP 协议**的独立实现,只用 Python 标准库
`socket` / `struct` / `zlib`,**不引入任何第三方依赖**。

## clean-room 边界

- 本实现只复刻**协议事实**:字节布局、长度字段、压缩标志、整数/价格/成交额的编码算法。
  这些互操作所必需的 wire format 属事实,不构成受版权保护的表达。
- 实现代码为**独立编写**,未照搬任何参考实现的代码结构、命名、注释或表达。
- 开发期曾用一个公开参考实现对**同一段真实响应字节**做解码对照(oracle 验证),确认本实现解码一致;
  该参考实现**不进入运行时依赖、也不随包分发**。冻结的对照样本见 `tests/fixtures/tdx_quotes_raw.json`。

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

> 当前仅实现 `get_security_quotes`(quote 标杆)。K 线 / 分时 / 逐笔 / 除权除息等命令按同一框架后续接入。
