"""probar 接口可视化测试台(本地)。

自省 pb.dc / pb.tdx / pb.ths 的全部接口,前端可选接口、填参数、运行,
查看输入与输出(表格 + 来源 provenance + 耗时),错误也清晰展示。

启动::
    pip install "probar[playground]"
    python -m probar.playground            # 默认 http://127.0.0.1:8787

⚠️ 仅本地开发/测试用;会**真实调用**数据源接口(联网取数)。
"""

from __future__ import annotations

import inspect
import json
import time
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

import probar as pb
from probar.core.capabilities import capabilities

app = FastAPI(title="probar playground", docs_url="/docs")

NAMESPACES: dict[str, Any] = {"dc": pb.dc, "tdx": pb.tdx, "ths": pb.ths}
NS_LABEL = {"dc": "东方财富", "tdx": "通达信", "ths": "同花顺"}
_SKIP = {"close"}  # 生命周期方法,非数据接口

_EMPTY = inspect.Parameter.empty

# 每个接口的「可直接跑的示例参数」+「注意事项」,在页面里展示并支持一键填入。
EXAMPLES: dict[str, dict] = {
    "dc.quote": {
        "params": {"symbol": "600519.SH"},
        "note": "单只返回 dict;停牌时 price 可能为 None。金额=元,成交量=手。",
    },
    "dc.quotes": {
        "params": {"symbol_list": "000001.SZ,600519.SH"},
        "note": "批量返回 DataFrame;走 push2 ulist 批量端点,一次请求多只(每批<=100),省去逐只循环。",
    },
    "dc.kline": {
        "params": {"symbol": "600519.SH", "freq": "1d", "adjust": "qfq", "start": "2024-01-01"},
        "note": "freq=1m/5m/15m/30m/60m/1d/1w/1M;adjust=qfq/hfq/none(不复权);"
        "1 分钟历史深度有限;金额=元,量=手,涨跌幅/换手=%。",
    },
    "dc.intraday": {
        "params": {"symbol": "000001.SZ"},
        "note": "返回最近一个交易日的分时;盘中调用为当日实时。每分钟一行。",
    },
    "dc.fund_flow": {
        "params": {"symbol": "000001.SZ", "days": "30"},
        "note": "净额单位=元;main(主力)=large(大单)+super(超大单);占比=%。",
    },
    "dc.lhb": {
        "params": {"date": "2026-06-18"},
        "note": "date 必须 YYYY-MM-DD(否则 ValueError);非交易日 / 无榜单→NoData。金额=元。",
    },
    "dc.financials": {
        "params": {"symbol": "600519.SH"},
        "note": "按报告期,一行一期;金额=元,EPS/BPS=元,同比/ROE=%。",
    },
    "tdx.quotes": {
        "params": {"symbol_list": "000001.SZ,600519.SH"},
        "note": "通达信批量实时五档(分批<=80);只含协议真实字段,无 name/pct_chg。",
    },
    "tdx.quote": {
        "params": {"symbol": "600519.SH"},
        "note": "单只实时五档,返回 dict;无效/停牌无数据抛 NoData。",
    },
}


