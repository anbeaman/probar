"""通达信历史逐笔:codec(冻结真实字节,已与 pytdx 零不符)+ parser + client,默认离线。"""

import json
from pathlib import Path

import pytest

from probar.core.errors import NoData, SchemaChanged
from probar.providers.tdx import _codec, parsers

FIXTURES = Path(__file__).parent / "fixtures"
_COLS = ["symbol", "date", "time", "price", "vol", "buyorsell"]


def _fx():
    return json.loads((FIXTURES / "tdx_ticks_hist_raw.json").read_text(encoding="utf-8"))


def _ticks():
    return _codec.decode_ticks_hist(bytes.fromhex(_fx()["ticks_hist_600519"]))


def test_decode_ticks_hist():
    rows = _ticks()
    assert len(rows) == 20
    last = rows[-1]
    assert last["time"] == "15:00"
    assert last["price"] == pytest.approx(1215.0)
    assert last["vol"] == 1788 and last["buyorsell"] == 2
    assert "num" not in last                       # 历史逐笔无 num 字段
    assert all(":" in r["time"] and r["price"] > 0 for r in rows)


def test_decode_ticks_hist_truncated_is_schema_changed():
    with pytest.raises(SchemaChanged):
        _codec.decode_ticks_hist(bytes.fromhex(_fx()["ticks_hist_600519"])[:10])


def test_parse_ticks_hist():
    df = parsers.parse_ticks_hist(_ticks(), symbol="600519.SH", date="2026-06-18")
    assert list(df.columns) == _COLS
    assert (df["symbol"] == "600519.SH").all()
    assert (df["date"] == "2026-06-18").all()
    assert (df["price"] > 0).all()


def test_parse_ticks_hist_empty_is_nodata():
    with pytest.raises(NoData):
        parsers.parse_ticks_hist([], symbol="600519.SH", date="2026-06-18")


class _FakeHistTransport:
    def __init__(self, rows):
        self._rows = rows
        self.server = ("198.51.100.7", 7709)

    def get_history_transaction_data(self, market, code, date, start, count):
        return self._rows if start == 0 else []

    def close(self):
        pass


def test_ticks_hist_client():
    from probar import Tdx

    tdx = Tdx()
    tdx._transport = _FakeHistTransport(_ticks())
    df = tdx.ticks_hist("600519.SH", date="2026-06-18", limit=5)
    assert list(df.columns) == _COLS
    assert len(df) == 5                            # 截到 limit(最新 5 笔)
    assert (df["date"] == "2026-06-18").all()
    assert df.attrs["source"] == "tdx"


def test_ticks_hist_accepts_compact_date():
    """date 接受 YYYYMMDD 紧凑写法,归一为 YYYY-MM-DD。"""
    from probar import Tdx

    tdx = Tdx()
    tdx._transport = _FakeHistTransport(_ticks())
    df = tdx.ticks_hist("600519.SH", date="20260618", limit=3)
    assert (df["date"] == "2026-06-18").all()


@pytest.mark.network
def test_ticks_hist_live():
    import probar as pb

    df = pb.tdx.ticks_hist("600519.SH", date="2026-06-18", limit=20)
    assert list(df.columns) == _COLS
    assert len(df) >= 1 and (df["price"] > 0).all()
