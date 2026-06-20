from probar.core import symbols
from probar.core.symbols import BJ, SH, SZ


def test_normalize_plain_code():
    assert symbols.normalize("600519") == symbols.Symbol("600519", SH)
    assert symbols.normalize("000001") == symbols.Symbol("000001", SZ)
    assert symbols.normalize("300750") == symbols.Symbol("300750", SZ)
    assert symbols.normalize("688981") == symbols.Symbol("688981", SH)
    assert symbols.normalize("830799") == symbols.Symbol("830799", BJ)


def test_normalize_suffixed_and_prefixed():
    assert symbols.normalize("600519.SH").ts_code == "600519.SH"
    assert symbols.normalize("000001.sz").ts_code == "000001.SZ"
    assert symbols.normalize("SH600519").ts_code == "600519.SH"
    assert symbols.normalize("sz.000001").ts_code == "000001.SZ"


def test_market_inference_table():
    cases = {
        "688981": "688981.SH",  # 科创板
        "300750": "300750.SZ",  # 创业板
        "510300": "510300.SH",  # 沪市 ETF
        "159915": "159915.SZ",  # 深市 ETF
        "113008": "113008.SH",  # 沪市可转债
        "128036": "128036.SZ",  # 深市可转债
        "830799": "830799.BJ",  # 北交所
    }
    for code, expected in cases.items():
        assert symbols.normalize(code).ts_code == expected


def test_to_eastmoney_secid():
    assert symbols.to_eastmoney_secid("600519.SH") == "1.600519"
    assert symbols.to_eastmoney_secid("000001.SZ") == "0.000001"


def test_invalid_prefixed_code_rejected():
    import pytest

    with pytest.raises(ValueError):
        symbols.normalize("SHABC")


def test_to_tdx():
    assert symbols.to_tdx("000001.SZ") == (0, "000001")
    assert symbols.to_tdx("600519.SH") == (1, "600519")


def test_invalid():
    import pytest

    with pytest.raises(ValueError):
        symbols.normalize("not-a-code")
