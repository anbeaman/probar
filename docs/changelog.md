# 更新日志

完整记录见仓库 [`CHANGELOG.md`](https://github.com/anbeaman/probar/blob/main/CHANGELOG.md)。

## 0.3.0 (2026-06-21)

- 通达信 `pb.tdx.kline`:历史 K 线(原始价,clean-room 自写 `get_security_bars`;支持 1m~月线、start/end/limit)。复权需 xdxr(暂 `NotSupported`)。

## 0.2.0 (2026-06-21)

- 通达信 `pb.tdx.securities`:沪深 A 股代码表(clean-room 自写协议命令,按前缀筛股票 + GBK 名称;默认缓存)。北交所请用 `pb.dc.securities`。
- 修复:东财 datacenter "该日无数据"(code 9201)误判 `SchemaChanged` → 改 `NoData`。
- 通达信传输层重构为通用失败换服务器;默认连接超时 5→8s。

## 0.1.0 (2026-06-21)

- 按数据源拆分命名空间 `pb.dc / pb.tdx / pb.ths`(各源数据独立、不互相替换);每个只暴露该源真实支持的接口。
- 东方财富(`pb.dc`)已实现:`quote / quotes / kline / intraday / fund_flow / lhb / financials / securities`。
- 通达信(`pb.tdx`):`quotes / quote` 批量实时五档,clean-room 自写二进制协议(纯标准库,零第三方依赖)+ 服务器池业务探针。
- 共享层:统一异常模型、代码归一化、限流、缓存、HTTP 传输、能力矩阵 `pb.capabilities()`。
- 本地接口可视化测试台 `probar[playground]`。
- 离线解析测试(冻结真实响应 fixture)、GitHub CI、每日 canary smoke、PyPI Trusted Publishing 发布工作流。
- 文档站(本站)+ 工程规范 + 贡献指南。
