"""probar 接口可视化测试台(本地)。

自省 pb.dc / pb.tdx / pb.ths / pb.auto 的全部接口,前端可选接口、填参数、运行,
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

NAMESPACES: dict[str, Any] = {"dc": pb.dc, "tdx": pb.tdx, "ths": pb.ths, "auto": pb.auto}
NS_LABEL = {"dc": "东方财富", "tdx": "通达信", "ths": "同花顺", "auto": "跨源故障转移"}
_SKIP = {"close"}  # 生命周期方法,非数据接口

_EMPTY = inspect.Parameter.empty


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
            methods.append(
                {
                    "name": attr,
                    "doc": doc[0] if doc else "",
                    "implemented": not _is_stub(m),
                    "params": _param_spec(m),
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
