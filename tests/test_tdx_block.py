"""通达信板块/成分股:codec(合成 .dat 测布局+填充过滤)+ parser + client,默认离线。"""

import struct

import pytest

from probar.core.errors import NoData, SchemaChanged
from probar.providers.tdx import _codec, parsers

_COLS = ["block", "symbol", "code"]


def _make_dat(blocks):
    """构造合成板块 .dat:384 头 + <H 块数 + 每块(9 GBK 名 + <HH(成分数,类型)+ 2800 成分区)。

    blocks: [(name, stock_count_field, [codes]), ...];stock_count_field 可故意设大以测填充过滤。
    """
    buf = bytearray(384)                       # 头(全 0)
    buf += struct.pack("<H", len(blocks))
    for name, count_field, codes in blocks:
        buf += name.encode("gbk")[:9].ljust(9, b"\x00")
        buf += struct.pack("<HH", count_field, 2)   # block_type 恒 2
        section = bytearray(2800)
        for i, c in enumerate(codes[:400]):
            section[7 * i:7 * i + 7] = c.encode("ascii").ljust(7, b"\x00")
        buf += section
    return bytes(buf)


def test_decode_block():
    dat = _make_dat([
        ("沪深300", 2, ["600519", "000001"]),
        ("创业板指", 1, ["300750"]),
        ("", 1, ["999999"]),                   # 空名填充块 -> 过滤
        ("垃圾块", 9999, ["600000"]),          # 成分数 >400 -> 过滤
    ])
    rows = _codec.decode_block(dat)
    assert {(r["block"], r["code"]) for r in rows} == {
        ("沪深300", "600519"), ("沪深300", "000001"), ("创业板指", "300750"),
    }
    assert all(r["block"] for r in rows)        # 无空名


def test_decode_block_no_valid_is_schema_changed():
    dat = _make_dat([("", 1, ["600519"]), ("垃圾", 9999, ["000001"])])
    with pytest.raises(SchemaChanged):          # 全是填充/垃圾块 -> 0 有效
        _codec.decode_block(dat)


def test_decode_block_truncated_is_schema_changed():
    # 头部声明 3 块,但文件只够 1 块长度 -> 截断,应抛 SchemaChanged(而非静默产出部分行)
    full = _make_dat([("沪深300", 1, ["600519"]), ("B", 1, ["300750"]), ("C", 1, ["000001"])])
    with pytest.raises(SchemaChanged):
        _codec.decode_block(full[:384 + 2 + 2813])   # 只保留 1 块


def test_parse_block():
    raw = [{"block": "沪深300", "code": "600519"}, {"block": "沪深300", "code": "000001"},
           {"block": "创业板指", "code": "300750"}, {"block": "创业板指", "code": "302132"},
           {"block": "精选指数", "code": "399001"}]   # 指数代码应被剔除
    df = parsers.parse_block(raw)
    assert list(df.columns) == _COLS
    assert "399001" not in set(df["code"])             # 指数代码已过滤
    assert "302132" in set(df["code"])                 # 创业板新前缀(302)股票保留、不误杀
    by = {(r.block, r.code): r.symbol for r in df.itertuples()}
    assert by[("沪深300", "600519")] == "600519.SH"   # 前缀推断交易所
    assert by[("沪深300", "000001")] == "000001.SZ"
    assert by[("创业板指", "300750")] == "300750.SZ"


def test_parse_block_all_index_is_nodata():
    with pytest.raises(NoData):                         # 全是指数代码 -> 无有效成分股
        parsers.parse_block([{"block": "精选指数", "code": "399001"},
                             {"block": "精选指数", "code": "399006"}])


def test_parse_block_empty_is_nodata():
    with pytest.raises(NoData):
        parsers.parse_block([])


class _FakeTransport:
    def __init__(self, rows):
        self._rows = rows
        self.server = ("198.51.100.7", 7709)

    def get_block(self, blockfile):
        return self._rows

    def close(self):
        pass


def test_block_client():
    from probar import Tdx

    tdx = Tdx()
    tdx._transport = _FakeTransport(
        [{"block": "通达信88", "code": "000408"}, {"block": "通达信88", "code": "000538"}]
    )
    df = tdx.block("concept")
    assert list(df.columns) == _COLS
    assert set(df["block"]) == {"通达信88"}
    assert "000408.SZ" in set(df["symbol"])
    assert df.attrs["source"] == "tdx" and df.attrs["kind"] == "concept"


def test_block_bad_kind():
    from probar import Tdx

    with pytest.raises(ValueError):
        Tdx().block("xyz")


def test_block_list_and_cons():
    from probar import Tdx

    rows = [{"block": "板块A", "code": "600519"}, {"block": "板块A", "code": "000001"},
            {"block": "板块B", "code": "300750"}]
    tdx = Tdx()
    tdx._transport = _FakeTransport(rows)
    lst = tdx.block_list("concept")                       # 有哪些板块
    assert list(lst.columns) == ["block", "count"]
    assert dict(zip(lst["block"], lst["count"], strict=True)) == {"板块A": 2, "板块B": 1}
    cons = tdx.block_cons("板块A", kind="concept")        # 某板块成分股
    assert list(cons.columns) == ["symbol", "code"]
    assert set(cons["symbol"]) == {"600519.SH", "000001.SZ"}
    assert cons.attrs["block"] == "板块A"


def test_block_cons_unknown_is_nodata():
    from probar import Tdx

    tdx = Tdx()
    tdx._transport = _FakeTransport([{"block": "板块A", "code": "600519"}])
    with pytest.raises(NoData):
        tdx.block_cons("不存在的板块", kind="concept")


@pytest.mark.network
def test_block_live():
    import probar as pb

    idx = pb.tdx.block("index")
    assert list(idx.columns) == _COLS
    hs300 = idx[idx["block"] == "沪深300"]
    assert len(hs300) == 300                    # 沪深300 恰 300 只(铁证)
    assert "600519.SH" in set(hs300["symbol"])  # 含茅台
