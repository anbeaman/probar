# probar

> 稳定、可观测的 **A 股数据接入层** —— 覆盖东方财富、通达信、同花顺,既能做量化,也能取盘中实时行情。

probar 的目标不是"接口最多",而是 **接口坏了能最快发现、最快修、用户最少踩坑**。
它是数据层:回测/策略交给 backtrader、vnpy 等框架,probar 专注把数据源统一、可靠地喂出来。

## 特点

- **按数据源拆分命名空间**,每个命名空间只暴露该源**真实支持**的接口:
  `pb.dc`(东方财富)、`pb.tdx`(通达信)、`pb.ths`(同花顺)、`pb.auto`(跨源故障转移)。
- **统一返回**:`pandas.DataFrame`,列名 `snake_case`,来源/耗时等溯源信息写在 `df.attrs["provenance"]`。
- **结构化错误**:`NoData` / `SchemaChanged` / `RateLimited` 等,接口一变即可被捕获。
- **可视化测试台**:`python -m probar.playground`,网页里选接口、填参数、看输入输出。

## 快速一瞥

```python
import probar as pb

pb.dc.quote(["000001.SZ", "600519.SH"])          # 实时快照
pb.dc.kline("600519.SH", freq="1d", adjust="qfq")  # 历史 K 线(前复权)
pb.dc.fund_flow("000001.SZ")                      # 资金流
```

- 安装见 [安装](install.md),5 分钟上手见 [快速上手](quickstart.md)。
- 每个接口的用法/示例/注意事项见 **接口指南**(左侧导航)。
- 各源能力一览见 [能力矩阵](reference/capabilities.md)。

## 免责声明

probar 封装的是各平台**非官方 / 逆向**接口,仅供学习与研究。数据版权归东方财富、通达信、
同花顺等平台所有;使用者须遵守各平台服务条款,自行承担合规与风险。本库已内置限流以做"友好访问",
**不保证接口长期可用**,不对数据准确性或由此产生的任何损失负责。
