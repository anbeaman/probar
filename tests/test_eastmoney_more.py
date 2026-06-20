"""东财 fund_flow / intraday / lhb / financials 解析器的离线测试(基于真实响应 fixture)。"""

import json
from pathlib import Path

import pandas as pd
import pytest

from probar.core.errors import NoData, SchemaChanged
from probar.providers.eastmoney import endpoints as ep
from probar.providers.eastmoney import parsers

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_parse_fflow():
    df = parsers.parse_fflow(_load("eastmoney_fflow.json"), symbol="600519.SH")
    assert list(df.columns) == ["symbol", "date", *ep.FFLOW_NUMERIC]
    assert len(df) == 2
    row = df.iloc[0]
    assert row["symbol"] == "600519.SH"
    assert isinstance(row["date"], pd.Timestamp)
    assert row["main"] == -544577072.0
    assert row["super"] == -306740640.0
    assert row["close"] == 1255.67
    # 主力净额 = 大单 + 超大单(校验字段映射对齐)
    assert round(row["large"] + row["super"]) == round(row["main"])


def test_parse_trends():
    df = parsers.parse_trends(_load("eastmoney_trends.json"), symbol="600519.SH")
    expected = ["symbol", "time", "open", "high", "low", "close", "volume", "amount", "avg"]
    assert list(df.columns) == expected
    assert len(df) == 3
    assert isinstance(df.iloc[0]["time"], pd.Timestamp)
    assert df.iloc[0]["close"] == 1235.0
    assert df.iloc[-1]["avg"] == 1220.898


def test_parse_lhb():
    df = parsers.parse_datacenter(_load("eastmoney_lhb.json"), mapping=ep.LHB_MAP, interface="lhb")
    assert list(df.columns) == list(ep.LHB_MAP.values())
    assert len(df) == 2
    assert df.iloc[0]["code"] == "301687"
    assert df.iloc[0]["net_buy"] == 50000000.0


def test_parse_financials():
    df = parsers.parse_datacenter(
        _load("eastmoney_financials.json"), mapping=ep.FINANCIALS_MAP, interface="financials"
    )
    assert list(df.columns) == list(ep.FINANCIALS_MAP.values())
    assert df.iloc[0]["eps"] == 18.5
    assert df.iloc[0]["roe"] == 8.9


def test_datacenter_empty_is_nodata():
    with pytest.raises(NoData):
        parsers.parse_datacenter(
            {"success": True, "result": {"data": []}}, mapping=ep.LHB_MAP, interface="lhb"
        )


def test_datacenter_missing_field_is_schema_changed():
    payload = {"success": True, "result": {"data": [{"TRADE_DATE": "2026-06-18"}]}}
    with pytest.raises(SchemaChanged):
        parsers.parse_datacenter(payload, mapping=ep.LHB_MAP, interface="lhb")


def test_fflow_nan_main_is_schema_changed():
    payload = {"data": {"klines": ["2026-06-18,bad,1,2,3,4,5,6,7,8,9,10,11"]}}
    with pytest.raises(SchemaChanged):
        parsers.parse_fflow(payload, symbol="600519.SH")


def test_datacenter_partial_missing_row_is_schema_changed():
    # 首行完整、后续行缺字段:不能被 pandas 静默补 NaN,应抛 SchemaChanged
    payload = {
        "success": True,
        "result": {"data": [{k: 1 for k in ep.LHB_MAP}, {"TRADE_DATE": "2026-06-18"}]},
    }
    with pytest.raises(SchemaChanged):
        parsers.parse_datacenter(payload, mapping=ep.LHB_MAP, interface="lhb")


def test_datacenter_result_null_is_nodata():
    with pytest.raises(NoData):
        parsers.parse_datacenter(
            {"success": True, "result": None}, mapping=ep.LHB_MAP, interface="lhb"
        )


def test_lhb_rejects_bad_date():
    import probar as pb

    with pytest.raises(ValueError):
        pb.dc.lhb(date="2026/06/18")  # 非 YYYY-MM-DD,应在联网前就报错
