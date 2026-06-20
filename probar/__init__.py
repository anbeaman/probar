"""probar —— 稳定、可观测的 A 股数据接入层。

按数据源拆分独立命名空间,每个命名空间只暴露该源**真实支持**的接口:

    pb.dc    东方财富(最全,默认主源)
    pb.tdx   通达信(行情底座:批量实时 / 历史分钟 / 历史逐笔)
    pb.ths   同花顺(题材增强:问财 / 概念,best-effort 反爬,实验性)
    pb.auto  跨源故障转移(可选,默认不参与;结果带来源标注)

    pb.capabilities()   返回三源能力矩阵(DataFrame)

设计原则见 README。本库为非官方/逆向接口封装,使用前请阅读免责声明。
"""

from ._version import __version__
from .auto import Auto
from .core.capabilities import capabilities
from .core.errors import (
    NetworkError,
    NoData,
    NotSupported,
    ProbarError,
    RateLimited,
    SchemaChanged,
)
from .providers.eastmoney import EastMoney
from .providers.tdx import Tdx
from .providers.ths import Ths

# 默认实例:绑定到各命名空间。高级用户可自建实例传入配置,如
#     from probar import EastMoney
#     dc = EastMoney(timeout=5, proxy="http://127.0.0.1:7890")
dc = EastMoney()
tdx = Tdx()
ths = Ths()
auto = Auto(dc=dc, tdx=tdx)

__all__ = [
    "__version__",
    "capabilities",
    # 命名空间(默认实例)
    "dc",
    "tdx",
    "ths",
    "auto",
    # Provider 类(自定义配置时使用)
    "EastMoney",
    "Tdx",
    "Ths",
    "Auto",
    # 异常
    "ProbarError",
    "NetworkError",
    "RateLimited",
    "NotSupported",
    "NoData",
    "SchemaChanged",
]
