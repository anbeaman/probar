"""通达信 quote 标杆:纯函数解析器(oracle fixture)+ client 装配 + 禁网门禁,默认全离线。

``tdx_quotes.json`` 是用 pytdx 连真实服务器抓回、冻结的 ``get_security_quotes`` 输出
(即 oracle):离线断言 probar 能把这份真实输出正确解析为统一 schema、且 pytdx 的字段名 /
market 数字编码不外泄。实网连通性由带 ``@network`` 的用例覆盖(默认被排除)。
"""

import json
from pathlib import Path

import pytest

from probar.core.errors import NoData, SchemaChanged
from probar.core.models import QUOTE_COLUMNS, TDX_QUOTE_COLUMNS
from probar.providers.tdx import parsers

FIXTURES = Path(__file__).parent / "fixtures"


def _raw():
    return json.loads((FIXTURES / "tdx_quotes.json").read_text(encoding="utf-8"))


def test_parse_quotes_schema_and_values():
    df = parsers.parse_quotes(_raw())
    assert list(df.columns) == TDX_QUOTE_COLUMNS          # 列契约(schema contract)
    assert set(QUOTE_COLUMNS) <= set(df.columns)          # ⊇ 跨源核心列
    assert "market" not in df.columns                     # pytdx 的数字 market 不外泄
    assert len(df) == 2
    by = {r["symbol"]: r for r in df.to_dict("records")}
    a = by["000001.SZ"]
    assert a["name"] is None                              # TDX 行情不返回名称
    assert a["price"] == 10.52
    assert a["prev_close"] == 10.78
    assert a["volume"] == 1426893
    assert a["bid1"] == 10.52 and a["ask1"] == 10.53
    assert a["ask_vol1"] == 2
    assert a["bid1"] <= a["ask1"]                         # 盘口合理
    assert a["pct_chg"] == pytest.approx(round((10.52 - 10.78) / 10.78 * 100, 4))
    assert by["600519.SH"]["price"] == 1215.0


def test_market_inferred_into_symbol():
    df = parsers.parse_quotes(_raw())
    # market 0->SZ / 1->SH 已还原进 symbol
    assert set(df["symbol"]) == {"000001.SZ", "600519.SH"}


def test_parse_quotes_empty_is_nodata():
    with pytest.raises(NoData):
        parsers.parse_quotes([])


def test_parse_quotes_missing_field_is_schema_changed():
    with pytest.raises(SchemaChanged):
        parsers.parse_quotes([{"market": 0, "code": "000001"}])  # 缺 price/last_close/盘口


def _one(**over):
    """构造一行"字段齐全"的最小 quote,便于单独改坏某个值。"""
    base = {"market": 0, "code": "000001", "price": 10.0, "last_close": 9.0,
            "bid1": 9.9, "ask1": 10.1}
    base.update(over)
    return base


def test_parse_quotes_bad_market_is_schema_changed():
    # market 非 0/1/2 -> SchemaChanged(而非裸 ValueError / 泄漏 market 编码)
    with pytest.raises(SchemaChanged):
        parsers.parse_quotes([_one(market=5)])


def test_parse_quotes_bad_code_is_schema_changed():
    with pytest.raises(SchemaChanged):
        parsers.parse_quotes([_one(code=None)])
    with pytest.raises(SchemaChanged):
        parsers.parse_quotes([_one(code="60X")])


class _FakeTransport:
    """离线替身:按入参 (market, code) 过滤冻结 oracle(贴近真实 transport 行为)。"""

    def __init__(self, raw):
        self._by = {(r["market"], r["code"]): r for r in raw}
        self.server = ("198.51.100.7", 7709)

    def get_security_quotes(self, market_code):
        return [self._by[mc] for mc in market_code if mc in self._by]

    def close(self):
        pass


def test_quotes_client_assembly_offline():
    from probar import Tdx

    tdx = Tdx()
    tdx._transport = _FakeTransport(_raw())               # 注入替身,绕过真实 TCP
    df = tdx.quotes(["000001.SZ", "600519.SH"])
    assert list(df.columns) == TDX_QUOTE_COLUMNS
    assert len(df) == 2
    assert df.attrs["source"] == "tdx"
    assert df.attrs["schema_version"] == "tdx.quote/1"
    assert df.attrs["server"] == ("198.51.100.7", 7709)


def test_quote_single_returns_native_dict():
    from probar import Tdx

    tdx = Tdx()
    tdx._transport = _FakeTransport(_raw())
    q = tdx.quote("000001.SZ")
    assert q["symbol"] == "000001.SZ"
    assert q["price"] == 10.52 and isinstance(q["price"], float)  # 原生 float,非 numpy
    assert q["name"] is None


def test_quotes_empty_input_raises():
    from probar import Tdx

    with pytest.raises(ValueError):
        Tdx().quotes([])


def test_transport_failover_demotes_bad_server(monkeypatch):
    # Blocking 修复验证:首台"探针过但业务请求失败"时,应降级并真正换到下一台
    from probar.providers.tdx import transport as T

    visited: list[str] = []
    raw = _raw()

    class FakeApi:
        def __init__(self):
            self._host = None

        def connect(self, host, port, time_out=None):
            self._host = host
            visited.append(host)
            return True

        def get_security_quotes(self, req):
            if len(req) >= 2:            # _PROBE 业务探针:各服务器都过
                return raw
            if self._host == "bad":      # 坏服务器:真实业务请求抛
                raise RuntimeError("boom")
            return [raw[0]]

        def disconnect(self):
            pass

    monkeypatch.setattr(T, "_load_pytdx", lambda: FakeApi)
    t = T.TdxTransport(servers=[("bad", 7709), ("good", 7709)])
    out = t.get_security_quotes([(0, "000001")])
    assert out and out[0]["code"] == "000001"
    assert visited[0] == "bad" and "good" in visited   # 先碰坏的,再换到好的


@pytest.mark.network
def test_quotes_live_sanity():
    # 实网:连真实服务器池,校验五档合理(默认被 -m 'not network' 排除)
    from probar import Tdx

    tdx = Tdx()
    try:
        df = tdx.quotes(["000001.SZ", "600519.SH"])
    finally:
        tdx.close()
    assert len(df) >= 1
    for _, r in df.iterrows():
        assert r["price"] > 0
        if r["ask1"] and r["bid1"]:
            assert r["bid1"] <= r["ask1"]
