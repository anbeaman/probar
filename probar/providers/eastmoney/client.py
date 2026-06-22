"""东方财富 Provider —— 绑定到 ``pb.dc``。

v0.1 已实现:``quote`` / ``quotes`` / ``kline`` / ``intraday`` / ``fund_flow`` / ``lhb`` /
``financials``(全链路:请求 -> 解析 -> 归一化)。其余接口已在命名空间中声明(诚实反映能力矩阵),
按路线图分批落地,未实现者抛 :class:`NotImplementedError` 并注明计划版本。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from ...core import symbols
from ...core.cache import TTLCache
from ...core.errors import NoData, SchemaChanged
from ...core.models import QUOTE_COLUMNS, ensure_columns, stamp
from ..base import HttpProvider
from . import endpoints as ep
from . import parsers


def _todo(interface: str, version: str = "v0.2") -> NotImplementedError:
    return NotImplementedError(f"pb.dc.{interface} 计划在 {version} 实现")


class EastMoney(HttpProvider):
    name = "dc"

    def __init__(self, *, cache_ttl: float = 3600.0, **kwargs: Any) -> None:
        """``cache_ttl``: 慢变全量数据(如 securities)缓存秒数,默认 1h;余见 HttpProvider。"""
        super().__init__(**kwargs)
        self._cache: TTLCache = TTLCache(ttl=cache_ttl)

    # ---- 已实现:历史 K 线 ------------------------------------------------
    def kline(
        self,
        symbol: str,
        *,
        freq: str = "1d",
        adjust: str | None = "qfq",
        start: str | None = None,
        end: str | None = None,
        limit: int = 1000,
    ) -> pd.DataFrame:
        """历史 K 线。

        参数:
            symbol: 代码,如 "600519.SH" / "000001.SZ" / "600519"
            freq:   1m/5m/15m/30m/60m/1d/1w/1M(默认 1d)
            adjust: "qfq"前复权 / "hfq"后复权 / "none"(或 None)不复权(默认 qfq)
            start, end: "YYYY-MM-DD",省略取最近 limit 根
            limit:  最多根数(默认 1000)
        返回 DataFrame: symbol, date, open, high, low, close,
            volume(手), amount(元), pct_chg(%), turnover(%)
        示例:
            >>> pb.dc.kline("600519.SH", freq="1d", limit=2)
                  symbol       date    open   close  volume  pct_chg
            0  600519.SH 2024-01-02  1685.0  1648.0   38421    -2.11
        """
        if freq not in ep.KLT:
            raise ValueError(f"不支持的 freq={freq!r},可选: {list(ep.KLT)}")
        if adjust not in ep.FQT:
            raise ValueError(f"不支持的 adjust={adjust!r},可选: qfq/hfq/None")
        params = {
            "secid": symbols.to_eastmoney_secid(symbol),
            "ut": ep.UT,
            "fields1": ep.KLINE_FIELDS1,
            "fields2": ep.KLINE_FIELDS2,
            "klt": ep.KLT[freq],
            "fqt": ep.FQT[adjust],
            "beg": (start or "0").replace("-", ""),
            "end": (end or "20500101").replace("-", ""),
            "lmt": limit,
        }
        payload = self._http.get_json(ep.KLINE_URL, params, referer="https://quote.eastmoney.com/")
        df = parsers.parse_kline(payload, symbol=str(symbols.normalize(symbol)))
        # 东财在 beg=0(未给 start)时会忽略 lmt、返回整段历史 -> 仅此情形兜底取最近 limit 根;
        # 给了 start 的区间查询不截断(否则会丢掉区间早段数据)。
        if start is None and len(df) > limit:
            df = df.tail(limit).reset_index(drop=True)
        return stamp(df, source=self.name, freq=freq, adjust=adjust or "none")

    # ---- 已实现:实时快照 ------------------------------------------------
    def quote(self, symbol: str) -> dict[str, Any]:
        """单只实时快照,返回 dict。批量见 :meth:`quotes`。

        参数: symbol 证券代码。
        返回 dict: symbol, name, price(元), open, high, low, prev_close,
            volume(手), amount(元), pct_chg(%);停牌时 price 可能为 None。
        示例:
            >>> pb.dc.quote("600519.SH")
            {'symbol': '600519.SH', 'name': '贵州茅台', 'price': 1648.0,
             'prev_close': 1683.51, 'volume': 38421, 'pct_chg': -2.11}
        """
        params = {
            "secid": symbols.to_eastmoney_secid(symbol),
            "ut": ep.UT,
            "fields": ep.QUOTE_FIELDS,
        }
        payload = self._http.get_json(ep.QUOTE_URL, params, referer="https://quote.eastmoney.com/")
        return parsers.parse_quote(payload, symbol=str(symbols.normalize(symbol)))

    def quotes(self, symbol_list: list[str]) -> pd.DataFrame:
        """批量实时快照,返回 DataFrame(**一次请求多只**,免去逐只循环被限频)。

        参数: symbol_list 代码列表,如 ["000001.SZ", "600519.SH"];自动分批(每批<=100)。
        返回列: symbol, name, price(元), open, high, low, prev_close,
            volume(手), amount(元), pct_chg(%)。
        说明: 走 push2 ulist 批量端点,N 只仅发 ceil(N/100) 次请求(原先 N 次),显著降低被限频概率。
        示例:
            >>> pb.dc.quotes(["000001.SZ", "600519.SH"])[["symbol", "name", "price", "pct_chg"]]
                  symbol  name   price  pct_chg
            0  000001.SZ  平安银行   10.52    -2.41
            1  600519.SH  贵州茅台 1215.00    -2.02
        """
        if not symbol_list:
            raise ValueError("symbol_list 不能为空")
        secids = [symbols.to_eastmoney_secid(s) for s in symbol_list]
        frames: list[pd.DataFrame] = []
        for i in range(0, len(secids), ep.QUOTES_MAX_PER_REQ):
            chunk = secids[i : i + ep.QUOTES_MAX_PER_REQ]
            params = {
                "ut": ep.UT,
                "fltt": 2,
                "invt": 2,
                "fields": ep.QUOTES_FIELDS,
                "secids": ",".join(chunk),
            }
            payload = self._http.get_json(
                ep.ULIST_URL, params, referer="https://quote.eastmoney.com/"
            )
            frames.append(parsers.parse_quotes_batch(payload))
        df = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
        ensure_columns(df, QUOTE_COLUMNS, source=self.name, interface="quotes")
        return stamp(df, source=self.name)

    # ---- 已实现:当日分时 / 资金流 / 龙虎榜 / 主要财务 ----
    def intraday(self, symbol: str) -> pd.DataFrame:
        """当日分时(最近交易日;盘中为当日实时),返回 DataFrame。

        参数: symbol 证券代码。
        返回列: symbol, time, open, high, low, close, volume(手),
            amount(元), avg(当日均价, 元);每分钟一行。
        示例:
            >>> pb.dc.intraday("000001.SZ").tail(1)
                  symbol                time  close  volume     avg
            240  000001.SZ 2024-06-19 15:00  11.18    1788  11.205
        """
        params = {
            "secid": symbols.to_eastmoney_secid(symbol),
            "ut": ep.UT,
            "fields1": ep.TRENDS_FIELDS1,
            "fields2": ep.TRENDS_FIELDS2,
            "iscr": 0,
            "ndays": 1,
        }
        payload = self._http.get_json(
            ep.TRENDS_URL, params, referer="https://quote.eastmoney.com/"
        )
        df = parsers.parse_trends(payload, symbol=str(symbols.normalize(symbol)))
        return stamp(df, source=self.name)

    def fund_flow(self, symbol: str, *, days: int = 100) -> pd.DataFrame:
        """个股历史资金流,返回 DataFrame。

        参数: symbol 证券代码;days 取最近多少个交易日(默认 100)。
        返回列(净额=元, 占比=%): symbol, date, main(主力), small, mid,
            large(大单), super(超大单), main_pct…super_pct, close(元), pct_chg(%);
            口径: main = large + super。
        示例:
            >>> pb.dc.fund_flow("000001.SZ", days=2)[["date", "main", "super"]]
                     date          main          super
            0  2026-06-16  -544577072.0  -306740640.0
        """
        params = {
            "secid": symbols.to_eastmoney_secid(symbol),
            "ut": ep.FFLOW_UT,
            "fields1": ep.FFLOW_FIELDS1,
            "fields2": ep.FFLOW_FIELDS2,
            "klt": 101,
            "lmt": days,
        }
        payload = self._http.get_json(
            ep.FFLOW_URL, params, referer="https://data.eastmoney.com/"
        )
        df = parsers.parse_fflow(payload, symbol=str(symbols.normalize(symbol)))
        return stamp(df, source=self.name)

    def sector_fund_flow(self, kind: str = "industry") -> pd.DataFrame:
        """板块资金流榜(行业 / 概念),返回 DataFrame(按主力净额降序)。

        参数: kind = "industry"(行业)/ "concept"(概念)。
        返回列: name(板块名), code(板块代码 BK..), pct_chg(涨跌幅%), main(主力净额 元),
            super / large / mid / small(超大 / 大 / 中 / 小单净额 元), main_pct(主力净占比%),
            lead_stock(领涨股)。
        说明: 东财服务端直接给的**板块涨跌幅 + 主力资金分档**(通达信免费协议给不出,见 pb.tdx);
            一次翻页取全部板块。各源数据独立。
        示例:
            >>> pb.dc.sector_fund_flow("concept").head()[["name", "pct_chg", "main"]]
        """
        if kind not in ep.SECTOR_FFLOW_FS:
            raise ValueError(f"不支持的 kind={kind!r},可选: {list(ep.SECTOR_FFLOW_FS)}")
        items: list[dict[str, Any]] = []
        pn = 1
        while pn <= 50:                  # 上限保护(板块总数 < 1000)
            params = {
                "fid": "f62", "po": 1, "pz": 100, "pn": pn, "np": 1, "fltt": 2, "invt": 2,
                "fs": ep.SECTOR_FFLOW_FS[kind], "fields": ep.SECTOR_FFLOW_FIELDS, "ut": ep.FFLOW_UT,
            }
            payload = self._http.get_json(
                ep.CLIST_URL, params, referer="https://data.eastmoney.com/"
            )
            data = payload.get("data")
            if data is None:                       # 整体无数据
                break
            diff = data.get("diff")
            if diff is None:                       # 缺 diff = 上游字段变了,别静默截断成空页
                raise SchemaChanged(f"东财 sector_fund_flow 响应缺 'diff' 字段: keys={list(data)}")
            page = list(diff.values()) if isinstance(diff, dict) else diff
            if not page:                           # 空列表 = 到底
                break
            items.extend(page)
            if len(items) >= (data.get("total") or 0) or len(page) < 100:
                break
            pn += 1
        # items 为空 -> 交 parser 抛 NoData(语义统一)
        df = parsers.parse_sector_fund_flow({"data": {"diff": items}}, kind=kind)
        return stamp(df, source=self.name, kind=kind)

    def lhb(self, *, date: str) -> pd.DataFrame:
        """龙虎榜某日明细,返回 DataFrame。

        参数: date 交易日,必须 "YYYY-MM-DD"(非法抛 ValueError);
            非交易日 / 无榜单抛 NoData。
        返回列: date, code, name, close(元), change_rate(%), net_buy(元),
            buy, sell, deal_amt, turnover(%), amount(元), reason(上榜原因)。
        注意: 单日较多时取前 500 条,df.attrs["truncated"] 标记是否截断。
        示例:
            >>> pb.dc.lhb(date="2026-06-18")[["code", "name", "net_buy"]].head(1)
                 code  name      net_buy
            0  301687  示例股A  50000000.0
        """
        # 严格校验日期,避免把任意字符串拼进上游 filter 表达式(注入/逃逸)
        try:
            day = datetime.strptime(date, "%Y-%m-%d").strftime("%Y-%m-%d")
        except (TypeError, ValueError):
            raise ValueError(f"date 需为 'YYYY-MM-DD' 格式,得到 {date!r}") from None
        page_size = 500
        params = {
            "reportName": "RPT_DAILYBILLBOARD_DETAILS",
            "columns": "ALL",
            "pageNumber": 1,
            "pageSize": page_size,
            "sortColumns": "TRADE_DATE",
            "sortTypes": -1,
            "filter": f"(TRADE_DATE='{day}')",
        }
        payload = self._http.get_json(
            ep.DATACENTER_URL, params, referer="https://data.eastmoney.com/"
        )
        df = parsers.parse_datacenter(payload, mapping=ep.LHB_MAP, interface="lhb")
        return stamp(df, source=self.name, date=day, truncated=len(df) >= page_size)

    def financials(self, symbol: str) -> pd.DataFrame:
        """主要财务指标(按报告期,一行一期),返回 DataFrame。

        参数: symbol 证券代码。
        返回列: symbol, report_date, eps(元), eps_deduct(元), bps(元),
            revenue(营收, 元), net_profit(归母净利, 元),
            revenue_yoy(%), profit_yoy(%), roe(加权, %)。
        注意: 取最近 50 期,df.attrs["truncated"] 标记是否截断。
        示例:
            >>> pb.dc.financials("600519.SH")[["report_date", "eps", "roe"]].head(1)
                       report_date   eps  roe
            0  2026-03-31 00:00:00  18.5  8.9
        """
        sym = symbols.normalize(symbol)
        params = {
            "reportName": "RPT_F10_FINANCE_MAINFINADATA",
            "columns": "ALL",
            "pageSize": 50,
            "sortColumns": "REPORT_DATE",
            "sortTypes": -1,
            "filter": f'(SECUCODE="{sym.ts_code}")',
        }
        payload = self._http.get_json(
            ep.DATACENTER_URL, params, referer="https://data.eastmoney.com/"
        )
        df = parsers.parse_datacenter(payload, mapping=ep.FINANCIALS_MAP, interface="financials")
        df.insert(0, "symbol", str(sym))
        return stamp(df, source=self.name, truncated=len(df) >= 50)

    # ---- 待实现(占位,调用抛 NotImplementedError)----
    def intraday_hist(self, symbol: str, *, date: str) -> pd.DataFrame:
        raise _todo("intraday_hist")

    def ticks(self, symbol: str) -> pd.DataFrame:
        raise _todo("ticks")

    def hsgt(self) -> pd.DataFrame:
        raise _todo("hsgt")

    def holders(self, symbol: str) -> pd.DataFrame:
        raise _todo("holders", "v0.3")

    def unlock(self, symbol: str) -> pd.DataFrame:
        raise _todo("unlock", "v0.3")

    def dividend(self, symbol: str) -> pd.DataFrame:
        raise _todo("dividend", "v0.3")

    def industry(self) -> pd.DataFrame:
        raise _todo("industry", "v0.3")

    def industry_cons(self, board: str) -> pd.DataFrame:
        raise _todo("industry_cons", "v0.3")

    def concept(self) -> pd.DataFrame:
        raise _todo("concept", "v0.3")

    def concept_cons(self, board: str) -> pd.DataFrame:
        raise _todo("concept_cons", "v0.3")

    def securities(self, *, page_size: int = 1000, use_cache: bool = True) -> pd.DataFrame:
        """全市场 A 股(沪深京)代码表。

        参数:
            page_size: 每页条数(默认 1000,分页拉全,受统一限流器节流)。
            use_cache: 是否走 TTL 缓存(默认 True;代码表慢变,缓存秒数见 cache_ttl)。
        返回列: symbol(规范化,如 600519.SH), code(原始6位), name。
            **只留接口真实字段**:交易所看 symbol 后缀,不另列 market/asset_type。
        说明: 首版只含 A 股;ETF/可转债/指数留待后续小版本。分页拉全后**整表缓存**,
            重复调用直接命中(返回副本,改它不影响缓存),避免反复分页被限频。
        示例:
            >>> df = pb.dc.securities()
            >>> list(df.columns)
            ['symbol', 'code', 'name']
        """
        if use_cache:
            cached = self._cache.get("securities")
            if cached is not None:
                return cached.copy(deep=True)  # 防用户原地改写污染缓存
        frames: list[pd.DataFrame] = []
        seen: set[str] = set()
        total: int | None = None
        for page in range(1, 101):  # 最多 100 页,防失控
            params = {
                "pn": page,
                "pz": page_size,
                "po": 1,
                "np": 1,
                "fltt": 2,
                "invt": 2,
                "fid": "f12",
                "fs": ep.SECURITIES_FS,
                "fields": ep.SECURITIES_FIELDS,
            }
            payload = self._http.get_json(
                ep.CLIST_URL, params, referer="https://quote.eastmoney.com/"
            )
            data = payload.get("data")
            if total is None:
                total = int((data or {}).get("total") or 0)
            # 第 2 页起返回空/缺 diff = 正常翻过末页;第一页则交给 parser 正确抛 NoData/SchemaChanged
            if page > 1 and (not isinstance(data, dict) or not data.get("diff")):
                break
            df = parsers.parse_securities(payload)
            if df.empty:  # 末页(diff == [])
                break
            fresh = df[~df["symbol"].isin(seen)]
            if not fresh.empty:
                frames.append(fresh)
                seen.update(fresh["symbol"].tolist())
            # 按**去重后**的唯一数判断,避免跨页重复导致提前停而漏证券
            if total and len(seen) >= total:
                break
        if not frames:
            if total and total > 0:
                raise SchemaChanged(f"东财 securities total={total} 但未取到任何数据")
            raise NoData("东财 securities 无数据")
        if total and len(seen) < total:  # 100 页上限耗尽仍未拉满 -> 不返回/缓存残表
            raise SchemaChanged(
                f"东财 securities 未拉满: 取到 {len(seen)}/{total}(page_size={page_size} 可能偏小)"
            )
        result = stamp(pd.concat(frames, ignore_index=True), source=self.name, total=total)
        if use_cache:
            self._cache.set("securities", result.copy(deep=True))  # 存副本;异常已提前 raise,不缓存
        return result

    def xdxr(self, symbol: str) -> pd.DataFrame:
        raise _todo("xdxr", "v0.3")