# 每个接口的「返回数据格式」:kind=dict/DataFrame,fields=[字段名, 含义, 单位]。
_QUOTE_RET = [
    ["symbol", "证券代码", ""], ["name", "名称", ""], ["price", "最新价", "元"],
    ["open", "开盘", "元"], ["high", "最高", "元"], ["low", "最低", "元"],
    ["prev_close", "昨收", "元"], ["volume", "成交量", "手"], ["amount", "成交额", "元"],
    ["pct_chg", "涨跌幅", "%"],
]
RETURNS: dict[str, dict] = {
    "dc.quote": {"kind": "dict", "fields": _QUOTE_RET},
    "dc.quotes": {"kind": "DataFrame", "fields": _QUOTE_RET},
    "dc.kline": {"kind": "DataFrame", "fields": [
        ["symbol", "证券代码", ""], ["date", "日期/时间", "datetime"], ["open", "开盘", "元"],
        ["high", "最高", "元"], ["low", "最低", "元"], ["close", "收盘", "元"],
        ["volume", "成交量", "手"], ["amount", "成交额", "元"], ["pct_chg", "涨跌幅", "%"],
        ["turnover", "换手率", "%"],
    ]},
    "dc.intraday": {"kind": "DataFrame", "fields": [
        ["symbol", "证券代码", ""], ["time", "时间", "datetime"], ["open", "开", "元"],
        ["high", "高", "元"], ["low", "低", "元"], ["close", "现价/收", "元"],
        ["volume", "成交量", "手"], ["amount", "成交额", "元"], ["avg", "当日均价", "元"],
    ]},
    "dc.fund_flow": {"kind": "DataFrame", "fields": [
        ["symbol", "证券代码", ""], ["date", "日期", "datetime"],
        ["main", "主力净额", "元"], ["small", "小单净额", "元"],
        ["mid", "中单净额", "元"], ["large", "大单净额", "元"],
        ["super", "超大单净额", "元"], ["main_pct", "主力净占比", "%"],
        ["small_pct", "小单净占比", "%"], ["mid_pct", "中单净占比", "%"],
        ["large_pct", "大单净占比", "%"], ["super_pct", "超大单净占比", "%"],
        ["close", "收盘", "元"], ["pct_chg", "涨跌幅", "%"],
    ]},
    "dc.lhb": {"kind": "DataFrame", "fields": [
        ["date", "交易日", "datetime"], ["code", "代码", ""], ["name", "名称", ""],
        ["close", "收盘", "元"], ["change_rate", "涨跌幅", "%"], ["net_buy", "龙虎榜净买额", "元"],
        ["buy", "买入额", "元"], ["sell", "卖出额", "元"], ["deal_amt", "龙虎榜成交额", "元"],
        ["turnover", "换手率", "%"], ["amount", "总成交额", "元"], ["reason", "上榜原因", ""],
    ]},
    "dc.financials": {"kind": "DataFrame", "fields": [
        ["symbol", "证券代码", ""], ["report_date", "报告期", "datetime"],
        ["eps", "每股收益", "元"], ["eps_deduct", "扣非每股收益", "元"],
        ["bps", "每股净资产", "元"], ["revenue", "营业收入", "元"],
        ["net_profit", "归母净利润", "元"], ["revenue_yoy", "营收同比", "%"],
        ["profit_yoy", "净利同比", "%"], ["roe", "加权ROE", "%"],
    ]},
}


def _is_stub(method: Any) -> bool:
    try:
        src = inspect.getsource(method)
    except (OSError, TypeError):
        return False
    return "_todo(" in src or "raise NotImplementedError" in src


def _param_spec(method: Any) -> list[dict]:
    specs: list[dict] = []
    try:
        sig = inspect.signature(method)
    except (ValueError, TypeError):
        return specs
    for name, p in sig.parameters.items():
        if name == "self" or p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
            continue
        ann = p.annotation
        ann_str = getattr(ann, "__name__", None) or (str(ann) if ann is not _EMPTY else "str")
        specs.append(
            {
                "name": name,
                "type": ann_str,
                "required": p.default is _EMPTY,
                "default": None if p.default is _EMPTY else p.default,
            }
        )
    return specs


