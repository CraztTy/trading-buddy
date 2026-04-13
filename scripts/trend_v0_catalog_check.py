#!/usr/bin/env python3
"""
束 C3：策略 / 回测 / 因子三份 catalog 契约校验，与 ``scripts/verify_stack.py`` 内
``_verify_api_catalog_contracts()`` 同源（不重复实现规则）。

默认 **进程内**（FastAPI TestClient，无需 uvicorn）。可选 ``--http-base-url`` 对已部署 API 做同样断言。

用法（项目根）::

    python scripts/trend_v0_catalog_check.py
    python scripts/trend_v0_catalog_check.py --http-base-url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Any

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


def _load_verify_stack():
    spec = importlib.util.spec_from_file_location(
        "verify_stack_trend_c3",
        project_root / "scripts" / "verify_stack.py",
    )
    if not spec or not spec.loader:
        raise RuntimeError("无法加载 scripts/verify_stack.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _align_strategy_vs_backtest_catalog(sc_body: object, bc_body: object) -> str | None:
    """与 verify_stack._strategy_catalog_vs_backtest_archive_errors 中 archive_kind 对齐段一致。"""
    if not isinstance(bc_body, dict):
        return "backtest catalog: 响应体不是 JSON 对象"
    strategies_bc = bc_body.get("strategies")
    if not isinstance(strategies_bc, list):
        return "backtest catalog: strategies 非列表"
    by_engine: dict[str, str] = {
        str(s["strategy_id"]): str(s["archive_kind"])
        for s in strategies_bc
        if isinstance(s, dict) and "strategy_id" in s and "archive_kind" in s
    }
    if not isinstance(sc_body, dict):
        return "strategies catalog: 响应体不是 JSON 对象"
    strategies = sc_body.get("strategies")
    if not isinstance(strategies, list):
        return "strategies catalog: strategies 非列表"
    for j, st in enumerate(strategies):
        if not isinstance(st, dict):
            continue
        br = st.get("backtest_run")
        if not isinstance(br, dict):
            continue
        sid = br.get("strategy_id")
        ak = br.get("archive_kind")
        if not isinstance(sid, str) or sid not in by_engine:
            continue
        if not isinstance(ak, str):
            return f"strategies catalog: 条目 {j} backtest_run.archive_kind 非字符串"
        if ak != by_engine[sid]:
            return (
                f"archive_kind 不一致: strategy_id={sid!r} "
                f"strategies.catalog={ak!r} backtest.catalog={by_engine[sid]!r}"
            )
    return None


def _check_in_process(mod: Any) -> str | None:
    return mod._verify_api_catalog_contracts()


def _check_http(mod: Any, base_url: str) -> str | None:
    import httpx
    from unittest.mock import patch

    root = base_url.rstrip("/")
    paths = (
        "/api/strategies/catalog",
        "/api/backtest/catalog",
        "/api/factors/catalog",
    )
    bodies: dict[str, object] = {}
    with httpx.Client(base_url=root, timeout=30.0) as client:
        for path in paths:
            r = client.get(path)
            if r.status_code != 200:
                return f"{path} -> HTTP {r.status_code}"
            try:
                bodies[path] = r.json()
            except Exception as e:
                return f"{path} JSON 解析失败: {e}"

    sc = bodies["/api/strategies/catalog"]
    bc = bodies["/api/backtest/catalog"]
    fc = bodies["/api/factors/catalog"]

    err = mod._strategies_catalog_shape_errors(sc)
    if err:
        return err
    # 远程服务 persistence 可能与本地 .env 不同；按响应体自洽性校验（与 verify_stack 其余规则一致）
    ajp = bc.get("async_job_persistence") if isinstance(bc, dict) else None
    if ajp not in ("memory", "redis"):
        return f"backtest catalog: async_job_persistence 无效: {ajp!r}"
    with patch(
        "src.backtest.async_job_backend.catalog_async_job_persistence",
        return_value=ajp,
    ):
        err = mod._backtest_catalog_archive_kind_errors(bc)
    if err:
        return err
    err = _align_strategy_vs_backtest_catalog(sc, bc)
    if err:
        return err

    err = mod._factors_catalog_top_level_errors(fc)
    if err:
        return err
    err = mod._factors_catalog_shape_errors(fc)
    if err:
        return err
    return mod._factors_catalog_op_ids_match_opname(fc)


def main() -> int:
    p = argparse.ArgumentParser(description="趋势 v0 束 C3：三 catalog 契约（同 verify_stack）")
    p.add_argument(
        "--http-base-url",
        default="",
        metavar="URL",
        help="若设置，则对已运行 API 发 HTTP GET（否则用进程内 TestClient）",
    )
    args = p.parse_args()

    try:
        mod = _load_verify_stack()
    except Exception as e:
        print(f"加载 verify_stack 失败: {e}", file=sys.stderr)
        return 1

    try:
        if args.http_base_url.strip():
            err = _check_http(mod, args.http_base_url.strip())
            mode = f"HTTP {args.http_base_url.strip()}"
        else:
            err = _check_in_process(mod)
            mode = "in-process TestClient"
    except Exception as e:
        print(f"[FAIL] {mode}: {e}", file=sys.stderr)
        return 1

    if err:
        print(f"[FAIL] {mode}: {err}")
        return 1
    print(f"[OK] catalog contracts ({mode})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
