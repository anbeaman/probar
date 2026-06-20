# 更新日志

完整记录见仓库 [`CHANGELOG.md`](https://github.com/anbeaman/probar/blob/main/CHANGELOG.md)。

## Unreleased

- 按数据源拆分命名空间 `pb.dc / pb.tdx / pb.ths` + 可选 `pb.auto`;每个只暴露该源真实支持的接口。
- 东方财富(`pb.dc`)已实现:`quote / quotes / kline / intraday / fund_flow / lhb / financials`。
- 共享层:统一异常模型、代码归一化、限流、缓存、HTTP 传输、能力矩阵 `pb.capabilities()`。
- 本地接口可视化测试台 `probar[playground]`。
- 离线解析测试(冻结真实响应 fixture)、GitHub CI、每日 canary smoke、PyPI Trusted Publishing 发布工作流。
- 文档站(本站)+ 工程规范 + 贡献指南。
