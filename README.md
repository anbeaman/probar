# probar

稳定、可观测的 **A 股数据接入层** —— 覆盖东方财富、通达信、同花顺,既能做量化,也能取盘中实时行情。

> 设计目标不是"接口最多",而是 **接口坏了能最快发现、最快修、用户最少踩坑**。
> 数据层优先:回测交给 backtrader / vnpy 等框架,probar 专注把三源数据统一、可靠地喂出来。

[![ci](https://github.com/anbeaman/probar/actions/workflows/ci.yml/badge.svg)](https://github.com/anbeaman/probar/actions/workflows/ci.yml)

## 安装

```bash
pip install probar                # 核心:东方财富(pb.dc) + 通达信(pb.tdx)
pip install "probar[ths]"         # 实验性:同花顺 / 问财(pb.ths,反爬 best-effort)
pip install "probar[async]"       # 异步全市场扫描(v0.2)
```

## 按数据源拆分的命名空间

每个命名空间**只暴露该源真实支持的接口**。`pb.capabilities()` 记录三源能力(参考),
各命名空间暴露其中已实现或计划实现的方法子集。

> **v0.1 已实现**:`pb.dc` 的 `quote / quotes / kline / intraday / fund_flow / lhb / financials`(东财全链路)。
> `pb.tdx` / `pb.ths` 的接口已在命名空间中声明,调用会抛 `NotImplementedError` 并注明计划版本(v0.2 通达信 / v0.3 同花顺)。

```python
import probar as pb

# 东方财富(最全,默认主源)
pb.dc.quote("600519.SH")
pb.dc.kline("600519.SH", freq="1d", adjust="qfq")
pb.dc.fund_flow("000001.SZ")

# 通达信(行情底座:批量实时 / 历史分钟 / 历史逐笔)
pb.tdx.ticks_hist("000001.SZ", date="2026-06-19")
pb.tdx.kline("000001.SZ", freq="1m", adjust="qfq")   # 内部用 xdxr 自算复权

# 同花顺(题材增强:问财 / 概念,实验性)
pb.ths.wencai("近5日主力净流入为正且市值<100亿")

# 跨源故障转移(可选,默认不参与;结果带来源标注)
df = pb.auto.kline("000001.SZ", prefer=["dc", "tdx"])
df.attrs["source"], df.attrs.get("fallback_reason")

# 能力矩阵
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
| 东方财富 | `pb.dc` | 默认主源 | 实时/复权K/资金流/龙虎榜/财报/多市场最全 | 历史逐笔无;北向实时已停披露 |
| 通达信 | `pb.tdx` | 行情底座 | 批量实时、历史分钟、**历史逐笔** | 无资金流/龙虎榜/北向;复权需自算 |
| 同花顺 | `pb.ths` | 题材增强(实验) | **问财 NL 选股**、最细概念题材 | 全程反爬,best-effort |

完整能力矩阵见 `pb.capabilities()` 或 [`probar/core/capabilities.py`](probar/core/capabilities.py)。

## 路线图

- **v0.1**(当前):东财 `quote/kline` 全链路 + 统一 schema + 命名空间骨架 + 离线测试 + GitHub smoke + PyPI。
- **v0.2**:通达信(服务器池 + 业务探针 + 异步全市场)+ 国内 canary 节点(实网巡检自动开 Issue)。
- **v0.3**:数据质量标记 + 状态页 + 同花顺(问财/概念,实验性)。
- 暂缓:港美/期货/基金、指标层。

## 稳定性 / 每日维护

- 离线层:解析器单测(冻结样本)+ schema 契约 + ruff/mypy,见 [`ci.yml`](.github/workflows/ci.yml)。
- 实网层:每日 canary([`scripts/canary.py`](scripts/canary.py))打真实接口并**分类失败**(网络/限频/schema/数据)。
  GitHub runner 在境外会有误报,故 v0.1 为 soft smoke;v0.2 迁国内节点做主巡检。

## 免责声明

本库封装的是各平台**非官方 / 逆向**接口,仅供学习与研究使用。数据版权归东方财富、
通达信、同花顺等平台所有;使用者须遵守各平台服务条款,自行承担合规与风险。本库已内置
限流以做"友好访问",**不保证接口长期可用**,不对数据准确性或由此产生的任何损失负责。

## 开发协作

本项目维护实行**多方交叉复核**:任何实质性变更在交付前都会经过独立复核、显式标注分歧。
工程规范见 [docs/ENGINEERING_GUIDE.md](docs/ENGINEERING_GUIDE.md)、贡献见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## License

[MIT](LICENSE)
