# probar

稳定、可观测的 **A 股数据接入层** —— 覆盖东方财富、通达信、同花顺,既能做量化,也能取盘中实时行情。

> 设计目标不是"接口最多",而是 **接口坏了能最快发现、最快修、用户最少踩坑**。
> 数据层优先:回测交给 backtrader / vnpy 等框架,probar 专注把三源数据统一、可靠地喂出来。

[![ci](https://github.com/anbeaman/probar/actions/workflows/ci.yml/badge.svg)](https://github.com/anbeaman/probar/actions/workflows/ci.yml)

## 安装

```bash
pip install probar                # 核心:东方财富(pb.dc) + 通达信(pb.tdx),纯标准库实现通达信协议
pip install "probar[ths]"         # 实验性:同花顺 / 问财(pb.ths,反爬 best-effort)
pip install "probar[playground]"  # 本地接口可视化测试台
```

## 接口测试台(本地)

一个可视化网页,列出全部接口,可选接口、填参数、运行,查看输入/输出(表格 + 来源 + 耗时):

```bash
pip install "probar[playground]"
python -m probar.playground        # 打开 http://127.0.0.1:8787
```

左侧选数据源/接口(●已实现 / ○未实现)→ 填参数 → 运行。仅本地开发测试用,会真实联网取数。

## 按数据源拆分的命名空间

每个命名空间**只暴露该源真实支持的接口**。`pb.capabilities()` 记录三源能力(参考),
各命名空间暴露其中已实现或计划实现的方法子集。

> **已实现**:`pb.dc` 的 `quote / quotes / kline / intraday / fund_flow / lhb / financials / securities`(东财全链路);
> `pb.tdx` 的 `quotes / quote`(实时五档)、`securities`(代码表)、`kline`(历史 K 线 + 前/后复权)、`xdxr`(除权除息)、
> `ticks / ticks_hist`(当日 / 历史逐笔成交)、`finance_info`(股本结构快照)
> —— **clean-room 自写二进制协议、纯标准库零依赖**。`pb.ths`(实验性)计划后续;路线图未实现项调用抛 `NotImplementedError`。

```python
import probar as pb

# 东方财富(HTTP/JSON,数据最全)
pb.dc.quote("600519.SH")
pb.dc.kline("600519.SH", freq="1d", adjust="qfq")
pb.dc.fund_flow("000001.SZ")

# 通达信(自写二进制协议:实时五档 / K线含复权 / 除权除息 / 当日+历史逐笔 / 股本快照)
pb.tdx.quotes(["000001.SZ", "600519.SH"])            # 批量实时五档
pb.tdx.kline("600519.SH", freq="1d", adjust="qfq")  # 历史 K 线(前复权,用 xdxr 自算)
pb.tdx.ticks("600519.SH")                            # 当日逐笔成交
pb.tdx.ticks_hist("600519.SH", date="2026-06-18")   # 历史逐笔(东财免费源无,通达信独有)
pb.tdx.finance_info("600519.SH")                     # 股本结构 / 每股净资产快照

# 同花顺(题材增强:问财 / 概念;实验性,规划中)
# pb.ths.wencai("近5日主力净流入为正且市值<100亿")   # 规划中(stub,当前抛 NotImplementedError)

# 能力矩阵(各源能力参考;各源数据独立,不互相替换)
pb.capabilities()
```

高级用户可自建实例传入配置:

```python
from probar import EastMoney
dc = EastMoney(timeout=5, proxy="http://127.0.0.1:7890")
dc.kline("000001.SZ")
```

## 三源分工

| 源 | 命名空间 | 定位 | 强项 | 短板 |
|---|---|---|---|---|
| 东方财富 | `pb.dc` | 综合最全(HTTP) | 实时/复权K/资金流/龙虎榜/财报/多市场最全 | 历史逐笔无;北向实时已停披露 |
| 通达信 | `pb.tdx` | 行情底座 | 批量实时、历史分钟、**历史逐笔** | 无资金流/龙虎榜/北向;复权需自算 |
| 同花顺 | `pb.ths` | 题材增强(实验) | **问财 NL 选股**、最细概念题材 | 全程反爬,best-effort |

完整能力矩阵见 `pb.capabilities()` 或 [`probar/core/capabilities.py`](probar/core/capabilities.py)。

## 稳定性(v1.0)

自 **v1.0.0** 起,**已实现的公共 API**(`pb.dc.*` / `pb.tdx.*` 的已实现方法、返回列契约、`pb.capabilities()`、
结构化错误类型)遵循[语义化版本](https://semver.org):破坏性变更才升大版本。`pb.ths`(同花顺)为
**实验性**(反爬 best-effort,不在稳定承诺内);路线图未实现项调用抛 `NotImplementedError`,不属稳定面。

## 路线图

- **v0.1–v1.0**(已发布):东财全链路 8 接口;通达信 **clean-room 二进制协议**(纯标准库零依赖)全数据族 ——
  `quotes/quote`(五档)、`securities`(代码表)、`kline`(K 线 + 前/后复权)、`xdxr`(除权除息)、
  `ticks/ticks_hist`(当日 / 历史逐笔)、`finance_info`(股本快照)。
- **后续**:传输层延迟评分 / 熔断;异步全市场扫描;同花顺(问财 / 概念,实验性);国内 canary 节点。
- **有意不做**:`pb.tdx.intraday`(分时已被 `kline(freq="1m")` 完全覆盖);通达信 `finance_info` 的金额报表字段
  (口径不可靠,金额报表用 `pb.dc.financials`)。

## 稳定性 / 每日维护

- 离线层:解析器单测(冻结样本)+ schema 契约 + ruff/mypy,见 [`ci.yml`](.github/workflows/ci.yml)。
- 实网层:每日 canary([`scripts/canary.py`](scripts/canary.py))打真实接口并**分类失败**(网络/限频/schema/数据)。
  GitHub runner 在境外会有误报,故为 soft smoke;主巡检后续迁国内节点。

## 免责声明

本库封装的是各平台**非官方 / 逆向**接口,仅供学习与研究使用。数据版权归东方财富、
通达信、同花顺等平台所有;使用者须遵守各平台服务条款,自行承担合规与风险。本库已内置
限流以做"友好访问",**不保证接口长期可用**,不对数据准确性或由此产生的任何损失负责。

## 开发协作

本项目维护实行**多方交叉复核**:任何实质性变更在交付前都会经过独立复核、显式标注分歧。
工程规范见 [docs/ENGINEERING_GUIDE.md](docs/ENGINEERING_GUIDE.md)、贡献见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## License

[MIT](LICENSE)
