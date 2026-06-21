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
    assert nss == {"dc", "tdx", "ths"}            # 恰好三源;auto 若回归即失败

    dc = next(g for g in j["catalog"] if g["namespace"] == "dc")
    impl = {m["name"]: m["implemented"] for m in dc["methods"]}
    assert impl["kline"] is True            # 已实现
    assert impl["intraday_hist"] is False   # stub
    assert "fund_flow" in impl
    # tdx 不暴露资金流(协议无此数据域)
    tdx = next(g for g in j["catalog"] if g["namespace"] == "tdx")
    assert "fund_flow" not in {m["name"] for m in tdx["methods"]}
    assert j["capabilities"]

    # 每个接口带「示例参数」与「注意事项」供页面展示
    km = next(m for m in dc["methods"] if m["name"] == "kline")
    assert km["example"].get("symbol")        # 可一键填入的示例参数
    assert km["note"]                          # 注意事项
    assert "summary" in km and "doc" in km
    assert km["returns"]["kind"] == "DataFrame"   # 结构化返回格式
    assert any(f[0] == "close" for f in km["returns"]["fields"])
    ih = next(m for m in dc["methods"] if m["name"] == "intraday_hist")
    assert "NotImplementedError" in ih["note"]  # 未实现接口给默认提示


def test_call_stub_returns_error_cleanly():
    # tdx.block 仍是 stub(NotImplementedError,无参数);测试台应清晰回显异常类型
    r = client.post(
        "/api/call",
        json={"namespace": "tdx", "method": "block", "params": {}},
    )
    j = r.json()
    assert j["ok"] is False
    assert j["error"]["type"] == "NotImplementedError"


def test_call_not_supported_returns_error_cleanly():
    # tdx.intraday 有意不提供 -> NotSupported,测试台清晰回显(指向 kline 1m)
    r = client.post(
        "/api/call",
        json={"namespace": "tdx", "method": "intraday", "params": {"symbol": "000001.SZ"}},
    )
    j = r.json()
    assert j["ok"] is False
    assert j["error"]["type"] == "NotSupported"


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
