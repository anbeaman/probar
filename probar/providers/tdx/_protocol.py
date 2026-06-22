"""通达信标准行情 TCP 协议客户端(clean-room,纯标准库 socket/struct/zlib)。

流程:连接 -> 三步握手 -> 发请求 -> 收帧(按声明长度收满、必要时 zlib 解压)-> 交 ``_codec`` 解码。
协议字节布局见同目录 ``PROTOCOL.md``(独立实现,未照搬任何参考实现的代码)。一条连接一来一回,
**非线程安全**,由上层(:class:`.transport.TdxTransport`)串行化并在失败时换服务器。
"""

from __future__ import annotations

import socket
import struct
import zlib
from typing import Any

from . import _codec

# 连接后必须先发的三步握手包(TDX 标准行情固定 wire bytes,属协议事实;握手响应丢弃)
_HANDSHAKE = (
    bytes.fromhex("0c0218930001030003000d0001"),
    bytes.fromhex("0c0218940001030003000d0002"),
    bytes.fromhex(
        "0c031899000120002000db0fd5d0c9ccd6a4a8af0000008fc2254013"
        "0000d500c9ccbdf0d7ea00000002"
    ),
)
_RSP_HEADER = 16
_QUOTES_CMD = 0x5053E


class TdxProtocolError(Exception):
    """协议层错误(帧异常/长度不符/解压失败);上层转成 NetworkError 并换服务器。"""


