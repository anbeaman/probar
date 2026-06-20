"""`python -m probar.playground` 启动本地测试台。"""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="probar 接口可视化测试台")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError as e:  # noqa: B904
        raise SystemExit("缺少依赖,请先安装:pip install \"probar[playground]\"") from e

    print(f"probar 测试台: http://{args.host}:{args.port}")
    uvicorn.run("probar.playground.app:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
