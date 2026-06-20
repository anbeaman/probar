"""测试夹具:单元测试默认禁网。

任何**未标记** ``@pytest.mark.network`` 的测试若尝试建立**非本地**网络连接,会立即报错——
确保单测只跑冻结 fixture、不依赖真实数据源(纯函数 parser、TestClient 等走回环,不受影响)。
需要联网的测试必须显式标 ``network``,且默认被 ``-m "not network"`` 排除(见 pyproject)。
"""

import os
import socket

import pytest

_REAL_CONNECT = socket.socket.connect
_PROXY_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")


@pytest.fixture(autouse=True)
def _forbid_network(request):
    if request.node.get_closest_marker("network"):
        yield
        return

    def _blocked(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, (tuple, list)) else address
        # 放行本地回环(TestClient / Windows socketpair 内部用 127.0.0.1)
        if host in ("127.0.0.1", "::1", "localhost"):
            return _REAL_CONNECT(self, address, *args, **kwargs)
        raise RuntimeError(
            "单元测试禁止联网(非本地连接);如确需联网请标记 @pytest.mark.network(默认被排除)"
        )

    # 同时清掉代理变量:否则 httpx 会"先连本地代理(回环)再外联",绕过上面的拦截
    saved = {k: os.environ.pop(k, None) for k in _PROXY_VARS}
    socket.socket.connect = _blocked
    try:
        yield
    finally:
        socket.socket.connect = _REAL_CONNECT
        for key, val in saved.items():
            if val is not None:
                os.environ[key] = val
