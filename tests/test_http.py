"""HttpClient 稳健性:指数退避重试 / 429 退避 / 非 JSON 重试 / 浏览器请求头(全离线)。

不真实联网、不真实 sleep:用假 client 注入行为,patch _sleep_backoff 或 time.sleep。
"""

import httpx
import pytest

from probar.core import http as http_mod
from probar.core.errors import NetworkError, RateLimited


class FakeResp:
    def __init__(self, status_code=200, json_data=None, json_exc=None):
        self.status_code = status_code
        self._json_data = json_data
        self._json_exc = json_exc

    def raise_for_status(self):
        if self.status_code >= 400 and self.status_code != 429:
            req = httpx.Request("GET", "http://x")
            raise httpx.HTTPStatusError(
                "err", request=req, response=httpx.Response(self.status_code, request=req)
            )

    def json(self):
        if self._json_exc is not None:
            raise self._json_exc
        return self._json_data


class FakeClient:
    """按预设行为序列逐次返回/抛出;记录调用次数与最后一次请求头。"""

    def __init__(self, behaviors):
        self.behaviors = list(behaviors)
        self.calls = 0
        self.last_headers = None
        self.last_params = None

    def get(self, url, params=None, headers=None):
        self.calls += 1
        self.last_headers = headers
        self.last_params = params
        b = self.behaviors.pop(0)
        if isinstance(b, Exception):
            raise b
        return b


def _client(behaviors, **kw):
    hc = http_mod.HttpClient(rate=1000.0, **kw)
    hc._client = FakeClient(behaviors)
    return hc


def test_retries_transient_then_succeeds(monkeypatch):
    hc = _client([httpx.ConnectError("boom"), FakeResp(json_data={"ok": 1})])
    backoffs = []
    monkeypatch.setattr(hc, "_sleep_backoff", lambda *a, **k: backoffs.append((a, k)))
    assert hc.get_json("http://x") == {"ok": 1}
    assert hc._client.calls == 2
    assert len(backoffs) == 1  # 瞬断后退避一次再成功


def test_exhausts_retries_raises_network(monkeypatch):
    hc = _client([httpx.ConnectError("boom")] * 5, retries=5)
    monkeypatch.setattr(hc, "_sleep_backoff", lambda *a, **k: None)
    with pytest.raises(NetworkError):
        hc.get_json("http://x")
    assert hc._client.calls == 5  # 用满 retries 次


def test_http_500_retried(monkeypatch):
    hc = _client([FakeResp(status_code=500), FakeResp(json_data={"ok": 1})])
    monkeypatch.setattr(hc, "_sleep_backoff", lambda *a, **k: None)
    assert hc.get_json("http://x") == {"ok": 1}
    assert hc._client.calls == 2


def test_429_retries_with_longer_backoff(monkeypatch):
    hc = _client([FakeResp(status_code=429), FakeResp(json_data={"ok": 1})])
    seen = []
    monkeypatch.setattr(hc, "_sleep_backoff", lambda *a, **k: seen.append(k))
    assert hc.get_json("http://x") == {"ok": 1}
    assert seen and seen[0].get("factor") == 2.0  # 429 退避更久(factor=2)


def test_429_exhausts_raises_ratelimited(monkeypatch):
    hc = _client([FakeResp(status_code=429)] * 3, retries=3)
    monkeypatch.setattr(hc, "_sleep_backoff", lambda *a, **k: None)
    with pytest.raises(RateLimited):
        hc.get_json("http://x")
    assert hc._client.calls == 3


def test_non_json_retried_then_network(monkeypatch):
    hc = _client([FakeResp(json_exc=ValueError("not json"))] * 3, retries=3)
    monkeypatch.setattr(hc, "_sleep_backoff", lambda *a, **k: None)
    with pytest.raises(NetworkError):  # 被 WAF 返回 HTML 等 -> 重试后归类网络错
        hc.get_json("http://x")
    assert hc._client.calls == 3


def test_referer_passed_as_header():
    hc = _client([FakeResp(json_data={"ok": 1})])
    hc.get_json("http://x", referer="http://ref")
    assert hc._client.last_headers == {"Referer": "http://ref"}


def test_browser_headers_present():
    hc = http_mod.HttpClient(rate=1000.0)
    try:
        h = hc._client.headers
        assert "zh-CN" in h["Accept-Language"]
        assert h["Sec-Fetch-Mode"] == "cors"
        assert "Chrome" in h["User-Agent"]
    finally:
        hc.close()


