"""东方财富 Provider —— 绑定到 ``pb.dc``。

v0.1 已实现:``quote`` / ``quotes`` / ``kline``(全链路:请求 -> 解析 -> 归一化)。
其余接口已在命名空间中声明(诚实反映能力矩阵),实现按路线图分批落地,未实现者
抛 :class:`NotImplementedError` 并注明计划版本。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from ...core import symbols
from ...core.models import QUOTE_COLUMNS, ensure_columns, stamp
from ..base import HttpProvider
from . import endpoints as ep
from . import parsers


def _todo(interface: str, version: str = "v0.2") -> NotImplementedError:
    return NotImplementedError(f"pb.dc.{interface} 计划在 {version} 实现")


class EastMoney(HttpProvider):
    name = "dc"

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
        """历史 K 线。``freq`` ∈ {1m,5m,15m,30m,60m,1d,1w,1M};``adjust`` ∈ {qfq,hfq,None}。"""
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
        return stamp(df, source=self.name, freq=freq, adjust=adjust or "none")

    # ---- 已实现:实时快照 ------------------------------------------------
    def quote(self, symbol: str) -> dict[str, Any]:
        """单只实时快照(dict)。批量见 :meth:`quotes`。"""
        params = {
            "secid": symbols.to_eastmoney_secid(symbol),
            "ut": ep.UT,
            "fields": ep.QUOTE_FIELDS,
        }
        payload = self._http.get_json(ep.QUOTE_URL, params, referer="https://quote.eastmoney.com/")
        return parsers.parse_quote(payload, symbol=str(symbols.normalize(symbol)))

    def quotes(self, symbol_list: list[str]) -> pd.DataFrame:
        """批量实时快照(DataFrame)。v0.1 串行实现;v0.2 改用东财批量接口 + 异步。"""
        rows = [self.quote(s) for s in symbol_list]
        df = pd.DataFrame(rows)
        ensure_columns(df, QUOTE_COLUMNS, source=self.name, interface="quotes")
        return stamp(df, source=self.name)

    # ---- 已声明、待实现(诚实反映能力矩阵)-------------------------------
    def intraday(self, symbol: str) -> pd.DataFrame:
        """当日分时(trends2):时间/开/高/低/收/量/额/均价。"""
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
        """个股历史资金流:主力/超大单/大单/中单/小单净额与净占比。"""
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

    def lhb(self, *, date: str) -> pd.DataFrame:
        """龙虎榜某日明细。``date`` 形如 ``'2026-06-18'``。"""
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
        """主要财务指标(按报告期):EPS/扣非EPS/BPS/营收/归母净利/同比/ROE。"""
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

    def securities(self) -> pd.DataFrame:
        raise _todo("securities")

    def xdxr(self, symbol: str) -> pd.DataFrame:
        raise _todo("xdxr", "v0.3")
