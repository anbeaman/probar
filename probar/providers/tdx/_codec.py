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
