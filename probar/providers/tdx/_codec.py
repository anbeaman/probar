"""通达信二进制行情的纯函数编解码(clean-room,零第三方依赖)。

只复刻**协议事实**(字节布局 + 整数/价格/成交额的编码算法),不照搬任何实现代码;
协议说明见同目录 ``PROTOCOL.md``。输出 dict 的字段名/形态对齐 :mod:`.parsers` 的输入约定。

要点:
  - TDX 价格用"变长有符号整数"(vint)编码;开高低收与五档都存成相对基准价的**差分**,
    最终价 = ``(base + diff) / 100``;
  - 成交额用一种 32 位整数承载的**私有压缩浮点**(:func:`decode_amount`);
  - 服务器时间由一个整数按 :func:`_format_time` 还原成 ``HH:MM:SS.mmm``。
"""

from __future__ import annotations

import struct
from typing import Any

from ...core.errors import SchemaChanged

_LEVELS = range(1, 6)


def read_vint(buf: bytes, pos: int) -> tuple[int, int]:
    """读 TDX 变长有符号整数,返回 ``(值, 新位置)``。

    首字节:低 6 位为数值低位,bit6(``0x40``)为符号,bit7(``0x80``)表示"还有后续字节";
    后续每字节取低 7 位,依次左移 6、13、20… 拼接。
    """
    b = buf[pos]
    pos += 1
    value = b & 0x3F
    negative = bool(b & 0x40)
    shift = 6
    while b & 0x80:
        b = buf[pos]
        pos += 1
        value |= (b & 0x7F) << shift
        shift += 7
    return (-value if negative else value), pos


def decode_amount(raw: int) -> float:
    """解 TDX 成交额的压缩浮点:高字节为指数,低 3 字节为尾数。"""
    exponent = (raw >> 24) & 0xFF
    b2 = (raw >> 16) & 0xFF
    b1 = (raw >> 8) & 0xFF
    b0 = raw & 0xFF

    e_hi = exponent * 2 - 0x7F
    e_b2 = exponent * 2 - 0x86
    e_b1 = exponent * 2 - 0x8E
    e_b0 = exponent * 2 - 0x96

    out = 2.0 ** abs(e_hi)
    if e_hi < 0:
        out = 1.0 / out

    if b2 > 0x80:
        part = (2.0**e_b2) * 128.0 + (b2 & 0x7F) * (2.0 ** (e_b2 + 1))
    elif e_b2 >= 0:
        part = (2.0**e_b2) * b2
    else:
        # 此负指数分支照协议参考算法实现,已 oracle 逐字节验证,勿改(改了反与真值不符)
        part = (1.0 / (2.0**e_b2)) * b2
    out += part

    t_b1 = (2.0**e_b1) * b1
    t_b0 = (2.0**e_b0) * b0
    if b2 & 0x80:
        t_b1 *= 2.0
        t_b0 *= 2.0
    return out + t_b1 + t_b0


def _price(base: int, diff: int) -> float:
    return (base + diff) / 100.0


def _format_time(raw: int) -> str | None:
    """把 TDX 的整数时间戳还原成 ``HH:MM:SS.mmm``;格式异常返回 None。"""
    try:
        s = str(raw)
        out = s[:-6] + ":"
        if int(s[-6:-4]) < 60:
            out += f"{s[-6:-4]}:"
            out += f"{int(s[-4:]) * 60 / 10000.0:06.3f}"
        else:
            out += f"{int(s[-6:]) * 60 // 1000000:02d}:"
            out += f"{(int(s[-6:]) * 60 % 1000000) * 60 / 1000000.0:06.3f}"
        return out
    except (ValueError, IndexError):
        return None


