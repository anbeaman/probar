"""通达信 xdxr 除权除息:codec(冻结真实字节,已与 pytdx 逐值零不符)+ parser + client,默认离线。"""

import json
from pathlib import Path

import pandas as pd
import pytest

from probar.core.errors import SchemaChanged
from probar.providers.tdx import _codec, parsers

FIXTURES = Path(__file__).parent / "fixtures"

_COLS = ["symbol", "date", "category", "name", "fenhong", "songzhuangu", "peigu",
         "peigujia", "suogu"]


def _fx():
    return json.loads((FIXTURES / "tdx_xdxr_raw.json").read_text(encoding="utf-8"))


def _rows():
    return _codec.decode_xdxr(bytes.fromhex(_fx()["xdxr_600519"]))


def test_decode_xdxr():
    rows = _rows()
    assert len(rows) == 44
    cat1 = [r for r in rows if r["category"] == 1]
    assert len(cat1) == 29
    assert all(r["name"] == "除权除息" for r in cat1)
    last = cat1[-1]
    assert last["date"] == "2025-12-19"
    assert last["fenhong"] == pytest.approx(239.57, abs=0.01)
    assert last["songzhuangu"] == 0.0
    assert [r["date"] for r in rows] == sorted(r["date"] for r in rows)   # 日期升序


def test_decode_xdxr_zero_events_is_empty():
    # 合法 0 事件:11 字节(skip 9 + count=0)-> []
    assert _codec.decode_xdxr(b"\x00" * 9 + b"\x00\x00") == []


def test_decode_xdxr_truncated_is_schema_changed():
    with pytest.raises(SchemaChanged):
        _codec.decode_xdxr(b"\x00" * 5)                               # 不足读 count
    with pytest.raises(SchemaChanged):
        _codec.decode_xdxr(bytes.fromhex(_fx()["xdxr_600519"])[:40])  # count 声明 > 实际长度


def test_parse_xdxr():
    df = parsers.parse_xdxr(_rows(), symbol="600519.SH")
    assert list(df.columns) == _COLS
    assert (df["symbol"] == "600519.SH").all()
    assert isinstance(df["date"].iloc[0], pd.Timestamp)
    assert (df[df["category"] == 1]["fenhong"] > 0).any()


def test_parse_xdxr_empty_returns_empty_table():
    df = parsers.parse_xdxr([], symbol="600519.SH")     # 无事件是合法空集 -> 空表
    assert df.empty and list(df.columns) == _COLS


def test_build_xdxr_request():
    from probar.providers.tdx._protocol import _build_xdxr_request

    pkg = _build_xdxr_request(1, "600519")
    assert pkg.hex().startswith("0c1f187600010b000b000f000100")   # 固定前缀
    assert len(pkg) == 14 + 7                                       # 前缀(14)+ B6s(7)
    with pytest.raises(ValueError):
        _build_xdxr_request(1, "60051")                            # code 非 6 位


class _FakeTransport:
    def __init__(self, rows):
        self._rows = rows
        self.server = ("198.51.100.7", 7709)

    def get_xdxr_info(self, market, code):
        return self._rows

    def close(self):
        pass


def test_xdxr_client():
    from probar import Tdx

    tdx = Tdx()
    tdx._transport = _FakeTransport(_rows())
    df = tdx.xdxr("600519.SH")
    assert len(df) == 44
    assert df.attrs["source"] == "tdx"
    assert df["date"].is_monotonic_increasing


@pytest.mark.network
def test_xdxr_live():
    import probar as pb

    df = pb.tdx.xdxr("600519.SH")
    assert len(df) >= 20
    assert (df[df["category"] == 1]["fenhong"].fillna(0) >= 0).all()
