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

import datetime as dt
import sys

import probar as pb
from probar.core.errors import NetworkError, NoData, RateLimited, SchemaChanged
from probar.core.models import SECURITIES_COLUMNS

PROBES = ["600519.SH", "000001.SZ"]
# 通达信只返回协议真实字段(不含 dc 才有的 name/pct_chg/turnover)
_TDX_KLINE_COLS = ["symbol", "date", "open", "high", "low", "close", "volume", "amount"]
_TDX_QUOTE_CORE = {"symbol", "price", "open", "high", "low", "prev_close", "volume", "amount"}


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
        return "data", f"{symbol} 收盘价异常(前8): {df['close'].tolist()[:8]}(共{len(df)}行)"
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


def classify_tdx_quote() -> tuple[str, str]:
    try:
        df = pb.tdx.quotes(PROBES)
    except Exception as e:  # noqa: BLE001
        return _classify_exc(e)
    if _TDX_QUOTE_CORE - set(df.columns):
        return "schema", f"缺核心列: 实得 {list(df.columns)[:6]}…"
    if df.empty or (df["price"] <= 0).any():
        return "data", f"现价异常: {df['price'].tolist()}"
    bad = df[(df["ask1"] > 0) & (df["bid1"] > df["ask1"])]
    if not bad.empty:
        return "data", f"bid1>ask1(盘口错乱): {bad['symbol'].tolist()}"
    return "ok", f"{len(df)} 只五档,server={df.attrs.get('server')}"


def classify_tdx_securities() -> tuple[str, str]:
    try:
        df = pb.tdx.securities(use_cache=False)
    except Exception as e:  # noqa: BLE001
        return _classify_exc(e)
    if list(df.columns) != SECURITIES_COLUMNS:
        return "schema", f"列契约变化: {list(df.columns)}"
    markets = set(df["market"])
    if not {"SH", "SZ"} <= markets:
        return "data", f"缺沪深: {sorted(markets)}"
    n_uniq = df["symbol"].nunique()
    if n_uniq != len(df):
        return "data", f"symbol 有重复: {len(df)} 行 / {n_uniq} 唯一"
    if n_uniq < 4500:
        return "data", f"仅 {n_uniq} 只(疑似偏少)"
    return "ok", f"{n_uniq} 只沪深"


def classify_tdx_kline() -> tuple[str, str]:
    try:
        df = pb.tdx.kline("600519.SH", freq="1d", limit=5)
    except Exception as e:  # noqa: BLE001
        return _classify_exc(e)
    if list(df.columns) != _TDX_KLINE_COLS:
        return "schema", f"列契约变化: {list(df.columns)}"
    if df.empty or (df["close"] <= 0).any():
        return "data", f"收盘价异常(前8): {df['close'].tolist()[:8]}"
    return "ok", f"{len(df)} 根,最新收盘 {df['close'].iloc[-1]}"


def classify_tdx_index_kline() -> tuple[str, str]:
    try:
        df = pb.tdx.index_kline("000001.SH", limit=5)   # 上证指数
    except Exception as e:  # noqa: BLE001
        return _classify_exc(e)
    if list(df.columns) != [*_TDX_KLINE_COLS, "up_count", "down_count"]:
        return "schema", f"列契约变化: {list(df.columns)}"
    if df.empty or (df["close"] <= 0).any():
        return "data", f"指数收盘异常(前8): {df['close'].tolist()[:8]}"
    return "ok", f"上证指数 {len(df)} 根,最新 {df['close'].iloc[-1]}"


def classify_tdx_xdxr() -> tuple[str, str]:
    try:
        df = pb.tdx.xdxr("600519.SH")
    except Exception as e:  # noqa: BLE001
        return _classify_exc(e)
    if "fenhong" not in df.columns or "category" not in df.columns:
        return "schema", f"列缺失: {list(df.columns)}"
    cat1 = df[df["category"] == 1]
    if cat1.empty:
        return "data", "无除权除息事件(茅台应有分红)"
    return "ok", f"{len(df)} 事件,{len(cat1)} 除权除息"


def classify_tdx_ticks() -> tuple[str, str]:
    try:
        df = pb.tdx.ticks("600519.SH", limit=50)
    except Exception as e:  # noqa: BLE001
        return _classify_exc(e)
    expect = ["symbol", "time", "price", "vol", "num", "buyorsell"]
    if list(df.columns) != expect:
        return "schema", f"列契约变化: {list(df.columns)}"
    if df.empty or (df["price"] <= 0).any():
        return "data", f"成交价异常(前8): {df['price'].tolist()[:8]}"
    return "ok", f"{len(df)} 笔,最新 {df['time'].iloc[-1]} @ {df['price'].iloc[-1]}"


def _recent_weekday() -> str:
    """最近一个工作日(历史逐笔探针用;挑到节假日 -> NoData 软失败,可接受)。"""
    d = dt.date.today() - dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def classify_tdx_ticks_hist() -> tuple[str, str]:
    try:
        df = pb.tdx.ticks_hist("600519.SH", date=_recent_weekday(), limit=50)
    except NoData as e:
        return "network", f"非交易日/无历史逐笔(软): {e}"   # 日期可能挑到节假日,属正常
    except Exception as e:  # noqa: BLE001
        return _classify_exc(e)
    expect = ["symbol", "date", "time", "price", "vol", "buyorsell"]
    if list(df.columns) != expect:
        return "schema", f"列契约变化: {list(df.columns)}"
    if df.empty or (df["price"] <= 0).any():
        return "data", f"成交价异常(前8): {df['price'].tolist()[:8]}"
    return "ok", f"{len(df)} 笔 @ {df['date'].iloc[0]}"


def classify_tdx_finance_info() -> tuple[str, str]:
    try:
        d = pb.tdx.finance_info("600519.SH")
    except Exception as e:  # noqa: BLE001
        return _classify_exc(e)
    need = {"symbol", "total_shares", "bvps", "ipo_date"}
    if not need <= set(d):
        return "schema", f"缺字段: 实得 {sorted(d)[:8]}"
    if not (d["total_shares"] > 0 and d["bvps"] > 0):
        return "data", f"股本/每股净资产异常: shares={d['total_shares']} bvps={d['bvps']}"
    return "ok", f"总股本 {d['total_shares']:.0f}, bvps {d['bvps']}, ipo {d['ipo_date']}"


def main() -> int:
    results: list[tuple[str, str, str]] = [
        (f"dc.kline {s}", *classify_kline(s)) for s in PROBES
    ]
    results.append(("dc.securities", *classify_securities()))
    results.append(("tdx.quotes", *classify_tdx_quote()))
    results.append(("tdx.securities", *classify_tdx_securities()))
    results.append(("tdx.kline", *classify_tdx_kline()))
    results.append(("tdx.index_kline", *classify_tdx_index_kline()))
    results.append(("tdx.xdxr", *classify_tdx_xdxr()))
    results.append(("tdx.ticks", *classify_tdx_ticks()))
    results.append(("tdx.ticks_hist", *classify_tdx_ticks_hist()))
    results.append(("tdx.finance_info", *classify_tdx_finance_info()))
    hard = [r for r in results if r[1] in ("schema", "data")]

    for label, status, detail in results:
        print(f"[{status:9}] {label}: {detail}")

    print(f"\n=== canary: {len(results)} probes, {len(hard)} hard failures ===")
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
