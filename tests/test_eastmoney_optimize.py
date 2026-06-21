"""东财优化离线测试:kline 兜底截断 + securities 缓存 + quotes 批量(全离线,mock HTTP)。"""

import json
from pathlib import Path

import pandas as pd
import pytest

from probar.core.errors import NoData, SchemaChanged
from probar.core.models import QUOTE_COLUMNS
from probar.providers.eastmoney import parsers

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_kline_caps_to_limit(monkeypatch):
    # 东财在 beg=0 时会忽略 lmt 返回整段历史;client 应兜底只留最近 limit 根
    from probar import EastMoney

    dc = EastMoney()
    klines = [f"2024-01-{d:02d},10,11,12,9,100,1000,5,1.0,0.1,0.5" for d in range(1, 11)]
    payload = {"rc": 0, "data": {"code": "600519", "klines": klines}}
    monkeypatch.setattr(dc._http, "get_json", lambda *a, **k: payload)

    df = dc.kline("600519.SH", freq="1d", adjust="qfq", limit=3)
    assert len(df) == 3                                   # 截到 limit
    assert df["date"].iloc[-1] == pd.Timestamp("2024-01-10")  # 取最近的
    assert df["date"].iloc[0] == pd.Timestamp("2024-01-08")
    assert list(df.index) == [0, 1, 2]                    # reset_index
    assert df.attrs["source"] == "dc"                     # 兜底后溯源仍在


def test_kline_under_limit_unchanged(monkeypatch):
    from probar import EastMoney

    dc = EastMoney()
    klines = [f"2024-01-{d:02d},10,11,12,9,100,1000,5,1.0,0.1,0.5" for d in range(1, 4)]
    monkeypatch.setattr(dc._http, "get_json", lambda *a, **k: {"data": {"klines": klines}})
    df = dc.kline("600519.SH", limit=100)
    assert len(df) == 3                                   # 不足 limit 时全返回


def test_kline_with_start_not_truncated(monkeypatch):
    # 给了 start 的区间查询不应被 limit 截掉早段(回归保护)
    from probar import EastMoney

    dc = EastMoney()
    klines = [f"2024-01-{d:02d},10,11,12,9,100,1000,5,1.0,0.1,0.5" for d in range(1, 11)]
    monkeypatch.setattr(dc._http, "get_json", lambda *a, **k: {"data": {"klines": klines}})
    df = dc.kline("600519.SH", start="2024-01-01", limit=3)
    assert len(df) == 10                                  # start 给定 -> 不按 limit 截


_PAGES = {
    1: {"data": {"total": 2, "diff": [
        {"f12": "600519", "f13": 1, "f14": "贵州茅台"},
        {"f12": "000001", "f13": 0, "f14": "平安银行"},
    ]}},
    2: {"data": {"total": 2, "diff": []}},
}


def test_securities_cache_hit_and_copy(monkeypatch):
    from probar import EastMoney

    dc = EastMoney(cache_ttl=60)
    calls = {"n": 0}

    def fake(url, params=None, *, referer=None):
        calls["n"] += 1
        return _PAGES[params["pn"]]

    monkeypatch.setattr(dc._http, "get_json", fake)

    df1 = dc.securities()
    first = calls["n"]
    assert len(df1) == 2 and first >= 1

    df2 = dc.securities()                 # 命中缓存:不再发 HTTP
    assert calls["n"] == first
    assert len(df2) == 2

    df2.loc[0, "name"] = "改了"           # 改返回值不污染缓存(返回的是副本)
    assert "改了" not in set(dc.securities()["name"])
    dc.securities().attrs["source"] = "tampered"        # 改 attrs 也不污染缓存
    assert dc.securities().attrs.get("source") == "dc"

    dc.securities(use_cache=False)        # 显式绕过缓存 -> 重新请求
    assert calls["n"] > first


def test_securities_incomplete_raises(monkeypatch):
    # 100 页耗尽仍未拉满(< total)-> SchemaChanged,不缓存残表(回归保护)
    from probar import EastMoney

    dc = EastMoney()
    pages = {
        1: {"data": {"total": 5, "diff": [
            {"f12": "600519", "f14": "x"}, {"f12": "000001", "f14": "y"},
        ]}},
        2: {"data": {"total": 5, "diff": []}},   # 末页,但只收到 2/5
    }
    monkeypatch.setattr(
        dc._http, "get_json", lambda url, params=None, *, referer=None: pages[params["pn"]]
    )
    with pytest.raises(SchemaChanged):
        dc.securities(page_size=2)


def test_parse_quotes_batch():
    df = parsers.parse_quotes_batch(_load("eastmoney_quotes_batch.json"))
    assert list(df.columns) == QUOTE_COLUMNS
    assert len(df) == 2
    by = {r["symbol"]: r for r in df.to_dict("records")}
    a = by["000001.SZ"]
    assert a["name"] == "平安银行"
    assert a["price"] == 10.52 and a["open"] == 10.74 and a["prev_close"] == 10.78
    assert a["high"] == 10.77 and a["low"] == 10.52
    assert a["pct_chg"] == -2.41
    assert by["600519.SH"]["price"] == 1215.0


def test_parse_quotes_batch_empty_is_nodata():
    with pytest.raises(NoData):
        parsers.parse_quotes_batch({"data": {"total": 0, "diff": []}})


def test_quotes_batch_single_request(monkeypatch):
    from probar import EastMoney

    dc = EastMoney()
    seen = {}

    def fake(url, params=None, *, referer=None):
        seen["url"], seen["params"] = url, params
        return _load("eastmoney_quotes_batch.json")

    monkeypatch.setattr(dc._http, "get_json", fake)
    df = dc.quotes(["000001.SZ", "600519.SH"])
    assert list(df.columns) == QUOTE_COLUMNS and len(df) == 2
    assert seen["url"].endswith("ulist.np/get")             # 走批量端点
    assert seen["params"]["fltt"] == 2
    assert seen["params"]["secids"] == "0.000001,1.600519"  # 两只拼成一次请求
    assert df.attrs["source"] == "dc"


def test_quotes_batch_chunks(monkeypatch):
    from probar import EastMoney
    from probar.providers.eastmoney import endpoints as ep

    monkeypatch.setattr(ep, "QUOTES_MAX_PER_REQ", 2)  # 每批 2 只
    dc = EastMoney()
    secids_seen = []

    def fake(url, params=None, *, referer=None):
        secids_seen.append(params["secids"])
        return _load("eastmoney_quotes_batch.json")

    monkeypatch.setattr(dc._http, "get_json", fake)
    dc.quotes(["000001.SZ", "600519.SH", "300750.SZ"])   # 3 只 / 每批 2 -> 2 次
    assert secids_seen == ["0.000001,1.600519", "0.300750"]   # 分批 secids 正确


def test_quotes_empty_raises():
    from probar import EastMoney

    with pytest.raises(ValueError):
        EastMoney().quotes([])


@pytest.mark.network
def test_quotes_batch_live():
    import probar as pb

    df = pb.dc.quotes(["000001.SZ", "600519.SH"])
    assert list(df.columns) == QUOTE_COLUMNS
    assert len(df) >= 1 and (df["price"] > 0).all()
