"""pb.auto —— 可选的跨源故障转移(默认不参与任何调用)。

按 ``prefer`` 顺序依次尝试,成功即返回,并在 ``df.attrs`` 标注真实来源与降级原因。
**绝不静默**:用户始终能从 attrs 看出数据来自哪个源、为什么降级 —— 这是为了避免
不同源的口径差异(复权/时间戳/字段)造成不可解释的回测结果。
"""

from __future__ import annotations

from typing import Any

from .core.errors import NetworkError, NotSupported, ProbarError, RateLimited

# 仅在"该源暂时不可用/不支持该接口"时才降级到下一个源。
# SchemaChanged / NoData 故意**不**降级:接口变更或确无数据是确定性结果,
# 用别的源的数据掩盖只会制造不可解释的差异(与"绝不静默"原则一致)。
_FALLBACKABLE = (NotImplementedError, NetworkError, RateLimited, NotSupported)


class Auto:
    def __init__(self, *, dc: Any, tdx: Any) -> None:
        self._providers = {"dc": dc, "tdx": tdx}

    def _run(self, interface: str, prefer: list[str], *args: Any, **kwargs: Any) -> Any:
        errors: dict[str, str] = {}
        for name in prefer:
            provider = self._providers.get(name)
            if provider is None:
                errors[name] = "未知数据源"
                continue
            method = getattr(provider, interface, None)
            if method is None:
                errors[name] = "该源不提供此接口"
                continue
            try:
                result = method(*args, **kwargs)
            except _FALLBACKABLE as err:
                errors[name] = repr(err)
                continue
            if hasattr(result, "attrs"):
                result.attrs["source"] = name
                if errors:
                    result.attrs["fallback_reason"] = errors
            return result
        raise ProbarError(f"auto.{interface} 所有源均失败: {errors}")

    def kline(self, symbol: str, *, prefer: list[str] | None = None, **kwargs: Any) -> Any:
        return self._run("kline", prefer or ["dc", "tdx"], symbol, **kwargs)

    def quote(self, symbol: str, *, prefer: list[str] | None = None, **kwargs: Any) -> Any:
        return self._run("quote", prefer or ["dc", "tdx"], symbol, **kwargs)
