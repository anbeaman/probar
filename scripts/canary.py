"""每日金丝雀巡检(v0.1 最小实现)。

打几个真实接口,校验 schema + 数值合理性,并把失败**分类**:
    network   网络/超时(GitHub runner 在境外,打国内接口常见,属噪声)
    ratelimit 被限频
    schema    上游字段变更(真正需要修代码的信号)
    data      返回了但数值不合理
    ok        正常

退出码:全部 ok -> 0;仅 network/ratelimit -> 0(soft,不算真失败);出现 schema/data -> 1。

注意(与方案一致):GitHub runner IP 在境外,实网 canary 会有误报;v0.2 起主巡检迁到
国内节点(云函数/VPS),GitHub Actions 仅作轻量 smoke。
"""

from __future__ import annotations

import sys

import probar as pb
from probar.core.errors import NetworkError, RateLimited, SchemaChanged
from probar.core.models import SECURITIES_COLUMNS

PROBES = ["600519.SH", "000001.SZ"]


def _classify_exc(e: Exception) -> tuple[str, str]:
    if isinstance(e, SchemaChanged):
        return "schema", str(e)
    if isinstance(e, RateLimited):
        return "ratelimit", str(e)
    if isinstance(e, NetworkError):
        return "network", str(e)
    return "data", f"{type(e).__name__}: {e}"


def classify_kline(symbol: str) -> tuple[str, str]:
    try:
        df = pb.dc.kline(symbol, freq="1d", adjust="qfq", limit=5)
    except Exception as e:  # noqa: BLE001
        return _classify_exc(e)
    if df.empty or (df["close"] <= 0).any():
        return "data", f"{symbol} 收盘价异常: {df['close'].tolist()}"
    return "ok", f"{symbol} {len(df)} 行,最新收盘 {df['close'].iloc[-1]}"


def classify_securities() -> tuple[str, str]:
    try:
        df = pb.dc.securities()
    except Exception as e:  # noqa: BLE001
        return _classify_exc(e)
    if list(df.columns) != SECURITIES_COLUMNS:
        return "schema", f"列契约变化: {list(df.columns)}"
    markets = set(df["market"])
    if not {"SH", "SZ", "BJ"} <= markets:
        return "data", f"缺市场: 实得 {sorted(markets)}"
    n_uniq = df["symbol"].nunique()
    if n_uniq != len(df):
        return "data", f"symbol 有重复: {len(df)} 行 / {n_uniq} 唯一"
    if n_uniq < 4500:
        return "data", f"仅 {n_uniq} 只(疑似偏少)"
    return "ok", f"{n_uniq} 只,市场 {sorted(markets)}"


def main() -> int:
    results: list[tuple[str, str, str]] = [
        (f"dc.kline {s}", *classify_kline(s)) for s in PROBES
    ]
    results.append(("dc.securities", *classify_securities()))
    hard = [r for r in results if r[1] in ("schema", "data")]

    for label, status, detail in results:
        print(f"[{status:9}] {label}: {detail}")

    print(f"\n=== canary: {len(results)} probes, {len(hard)} hard failures ===")
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