class TdxClient:
    """一条到某台行情服务器的连接(connect / get_security_quotes / disconnect)。"""

    def __init__(self, *, timeout: float = 5.0) -> None:
        self._timeout = timeout
        self._sock: socket.socket | None = None

    def connect(self, host: str, port: int) -> bool:
        """建立 TCP 连接并完成握手;成功 True,连接/握手失败 False(已清理 socket)。"""
        self.disconnect()  # 幂等:重复 connect 先关旧连接,避免 socket 泄漏
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self._timeout)
        try:
            sock.connect((host, port))
        except OSError:
            self._close_sock(sock)
            return False
        self._sock = sock
        try:
            for pkg in _HANDSHAKE:
                self._call(pkg)  # 握手响应丢弃
        except (OSError, TdxProtocolError):
            self.disconnect()
            return False
        return True

    def get_security_quotes(self, market_code: list[tuple[int, str]]) -> list[dict[str, Any]]:
        """拉批量实时五档,返回 ``list[dict]``(字段对接 :func:`.parsers.parse_quotes`)。"""
        body = self._call(_build_quotes_request(market_code))
        return _codec.decode_quotes(body)

    def get_security_count(self, market: int) -> int:
        """拉某市场证券数量(market: 0=深 1=沪 2=北)。"""
        body = self._call(_build_count_request(market))
        return _codec.decode_security_count(body)

    def get_security_list(self, market: int, start: int) -> list[dict[str, Any]]:
        """拉某市场证券列表一页(每页最多 1000 条),返回 ``list[dict]``。"""
        body = self._call(_build_list_request(market, start))
        return _codec.decode_security_list(body, market)

    def get_security_bars(
        self, category: int, market: int, code: str, start: int, count: int
    ) -> list[dict[str, Any]]:
        """拉一页 K 线 bar(category=周期;start=距最新的偏移,count<=800),返回 ``list[dict]``。"""
        body = self._call(_build_bars_request(category, market, code, start, count))
        return _codec.decode_kline(body, category)

    def get_index_bars(
        self, category: int, market: int, code: str, start: int, count: int
    ) -> list[dict[str, Any]]:
        """拉一页指数 K 线(请求同个股,响应每 bar 多 up/down 家数),返回 ``list[dict]``。"""
        body = self._call(_build_bars_request(category, market, code, start, count))
        return _codec.decode_index_kline(body, category)

    def get_xdxr_info(self, market: int, code: str) -> list[dict[str, Any]]:
        """拉除权除息信息(全历史事件),返回 ``list[dict]``。"""
        body = self._call(_build_xdxr_request(market, code))
        return _codec.decode_xdxr(body)

    def get_transaction_data(
        self, market: int, code: str, start: int, count: int
    ) -> list[dict[str, Any]]:
        """拉一页当日逐笔成交(start=距最新偏移,count<=约 2000),返回 ``list[dict]``。"""
        body = self._call(_build_ticks_request(market, code, start, count))
        return _codec.decode_ticks(body)

    def get_history_transaction_data(
        self, market: int, code: str, date: int, start: int, count: int
    ) -> list[dict[str, Any]]:
        """拉一页历史逐笔成交(date=YYYYMMDD 整数;start=距当日最新偏移,count<=约 2000)。"""
        body = self._call(_build_ticks_hist_request(market, code, date, start, count))
        return _codec.decode_ticks_hist(body)

    def get_finance_info(self, market: int, code: str) -> dict[str, Any]:
        """拉财务快照(股本结构 + 基本面;单只),返回 ``dict``。"""
        body = self._call(_build_finance_info_request(market, code))
        return _codec.decode_finance_info(body)

    def get_block(self, blockfile: str) -> list[dict[str, Any]]:
        """拉板块文件(meta 取大小 + 分块拉满 + 解析)-> ``[{block, code}]``。

        板块走**文件协议**:先 ``GetBlockInfoMeta`` 取文件字节大小,再按 0x7530 分块 ``GetBlockInfo``
        拉满、截到真实大小,交 :func:`_codec.decode_block` 解析。一条连接串行多次往返。
        """
        meta = self._call(_build_block_meta_request(blockfile))
        if len(meta) < 4:
            raise TdxProtocolError(f"板块 meta 响应过短: {len(meta)} 字节")
        (size,) = struct.unpack_from("<I", meta, 0)
        if size <= 0 or size > 50_000_000:           # 防异常/超大(板块文件实测 <1MB)
            raise TdxProtocolError(f"板块文件大小异常: {size}")
        content = bytearray()
        while len(content) < size:
            piece = self._call(_build_block_request(blockfile, len(content), size))[4:]
            if not piece:                            # 短读:别静默返回半个文件(交上层换服务器)
                raise TdxProtocolError(f"板块文件短读: 收到 {len(content)}/{size} 字节")
            content.extend(piece)
        return _codec.decode_block(bytes(content[:size]))

    # ---- 帧收发 ----
    def _call(self, pkg: bytes) -> bytes:
        sock = self._sock
        if sock is None:
            raise TdxProtocolError("未连接")
        sock.sendall(pkg)
        header = self._recv_exact(_RSP_HEADER)
        # 16 字节响应头:前 12 字节(3×uint32)此处不需要,末两 uint16 = 压缩/原始长度
        _, _, _, zip_size, unzip_size = struct.unpack("<IIIHH", header)
        if zip_size == 0 or unzip_size == 0:  # uint16(协议上限 65535);0 视为异常帧
            raise TdxProtocolError(f"响应体长度异常: zip={zip_size} unzip={unzip_size}")
        body = self._recv_exact(zip_size)
        if zip_size != unzip_size:  # 压缩了:有界解压 + 校验长度,防坏数据 / zip bomb
            try:
                dec = zlib.decompressobj()
                body = dec.decompress(body, unzip_size)
                if dec.unconsumed_tail or len(body) != unzip_size:
                    raise TdxProtocolError(f"解压结果异常: 得到 {len(body)} 期望 {unzip_size}")
            except zlib.error as e:
                raise TdxProtocolError(f"zlib 解压失败: {e}") from e
        return body

    def _recv_exact(self, n: int) -> bytes:
        sock = self._sock
        if sock is None:
            raise TdxProtocolError("未连接")
        chunks = bytearray()
        while len(chunks) < n:
            buf = sock.recv(n - len(chunks))
            if not buf:
                raise TdxProtocolError("连接被对端关闭(收到 0 字节)")
            chunks.extend(buf)
        return bytes(chunks)

    def disconnect(self) -> None:
        if self._sock is not None:
            self._close_sock(self._sock)
            self._sock = None

    @staticmethod
    def _close_sock(sock: socket.socket) -> None:
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            sock.close()
        except OSError:
            pass


def _build_quotes_request(market_code: list[tuple[int, str]]) -> bytes:
    """组 get_security_quotes 请求包:22 字节头 + 每只 7 字节(market + 6 位 code)。"""
    n = len(market_code)
    body_len = n * 7 + 12
    header = struct.pack(
        "<HIHHIIHH", 0x10C, 0x02006320, body_len, body_len, _QUOTES_CMD, 0, 0, n
    )
    pkg = bytearray(header)
    for market, code in market_code:
        raw_code = code.encode("ascii") if isinstance(code, str) else bytes(code)
        if market not in (0, 1, 2) or len(raw_code) != 6:
            raise ValueError(f"非法 (market, code): ({market!r}, {code!r})")
        pkg += struct.pack("<B6s", market, raw_code)
    return bytes(pkg)


