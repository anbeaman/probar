"""东财板块资金流榜:parser(冻结真实响应)+ client 分页装配,默认离线。"""

import json
from pathlib import Path

import pytest

from probar.core.errors import NoData, SchemaChanged
from probar.providers.eastmoney import endpoints as ep
from probar.providers.eastmoney import parsers

FIXTURES = Path(__file__).parent / "fixtures"


def _fx():
    return json.loads((FIXTURES / "dc_sector_fflow.json").read_text(encoding="utf-8"))


def test_parse_sector_fund_flow():
    df = parsers.parse_sector_fund_flow(_fx(), kind="industry")
    assert list(df.columns) == ep.SECTOR_FFLOW_COLUMNS
    assert df["main"].is_monotonic_decreasing                  # 按主力净额降序
    top = df.iloc[0]
    assert top["name"] == "非银金融" and top["code"] == "BK1203"
    assert top["pct_chg"] == pytest.approx(5.52)
    assert top["main"] == pytest.approx(12377014272.0)
    assert top["super"] == pytest.approx(10320172288.0)
    assert top["lead_stock"] == "东方财富"
    # main = super + large 量级合理(净额单位元)
    assert (df["main"] > 0).all()


def test_parse_sector_empty_is_nodata():
    with pytest.raises(NoData):
        parsers.parse_sector_fund_flow({"data": {"diff": []}}, kind="industry")


def test_parse_sector_missing_diff_is_schema_changed():
    with pytest.raises(SchemaChanged):
        parsers.parse_sector_fund_flow({"data": {"x": 1}}, kind="industry")


class _FakeHttp:
    def __init__(self, payload):
        self._payload = payload

    def get_json(self, url, params, **kw):
        return self._payload if params["pn"] == 1 else {"data": {"diff": []}}


def test_sector_fund_flow_client():
    from probar import EastMoney

    dc = EastMoney()
    dc._http = _FakeHttp(_fx())
    df = dc.sector_fund_flow("industry")
    assert list(df.columns) == ep.SECTOR_FFLOW_COLUMNS
    assert df["main"].is_monotonic_decreasing
    assert df.attrs["source"] == "dc" and df.attrs["kind"] == "industry"


def test_sector_fund_flow_bad_kind():
    from probar import EastMoney

    with pytest.raises(ValueError):
        EastMoney().sector_fund_flow("xyz")


def _page(lo, hi, total):
    diff = [{"f12": f"BK{i:04d}", "f14": f"板块{i}", "f3": 1.0, "f62": float(10000 - i),
             "f184": 1.0, "f66": 1.0, "f72": 1.0, "f78": 1.0, "f84": 1.0, "f204": "x"}
            for i in range(lo, hi)]
    return {"data": {"total": total, "diff": diff}}


class _FakeHttpPaged:
    def get_json(self, url, params, **kw):
        pn = params["pn"]
        if pn == 1:
            return _page(0, 100, 150)        # 满页 -> 继续翻
        if pn == 2:
            return _page(100, 150, 150)       # 不足一页 -> 停
        return {"data": {"diff": []}}


def test_sector_fund_flow_paginates():
    from probar import EastMoney

    dc = EastMoney()
    dc._http = _FakeHttpPaged()
    df = dc.sector_fund_flow("concept")
    assert len(df) == 150                      # 翻两页拼满
    assert df["main"].is_monotonic_decreasing


class _FakeHttpNoDiff:
    def get_json(self, url, params, **kw):
        return {"data": {"total": 10}}         # 缺 diff(上游字段变了)


def test_sector_fund_flow_missing_diff_is_schema_changed():
    from probar import EastMoney

    dc = EastMoney()
    dc._http = _FakeHttpNoDiff()
    with pytest.raises(SchemaChanged):         # 分页层不能把缺 diff 静默当空页
        dc.sector_fund_flow("industry")


@pytest.mark.network
def test_sector_fund_flow_live():
    import probar as pb

    for kind in ("industry", "concept"):
        df = pb.dc.sector_fund_flow(kind)
        assert list(df.columns) == ep.SECTOR_FFLOW_COLUMNS
        assert len(df) > 50                                    # 板块数百
        assert df["main"].is_monotonic_decreasing
        assert df["pct_chg"].notna().any()