def _catalog() -> list[dict]:
    out = []
    for ns_name, ns in NAMESPACES.items():
        methods = []
        for attr in sorted(dir(ns)):
            if attr.startswith("_") or attr in _SKIP:
                continue
            m = getattr(ns, attr)
            if not callable(m):
                continue
            doc = (inspect.getdoc(m) or "").strip().splitlines()
            implemented = not _is_stub(m)
            ex = EXAMPLES.get(f"{ns_name}.{attr}", {})
            note = ex.get("note") or (
                "" if implemented else "未实现:调用会抛 NotImplementedError(计划后续版本)。"
            )
            methods.append(
                {
                    "name": attr,
                    "summary": doc[0] if doc else "",
                    "doc": "\n".join(doc),
                    "implemented": implemented,
                    "params": _param_spec(m),
                    "example": ex.get("params", {}),
                    "note": note,
                    "returns": RETURNS.get(f"{ns_name}.{attr}"),
                }
            )
        out.append(
            {"namespace": ns_name, "label": NS_LABEL.get(ns_name, ns_name), "methods": methods}
        )
    return out


def _coerce(value: Any, type_str: str | None) -> Any:
    if value is None or value == "":
        return None
    t = (type_str or "").lower()
    try:
        if "list" in t:
            if isinstance(value, list):
                return value
            return [s.strip() for s in str(value).split(",") if s.strip()]
        if "bool" in t:
            return str(value).lower() in ("1", "true", "yes", "on")
        if "int" in t:
            return int(value)
        if "float" in t:
            return float(value)
    except (ValueError, TypeError):
        return value
    return value


def _safe(v: Any) -> Any:
    return v if isinstance(v, (str, int, float, bool, type(None))) else str(v)


def _jsonify(result: Any) -> dict:
    if isinstance(result, pd.DataFrame):
        df = result.head(300).copy()
        for c in df.columns:
            if str(df[c].dtype).startswith("datetime"):
                df[c] = df[c].astype(str)
        rows = json.loads(df.to_json(orient="values", date_format="iso"))
        attrs = {k: _safe(v) for k, v in result.attrs.items()}
        return {
            "kind": "table",
            "columns": [str(c) for c in df.columns],
            "rows": rows,
            "total_rows": int(len(result)),
            "shown": int(len(df)),
            "attrs": attrs,
        }
    if isinstance(result, dict):
        return {"kind": "dict", "data": {str(k): _safe(v) for k, v in result.items()}}
    return {"kind": "text", "data": str(result)}


class CallReq(BaseModel):
    namespace: str
    method: str
    params: dict[str, Any] = {}


@app.get("/api/interfaces")
def interfaces() -> dict:
    return {
        "catalog": _catalog(),
        "capabilities": capabilities().reset_index().to_dict(orient="records"),
    }


@app.post("/api/call")
def call(req: CallReq) -> Any:
    ns = NAMESPACES.get(req.namespace)
    if ns is None:
        return JSONResponse(
            {"ok": False, "error": {"type": "BadNamespace", "message": req.namespace}},
            status_code=400,
        )
    method = getattr(ns, req.method, None)
    if not callable(method):
        msg = f"{req.namespace}.{req.method} 不存在"
        return JSONResponse(
            {"ok": False, "error": {"type": "NotSupported", "message": msg}}, status_code=400
        )
    specs = {s["name"]: s for s in _param_spec(method)}
    kwargs = {}
    for k, v in (req.params or {}).items():
        cv = _coerce(v, specs.get(k, {}).get("type"))
        if cv is not None:
            kwargs[k] = cv

    t0 = time.perf_counter()
    try:
        result = method(**kwargs)
    except Exception as e:  # noqa: BLE001 —— 测试台要把任何异常都清晰回显
        return {
            "ok": False,
            "elapsed_ms": round((time.perf_counter() - t0) * 1000),
            "called": f"pb.{req.namespace}.{req.method}({kwargs})",
            "error": {"type": type(e).__name__, "message": str(e)},
        }
    payload = _jsonify(result)
    payload.update(
        {
            "ok": True,
            "elapsed_ms": round((time.perf_counter() - t0) * 1000),
            "called": f"pb.{req.namespace}.{req.method}({kwargs})",
        }
    )
    return payload


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (Path(__file__).parent / "index.html").read_text(encoding="utf-8")