def test_sleep_backoff_exponential_capped(monkeypatch):
    hc = http_mod.HttpClient(rate=1000.0, backoff=0.5, backoff_cap=8.0)
    slept = []
    monkeypatch.setattr(http_mod.time, "sleep", lambda d: slept.append(d))
    monkeypatch.setattr(http_mod.random, "uniform", lambda a, b: 0.0)  # 关抖动看本体
    try:
        for attempt in range(6):
            hc._sleep_backoff(attempt)
        assert slept == [0.5, 1.0, 2.0, 4.0, 8.0, 8.0]  # 翻倍到上界封顶
    finally:
        hc.close()


def test_sleep_backoff_adds_jitter(monkeypatch):
    hc = http_mod.HttpClient(rate=1000.0, backoff=1.0)
    slept = []
    monkeypatch.setattr(http_mod.time, "sleep", lambda d: slept.append(d))
    monkeypatch.setattr(http_mod.random, "uniform", lambda a, b: b)  # 抖动取上界
    try:
        hc._sleep_backoff(0)  # delay=1.0,+50% -> 1.5
        assert slept == [1.5]
    finally:
        hc.close()


# ---- 按 host 熔断:连续断连后快速失败,不再捶打(避免延长反爬封禁)----


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


def test_breaker_opens_after_threshold_then_fast_fails(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(http_mod.time, "monotonic", clock)
    hc = _client([], retries=5, breaker_threshold=2, breaker_cooldown=60.0)
    monkeypatch.setattr(hc, "_sleep_backoff", lambda *a, **k: None)

    hc._client.behaviors = [httpx.ConnectError("x")] * 5
    with pytest.raises(NetworkError):
        hc.get_json("http://push2.x/api")  # 调用1:整通断连 -> fails=1,未开闸
    assert hc._client.calls == 5

    hc._client.behaviors = [httpx.ConnectError("x")] * 5
    with pytest.raises(NetworkError):
        hc.get_json("http://push2.x/api")  # 调用2:fails=2 -> 开闸
    assert hc._client.calls == 10

    hc._client.behaviors = [httpx.ConnectError("x")] * 5
    with pytest.raises(NetworkError) as ei:
        hc.get_json("http://push2.x/api")  # 调用3:已熔断 -> 快速失败,不发请求
    assert hc._client.calls == 10
    assert "熔断" in str(ei.value)

    clock.advance(61)  # 冷却过 -> 自动闭合,再试真请求
    hc._client.behaviors = [FakeResp(json_data={"ok": 1})]
    assert hc.get_json("http://push2.x/api") == {"ok": 1}
    assert hc._client.calls == 11


def test_breaker_resets_on_success(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(http_mod.time, "monotonic", clock)
    hc = _client([], retries=3, breaker_threshold=2)
    monkeypatch.setattr(hc, "_sleep_backoff", lambda *a, **k: None)

    hc._client.behaviors = [httpx.ConnectError("x")] * 3
    with pytest.raises(NetworkError):
        hc.get_json("http://h/a")
    assert hc._fails.get("h") == 1

    hc._client.behaviors = [FakeResp(json_data={"ok": 1})]
    hc.get_json("http://h/a")  # 成功 -> 计数复位
    assert hc._fails.get("h") == 0

    hc._client.behaviors = [httpx.ConnectError("x")] * 3
    with pytest.raises(NetworkError):
        hc.get_json("http://h/a")  # 复位后单次失败不应开闸
    assert hc._breaker_remaining("h") == 0


def test_breaker_ignores_non_transport_errors(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(http_mod.time, "monotonic", clock)
    hc = _client([], retries=2, breaker_threshold=2)
    monkeypatch.setattr(hc, "_sleep_backoff", lambda *a, **k: None)
    for _ in range(4):  # 多次 500 也不熔断(不是断连信号)
        hc._client.behaviors = [FakeResp(status_code=500)] * 2
        with pytest.raises(NetworkError):
            hc.get_json("http://h/a")
    assert hc._breaker_remaining("h") == 0
    assert hc._fails.get("h", 0) == 0


def test_breaker_counts_429(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(http_mod.time, "monotonic", clock)
    hc = _client([], retries=2, breaker_threshold=2, breaker_cooldown=30.0)
    monkeypatch.setattr(hc, "_sleep_backoff", lambda *a, **k: None)

    hc._client.behaviors = [FakeResp(status_code=429)] * 2
    with pytest.raises(RateLimited):
        hc.get_json("http://h/a")  # fails=1
    hc._client.behaviors = [FakeResp(status_code=429)] * 2
    with pytest.raises(RateLimited):
        hc.get_json("http://h/a")  # fails=2 -> 开闸
    hc._client.behaviors = [FakeResp(status_code=429)] * 2
    with pytest.raises(NetworkError):  # 已熔断 -> 转 NetworkError 快速失败
        hc.get_json("http://h/a")
    assert hc._client.calls == 4  # 第三次没发请求