def _build_count_request(market: int) -> bytes:
    """组 get_security_count 请求:固定前缀 + market(<H) + 固定尾(均为协议事实)。"""
    return (
        bytes.fromhex("0c0c186c0001080008004e04")
        + struct.pack("<H", market)
        + bytes.fromhex("75c73301")
    )


def _build_list_request(market: int, start: int) -> bytes:
    """组 get_security_list 请求:固定前缀 + market(<H) + start(<H)。"""
    return bytes.fromhex("0c0118640101060006005004") + struct.pack("<HH", market, start)


def _build_bars_request(category: int, market: int, code: str, start: int, count: int) -> bytes:
    """组 get_security_bars 请求(命令 0x052d):固定头 + market/code/category/start/count。"""
    raw_code = code.encode("ascii") if isinstance(code, str) else bytes(code)
    if market not in (0, 1, 2) or len(raw_code) != 6:
        raise ValueError(f"非法 (market, code): ({market!r}, {code!r})")
    return struct.pack(
        "<HIHHHH6sHHHHIIH",
        0x10C, 0x01016408, 0x1C, 0x1C, 0x052D,
        market, raw_code, category, 1, start, count, 0, 0, 0,
    )


def _build_xdxr_request(market: int, code: str) -> bytes:
    """组 get_xdxr_info 请求:固定前缀 + `<B6s (market, code)`。"""
    raw_code = code.encode("ascii") if isinstance(code, str) else bytes(code)
    if market not in (0, 1, 2) or len(raw_code) != 6:
        raise ValueError(f"非法 (market, code): ({market!r}, {code!r})")
    return bytes.fromhex("0c1f187600010b000b000f000100") + struct.pack("<B6s", market, raw_code)


def _build_ticks_request(market: int, code: str, start: int, count: int) -> bytes:
    """组 get_transaction_data 请求(0x0fc5):前缀 + `<H6sHH`(market/code/start/count)。"""
    raw_code = code.encode("ascii") if isinstance(code, str) else bytes(code)
    if market not in (0, 1, 2) or len(raw_code) != 6:
        raise ValueError(f"非法 (market, code): ({market!r}, {code!r})")
    return bytes.fromhex("0c1708010101 0e000e00c50f".replace(" ", "")) + struct.pack(
        "<H6sHH", market, raw_code, start, count
    )


def _build_ticks_hist_request(
    market: int, code: str, date: int, start: int, count: int
) -> bytes:
    """组历史逐笔请求(0x0fb5):前缀 + `<IH6sHH`(date/market/code/start/count)。"""
    raw_code = code.encode("ascii") if isinstance(code, str) else bytes(code)
    if market not in (0, 1, 2) or len(raw_code) != 6:
        raise ValueError(f"非法 (market, code): ({market!r}, {code!r})")
    return bytes.fromhex("0c013001000112001200b50f") + struct.pack(
        "<IH6sHH", date, market, raw_code, start, count
    )


def _build_finance_info_request(market: int, code: str) -> bytes:
    """组 get_finance_info 请求(命令 0x0010):固定前缀 + `<B6s`(market, code)。"""
    raw_code = code.encode("ascii") if isinstance(code, str) else bytes(code)
    if market not in (0, 1, 2) or len(raw_code) != 6:
        raise ValueError(f"非法 (market, code): ({market!r}, {code!r})")
    return bytes.fromhex("0c1f187600010b000b0010000100") + struct.pack(
        "<B6s", market, raw_code
    )


def _build_block_meta_request(blockfile: str) -> bytes:
    """组 GetBlockInfoMeta 请求(命令 0x02c5):固定前缀 + 40 字节文件名(尾部补零)。"""
    name = blockfile.encode("ascii") if isinstance(blockfile, str) else bytes(blockfile)
    return bytes.fromhex("0c39186900012a002a00c502") + struct.pack("<40s", name)


def _build_block_request(blockfile: str, start: int, size: int) -> bytes:
    """组 GetBlockInfo 请求(命令 0x06b9):固定前缀 + `<II`(start, size)+ 100 字节文件名。"""
    name = blockfile.encode("ascii") if isinstance(blockfile, str) else bytes(blockfile)
    return bytes.fromhex("0c37186a00016e006e00b906") + struct.pack("<II100s", start, size, name)
