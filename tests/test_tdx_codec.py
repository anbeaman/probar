"""通达信 clean-room 协议的离线测试:解码器(_codec)+ 收发帧(_protocol),全程不联网。

``tdx_quotes_raw.json`` 是用自写客户端抓回的**真实响应体原始字节** + 解码结果;该结果在开发期
已与一个独立参考实现对同一段字节比对一致(oracle 验证,边界见 ``probar/providers/tdx/PROTOCOL.md``),
此处做确定性离线回归。
"""

import json
import struct
import zlib
from pathlib import Path

import pytest

from probar.core.errors import SchemaChanged
from probar.providers.tdx import _codec
from probar.providers.tdx._protocol import TdxClient, TdxProtocolError, _build_quotes_request

FIXTURES = Path(__file__).parent / "fixtures"


# ---- 解码器 _codec ----
def test_decode_quotes_matches_frozen_oracle():
    fx = json.loads((FIXTURES / "tdx_quotes_raw.json").read_text(encoding="utf-8"))
    decoded = _codec.decode_quotes(bytes.fromhex(fx["raw_hex"]))
    assert decoded == fx["decoded"]  # 与 oracle 验证过的冻结结果逐字段一致


def test_read_vint_positive_negative_multibyte():
    assert _codec.read_vint(b"\x05", 0) == (5, 1)        # 低 6 位
    assert _codec.read_vint(b"\x00", 0) == (0, 1)
    assert _codec.read_vint(b"\x45", 0) == (-5, 1)       # bit6 符号位
    # 多字节:100 = 0b1100100 -> byte0=0xA4(续位+低6位36), byte1=0x01(<<6=64)
    assert _codec.read_vint(b"\xa4\x01", 0) == (100, 2)
    # 从中间位置开始读,返回的新 pos 应正确推进
    assert _codec.read_vint(b"\xff\x05", 1) == (5, 2)


def test_decode_amount_zero_is_negligible():
    assert _codec.decode_amount(0) < 1.0  # 停牌/无额时 raw=0 -> 约 0


def test_decode_quotes_truncated_raises_schema_changed():
    # 声明 1 只但记录不完整 -> 归一为 SchemaChanged(便于上层如实上报,而非裸 struct.error)
    body = b"\x00\x00" + struct.pack("<H", 1) + b"\x00" + b"000001"
    with pytest.raises(SchemaChanged):
        _codec.decode_quotes(body)


def test_decode_quotes_trailing_garbage_raises():
    # 真实字节尾部多 1 字节 -> 消费长度不符 -> SchemaChanged(也反证真实响应被精确消费完)
    fx = json.loads((FIXTURES / "tdx_quotes_raw.json").read_text(encoding="utf-8"))
    with pytest.raises(SchemaChanged):
        _codec.decode_quotes(bytes.fromhex(fx["raw_hex"]) + b"\x00")


def test_read_vint_continuation_eof_raises():
    with pytest.raises(IndexError):
        _codec.read_vint(b"\x80", 0)  # 续位置位但无后续字节


# ---- 收发帧 _protocol ----
class _ChunkedSock:
    """假 socket:把响应字节按小片喂出,专门考验 recv_exact 收满逻辑。"""

    def __init__(self, data: bytes, chunk: int = 3):
        self._buf = bytes(data)
        self._pos = 0
        self._chunk = chunk
        self.sent = bytearray()

    def sendall(self, data):
        self.sent += data

    def recv(self, n):
        if self._pos >= len(self._buf):
            return b""
        end = min(self._pos + min(n, self._chunk), len(self._buf))
        out = self._buf[self._pos:end]
        self._pos = end
        return out

    def shutdown(self, how):
        pass

    def close(self):
        pass


def _frame(payload: bytes, *, compress: bool) -> bytes:
    body = zlib.compress(payload) if compress else payload
    unzip = len(payload)
    return struct.pack("<IIIHH", 0, 0, 0, len(body), unzip) + body


def test_call_uncompressed_recv_exact_loops():
    c = TdxClient()
    payload = bytes(range(20))
    c._sock = _ChunkedSock(_frame(payload, compress=False), chunk=3)  # 分片喂
    assert c._call(b"REQ") == payload
    assert bytes(c._sock.sent) == b"REQ"


def test_call_compressed_decompresses():
    c = TdxClient()
    payload = b"the quick brown fox " * 4
    c._sock = _ChunkedSock(_frame(payload, compress=True), chunk=5)
    assert c._call(b"x") == payload


def test_call_eof_mid_header_raises():
    c = TdxClient()
    c._sock = _ChunkedSock(b"\x00\x00\x00", chunk=1)  # 头都收不满 16 字节
    with pytest.raises(TdxProtocolError):
        c._call(b"x")


def test_call_zero_length_body_raises():
    c = TdxClient()
    c._sock = _ChunkedSock(struct.pack("<IIIHH", 0, 0, 0, 0, 0), chunk=8)  # zip_size=0 非法
    with pytest.raises(TdxProtocolError):
        c._call(b"x")


def test_call_bad_zlib_raises_protocol_error():
    c = TdxClient()
    bad = b"not zlib data!!"
    frame = struct.pack("<IIIHH", 0, 0, 0, len(bad), len(bad) + 10) + bad  # zip!=unzip 触发解压
    c._sock = _ChunkedSock(frame, chunk=7)
    with pytest.raises(TdxProtocolError):
        c._call(b"x")


def test_call_decompress_length_mismatch_raises():
    payload = b"hello"
    comp = zlib.compress(payload)
    frame = struct.pack("<IIIHH", 0, 0, 0, len(comp), len(payload) + 5) + comp  # unzip 声明偏大
    c = TdxClient()
    c._sock = _ChunkedSock(frame, chunk=4)
    with pytest.raises(TdxProtocolError):
        c._call(b"x")


def test_build_quotes_request_shape():
    pkg = _build_quotes_request([(0, "000001"), (1, "600519")])
    # 22 字节头 + 每只 7 字节
    assert len(pkg) == 22 + 2 * 7
    n = struct.unpack_from("<H", pkg, 20)[0]  # 头末尾的 stock_len
    assert n == 2
    assert pkg[22] == 0 and pkg[23:29] == b"000001"  # 第一只:market + 6 位 code
