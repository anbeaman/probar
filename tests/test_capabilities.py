from probar.core.capabilities import CAPABILITIES, FULL, NONE, capabilities


def test_matrix_shape():
    df = capabilities()
    assert list(df.columns) == ["dc", "tdx", "ths"]
    assert df.index.name == "capability"
    assert len(df) == len(CAPABILITIES)


def test_known_cells():
    # 通达信没有资金流(协议无此数据域)
    assert CAPABILITIES["资金流 fund_flow"]["tdx"] == NONE
    # 问财是同花顺独有(dc/tdx 都没有)
    assert CAPABILITIES["自然语言选股 wencai"]["dc"] == NONE
    assert CAPABILITIES["自然语言选股 wencai"]["tdx"] == NONE
    # 历史逐笔只有通达信可取(dc/ths 无)
    assert CAPABILITIES["历史逐笔 ticks_hist"]["dc"] == NONE
    assert CAPABILITIES["历史逐笔 ticks_hist"]["ths"] == NONE


def test_implemented_tdx_interfaces_are_full():
    """已 clean-room 实现的通达信接口须标 FULL,防能力矩阵与实现静默漂移。"""
    for cap in (
        "当日逐笔 ticks",
        "历史逐笔 ticks_hist",
        "除权除息 xdxr",
        "K线 日/周/月",
        "K线 分钟",
        "证券代码表 securities",
    ):
        assert CAPABILITIES[cap]["tdx"] == FULL, f"{cap} tdx 档位应为 FULL"
