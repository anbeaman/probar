# 快速上手

## 1. 选对命名空间

每个数据源是一个命名空间,**只暴露该源真实支持的接口**:

| 命名空间 | 数据源 | 用途 |
|---|---|---|
| `pb.dc` | 东方财富 | 数据最全:实时、K线、资金流、龙虎榜、财务 |
| `pb.tdx` | 通达信 | 行情底座:批量实时五档、历史分钟、历史逐笔(规划中) |
| `pb.ths` | 同花顺 | 题材增强:问财、概念(实验性,规划中) |

不确定哪个源支持什么?调用 `pb.capabilities()` 或看 [能力矩阵](reference/capabilities.md)。

## 2. 取数据

```python
import probar as pb

# 实时快照(单只 dict / 批量 DataFrame)
one = pb.dc.quote("000001.SZ")
many = pb.dc.quote(["000001.SZ", "600519.SH"])   # 也可用 pb.dc.quotes([...])

# 历史 K 线(默认前复权)
df = pb.dc.kline("600519.SH", freq="1d", adjust="qfq", start="2024-01-01")

# 当日分时
df = pb.dc.intraday("000001.SZ")

# 资金流(主力/超大单…)
df = pb.dc.fund_flow("000001.SZ", days=30)

# 龙虎榜某日明细
df = pb.dc.lhb(date="2026-06-18")

# 主要财务指标
df = pb.dc.financials("600519.SH")
```

## 3. 看返回与来源

所有表格返回 `pandas.DataFrame`;来源、复权口径、耗时等写在 `df.attrs`:

```python
df = pb.dc.kline("600519.SH")
df.attrs["source"]    # 'dc'
df.attrs["provenance"] if "provenance" in df.attrs else df.attrs
```

## 4. 处理异常

接口用结构化异常表达各种情况(见 [错误模型](reference/errors.md)):

```python
from probar import NoData, RateLimited, SchemaChanged

try:
    df = pb.dc.kline("000001.SZ", start="2024-01-01")
except NoData:
    ...          # 合法但无数据(停牌/区间无交易日)
except RateLimited:
    ...          # 被限频,稍后再试
except SchemaChanged:
    ...          # 上游接口变了(请提 issue)
```

## 5. 可视化测试

不想写代码也能测:

```bash
pip install "probar[playground]"
python -m probar.playground          # 打开 http://127.0.0.1:8787
```

下一步:逐个接口的参数、返回列(含单位)、示例与注意事项,见 **接口指南**(左侧)。
