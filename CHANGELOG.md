# Changelog

本项目遵循[语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added

- 按数据源拆分的独立命名空间:`pb.dc`(东方财富)/ `pb.tdx`(通达信)/ `pb.ths`(同花顺),外加可选的跨源故障转移 `pb.auto`。
- 东方财富(`pb.dc`)已实现:`quote` / `quotes` / `kline` / `intraday` / `fund_flow` / `lhb` / `financials`。
- 共享基础设施:结构化异常模型、证券代码归一化、令牌桶限流、TTL 缓存、HTTP 传输(重试+限流)、能力矩阵 `pb.capabilities()`。
- 离线解析测试(冻结真实响应 fixture)、GitHub CI(ruff / mypy / pytest)与每日 canary smoke。
- 通达信 / 同花顺命名空间已声明接口面(stub),计划 v0.2 / v0.3 落地真实实现。

### 说明

- 本库封装非官方/逆向接口,详见 README 免责声明。
- 发布采用 PyPI Trusted Publishing(OIDC),见 `.github/workflows/release.yml`。

[Unreleased]: https://github.com/anbeaman/probar
