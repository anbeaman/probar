"""通达信 kline:codec(冻结真实字节,已与 pytdx 逐 bar 零不符)+ parser + client 装配,默认离线。"""

import json
from pathlib import Path

import pandas as pd
import pytest

from probar.core.errors import NoData, NotSupported, SchemaChanged
from probar.core.models import KLINE_COLUMNS
from probar.providers.tdx import _codec, parsers

FIXTURES = Path(__file__).parent / "fixtures"


def _fx():
    return json.loads((FIXTURES / "tdx_kline_raw.json").read_text(encoding="utf-8"))


def test_decode_kline():
    fx = _fx()
    bars = _codec.decode_kline(bytes.fromhex(fx["bars_day_600519"]), fx["category"])
    assert len(bars) == 10
    last = bars[-1]
    assert last["datetime"] == "2026-06-18 15:00"
    assert last["open"] == pytest.approx(1235.0)
    assert last["close"] == pytest.approx(1215.0)
    assert last["high"] == pytest.approx(1238.87)
    assert last["low"] == pytest.approx(1211.22)
    assert last["amount"] == pytest.approx(7016713728, rel=1e-6)
    assert all(b["high"] >= b["low"] for b in bars)
    assert all(b["open"] > 0 and b["close"] > 0 for b in bars)


def test_decode_kline_truncated_is_schema_changed():
    body = bytes.fromhex(_fx()["bars_day_600519"])[:30]
    with pytest.raises(SchemaChanged):
        _codec.decode_kline(body, 4)


def test_parse_kline():
    fx = _fx()
    bars = _codec.decode_kline(bytes.fromhex(fx["bars_day_600519"]), fx["category"])
    df = parsers.parse_kline(bars, symbol="600519.SH", freq="1d")
    assert list(df.columns) == KLINE_COLUMNS
    assert (df["symbol"] == "600519.SH").all()
    assert df["turnover"].isna().all()                       # 通达信不给换手率
    last = df.iloc[-1]
    assert last["close"] == pytest.approx(1215.0)
    assert last["volume"] == pytest.approx(57471.73, abs=0.01)   # 股 / 100 -> 手
    assert last["pct_chg"] == pytest.approx(-2.0161, abs=1e-3)
    assert last["date"] == pd.Timestamp("2026-06-18")        # 日线归零点


def test_parse_kline_empty_is_nodata():
    with pytest.raises(NoData):
        parsers.parse_kline([], symbol="600519.SH", freq="1d")


def _mkbars(n):
    return [
        {"datetime": f"2026-06-{1 + i:02d} 15:00", "open": 10.0 + i, "close": 10.5 + i,
         "high": 11.0 + i, "low": 9.5 + i, "vol": 100000.0, "amount": 1e6}
        for i in range(n)
    ]


class _FakeTransport:
    """离线替身:offset=0 返回构造的全部 bar,其余空(模拟一页到底)。"""

    def __init__(self, bars):
        self._bars = bars
        self.server = ("198.51.100.7", 7709)

    def get_security_bars(self, category, market, code, start, count):
        return self._bars if start == 0 else []

    def close(self):
        pass


def test_kline_client_limit():
    from probar import Tdx

    tdx = Tdx()
    tdx._transport = _FakeTransport(_mkbars(10))
    df = tdx.kline("600519.SH", freq="1d", limit=3)
    assert list(df.columns) == KLINE_COLUMNS
    assert len(df) == 3                                       # 截到 limit(最近 3 根)
    assert df["date"].is_monotonic_increasing
    assert df.attrs["freq"] == "1d" and df.attrs["adjust"] == "none"


def test_kline_client_range():
    from probar import Tdx

    tdx = Tdx()
    tdx._transport = _FakeTransport(_mkbars(10))             # 2026-06-01 .. 06-10
    df = tdx.kline("600519.SH", freq="1d", start="2026-06-03", end="2026-06-05")
    assert set(df["date"]) == {pd.Timestamp("2026-06-03"), pd.Timestamp("2026-06-04"),
                               pd.Timestamp("2026-06-05")}


def test_kline_adjust_not_supported():
    from probar import Tdx

    with pytest.raises(NotSupported):
        Tdx().kline("600519.SH", adjust="qfq")


def test_kline_bad_freq():
    from probar import Tdx

    with pytest.raises(ValueError):
        Tdx().kline("600519.SH", freq="2d")


def _bar(d, c):
    return {"datetime": f"{d} 15:00", "open": c - 1, "close": c, "high": c + 1, "low": c - 2,
            "vol": 1e5, "amount": 1e6}


class _TwoPageTransport:
    server = ("198.51.100.7", 7709)

    def get_security_bars(self, category, market, code, start, count):
        if start == 0:
            return [_bar("2026-06-05", 30.0), _bar("2026-06-06", 31.0)]   # 最新页
        if start == 2:
            return [_bar("2026-06-03", 20.0), _bar("2026-06-04", 21.0)]   # 更旧页
        return []

    def close(self):
        pass


def test_kline_two_page_assembly(monkeypatch):
    # 多页:翻页拼接顺序(整体升序)+ 含前置 bar 使首行 pct_chg 非 NaN(分页边界回归)
    from probar import Tdx
    from probar.providers.tdx import client as tdx_client

    monkeypatch.setattr(tdx_client, "_BARS_PER_PAGE", 2)   # 小页触发翻页
    tdx = Tdx()
    tdx._transport = _TwoPageTransport()
    df = tdx.kline("600519.SH", freq="1d", limit=3)
    assert len(df) == 3                                    # 跨两页取最近 3 根
    assert df["date"].is_monotonic_increasing             # 旧页拼前 -> 整体升序
    assert list(df["close"]) == [21.0, 30.0, 31.0]
    assert df["pct_chg"].notna().all()                    # 含前置 -> 首行非 NaN


@pytest.mark.network
def test_kline_live():
    import probar as pb

    df = pb.tdx.kline("600519.SH", freq="1d", limit=5)
    assert list(df.columns) == KLINE_COLUMNS
    assert len(df) <= 5 and (df["close"] > 0).all()
    assert df["date"].is_monotonic_increasing
