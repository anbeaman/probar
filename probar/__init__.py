"""probar —— 稳定、可观测的 A 股数据接入层。

按数据源拆分独立命名空间,每个命名空间只暴露该源**真实支持**的接口:

    pb.dc    东方财富(HTTP/JSON,数据最全:实时 / 复权K / 资金流 / 龙虎榜 / 财报)
    pb.tdx   通达信(自写二进制协议,行情底座:批量实时五档 / 历史分钟 / 历史逐笔)
    pb.ths   同花顺(题材增强:问财 / 概念,best-effort 反爬,实验性)

    pb.capabilities()   返回三源能力矩阵(DataFrame)

各源数据**各自独立、口径可能不一致**:用户按需选源,probar 不做"主源"也不做跨源替换。
设计原则见 README。本库为非官方/逆向接口封装,使用前请阅读免责声明。
"""

from ._version import __version__
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

__all__ = [
    "__version__",
    "capabilities",
    # 命名空间(默认实例)
    "dc",
    "tdx",
    "ths",
    # Provider 类(自定义配置时使用)
    "EastMoney",
    "Tdx",
    "Ths",
    # 异常
    "ProbarError",
    "NetworkError",
    "RateLimited",
    "NotSupported",
    "NoData",
    "SchemaChanged",
]