def decode_quotes(body: bytes) -> list[dict[str, Any]]:
    """解码 get_security_quotes 响应体 -> ``list[dict]``(对接 :func:`.parsers.parse_quotes`)。

    响应体已过帧层长度校验;若内容不符合预期协议布局(截断 / 尾部多余 / 字段错位),抛
    :class:`SchemaChanged` 由上层如实上报,而**不**被当作"坏服务器"无限换(避免掩盖解码 bug)。
    """
    try:
        pos = 2  # 跳过 2 字节包头(b1, cb)
        (count,) = struct.unpack_from("<H", body, pos)
        pos += 2
        out: list[dict[str, Any]] = []
        for _ in range(count):
            market, code, active1 = struct.unpack_from("<B6sH", body, pos)
            pos += 9
            base, pos = read_vint(body, pos)
            last_close_diff, pos = read_vint(body, pos)
            open_diff, pos = read_vint(body, pos)
            high_diff, pos = read_vint(body, pos)
            low_diff, pos = read_vint(body, pos)
            rb0, pos = read_vint(body, pos)  # 服务器时间编码源
            _, pos = read_vint(body, pos)  # reserved
            vol, pos = read_vint(body, pos)
            cur_vol, pos = read_vint(body, pos)
            (amount_raw,) = struct.unpack_from("<I", body, pos)
            pos += 4
            s_vol, pos = read_vint(body, pos)
            b_vol, pos = read_vint(body, pos)
            _, pos = read_vint(body, pos)  # reserved
            _, pos = read_vint(body, pos)  # reserved

            levels: dict[str, Any] = {}
            for i in _LEVELS:
                bid_diff, pos = read_vint(body, pos)
                ask_diff, pos = read_vint(body, pos)
                bid_vol, pos = read_vint(body, pos)
                ask_vol, pos = read_vint(body, pos)
                levels[f"bid{i}"] = _price(base, bid_diff)
                levels[f"ask{i}"] = _price(base, ask_diff)
                levels[f"bid_vol{i}"] = bid_vol
                levels[f"ask_vol{i}"] = ask_vol

            pos += 2  # reserved <H>
            for _ in range(4):  # reserved ×4(vint)
                _, pos = read_vint(body, pos)
            pos += 4  # reserved + active2 <hH>

            out.append(
                {
                    "market": market,
                    "code": code.decode("utf-8"),
                    "active1": active1,
                    "price": _price(base, 0),
                    "last_close": _price(base, last_close_diff),
                    "open": _price(base, open_diff),
                    "high": _price(base, high_diff),
                    "low": _price(base, low_diff),
                    "servertime": _format_time(rb0),
                    "vol": vol,
                    "cur_vol": cur_vol,
                    "amount": decode_amount(amount_raw),
                    "s_vol": s_vol,
                    "b_vol": b_vol,
                    **levels,
                }
            )
        consumed = pos
    except (struct.error, IndexError, UnicodeDecodeError, OverflowError) as e:
        raise SchemaChanged(f"通达信 quote 响应不符合预期协议布局: {e}") from e
    # 帧长正确但内容没消费完(尾部截断会令 pos 越界、尾部垃圾会令 pos 不到尾)
    if consumed != len(body):
        raise SchemaChanged(f"通达信 quote 响应长度不符:消费 {consumed} != 实际 {len(body)}")
    return out


def decode_security_count(body: bytes) -> int:
    """解 get_security_count 响应 -> 该市场证券数量(count 在偏移 0,uint16)。"""
    try:
        (count,) = struct.unpack_from("<H", body, 0)
    except struct.error as e:
        raise SchemaChanged(f"通达信 security_count 响应异常: {e}") from e
    return count


def decode_security_list(body: bytes, market: int) -> list[dict[str, Any]]:
    """解 get_security_list 一页 -> ``list[dict]``(market/code/name/decimal/pre_close)。

    count(``<H``)在偏移 0,随后每条 29 字节 ``<6sH8s4sBI4s``:
    code(6 位 ascii)/ volunit / name(8 字节 GBK)/ 保留 / 小数位 / 昨收(压缩浮点)/ 保留。
    """
    try:
        (count,) = struct.unpack_from("<H", body, 0)
        pos = 2
        out: list[dict[str, Any]] = []
        for _ in range(count):
            code_b, _vu, name_b, _r1, decimal, preclose_raw, _r2 = struct.unpack_from(
                "<6sH8s4sBI4s", body, pos
            )
            pos += 29
            out.append(
                {
                    "market": market,
                    "code": code_b.decode("ascii"),
                    "name": name_b.decode("gbk", errors="replace").rstrip("\x00").strip(),
                    "decimal": decimal,
                    "pre_close": decode_amount(preclose_raw),
                }
            )
    except (struct.error, IndexError, UnicodeDecodeError) as e:
        raise SchemaChanged(f"通达信 security_list 响应不符合预期协议布局: {e}") from e
    if pos != len(body):
        raise SchemaChanged(f"通达信 security_list 响应长度不符: pos {pos} != 实际 {len(body)}")
    return out


