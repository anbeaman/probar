"""结构化异常模型。

调用方可按类型精确处理:网络抖动重试、限频退避、源不支持降级、无数据跳过。
其中 ``SchemaChanged`` 通常意味着上游接口字段变更 —— 正是每日 canary 巡检要替用户
最先发现的那一类。
"""

from __future__ import annotations


class ProbarError(Exception):
    """probar 所有异常的基类。"""


class NetworkError(ProbarError):
    """网络/超时/连接失败(已穷尽重试)。"""


class RateLimited(ProbarError):
    """被数据源限频(如 HTTP 429)。"""


class NotSupported(ProbarError):
    """该数据源不支持此接口(能力矩阵中标记为无)。"""


class NoData(ProbarError):
    """请求合法但无数据(停牌 / 未上市 / 区间无成交)。"""


class SchemaChanged(ProbarError):
    """上游响应结构与预期契约不符,接口可能已变更。"""
