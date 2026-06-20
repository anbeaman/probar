"""测试台离线测试(TestClient,不联网):只验证自省与调用路径,不打真实数据源。"""

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from probar.playground.app import app  # noqa: E402

client = TestClient(app)


def test_interfaces_catalog():
    r = client.get("/api/interfaces")
    assert r.status_code == 200
    j = r.json()
    nss = {g["namespace"] for g in j["catalog"]}
    assert {"dc", "tdx", "ths", "auto"} <= nss

    dc = next(g for g in j["catalog"] if g["namespace"] == "dc")
    impl = {m["name"]: m["implemented"] for m in dc["methods"]}
    assert impl["kline"] is True            # 已实现
    assert impl["intraday_hist"] is False   # stub
    assert "fund_flow" in impl
    # tdx 不暴露资金流(协议无此数据域)
    tdx = next(g for g in j["catalog"] if g["namespace"] == "tdx")
    assert "fund_flow" not in {m["name"] for m in tdx["methods"]}
    assert j["capabilities"]


def test_call_stub_returns_error_cleanly():
    r = client.post(
        "/api/call", json={"namespace": "tdx", "method": "kline", "params": {"symbol": "000001.SZ"}}
    )
    j = r.json()
    assert j["ok"] is False
    assert j["error"]["type"] == "NotImplementedError"


def test_call_invalid_symbol_is_clean_error():
    # 非法代码在联网前就抛 ValueError,测试台应清晰回显
    r = client.post(
        "/api/call", json={"namespace": "dc", "method": "kline", "params": {"symbol": "???"}}
    )
    j = r.json()
    assert j["ok"] is False
    assert j["error"]["type"] == "ValueError"


def test_index_html():
    r = client.get("/")
    assert r.status_code == 200
    assert "probar 接口测试台" in r.text
