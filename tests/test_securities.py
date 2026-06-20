"""securities 标杆:解析器 + 列契约 + 禁网门禁(全离线)。"""

import json
import socket
from pathlib import Path

import pytest

from probar.core.errors import NoData, SchemaChanged
from probar.core.models import SECURITIES_COLUMNS
from probar.providers.eastmoney import parsers

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_parse_securities_schema_and_market():
    df = parsers.parse_securities(_load("eastmoney_securities.json"))
    assert list(df.columns) == SECURITIES_COLUMNS          # 列契约(schema contract)
    assert len(df) == 5
    by_code = {r["code"]: r for r in df.to_dict("records")}
    # market 由代码前缀推断:沪 / 深 / 京
    assert by_code["600519"]["market"] == "SH"
    assert by_code["000001"]["market"] == "SZ"
    assert by_code["300750"]["market"] == "SZ"
    assert by_code["688981"]["market"] == "SH"
    assert by_code["830799"]["market"] == "BJ"
    assert by_code["600519"]["symbol"] == "600519.SH"
    assert set(df["asset_type"]) == {"stock"}


def test_parse_securities_missing_diff_is_schema_changed():
    with pytest.raises(SchemaChanged):
        parsers.parse_securities({"data": {"total": 0}})


def test_parse_securities_null_data_is_nodata():
    with pytest.raises(NoData):
        parsers.parse_securities({"rc": 1, "data": None})


def test_securities_pagination(monkeypatch):
    # mock 掉 HTTP 层,离线验证 client 的分页 + 拼接 + 去重 + 末页终止
    from probar import EastMoney

    dc = EastMoney()
    pages = {
        1: {"data": {"total": 3, "diff": [
            {"f12": "600519", "f13": 1, "f14": "贵州茅台"},
            {"f12": "000001", "f13": 0, "f14": "平安银行"},
        ]}},
        2: {"data": {"total": 3, "diff": [{"f12": "300750", "f13": 0, "f14": "宁德时代"}]}},
        3: {"data": {"total": 3, "diff": []}},  # 末页
    }

    def fake_get_json(url, params=None, *, referer=None):
        return pages[params["pn"]]

    monkeypatch.setattr(dc._http, "get_json", fake_get_json)
    df = dc.securities(page_size=2)
    assert list(df.columns) == SECURITIES_COLUMNS
    assert len(df) == 3
    assert set(df["code"]) == {"600519", "000001", "300750"}
    assert df.attrs["total"] == 3


def test_securities_first_page_empty_with_total_is_schema_changed(monkeypatch):
    # total>0 但第一页空 diff = 异常响应,应抛 SchemaChanged 而非静默返回空表
    from probar import EastMoney

    dc = EastMoney()
    monkeypatch.setattr(
        dc._http, "get_json",
        lambda url, params=None, *, referer=None: {"data": {"total": 100, "diff": []}},
    )
    with pytest.raises(SchemaChanged):
        dc.securities()


def test_securities_cross_page_dedup(monkeypatch):
    from probar import EastMoney

    dc = EastMoney()
    pages = {
        1: {"data": {"total": 3, "diff": [
            {"f12": "600519", "f13": 1, "f14": "贵州茅台"},
            {"f12": "000001", "f13": 0, "f14": "平安银行"},
        ]}},
        2: {"data": {"total": 3, "diff": [
            {"f12": "000001", "f13": 0, "f14": "平安银行"},  # 跨页重复
            {"f12": "300750", "f13": 0, "f14": "宁德时代"},
        ]}},
        3: {"data": {"total": 3, "diff": []}},
    }
    monkeypatch.setattr(
        dc._http, "get_json",
        lambda url, params=None, *, referer=None: pages[params["pn"]],
    )
    df = dc.securities(page_size=2)
    assert len(df) == 3 and df["symbol"].nunique() == 3  # 去重后 3 只


def test_parse_securities_bad_code_is_schema_changed():
    with pytest.raises(SchemaChanged):
        parsers.parse_securities({"data": {"diff": [{"f12": "60X", "f14": "怪"}]}})


def test_network_gate_blocks_unmarked():
    # 未标 @network 的测试一旦尝试连**外网**应被拦截 —— 验证"单测禁网"门禁生效
    # 192.0.2.1 是 TEST-NET-1(RFC 5737),非本地、不可路由
    with pytest.raises(RuntimeError):
        socket.create_connection(("192.0.2.1", 80), timeout=1)
