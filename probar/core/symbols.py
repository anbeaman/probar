"""证券代码归一化。

统一内部表示为 ``Symbol(code, market)``,market ∈ {SH, SZ, BJ}。
对外规范文本形如 ``600519.SH`` / ``000001.SZ``;并提供到各数据源的格式转换:

    to_eastmoney_secid("600519.SH") -> "1.600519"
    to_tdx("000001.SZ")            -> (0, "000001")

接受的输入:``600519`` / ``600519.SH`` / ``SH600519`` / ``sh.600519`` 等。
"""

from __future__ import annotations

from dataclasses import dataclass

SH, SZ, BJ = "SH", "SZ", "BJ"
_MARKETS = {SH, SZ, BJ}


@dataclass(frozen=True)
class Symbol:
    code: str
    market: str  # SH / SZ / BJ

    @property
    def ts_code(self) -> str:
        """tushare 风格规范代码,如 ``600519.SH``。"""
        return f"{self.code}.{self.market}"

    def __str__(self) -> str:
        return self.ts_code


def _infer_market(code: str) -> str:
    """按代码前缀推断交易所(覆盖主板/创业板/科创板/北交所/ETF/可转债等常见段)。"""
    if code.startswith(("50", "51", "52", "56", "58", "60", "68", "90", "11", "70")):
        return SH
    if code.startswith(("00", "30", "12", "15", "16", "18", "20", "39", "13")):
        return SZ
    if code.startswith(("43", "82", "83", "87", "88", "92")):
        return BJ
    # 兜底:6 开头归上交所,其余归深交所
    return SH if code[:1] == "6" else SZ


def normalize(symbol: str) -> Symbol:
    """把任意常见写法归一为 :class:`Symbol`。"""
    s = str(symbol).strip().upper().replace(" ", "").replace(".", "")
    # 形如 SH600519 / 600519SH —— 去掉市场前后缀后,剩余部分必须是纯数字代码
    if s[:2] in _MARKETS:
        code, market = s[2:], s[:2]
    elif s[-2:] in _MARKETS:
        code, market = s[:-2], s[-2:]
    elif s.isdigit():
        code = s
        market = _infer_market(s)
    else:
        raise ValueError(f"无法解析证券代码: {symbol!r}")
    if not code.isdigit():
        raise ValueError(f"无法解析证券代码: {symbol!r}")
    return Symbol(code, market)


_EM_MARKET = {SH: "1", SZ: "0", BJ: "0"}
_TDX_MARKET = {SZ: 0, SH: 1, BJ: 2}
_TDX_MARKET_REV = {0: SZ, 1: SH, 2: BJ}


def to_eastmoney_secid(symbol: str) -> str:
    """东方财富 secid,如 ``1.600519`` / ``0.000001``。"""
    sym = normalize(symbol)
    return f"{_EM_MARKET[sym.market]}.{sym.code}"


def to_tdx(symbol: str) -> tuple[int, str]:
    """通达信 (market, code),market: 0=深 1=沪 2=北。"""
    sym = normalize(symbol)
    return _TDX_MARKET[sym.market], sym.code


def from_tdx(market: int, code: str) -> Symbol:
    """通达信 (market, code) -> :class:`Symbol`。market: 0=深 1=沪 2=北。

    把行情响应里的数字 market 还原为 probar 规范市场,避免 pytdx 的 market 编码外泄到公共 API。
    """
    try:
        return Symbol(str(code), _TDX_MARKET_REV[int(market)])
    except (KeyError, TypeError, ValueError):
        raise ValueError(f"无法识别的通达信 market={market!r} code={code!r}") from None
