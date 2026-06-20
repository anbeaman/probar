"""pb.auto 故障转移策略:只对"暂时不可用/不支持"降级;SchemaChanged/NoData 直接上抛。"""

import pytest

from probar.auto import Auto
from probar.core.errors import NetworkError, NoData, SchemaChanged


class _FakeDF:
    def __init__(self):
        self.attrs = {}


class _Provider:
    def __init__(self, *, exc=None, df=None):
        self._exc = exc
        self._df = df

    def kline(self, symbol, **kwargs):
        if self._exc is not None:
            raise self._exc
        return self._df


def test_fallback_on_network_error():
    df = _FakeDF()
    auto = Auto(dc=_Provider(exc=NetworkError("boom")), tdx=_Provider(df=df))
    out = auto.kline("000001.SZ")
    assert out is df
    assert out.attrs["source"] == "tdx"
    assert "dc" in out.attrs["fallback_reason"]


def test_no_fallback_on_schema_changed():
    auto = Auto(dc=_Provider(exc=SchemaChanged("changed")), tdx=_Provider(df=_FakeDF()))
    with pytest.raises(SchemaChanged):
        auto.kline("000001.SZ")


def test_no_fallback_on_no_data():
    auto = Auto(dc=_Provider(exc=NoData("none")), tdx=_Provider(df=_FakeDF()))
    with pytest.raises(NoData):
        auto.kline("000001.SZ")


def test_first_source_success_has_no_fallback_reason():
    df = _FakeDF()
    auto = Auto(dc=_Provider(df=df), tdx=_Provider(df=_FakeDF()))
    out = auto.kline("000001.SZ")
    assert out.attrs["source"] == "dc"
    assert "fallback_reason" not in out.attrs
