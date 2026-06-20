from probar.core.capabilities import CAPABILITIES, NONE, capabilities


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
