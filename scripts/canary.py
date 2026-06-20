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

PROBES = ["600519.SH", "000001.SZ"]


def classify_kline(symbol: str) -> tuple[str, str]:
    try:
        df = pb.dc.kline(symbol, freq="1d", adjust="qfq", limit=5)
    except SchemaChanged as e:
        return "schema", str(e)
    except RateLimited as e:
        return "ratelimit", str(e)
    except NetworkError as e:
        return "network", str(e)
    except Exception as e:  # noqa: BLE001
        return "data", f"{type(e).__name__}: {e}"

    if df.empty or (df["close"] <= 0).any():
        return "data", f"{symbol} 收盘价异常: {df['close'].tolist()}"
    return "ok", f"{symbol} {len(df)} 行,最新收盘 {df['close'].iloc[-1]}"


def main() -> int:
    results = [(s, *classify_kline(s)) for s in PROBES]
    hard = [r for r in results if r[1] in ("schema", "data")]

    for symbol, status, detail in results:
        print(f"[{status:9}] dc.kline {symbol}: {detail}")

    print(f"\n=== canary: {len(results)} probes, {len(hard)} hard failures ===")
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