def _kline_datetime(category: int, buf: bytes, pos: int) -> tuple[int, int, int, int, int, int]:
    """按 K 线周期解出 (年,月,日,时,分,新位置)。分钟级含时分,日及以上仅日期(时=15分=0)。"""
    if category < 4 or category in (7, 8):   # 分钟级(5/15/30/60min、1min):4 字节 = 日(H)+ 分钟数(H)
        zipday, tmin = struct.unpack_from("<HH", buf, pos)
        year = (zipday >> 11) + 2004
        month = (zipday % 2048) // 100
        day = (zipday % 2048) % 100
        hour, minute = tmin // 60, tmin % 60
    else:                                    # 日/周/月:4 字节 = YYYYMMDD(I)
        (zipday,) = struct.unpack_from("<I", buf, pos)
        year, month, day = zipday // 10000, (zipday % 10000) // 100, zipday % 100
        hour, minute = 15, 0
    return year, month, day, hour, minute, pos + 4


def decode_kline(body: bytes, category: int) -> list[dict[str, Any]]:
    """解码 get_security_bars 响应 -> ``list[dict]``(datetime/open/close/high/low/vol/amount)。

    count(``<H``)在偏移 0;每 bar:datetime(按 category)+ 开/收/高/低 4 个 vint **跨 bar 差分**
    + vol/amount 各 ``<I``(压缩浮点)。价格用 ``/1000``:开 = (开差 + 上一 bar 收基准)/1000,
    收/高/低 = (绝对开 + 各自差分)/1000;下一 bar 的基准 = 绝对开 + 收差。
    """
    try:
        (count,) = struct.unpack_from("<H", body, 0)
        pos = 2
        out: list[dict[str, Any]] = []
        base = 0
        for _ in range(count):
            year, month, day, hour, minute, pos = _kline_datetime(category, body, pos)
            open_diff, pos = read_vint(body, pos)
            close_diff, pos = read_vint(body, pos)
            high_diff, pos = read_vint(body, pos)
            low_diff, pos = read_vint(body, pos)
            (vol_raw,) = struct.unpack_from("<I", body, pos)
            pos += 4
            (amount_raw,) = struct.unpack_from("<I", body, pos)
            pos += 4
            abs_open = open_diff + base
            out.append(
                {
                    "datetime": f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}",
                    "open": abs_open / 1000.0,
                    "close": (abs_open + close_diff) / 1000.0,
                    "high": (abs_open + high_diff) / 1000.0,
                    "low": (abs_open + low_diff) / 1000.0,
                    "vol": decode_amount(vol_raw),
                    "amount": decode_amount(amount_raw),
                }
            )
            base = abs_open + close_diff
    except (struct.error, IndexError, OverflowError) as e:
        raise SchemaChanged(f"通达信 kline 响应不符合预期协议布局: {e}") from e
    if pos != len(body):
        raise SchemaChanged(f"通达信 kline 响应长度不符: pos {pos} != 实际 {len(body)}")
    return out


def decode_index_kline(body: bytes, category: int) -> list[dict[str, Any]]:
    """解码指数 K 线响应 -> ``list[dict]``。

    与 :func:`decode_kline` **同布局**,但每 bar 末尾**多 4 字节** ``<HH``
    (up_count 上涨家数 / down_count 下跌家数)—— 这是指数 bar 相对个股 bar 的唯一差异
    (故个股解码器读指数响应会 pos 不足而判 SchemaChanged)。
    """
    try:
        (count,) = struct.unpack_from("<H", body, 0)
        pos = 2
        out: list[dict[str, Any]] = []
        base = 0
        for _ in range(count):
            year, month, day, hour, minute, pos = _kline_datetime(category, body, pos)
            open_diff, pos = read_vint(body, pos)
            close_diff, pos = read_vint(body, pos)
            high_diff, pos = read_vint(body, pos)
            low_diff, pos = read_vint(body, pos)
            (vol_raw,) = struct.unpack_from("<I", body, pos)
            pos += 4
            (amount_raw,) = struct.unpack_from("<I", body, pos)
            pos += 4
            (up_count, down_count) = struct.unpack_from("<HH", body, pos)
            pos += 4
            abs_open = open_diff + base
            out.append(
                {
                    "datetime": f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}",
                    "open": abs_open / 1000.0,
                    "close": (abs_open + close_diff) / 1000.0,
                    "high": (abs_open + high_diff) / 1000.0,
                    "low": (abs_open + low_diff) / 1000.0,
                    "vol": decode_amount(vol_raw),
                    "amount": decode_amount(amount_raw),
                    "up_count": up_count,
                    "down_count": down_count,
                }
            )
            base = abs_open + close_diff
    except (struct.error, IndexError, OverflowError) as e:
        raise SchemaChanged(f"通达信 index_kline 响应不符合预期协议布局: {e}") from e
    if pos != len(body):
        raise SchemaChanged(f"通达信 index_kline 响应长度不符: pos {pos} != 实际 {len(body)}")
    return out


