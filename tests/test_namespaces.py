"""命名空间形态测试:每个源只暴露其真实支持的接口(能力矩阵 = 可发现 API)。"""

import probar as pb


def test_namespaces_exist():
    assert pb.dc.name == "dc"
    assert pb.tdx.name == "tdx"
    assert pb.ths.name == "ths"


def test_dc_surface():
    methods = ["quote", "quotes", "kline", "fund_flow", "lhb", "hsgt"]
    methods += ["financials", "securities", "xdxr"]
    for m in methods:
        assert callable(getattr(pb.dc, m)), m


def test_tdx_has_no_unsupported_methods():
    # 通达信协议无资金流/龙虎榜/北向 —— 命名空间里压根不该有这些属性
    assert not hasattr(pb.tdx, "fund_flow")
    assert not hasattr(pb.tdx, "lhb")
    assert not hasattr(pb.tdx, "hsgt")
    # 但应有其强项接口
    assert callable(pb.tdx.ticks_hist)
    assert callable(pb.tdx.xdxr)


def test_ths_flagship():
    assert callable(pb.ths.wencai)
    assert callable(pb.ths.concept)


def test_unimplemented_raise_not_implemented():
    import pytest

    with pytest.raises(NotImplementedError):
        pb.tdx.kline("000001.SZ")
    with pytest.raises(NotImplementedError):
        pb.ths.wencai("涨停")
