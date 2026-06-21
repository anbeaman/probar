# Changelog

本项目遵循[语义化版本](https://semver.org/lang/zh-CN/)。

## [0.8.1] - 2026-06-21

### Fixed

- `pb.capabilities()` 能力矩阵修正:历史逐笔 `ticks_hist` 的通达信档位由 🔸PART 改为 ✅FULL(已 clean-room 全实现);通达信备注补充"分时用 `kline(freq='1m')` 取、`financials` 为股本/每股净资产快照"。新增回归测试钉住已实现接口档位,防矩阵与实现静默漂移。

## [0.8.0] - 2026-06-21

### Added

- 通达信 `pb.tdx.finance_info`:财务快照(clean-room 自写 `get_finance_info` 协议命令 `0x0010`),返回 dict。**只外泄经实盘核验可靠的字段**:`float_shares`(流通股本,股)、`total_shares`(总股本,股)、`holders`(股东人数)、`bvps`(每股净资产,元/股)、`ipo_date`(上市日)、`report_date`(财务更新日)。通达信本接口的总资产/净资产/营收/利润等金额字段口径混乱(实测常与公告差约 10 倍),**刻意不外泄**——季度报表请用 `pb.dc.financials`(各源独立)。600519 + 000001 全部可靠字段与参考实现逐字段零不符。

### Changed

- 通达信 `pb.tdx.intraday` / `intraday_hist` 明确为**有意不提供**(调用抛 `NotSupported` 并指向替代):通达信分时仅 price+vol,已被 `kline(freq="1m")`(含 OHLC+量额)完全覆盖;要均价线用 `pb.dc.intraday`。此前为"计划实现"占位。

## [0.7.0] - 2026-06-21

### Added

- 通达信 `pb.tdx.ticks_hist`:历史逐笔成交(clean-room 自写 `get_history_transaction_data` 协议命令 `0x0fb5`)。`date` 接受 `"YYYY-MM-DD"` 或 `"YYYYMMDD"`,`limit=None` 取全天、给值取最新 N 笔(自动翻页)。返回 `symbol/date/time(HH:MM)/price/vol(手)/buyorsell`。**与当日逐笔体格式不同**:头部多跳 4 字节、每笔 4 个变长整数、**无 `num`(笔数)列**。实盘全天 4744 笔与参考实现逐字段零不符。东财免费源无完整历史逐笔,为通达信独有强项。

## [0.6.0] - 2026-06-21

### Added

- 通达信 `pb.tdx.ticks`:当日逐笔成交(clean-room 自写 `get_transaction_data` 协议命令 `0x0fc5`;`<H` 分钟戳 + 5×变长整数,价差跨笔累加 /100,与参考实现逐笔零不符)。返回 `symbol/time(HH:MM)/price/vol(手)/num(笔数)/buyorsell`;协议按页(每页约 2000 笔)自动翻页拼成当日全量,`limit` 截最新 N 笔。`buyorsell` 保留通达信原值(常见 0 买 / 1 卖 / 2 中性,集合竞价等为特殊值,不强行归一)。属**分笔成交明细**,非 L2 逐笔委托。

## [0.5.0] - 2026-06-21

### Added

- 通达信 `pb.tdx.kline` 支持**前/后复权** `adjust="qfq"/"hfq"`:用 `xdxr` 除权除息事件自算(除权参考价 =(前收盘×10 − 分红 + 配股×配股价)/(10 + 送转 + 配股),逐事件累乘因子)。仅调 OHLC、`pct_chg` 按复权收盘重算;**qfq 锚最新一根、hfq 锚拉取窗口最早一根**(窗口相对,各源口径不同,不与东财逐值相等)。

### Fixed

- `pb.tdx.kline` 的 `df.attrs["adjust"]` 此前恒为 `"none"`,现正确记录实际复权方式。

## [0.4.0] - 2026-06-21

### Added

- 通达信 `pb.tdx.xdxr`:除权除息事件(clean-room 自写 `get_xdxr_info`;与参考实现逐值零不符)。返回 date/category/name/fenhong(分红 元/10股)/songzhuangu/peigu/peigujia/suogu;为前/后复权计算的基石(qfq/hfq 接入 kline 见路线图)。

## [0.3.0] - 2026-06-21

### Added

- 通达信 `pb.tdx.kline`:历史 K 线(**原始价**,clean-room 自写 `get_security_bars` 协议命令;跨 bar 差分 + 压缩浮点解码,与参考实现逐 bar 零不符)。支持 `1m/5m/15m/30m/60m/1d/1w/1M`,`start`/`end`/`limit` 分页;`volume` 由股数转手、`pct_chg` 由收盘价自算;`turnover` 恒 `NaN`、`qfq`/`hfq` 复权需除权除息数据(暂抛 `NotSupported`,计划后续接入 xdxr)。

## [0.2.0] - 2026-06-21

### Added

- 通达信 `pb.tdx.securities`:沪深 A 股代码表 —— **clean-room 自写 `get_security_count` / `get_security_list` 协议命令**,按代码前缀从全品种筛出股票、GBK 名称解码(与参考实现逐条交叉验证零不符);默认 TTL 缓存。北交所经通达信行情服务器覆盖不稳定,北交所代码表请用 `pb.dc.securities`(各源独立)。

### Fixed

- 东财 datacenter(`lhb` / `financials` 等):"该日无数据"(`success=false` + code 9201"查询数据为空")被误判为 `SchemaChanged`,改为如实抛 `NoData`;未知失败仍 `SchemaChanged`。

### Changed

- 通达信传输层重构为通用 `_with_retry`(连接/帧异常降级换服务器,解码/Schema 类如实上抛);默认连接超时 5→8s。

## [0.1.0] - 2026-06-21

首个公开发布。**稳定公共 API 仅含已实现接口**(下列);命名空间里的占位接口与路线图项**不属于** v0.1.0 稳定承诺。

### Added

- 按数据源拆分的独立命名空间:`pb.dc`(东方财富)/ `pb.tdx`(通达信)/ `pb.ths`(同花顺)。各源数据独立、口径可能不一致,按需选源;**不做"主源",不做跨源故障转移**。
- 东方财富(`pb.dc`)已实现:`quote` / `quotes` / `kline` / `intraday` / `fund_flow` / `lhb` / `financials` / `securities`(全市场代码表)。
- 共享基础设施:结构化异常模型、证券代码归一化、令牌桶限流、TTL 缓存、HTTP 传输(重试+限流)、能力矩阵 `pb.capabilities()`。
- 离线解析测试(冻结真实响应 fixture)、GitHub CI(ruff / mypy / pytest)与每日 canary smoke。
- 通达信(`pb.tdx`)已实现:`quotes` / `quote` 批量实时五档,**clean-room 自写二进制 TCP 协议(纯标准库 `socket`/`struct`/`zlib`,零第三方依赖)** + 服务器池业务探针;其余接口已声明、分批落地。同花顺(`pb.ths`)命名空间已声明接口面(stub),计划 v0.3 落地。
- 东财抗限频优化:`dc.quotes` 改 push2 `ulist` 批量端点(一次多只、自动分批 ≤100),`dc.securities` 接 TTL 缓存(默认 1h、未拉满抛 `SchemaChanged` 不缓存残表),`dc.kline` 修复 `limit` 兜底(东财 beg=0 忽略 lmt 时只取最近 limit 根)。
- 本地接口可视化测试台(`probar[playground]`,`python -m probar.playground`):网页列出全部接口,可选接口、填参数、运行,查看输入/输出 + 来源 + 耗时。
- 工程规范 `docs/ENGINEERING_GUIDE.md` + 《项目总体方案》`docs/PROJECT_PLAN.md`(运维/发布/演进 + 决策记录)+ 贡献指南 + `.github` issue/PR 模板 + `SECURITY.md`。

### 说明

- 本库封装非官方/逆向接口,详见 README 免责声明。
- 发布采用 PyPI Trusted Publishing(OIDC),见 `.github/workflows/release.yml`。

[0.8.1]: https://github.com/anbeaman/probar/releases/tag/v0.8.1
[0.8.0]: https://github.com/anbeaman/probar/releases/tag/v0.8.0
[0.7.0]: https://github.com/anbeaman/probar/releases/tag/v0.7.0
[0.6.0]: https://github.com/anbeaman/probar/releases/tag/v0.6.0
[0.5.0]: https://github.com/anbeaman/probar/releases/tag/v0.5.0
[0.4.0]: https://github.com/anbeaman/probar/releases/tag/v0.4.0
[0.3.0]: https://github.com/anbeaman/probar/releases/tag/v0.3.0
[0.2.0]: https://github.com/anbeaman/probar/releases/tag/v0.2.0
[0.1.0]: https://github.com/anbeaman/probar/releases/tag/v0.1.0
