# 更新日志

完整逐版记录见仓库 [`CHANGELOG.md`](https://github.com/anbeaman/probar/blob/main/CHANGELOG.md)。下面是里程碑摘要。

## 2.0.0 — 通达信接口只返回协议真实字段(**BREAKING**)

移除 probar 自算 / 恒空的列:`pb.tdx.kline` 去 `pct_chg` / `turnover`、`pb.tdx.quotes` / `quote` 去 `name` / `pct_chg`。
**东财 `pb.dc.*` 完全不受影响**(其 `name` / `pct_chg` / `turnover` 是东财接口真实返回)。
迁移:涨跌幅自算(`close.pct_change()`)、名称用 `pb.dc` 或 `pb.tdx.securities`、换手率用 `pb.dc.kline`。

## 1.0.0 — 首个稳定版

已实现的公共 API 进入语义化版本稳定承诺。通达信 clean-room 数据族完整:
`quotes / quote / securities / kline`(含 qfq/hfq 复权)`/ xdxr / ticks / ticks_hist / finance_info`,纯标准库、零第三方依赖。

## 0.6.0 – 0.8.1

通达信 `ticks`(当日逐笔)、`ticks_hist`(历史逐笔)、`finance_info`(股本结构快照);`pb.capabilities()` 能力矩阵精度修正。

## 0.1.0 – 0.5.0

按数据源拆分命名空间 `pb.dc / pb.tdx / pb.ths`;东财 8 接口全链路;
通达信 clean-room 二进制协议(批量五档 / 代码表 / 历史 K 线 + 前后复权 / 除权除息)。
