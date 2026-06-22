"""通达信指数 K 线:codec(冻结真实字节,已与 pytdx 逐 bar 零不符)+ parser + client,默认离线。"""

import json
from pathlib import Path

import pytest

from probar.core.errors import NoData, NotSupported, SchemaChanged
from probar.providers.tdx import _codec, parsers

FIXTURES = Path(__file__).parent / "fixtures"
_COLS = ["symbol", "date", "open", "high", "low", "close", "volume", "amount",
         "up_count", "down_count"]


def _fx():
    return json.loads((FIXTURES / "tdx_index_raw.json").read_text(encoding="utf-8"))


def _bars():
    fx = _fx()
    return _codec.decode_index_kline(bytes.fromhex(fx["bars_index_sh"]), fx["category"])


def test_decode_index_kline():
    bars = _bars()
    assert len(bars) == 10
    last = bars[-1]
    assert last["datetime"] == "2026-06-22 15:00"
    assert last["close"] == pytest.approx(4098.01, abs=0.01)     # 上证指数级别(非个股)
    assert last["up_count"] == 587 and last["down_count"] == 1739
    assert all(b["high"] >= b["low"] for b in bars)


def test_decode_index_truncated_is_schema_changed():
    with pytest.raises(SchemaChanged):
        _codec.decode_index_kline(bytes.fromhex(_fx()["bars_index_sh"])[:40], 4)


def test_stock_decoder_underreads_index_is_schema_changed():
    # 个股解码器读指数响应:每 bar 少读 4 字节(上涨/下跌家数)-> 末尾 pos 不符
    with pytest.raises(SchemaChanged):
        _codec.decode_kline(bytes.fromhex(_fx()["bars_index_sh"]), 4)


def test_parse_index_kline():
    df = parsers.parse_index_kline(_bars(), symbol="000001.SH", freq="1d")
    assert list(df.columns) == _COLS
    assert "pct_chg" not in df.columns and "turnover" not in df.columns
    last = df.iloc[-1]
    assert last["close"] == pytest.approx(4098.01, abs=0.01)
    assert last["up_count"] == 587 and last["down_count"] == 1739
    assert last["volume"] == pytest.approx(474869952.0)   # 指数协议已是手,不 /100


def test_parse_index_kline_empty_is_nodata():
    with pytest.raises(NoData):
        parsers.parse_index_kline([], symbol="000001.SH", freq="1d")


class _FakeTransport:
    def __init__(self, bars):
        self._bars = bars
        self.server = ("198.51.100.7", 7709)

    def get_index_bars(self, category, market, code, start, count):
        return self._bars if start == 0 else []

    def close(self):
        pass


def test_index_kline_client():
    from probar import Tdx

    tdx = Tdx()
    tdx._transport = _FakeTransport(_bars())
    df = tdx.index_kline("000001.SH", limit=3)
    assert list(df.columns) == _COLS
    assert len(df) == 3
    assert df["date"].is_monotonic_increasing
    assert df.attrs["source"] == "tdx" and df.attrs["freq"] == "1d"


def test_kline_rejects_index_with_clear_error():
    from probar import Tdx

    with pytest.raises(NotSupported):          # 个股 kline 取指数 -> 清晰指引(而非 SchemaChanged)
        Tdx().kline("000001.SH")


def test_index_kline_rejects_stock():
    from probar import Tdx

    with pytest.raises(NotSupported):          # index_kline 取个股 -> 指回 kline
        Tdx().index_kline("600519.SH")


@pytest.mark.network
def test_index_kline_live():
    import probar as pb

    df = pb.tdx.index_kline("000001.SH", limit=5)
    assert list(df.columns) == _COLS
    assert len(df) <= 5 and (df["close"] > 0).all()
    assert (df["up_count"] >= 0).all() and (df["down_count"] >= 0).all()
