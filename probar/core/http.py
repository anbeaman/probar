"""基于 httpx 的同步 HTTP 传输层:统一超时、限流、退避重试、浏览器级请求头、按 host 熔断。

只负责"把请求安全地发出去、把 JSON 拿回来",不关心字段语义(解析交给各 provider)。

抗反爬/抗抖动取舍(均为**稳健 + 友好访问**,非滥用):
  - 浏览器级请求头(UA + Accept-Language + Sec-Fetch),降低被 WAF 当爬虫拦的概率;
  - **指数退避 + 随机抖动**重试,riding out 东财常见的瞬时断连(RemoteProtocolError)与限频;
  - 429 先退避重试(更久),穷尽才抛 RateLimited;
  - **按 host 熔断**:某 host 连续整通断连(东财 push2 突发后 IP 级封禁的特征)后,短时熔断,
    后续调用**快速失败**而非继续捶打(继续打只会延长封禁、空耗重试);
  - 保留 TokenBucket 限流且**默认放缓到 5/s**(预防突发封禁优于事后退避)。
    **不轮换 UA**(同 IP 换 UA 反而像 bot);**不轮换备用 host**(push2 编号镜像同 IP 同封,
    push2delay 延迟镜像不尊重 fs 过滤会返回错配数据——实测否决)。
"""

from __future__ import annotations

import random
import time
from typing import Any

import httpx

from .errors import NetworkError, RateLimited
from .rate_limit import TokenBucket

# 单一、稳定、真实的浏览器请求头(同 IP 保持一致比乱换更不易被判爬虫)
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
    # 现代 Chrome 对 XHR 都带 Sec-Fetch;东财 push2/datacenter 由其自身页面跨站调用 -> same-site
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
}


class HttpClient:
    def __init__(
        self,
        *,
        timeout: float = 8.0,
        rate: float = 5.0,
        proxy: str | None = None,
        headers: dict[str, str] | None = None,
        retries: int = 5,
        backoff: float = 0.5,
        backoff_cap: float = 8.0,
        breaker_threshold: int = 2,
        breaker_cooldown: float = 60.0,
    ) -> None:
        self._bucket = TokenBucket(rate)
        self._retries = max(1, retries)
        self._backoff = max(0.0, backoff)
        self._backoff_cap = max(self._backoff, backoff_cap)
        self._breaker_threshold = max(1, breaker_threshold)
        self._breaker_cooldown = max(0.0, breaker_cooldown)
        self._fails: dict[str, int] = {}  # host -> 连续"整通断连失败"的调用数
        self._open_until: dict[str, float] = {}  # host -> 熔断恢复的 monotonic 时刻
        client_kwargs: dict[str, Any] = {
            "timeout": timeout,
            "headers": {**DEFAULT_HEADERS, **(headers or {})},
            "follow_redirects": True,
        }
        if proxy:  # 仅在显式传入时才加,避免老版 httpx 不识别 proxy/proxies 之别
            client_kwargs["proxy"] = proxy
        self._client = httpx.Client(**client_kwargs)

    def _sleep_backoff(self, attempt: int, *, factor: float = 1.0) -> None:
        """指数退避 + 0~50% 随机抖动(打散规律,降低被限频/识别概率)。"""
        delay = min(self._backoff_cap, self._backoff * (2**attempt) * factor)
        if delay > 0:
            time.sleep(delay + random.uniform(0.0, delay * 0.5))

    def _breaker_remaining(self, host: str) -> float:
        """该 host 熔断剩余秒数(0 = 未熔断)。"""
        return max(0.0, self._open_until.get(host, 0.0) - time.monotonic())

    def _trip_breaker(self, host: str) -> None:
        """记一次该 host 的断连/限频失败;连续达阈值则开闸熔断一个冷却窗口。"""
        self._fails[host] = self._fails.get(host, 0) + 1
        if self._fails[host] >= self._breaker_threshold:
            self._open_until[host] = time.monotonic() + self._breaker_cooldown

    def _reset_breaker(self, host: str) -> None:
        """成功一次即复位该 host 的失败计数与熔断。"""
        if self._fails.get(host):
            self._fails[host] = 0
        self._open_until.pop(host, None)

    def get_json(
        self, url: str, params: dict[str, Any] | None = None, *, referer: str | None = None
    ) -> Any:
        """限流 + 指数退避重试地发起 GET 并解析 JSON。穷尽重试后抛 :class:`NetworkError`。

        429 先退避重试(更久),最后一次才抛 :class:`RateLimited`;瞬时断连/被 WAF 返回非 JSON
        等(TransportError / HTTPStatusError / ValueError)按指数退避重试。某 host 连续整通断连达
        阈值后**熔断**:冷却窗口内对该 host 的调用直接快速失败,不再捶打(避免延长封禁)。
        """
        host = httpx.URL(url).host
        remaining = self._breaker_remaining(host)
        if remaining > 0:
            raise NetworkError(
                f"{host} 暂时熔断(疑似限流/反爬,连续断连);约 {remaining:.0f}s 后再试"
            )
        headers = {"Referer": referer} if referer else None
        last_err: Exception | None = None
        transport_fail = False  # 末次失败是否为传输层断连(熔断只认这种硬信号)
        for attempt in range(self._retries):
            self._bucket.acquire()
            last = attempt == self._retries - 1
            try:
                resp = self._client.get(url, params=params, headers=headers)
                if resp.status_code == 429:
                    if last:
                        self._trip_breaker(host)  # 429 也是限流信号,计入熔断
                        raise RateLimited(f"429 Too Many Requests: {url}")
                    self._sleep_backoff(attempt, factor=2.0)  # 限频:退避更久再试
                    continue
                resp.raise_for_status()
                # 非 JSON(被 WAF 拦截返回 HTML 等)时 .json() 抛 ValueError,纳入重试与分类
                data = resp.json()
                self._reset_breaker(host)  # 成功 -> 复位熔断
                return data
            except RateLimited:
                raise
            except httpx.TransportError as err:  # 断连/超时:反爬硬信号
                last_err, transport_fail = err, True
                if not last:
                    self._sleep_backoff(attempt)
            except (httpx.HTTPStatusError, ValueError) as err:  # 4xx/5xx、非 JSON:非熔断信号
                last_err, transport_fail = err, False
                if not last:
                    self._sleep_backoff(attempt)
        if transport_fail:  # 整通调用都断在传输层 -> 计一次熔断
            self._trip_breaker(host)
        raise NetworkError(f"GET {url} 失败(已重试 {self._retries} 次): {last_err!r}")

    def close(self) -> None:
        self._client.close()
