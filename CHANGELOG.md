# Changelog

本项目遵循[语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added

- 按数据源拆分的独立命名空间:`pb.dc`(东方财富)/ `pb.tdx`(通达信)/ `pb.ths`(同花顺)。各源数据独立、口径可能不一致,按需选源;**不做"主源",不做跨源故障转移**。
- 东方财富(`pb.dc`)已实现:`quote` / `quotes` / `kline` / `intraday` / `fund_flow` / `lhb` / `financials` / `securities`(全市场代码表)。
- 共享基础设施:结构化异常模型、证券代码归一化、令牌桶限流、TTL 缓存、HTTP 传输(重试+限流)、能力矩阵 `pb.capabilities()`。
- 离线解析测试(冻结真实响应 fixture)、GitHub CI(ruff / mypy / pytest)与每日 canary smoke。
- 通达信(`pb.tdx`)已实现:`quotes` / `quote` 批量实时五档,**clean-room 自写二进制 TCP 协议(纯标准库 `socket`/`struct`/`zlib`,零第三方依赖)** + 服务器池业务探针;其余接口已声明、分批落地。同花顺(`pb.ths`)命名空间已声明接口面(stub),计划 v0.3 落地。
- 本地接口可视化测试台(`probar[playground]`,`python -m probar.playground`):网页列出全部接口,可选接口、填参数、运行,查看输入/输出 + 来源 + 耗时。
- 工程规范 `docs/ENGINEERING_GUIDE.md` + 贡献指南 + `.github` issue/PR 模板 + `SECURITY.md`。

### 说明

- 本库封装非官方/逆向接口,详见 README 免责声明。
- 发布采用 PyPI Trusted Publishing(OIDC),见 `.github/workflows/release.yml`。

[Unreleased]: https://github.com/anbeaman/probar
