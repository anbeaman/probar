"""通达信 ticks 当日逐笔:codec(冻结真实字节,已与 pytdx 零不符)+ parser + client,默认离线。"""

import json
from pathlib import Path

import pytest

from probar.core.errors import NoData, SchemaChanged
from probar.providers.tdx import _codec, parsers

FIXTURES = Path(__file__).parent / "fixtures"
_COLS = ["symbol", "time", "price", "vol", "num", "buyorsell"]


def _fx():
    return json.loads((FIXTURES / "tdx_ticks_raw.json").read_text(encoding="utf-8"))


def _ticks():
    return _codec.decode_ticks(bytes.fromhex(_fx()["ticks_600519"]))


def test_decode_ticks():
    rows = _ticks()
    assert len(rows) == 12
    last = rows[-1]
    assert last["time"] == "15:00"
    assert last["price"] == pytest.approx(1215.0)
    assert last["vol"] == 1788 and last["num"] == 580
    assert all(":" in r["time"] and r["price"] > 0 for r in rows)


def test_decode_ticks_truncated_is_schema_changed():
    with pytest.raises(SchemaChanged):
        _codec.decode_ticks(bytes.fromhex(_fx()["ticks_600519"])[:8])


def test_parse_ticks():
    df = parsers.parse_ticks(_ticks(), symbol="600519.SH")
    assert list(df.columns) == _COLS
    assert (df["symbol"] == "600519.SH").all()
    assert (df["price"] > 0).all()


def test_parse_ticks_empty_is_nodata():
    with pytest.raises(NoData):
        parsers.parse_ticks([], symbol="600519.SH")


class _FakeTransport:
    def __init__(self, rows):
        self._rows = rows
        self.server = ("198.51.100.7", 7709)

    def get_transaction_data(self, market, code, start, count):
        return self._rows if start == 0 else []

    def close(self):
        pass


def test_ticks_client():
    from probar import Tdx

    tdx = Tdx()
    tdx._transport = _FakeTransport(_ticks())
    df = tdx.ticks("600519.SH", limit=5)
    assert list(df.columns) == _COLS
    assert len(df) == 5                        # 截到 limit(最新 5 笔)
    assert df.attrs["source"] == "tdx"


class _PagedTransport:
    """按 start 返回不同页,验证多页拼接顺序(start 越大越早)。"""

    def __init__(self, pages):
        self._pages = pages
        self.server = ("198.51.100.7", 7709)

    def get_transaction_data(self, market, code, start, count):
        return self._pages.get(start, [])

    def close(self):
        pass


def test_ticks_pagination_order():
    """offset=0 是最新页,更早的页(start 越大)应拼到前面 -> 整体时间升序,tail 取最新。"""
    from probar import Tdx
    from probar.providers.tdx.client import _TICKS_PER_PAGE

    latest = [{"time": "11:30", "price": 100.0, "vol": 1, "num": 1, "buyorsell": 0}
              for _ in range(_TICKS_PER_PAGE)]   # 满页 -> 触发继续翻页
    earlier = [{"time": "09:30", "price": 50.0, "vol": 9, "num": 2, "buyorsell": 1}
               for _ in range(3)]                # 不足一页 -> 翻页停止
    tdx = Tdx()
    tdx._transport = _PagedTransport({0: latest, _TICKS_PER_PAGE: earlier})
    df = tdx.ticks("600519.SH", limit=_TICKS_PER_PAGE + 3)
    assert len(df) == _TICKS_PER_PAGE + 3
    assert df["vol"].iloc[0] == 9 and df["time"].iloc[0] == "09:30"     # 更早的在前
    assert df["vol"].iloc[-1] == 1 and df["time"].iloc[-1] == "11:30"   # 最新的在尾


def test_ticks_limit_stops_paging():
    """limit 不超过一页时,不应触发第二页拉取(只保留最新一页并截断)。"""
    from probar import Tdx
    from probar.providers.tdx.client import _TICKS_PER_PAGE

    latest = [{"time": "11:30", "price": 100.0, "vol": 1, "num": 1, "buyorsell": 0}
              for _ in range(_TICKS_PER_PAGE)]
    # 若错误地翻了第二页,earlier 会混进来;limit<=一页时不应发生
    earlier = [{"time": "09:30", "price": 50.0, "vol": 9, "num": 2, "buyorsell": 1}]
    tdx = Tdx()
    tdx._transport = _PagedTransport({0: latest, _TICKS_PER_PAGE: earlier})
    df = tdx.ticks("600519.SH", limit=10)
    assert len(df) == 10
    assert (df["vol"] == 1).all()              # 全来自最新页,未误翻第二页


@pytest.mark.network
def test_ticks_live():
    import probar as pb

    df = pb.tdx.ticks("600519.SH", limit=20)
    assert list(df.columns) == _COLS
    assert len(df) >= 1 and (df["price"] > 0).all()
