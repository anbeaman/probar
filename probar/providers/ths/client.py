"""同花顺 Provider —— 绑定到 ``pb.ths``(实验性,best-effort)。

价值集中在**问财 iwencai 自然语言选股**与**细粒度概念/行业题材**,这是同花顺独有的。
但全程反爬(hexin-v / cookie / 风控),长期稳定性不保证 —— 因此**不进核心行情主链路**,
对外明确标注 best-effort,计划 v0.3 接入(需 ``pip install "probar[ths]"``)。

命名空间只暴露同花顺有独特价值或可取的接口;高频行情请用 pb.dc / pb.tdx。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

_V = "v0.3"


def _todo(interface: str) -> NotImplementedError:
    return NotImplementedError(
        f"pb.ths.{interface} 计划在 {_V} 接入(实验性,反爬 best-effort);需 pip install 'probar[ths]'"
    )


class Ths:
    name = "ths"

    def __init__(
        self, *, timeout: float = 8.0, cookie: str | None = None, proxy: str | None = None
    ) -> None:
        self.timeout = timeout
        self.cookie = cookie
        self.proxy = proxy

    def __repr__(self) -> str:  # noqa: D105
        return "<Ths source='ths' experimental=True>"

    # ---- 旗舰:问财 ----
    def wencai(self, query: str, *, kind: str = "stock") -> pd.DataFrame:
        """问财自然语言选股,如 wencai('近5日主力净流入为正且市值<100亿')。"""
        raise _todo("wencai")

    # ---- 题材/概念 ----
    def concept(self) -> pd.DataFrame:
        raise _todo("concept")

    def concept_cons(self, name: str) -> pd.DataFrame:
        raise _todo("concept_cons")

    def industry(self) -> pd.DataFrame:
        raise _todo("industry")

    def industry_cons(self, name: str) -> pd.DataFrame:
        raise _todo("industry_cons")

    # ---- 其它 ----
    def quote(self, symbol: str) -> dict:
        raise _todo("quote")

    def f10(self, symbol: str) -> dict:
        raise _todo("f10")

    def lhb(self, *, date: str) -> pd.DataFrame:
        raise _todo("lhb")
