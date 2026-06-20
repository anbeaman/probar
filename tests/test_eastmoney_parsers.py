"""东财解析器的离线确定性测试:喂冻结样本,测 parser,不碰网络。"""

import json
from pathlib import Path

import pandas as pd
import pytest

from probar.core.errors import NoData, SchemaChanged
from probar.core.models import KLINE_COLUMNS
from probar.providers.eastmoney import parsers

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_parse_kline_columns_and_values():
    payload = _load("eastmoney_kline.json")
    df = parsers.parse_kline(payload, symbol="600519.SH")

    assert list(df.columns) == KLINE_COLUMNS
    assert len(df) == 2

    row = df.iloc[0]
    assert row["symbol"] == "600519.SH"
    assert isinstance(row["date"], pd.Timestamp)
    assert row["open"] == 1685.01
    assert row["high"] == 1695.00
    assert row["low"] == 1640.00
    assert row["close"] == 1648.00
    assert row["pct_chg"] == -2.11
    assert row["turnover"] == 0.31
    # 数值列应为浮点
    assert df["close"].dtype == float


def test_parse_kline_empty_is_nodata():
    payload = {"rc": 0, "data": {"code": "600519", "klines": []}}
    with pytest.raises(NoData):
        parsers.parse_kline(payload, symbol="600519.SH")


def test_parse_kline_null_data_is_nodata():
    with pytest.raises(NoData):
        parsers.parse_kline({"rc": 1, "data": None}, symbol="000001.SZ")


def test_parse_kline_missing_klines_is_schema_changed():
    with pytest.raises(SchemaChanged):
        parsers.parse_kline({"rc": 0, "data": {"code": "x"}}, symbol="000001.SZ")


def test_parse_kline_nan_close_is_schema_changed():
    # close 字段为非数值 -> 解析成 NaN -> 应报 SchemaChanged 而非静默返回脏数据
    payload = {
        "rc": 0,
        "data": {"code": "x", "klines": ["2024-01-02,1685.01,abc,1695,1640,1,1,1,1,1,1"]},
    }
    with pytest.raises(SchemaChanged):
        parsers.parse_kline(payload, symbol="600519.SH")


def test_parse_quote_empty_is_nodata():
    with pytest.raises(NoData):
        parsers.parse_quote({"data": {"f59": 2}}, symbol="600519.SH")


def test_parse_quote_scaling():
    payload = {
        "data": {
            "f43": 164800,  # 最新价 * 100
            "f44": 169500,
            "f45": 164000,
            "f46": 168501,
            "f47": 38421,
            "f48": 6398000000,
            "f57": "600519",
            "f58": "贵州茅台",
            "f60": 168351,
            "f170": -211,  # 涨跌幅 * 100 -> -2.11%
            "f59": 2,
        }
    }
    q = parsers.parse_quote(payload, symbol="600519.SH")
    assert q["name"] == "贵州茅台"
    assert q["price"] == 1648.00
    assert q["prev_close"] == 1683.51
    assert q["pct_chg"] == -2.11
