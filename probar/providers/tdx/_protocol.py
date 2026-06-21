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