def decode_xdxr(body: bytes) -> list[dict[str, Any]]:
    """解码 get_xdxr_info 响应 -> 除权除息等事件 ``list[dict]``。

    skip 9 字节后 `<H` 为条数;每条 29 字节:market/code/保留(8,跳过)+ 日期(4,日级)+
    category(1)+ 16 字节类别数据。category=1 除权除息 = `<ffff`(分红/配股价/送转股/配股,每 10 股);
    category 11/12 缩股取 suogu;其余类别仅推进位置、复权相关字段置 None。category 为协议原始码
    (1 除权除息 / 11、12 缩股 …),不外泄派生的中文名(只留协议字段)。
    """
    try:
        (count,) = struct.unpack_from("<H", body, 9)   # 合法 0 事件也应是 11 字节(count=0)
        pos = 11
        out: list[dict[str, Any]] = []
        for _ in range(count):
            pos += 8   # market(B)+code(6s)+保留(1):恒为查询股票,跳过
            year, month, day, _, _, pos = _kline_datetime(9, body, pos)   # 日级日期
            (category,) = struct.unpack_from("<B", body, pos)
            pos += 1
            row: dict[str, Any] = {
                "date": f"{year:04d}-{month:02d}-{day:02d}",
                "category": category,
                "fenhong": None, "songzhuangu": None, "peigu": None,
                "peigujia": None, "suogu": None,
            }
            if category == 1:
                fenhong, peigujia, songzhuangu, peigu = struct.unpack_from("<ffff", body, pos)
                row.update(fenhong=fenhong, peigujia=peigujia, songzhuangu=songzhuangu, peigu=peigu)
            elif category in (11, 12):
                row["suogu"] = struct.unpack_from("<IIfI", body, pos)[2]
            pos += 16
            out.append(row)
    except (struct.error, IndexError) as e:
        raise SchemaChanged(f"通达信 xdxr 响应不符合预期协议布局: {e}") from e
    if pos != len(body):
        raise SchemaChanged(f"通达信 xdxr 响应长度不符: pos {pos} != 实际 {len(body)}")
    return out


def decode_ticks(body: bytes) -> list[dict[str, Any]]:
    """解码 get_transaction_data(当日逐笔)响应 -> ``list[dict]``。

    count(``<H`` 偏移 0)后每笔:time(``<H`` 分钟数 -> HH:MM)+ 价差(vint,累计)+ vol + num(笔数)
    + buyorsell(0 主动买 / 1 主动卖 / 2 中性)+ 1 个保留 vint。价 = 累计价 / 100。
    """
    try:
        (count,) = struct.unpack_from("<H", body, 0)
        pos = 2
        out: list[dict[str, Any]] = []
        last = 0
        for _ in range(count):
            (tmin,) = struct.unpack_from("<H", body, pos)
            pos += 2
            price_diff, pos = read_vint(body, pos)
            vol, pos = read_vint(body, pos)
            num, pos = read_vint(body, pos)
            buyorsell, pos = read_vint(body, pos)
            _reserved, pos = read_vint(body, pos)
            last += price_diff
            out.append(
                {
                    "time": f"{tmin // 60:02d}:{tmin % 60:02d}",
                    "price": last / 100.0,
                    "vol": vol,
                    "num": num,
                    "buyorsell": buyorsell,
                }
            )
    except (struct.error, IndexError) as e:
        raise SchemaChanged(f"通达信 ticks 响应不符合预期协议布局: {e}") from e
    if pos != len(body):
        raise SchemaChanged(f"通达信 ticks 响应长度不符: pos {pos} != 实际 {len(body)}")
    return out


