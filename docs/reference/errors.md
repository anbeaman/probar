# 错误模型

所有异常继承 `probar.ProbarError`,可按类型精确处理:

```python
from probar import (
    ProbarError, NetworkError, RateLimited,
    NotSupported, NoData, SchemaChanged,
)
```

| 异常 | 含义 | 典型处理 |
|---|---|---|
| `NetworkError` | 网络/超时/源不可用(已穷尽重试) | 稍后重试 / 切换网络或代理 |
| `RateLimited` | 被数据源限频(如 429) | 退避后重试,降低频率 |
| `NotSupported` | 该源不支持此能力 | 换源(见能力矩阵) |
| `NoData` | 合法但无数据(停牌/非交易日/无记录) | 跳过 / 视为空 |
| `SchemaChanged` | 上游响应结构/字段变了 | **请提 issue**;canary 通常会先于你发现 |
| `ProbarError` | 上述基类 | 兜底捕获 |

```python
from probar import NoData, RateLimited, SchemaChanged
import probar as pb

try:
    df = pb.dc.fund_flow("000001.SZ", days=30)
except NoData:
    df = None                     # 无数据
except RateLimited:
    ...                           # 退避重试
except SchemaChanged:
    ...                           # 接口变更,提 issue
```

!!! note
    - 调用未实现的接口会抛标准 `NotImplementedError`(并注明计划版本)。
    - 非法证券代码会抛 `ValueError`。
    - `SchemaChanged` 是 probar 最看重的信号——它意味着上游接口变了,需要修 parser;每日 canary 会优先盯这类。
