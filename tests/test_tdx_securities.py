"""通达信 securities:codec(冻结真实字节)+ parser(筛股票/去重)+ client 装配,默认全离线。

``tdx_securities_raw.json`` 是用自写协议客户端连真实服务器抓回、冻结的 count / list 原始响应体
(并已与 pytdx 逐条交叉验证名称零不符);离线断言我方解码与筛选正确。
"""

import json
from pathlib import Path

import pytest

from probar.core.errors import NoData, SchemaChanged
from probar.core.models import SECURITIES_COLUMNS
from probar.providers.tdx import _codec, parsers

FIXTURES = Path(__file__).parent / "fixtures"


def _fx():
    return json.loads((FIXTURES / "tdx_securities_raw.json").read_text(encoding="utf-8"))


def test_decode_security_count():
    fx = _fx()
    assert _codec.decode_security_count(bytes.fromhex(fx["count_sz"])) == 23485
    assert _codec.decode_security_count(bytes.fromhex(fx["count_sh"])) == 27278


def test_decode_security_list():
    lst = _codec.decode_security_list(bytes.fromhex(_fx()["list_sz_page0"]), 0)
    assert len(lst) == 1000
    assert lst[0]["code"] == "395001" and lst[-1]["code"] == "002107"
    assert all(r["market"] == 0 for r in lst)
    assert all(r["code"].isdigit() and len(r["code"]) == 6 for r in lst)
    assert all(isinstance(r["name"], str) and r["name"] for r in lst)  # GBK 解码出非空名称


def test_decode_security_list_truncated_is_schema_changed():
    body = bytes.fromhex(_fx()["list_sz_page0"])[:100]   # 砍断:count 说有 1000 但体不够
    with pytest.raises(SchemaChanged):
        _codec.decode_security_list(body, 0)


def test_parse_securities_filters_and_dedup():
    raw = [
        {"market": 0, "code": "000001", "name": "平安银行"},   # 深主板股票
        {"market": 0, "code": "399001", "name": "深证成指"},   # 指数 -> 过滤
        {"market": 0, "code": "159915", "name": "创业板ETF"},  # ETF -> 过滤
        {"market": 1, "code": "600519", "name": "贵州茅台"},   # 沪主板股票
        {"market": 1, "code": "000001", "name": "上证指数"},   # 沪 000001 是指数 -> 过滤
        {"market": 1, "code": "688981", "name": "中芯国际"},   # 科创股票
        {"market": 0, "code": "000001", "name": "平安银行"},   # 跨页重复 -> 去重
    ]
    df = parsers.parse_securities(raw)
    assert list(df.columns) == SECURITIES_COLUMNS   # 只 symbol/code/name
    assert set(df["symbol"]) == {"000001.SZ", "600519.SH", "688981.SH"}
    assert "market" not in df.columns and "asset_type" not in df.columns
    # 交易所隐含在 symbol 后缀
    assert set(df["symbol"].str[-2:]) == {"SZ", "SH"}


def test_parse_securities_no_stock_is_nodata():
    with pytest.raises(NoData):   # 全是指数,筛完为空
        parsers.parse_securities([{"market": 0, "code": "399001", "name": "深证成指"}])


def test_parse_securities_bad_row_is_schema_changed():
    with pytest.raises(SchemaChanged):
        parsers.parse_securities([{"market": 0, "code": None, "name": "x"}])


class _FakeTransport:
    """离线替身:固定 count + 按 (market, start) 返回构造的页。"""

    def __init__(self):
        self.server = ("198.51.100.7", 7709)
        self._counts = {0: 2, 1: 1}
        self._pages = {
            (0, 0): [
                {"market": 0, "code": "000001", "name": "平安银行"},
                {"market": 0, "code": "399001", "name": "深证成指"},   # 指数,会被筛掉
            ],
            (1, 0): [{"market": 1, "code": "600519", "name": "贵州茅台"}],
        }

    def get_security_count(self, market):
        return self._counts.get(market, 0)

    def get_security_list(self, market, start):
        return self._pages.get((market, start), [])

    def close(self):
        pass


def test_securities_client_assembly_offline():
    from probar import Tdx

    tdx = Tdx()
    tdx._transport = _FakeTransport()          # 注入替身,绕过真实 TCP
    df = tdx.securities()
    assert list(df.columns) == SECURITIES_COLUMNS
    assert set(df["symbol"]) == {"000001.SZ", "600519.SH"}   # 指数被过滤,只剩股票
    assert df.attrs["schema_version"] == "tdx.securities/1"

    df2 = tdx.securities()                      # 命中缓存
    df2.loc[0, "name"] = "改了"                 # 改返回值不污染缓存(返回副本)
    assert "改了" not in set(tdx.securities()["name"])


def test_securities_incomplete_empty_page_raises():
    # 未到 count 却返回空页 -> SchemaChanged,不静默返回/缓存残表(回归保护)
    from probar import Tdx

    class _GappyTransport:
        server = ("198.51.100.7", 7709)

        def get_security_count(self, market):
            return 5 if market == 0 else 0       # 声称有 5 只

        def get_security_list(self, market, start):
            return [{"market": 0, "code": "000001", "name": "平安银行"}] if start == 0 else []

        def close(self):
            pass

    tdx = Tdx()
    tdx._transport = _GappyTransport()
    with pytest.raises(SchemaChanged):
        tdx.securities()


def test_transport_count_failover(monkeypatch):
    # count/list 与 quote 共用 _with_retry:坏服务器(连接/帧异常)应降级换台
    from probar.providers.tdx import transport as T
    from probar.providers.tdx._protocol import TdxProtocolError

    visited: list[str] = []

    class FakeClient:
        def __init__(self, *, timeout=5.0):
            self._host = None

        def connect(self, host, port):
            self._host = host
            visited.append(host)
            return True

        def get_security_quotes(self, req):   # 业务探针:都过
            return [
                {"market": 0, "code": "000001", "price": 10.5},
                {"market": 1, "code": "600519", "price": 1200.0},
            ]

        def get_security_count(self, market):
            if self._host == "bad":
                raise TdxProtocolError("boom")
            return 5208

        def disconnect(self):
            pass

    monkeypatch.setattr(T, "TdxClient", FakeClient)
    t = T.TdxTransport(servers=[("bad", 7709), ("good", 7709)])
    assert t.get_security_count(0) == 5208
    assert visited[0] == "bad" and "good" in visited


@pytest.mark.network
def test_securities_live():
    import probar as pb

    df = pb.tdx.securities(use_cache=False)
    assert list(df.columns) == SECURITIES_COLUMNS
    assert df["symbol"].nunique() >= 4500
    assert {"SH", "SZ"} <= set(df["symbol"].str[-2:])   # 交易所看 symbol 后缀
    assert "600519.SH" in set(df["symbol"])