def decode_ticks_hist(body: bytes) -> list[dict[str, Any]]:
    """解码 get_history_transaction_data(历史逐笔)响应 -> ``list[dict]``。

    与当日逐笔的体格式**不同**:count(``<H`` 偏移 0)后**跳 4 字节**,每笔只有 time(``<H``)+
    **4 个 vint**(价差累计 / vol / buyorsell / 1 个保留)——**无 num 字段**。价 = 累计价 / 100。
    """
    try:
        (count,) = struct.unpack_from("<H", body, 0)
        pos = 2 + 4   # count 后另有 4 字节保留,历史逐笔特有
        out: list[dict[str, Any]] = []
        last = 0
        for _ in range(count):
            (tmin,) = struct.unpack_from("<H", body, pos)
            pos += 2
            price_diff, pos = read_vint(body, pos)
            vol, pos = read_vint(body, pos)
            buyorsell, pos = read_vint(body, pos)
            _reserved, pos = read_vint(body, pos)
            last += price_diff
            out.append(
                {
                    "time": f"{tmin // 60:02d}:{tmin % 60:02d}",
                    "price": last / 100.0,
                    "vol": vol,
                    "buyorsell": buyorsell,
                }
            )
    except (struct.error, IndexError) as e:
        raise SchemaChanged(f"通达信 ticks_hist 响应不符合预期协议布局: {e}") from e
    if pos != len(body):
        raise SchemaChanged(f"通达信 ticks_hist 响应长度不符: pos {pos} != 实际 {len(body)}")
    return out


# 财务快照体:skip 2(num)+ <B6s(market/code)+ 31 个 float + 2 个 H + 2 个 I,共 136 字节定长
_FININFO_FMT = "<fHHIIffffffffffffffffffffffffffffff"


def _yyyymmdd(v: int) -> str | None:
    """通达信 YYYYMMDD 整数日期 -> "YYYY-MM-DD";0 / 非法 -> None。"""
    if not v or v < 19000000 or v > 21001231:
        return None
    return f"{v // 10000:04d}-{v % 10000 // 100:02d}-{v % 100:02d}"


def decode_finance_info(body: bytes) -> dict[str, Any]:
    """解码 get_finance_info(财务快照)响应 -> 可靠字段 dict。

    体首跳 2 字节(num)+ ``<B6s``(market/code)后,定长 :data:`_FININFO_FMT`。**只外泄经核验可靠的
    字段**:流通 / 总股本(万股 ×10000 还原为股)、股东人数、每股净资产、上市 / 财务更新日。
    通达信本接口的总资产 / 净资产 / 营收 / 利润等**金额字段口径混乱(常与公告差约 10 倍)**,
    刻意不外泄——季度报表请用 ``pb.dc.financials``。亦不外泄通达信内部省份 / 行业编码。
    """
    try:
        pos = 2                                       # 跳 num(本接口只查 1 只)
        _market, _code = struct.unpack_from("<B6s", body, pos)
        pos += 7
        vals = struct.unpack_from(_FININFO_FMT, body, pos)
        end = pos + struct.calcsize(_FININFO_FMT)
    except struct.error as e:
        raise SchemaChanged(f"通达信 finance_info 响应不符合预期协议布局: {e}") from e
    if end != len(body):
        raise SchemaChanged(f"通达信 finance_info 响应长度不符: 期望 {end} != 实际 {len(body)}")
    # 仅按位取出可靠字段;金额类(资产/营收/利润)口径不可靠,位置占位但不外泄
    float_shares = vals[0]
    updated_date, ipo_date, total_shares = vals[3], vals[4], vals[5]
    holders = vals[16]
    bvps = vals[33]                                   # 每股净资产(元/股),独立可靠字段
    return {
        "float_shares": float_shares * 10000.0,       # 流通股本(股)
        "total_shares": total_shares * 10000.0,        # 总股本(股)
        "holders": int(holders) if holders else 0,     # 股东人数
        "bvps": bvps,                                  # 每股净资产(元/股)
        "ipo_date": _yyyymmdd(ipo_date),               # 上市日期
        "report_date": _yyyymmdd(updated_date),        # 财务更新日期
    }
