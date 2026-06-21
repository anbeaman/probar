"""通达信财务快照:codec(冻结真实字节,已与 pytdx 零不符)+ parser + client,默认离线。"""

import json
from pathlib import Path

import pytest

from probar.core.errors import NoData, SchemaChanged
from probar.providers.tdx import _codec, parsers

FIXTURES = Path(__file__).parent / "fixtures"
_KEYS = ["float_shares", "total_shares", "holders", "bvps", "ipo_date", "report_date"]


def _fx():
    return json.loads((FIXTURES / "tdx_finance_raw.json").read_text(encoding="utf-8"))


def _decoded():
    return _codec.decode_finance_info(bytes.fromhex(_fx()["finance_600519"]))


def test_decode_finance_info():
    d = _decoded()
    assert list(d.keys()) == _KEYS
    assert d["total_shares"] == pytest.approx(1250081562.5)
    assert d["float_shares"] > 0
    assert d["holders"] == 243159
    assert d["bvps"] == pytest.approx(216.322, abs=1e-2)
    assert d["ipo_date"] == "2001-08-27"
    assert d["report_date"] == "2026-05-28"
    # 口径不可靠的金额字段刻意不外泄
    assert "net_profit" not in d and "net_assets" not in d and "revenue" not in d


def test_decode_finance_info_truncated_is_schema_changed():
    with pytest.raises(SchemaChanged):
        _codec.decode_finance_info(bytes.fromhex(_fx()["finance_600519"])[:40])


def test_parse_finance_info():
    info = parsers.parse_finance_info(_decoded(), symbol="600519.SH")
    assert info["symbol"] == "600519.SH"
    assert list(info.keys()) == ["symbol", *_KEYS]


def test_parse_finance_info_empty_is_nodata():
    with pytest.raises(NoData):
        parsers.parse_finance_info({}, symbol="600519.SH")
    with pytest.raises(NoData):                       # 总股本<=0 视为无数据
        parsers.parse_finance_info({"total_shares": 0}, symbol="600519.SH")


class _FakeTransport:
    def __init__(self, info):
        self._info = info
        self.server = ("198.51.100.7", 7709)

    def get_finance_info(self, market, code):
        return self._info

    def close(self):
        pass


def test_finance_info_client():
    from probar import Tdx

    tdx = Tdx()
    tdx._transport = _FakeTransport(_decoded())
    d = tdx.finance_info("600519.SH")
    assert d["symbol"] == "600519.SH"
    assert d["total_shares"] > 0
    assert isinstance(d["holders"], int) and d["holders"] == 243159
    assert d["ipo_date"] == "2001-08-27"


@pytest.mark.network
def test_finance_info_live():
    import probar as pb

    d = pb.tdx.finance_info("600519.SH")
    assert d["symbol"] == "600519.SH"
    assert d["total_shares"] > 0 and d["bvps"] > 0
