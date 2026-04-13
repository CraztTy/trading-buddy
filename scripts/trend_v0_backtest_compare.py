#!/usr/bin/env python3
"""
趋势 v0 束 D：回测可复现（D1）、扫描导出命名（D2）、费率敏感性（D3）、可选日期窗口（D4）。

依赖：库内有池内日 K。默认读 ``config/trend_v0_pool.txt``。可选 ``--start-date`` / ``--end-date``（ISO）写入 ``params``，与 **GET ma-cross/scan** 查询一致。

- **HTTP**（默认）：本机或其它地址已起 API，``--base-url``。
- **``--in-process``**：FastAPI ``TestClient``，无需 uvicorn；与 **``trend_v0_archive_baseline.py --in-process``** 一致，避免端口上旧进程导致 **400**。

用法（项目根）::

    python scripts/trend_v0_backtest_compare.py --base-url http://127.0.0.1:8000
    python scripts/trend_v0_backtest_compare.py --in-process --mode buy-hold-repeat --code sh.600519 --repeat 3
    python scripts/trend_v0_backtest_compare.py --mode scan-snapshot --out-dir artifacts/trend_v0
    python scripts/trend_v0_backtest_compare.py --mode fee-sweep
    python scripts/trend_v0_backtest_compare.py --in-process --mode fee-sweep-buy-hold --code sh.600519
"""

from __future__ import annotations

import argparse
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

project_root = Path(__file__).resolve().parent.parent
_root_s = str(project_root)
if _root_s not in sys.path:
    sys.path.insert(0, _root_s)

from src.common.cli_iso_date import (  # noqa: E402
    check_cli_date_order,
    parse_cli_iso_date,
)


class _HttpxApiBridge:
    """``path`` 须以 ``/`` 开头（如 ``/api/backtest/run``）。"""

    def __init__(self, client: httpx.Client, base: str) -> None:
        self._c = client
        self._base = base.rstrip("/")

    def post(self, path: str, json: dict[str, Any], timeout: float = 120.0) -> Any:
        return self._c.post(f"{self._base}{path}", json=json, timeout=timeout)

    def get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        timeout: float = 300.0,
    ) -> Any:
        return self._c.get(f"{self._base}{path}", params=params or {}, timeout=timeout)


class _TestClientApiBridge:
    def __init__(self, tc: Any) -> None:
        self._tc = tc

    def post(self, path: str, json: dict[str, Any], timeout: float = 120.0) -> Any:
        _ = timeout
        return self._tc.post(path, json=json)

    def get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        timeout: float = 300.0,
    ) -> Any:
        _ = timeout
        return self._tc.get(path, params=params or {})


def _load_codes(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        out.append(s.lower())
    return list(dict.fromkeys(out))


def _ts_compact() -> str:
    return datetime.now().strftime("%Y%m%dT%H%M%S")


def _single_body(
    code: str,
    *,
    commission_rate: float,
    slippage_rate: float,
    fast: int,
    slow: int,
    limit: int,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "code": code,
        "fast": fast,
        "slow": slow,
        "limit": limit,
        "commission_rate": commission_rate,
        "slippage_rate": slippage_rate,
    }
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    return {"strategy_id": "ma_cross", "strategy_version": "1", "params": params}


def _buy_hold_body(
    code: str,
    *,
    commission_rate: float,
    slippage_rate: float,
    limit: int,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "code": code,
        "limit": limit,
        "commission_rate": commission_rate,
        "slippage_rate": slippage_rate,
    }
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    return {"strategy_id": "buy_hold", "strategy_version": "1", "params": params}


def _fingerprint_single(data: dict[str, Any]) -> tuple[Any, ...]:
    ev = data.get("engine_version")
    res = data.get("result") or {}
    tr = res.get("total_return_pct")
    dd = res.get("max_drawdown_pct")
    sh = res.get("sharpe_ratio")
    bars = res.get("bars_used")
    sig = res.get("signal_changes")
    code = res.get("code")
    if isinstance(tr, (int, float)) and isinstance(dd, (int, float)) and isinstance(sh, (int, float)):
        return (ev, code, bars, round(float(tr), 6), round(float(dd), 6), round(float(sh), 6), sig)
    return (ev, code, bars, tr, dd, sh, sig)


def _scan_codes_str(codes: list[str], max_codes: int) -> str:
    return ",".join(codes[:max_codes])


def _scan_post_body(
    codes_csv: str,
    *,
    commission_rate: float,
    slippage_rate: float,
    fast: int,
    slow: int,
    limit: int,
    max_codes: int,
    sort_by: str,
    max_concurrent: int,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "codes": codes_csv,
        "fast": fast,
        "slow": slow,
        "limit": limit,
        "commission_rate": commission_rate,
        "slippage_rate": slippage_rate,
        "max_codes": max_codes,
        "sort_by": sort_by,
        "max_concurrent": max_concurrent,
    }
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    return {"strategy_id": "ma_cross_scan", "strategy_version": "1", "params": params}


def _scan_result_dict(data: dict[str, Any]) -> dict[str, Any]:
    """POST /run 为 ``{ scan_result: {...} }``；GET /ma-cross/scan 根对象即扫描体。"""
    sr = data.get("scan_result")
    if isinstance(sr, dict):
        return sr
    return data


def _fingerprint_scan(data: dict[str, Any]) -> tuple[Any, ...]:
    ev = data.get("engine_version")
    sr = _scan_result_dict(data)
    items = sr.get("items") or []
    rows: list[tuple[str, Any, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        c = str(it.get("code", ""))
        tr = it.get("total_return_pct")
        err = it.get("error")
        if isinstance(tr, (int, float)):
            rows.append((c, round(float(tr), 6), err))
        else:
            rows.append((c, None, err))
    rows.sort(key=lambda x: x[0])
    return (ev, sr.get("sort_by"), tuple(rows))


def run_single_repeat(
    api: Any,
    body: dict[str, Any],
    repeat: int,
    *,
    ok_tag: str = "single-repeat",
    post_timeout: float = 120.0,
) -> int:
    path = "/api/backtest/run"
    fps: list[tuple[Any, ...]] = []
    for i in range(repeat):
        r = api.post(path, json=body, timeout=post_timeout)
        if r.status_code != 200:
            print(f"[FAIL] POST run single HTTP {r.status_code} {r.text[:300]!r}")
            return 1
        data = r.json()
        fp = _fingerprint_single(data)
        fps.append(fp)
        print(f"  run {i + 1}/{repeat}: engine_version={fp[0]!r} total_return_pct={fp[3]!r} bars_used={fp[2]!r}")
    if len(set(fps)) != 1:
        print(f"[FAIL] 同参 {repeat} 次指纹不一致: {fps!r}")
        return 1
    print(f"[OK] {ok_tag}: {repeat} 次结果一致（engine_version 与核心指标）")
    return 0


def run_scan_snapshot(
    api: Any,
    pool: Path,
    out_dir: Path,
    max_codes: int,
    sort_by: str,
    fast: int,
    slow: int,
    limit: int,
    commission_rate: float,
    slippage_rate: float,
    max_concurrent: int,
    start_date: str | None,
    end_date: str | None,
) -> int:
    codes = _load_codes(pool)
    if not codes:
        print("[FAIL] 股票池为空", file=sys.stderr)
        return 1
    n = min(max_codes, len(codes))
    codes_csv = _scan_codes_str(codes, n)
    body = _scan_post_body(
        codes_csv,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        fast=fast,
        slow=slow,
        limit=limit,
        max_codes=n,
        sort_by=sort_by,
        max_concurrent=max_concurrent,
        start_date=start_date,
        end_date=end_date,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = _ts_compact()
    stem = f"scan_{ts}_sort-{sort_by}_max{n}"

    r = api.post("/api/backtest/run", json=body, timeout=300.0)
    if r.status_code != 200:
        print(f"[FAIL] POST scan HTTP {r.status_code} {r.text[:400]!r}")
        return 1
    post_path = out_dir / f"{stem}_POST.json"
    post_path.write_text(r.text, encoding="utf-8")
    print(f"  wrote {post_path}")
    data = r.json()

    params: dict[str, Any] = {
        "codes": codes_csv,
        "fast": fast,
        "slow": slow,
        "limit": limit,
        "commission_rate": commission_rate,
        "slippage_rate": slippage_rate,
        "max_codes": n,
        "sort_by": sort_by,
        "max_concurrent": max_concurrent,
        "export": "csv",
    }
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    r2 = api.get("/api/backtest/ma-cross/scan", params=params, timeout=300.0)
    if r2.status_code != 200:
        print(f"[FAIL] GET scan csv HTTP {r2.status_code} {r2.text[:200]!r}")
        return 1
    csv_path = out_dir / f"{stem}_GET.csv"
    csv_path.write_bytes(r2.content)
    print(f"  wrote {csv_path}")

    fp1 = _fingerprint_scan(data)
    r_json = api.get(
        "/api/backtest/ma-cross/scan",
        params={**params, "export": "json"},
        timeout=300.0,
    )
    if r_json.status_code != 200:
        print(f"[FAIL] GET scan json HTTP {r_json.status_code}")
        return 1
    fp2 = _fingerprint_scan(r_json.json())
    if fp1[1:] != fp2[1:]:
        print(f"[WARN] POST run 与 GET json 扫描行不一致 POST={fp1[1:]!r} GET={fp2[1:]!r}")
    else:
        print("  POST run 与 GET json 扫描行一致（sort_by 与逐 code total_return）")
    print("[OK] scan-snapshot")
    return 0


def run_fee_sweep(
    api: Any,
    code: str,
    slippage_rate: float,
    fast: int,
    slow: int,
    limit: int,
    start_date: str | None,
    end_date: str | None,
) -> int:
    path = "/api/backtest/run"
    tiers = (0.0, 0.00015, 0.001)
    rows: list[tuple[float, float, float, float, float]] = []
    print(f"code={code} slippage_rate={slippage_rate} fast={fast} slow={slow} limit={limit}")
    print("| commission_rate | total_return_pct | max_drawdown_pct | sharpe_ratio | annualized_return_pct |")
    print("|----------------:|-----------------:|-----------------:|-------------:|----------------------:|")
    for cr in tiers:
        body = _single_body(
            code,
            commission_rate=cr,
            slippage_rate=slippage_rate,
            fast=fast,
            slow=slow,
            limit=limit,
            start_date=start_date,
            end_date=end_date,
        )
        r = api.post(path, json=body, timeout=120.0)
        if r.status_code != 200:
            print(f"[FAIL] commission_rate={cr} HTTP {r.status_code} {r.text[:200]!r}")
            return 1
        data = r.json()
        res = data.get("result") or {}
        tr = float(res.get("total_return_pct", 0.0))
        dd = float(res.get("max_drawdown_pct", 0.0))
        sh = float(res.get("sharpe_ratio", 0.0))
        ann = float(res.get("annualized_return_pct", 0.0))
        rows.append((cr, tr, dd, sh, ann))
        print(f"| {cr:g} | {tr:.4f} | {dd:.4f} | {sh:.4f} | {ann:.4f} |")
    if all(math.isclose(rows[0][1], rows[i][1], rel_tol=0, abs_tol=1e-9) for i in range(1, len(rows))):
        print("[WARN] 三档费率 total_return 完全相同，请确认费率已传入内核。")
    print("[OK] fee-sweep")
    return 0


def run_fee_sweep_buy_hold(
    api: Any,
    code: str,
    slippage_rate: float,
    limit: int,
    start_date: str | None,
    end_date: str | None,
) -> int:
    """与 ``fee-sweep`` 相同三档 ``commission_rate``，请求体为 ``buy_hold``（无 fast/slow）。"""
    path = "/api/backtest/run"
    tiers = (0.0, 0.00015, 0.001)
    rows: list[tuple[float, float, float, float, float]] = []
    print(
        f"code={code} strategy=buy_hold slippage_rate={slippage_rate} limit={limit}"
    )
    print("| commission_rate | total_return_pct | max_drawdown_pct | sharpe_ratio | annualized_return_pct |")
    print("|----------------:|-----------------:|-----------------:|-------------:|----------------------:|")
    for cr in tiers:
        body = _buy_hold_body(
            code,
            commission_rate=cr,
            slippage_rate=slippage_rate,
            limit=limit,
            start_date=start_date,
            end_date=end_date,
        )
        r = api.post(path, json=body, timeout=120.0)
        if r.status_code != 200:
            print(f"[FAIL] commission_rate={cr} HTTP {r.status_code} {r.text[:200]!r}")
            return 1
        data = r.json()
        res = data.get("result") or {}
        tr = float(res.get("total_return_pct", 0.0))
        dd = float(res.get("max_drawdown_pct", 0.0))
        sh = float(res.get("sharpe_ratio", 0.0))
        ann = float(res.get("annualized_return_pct", 0.0))
        rows.append((cr, tr, dd, sh, ann))
        print(f"| {cr:g} | {tr:.4f} | {dd:.4f} | {sh:.4f} | {ann:.4f} |")
    if all(math.isclose(rows[0][1], rows[i][1], rel_tol=0, abs_tol=1e-9) for i in range(1, len(rows))):
        print("[WARN] 三档费率 total_return 完全相同，请确认费率已传入内核。")
    print("[OK] fee-sweep-buy-hold")
    return 0


def _run_all_modes(
    api: Any,
    args: argparse.Namespace,
    code: str,
    codes: list[str],
    start_d: str | None,
    end_d: str | None,
) -> int:
    if args.mode == "single-repeat":
        body = _single_body(
            code,
            commission_rate=args.commission_rate,
            slippage_rate=args.slippage_rate,
            fast=args.fast,
            slow=args.slow,
            limit=args.limit,
            start_date=start_d,
            end_date=end_d,
        )
        return run_single_repeat(api, body, max(2, args.repeat))
    if args.mode == "buy-hold-repeat":
        body_bh = _buy_hold_body(
            code,
            commission_rate=args.commission_rate,
            slippage_rate=args.slippage_rate,
            limit=args.limit,
            start_date=start_d,
            end_date=end_d,
        )
        return run_single_repeat(
            api,
            body_bh,
            max(2, args.repeat),
            ok_tag="buy-hold-repeat",
        )
    if args.mode == "scan-repeat":
        n = min(args.max_codes, len(codes))
        body = _scan_post_body(
            _scan_codes_str(codes, n),
            commission_rate=args.commission_rate,
            slippage_rate=args.slippage_rate,
            fast=args.fast,
            slow=args.slow,
            limit=args.limit,
            max_codes=n,
            sort_by=args.sort_by,
            max_concurrent=args.max_concurrent,
            start_date=start_d,
            end_date=end_d,
        )
        fps_sr: list[tuple[Any, ...]] = []
        for i in range(max(2, args.repeat)):
            r = api.post("/api/backtest/run", json=body, timeout=300.0)
            if r.status_code != 200:
                print(f"[FAIL] scan HTTP {r.status_code} {r.text[:400]!r}")
                return 1
            fp = _fingerprint_scan(r.json())
            fps_sr.append(fp)
            print(f"  scan {i + 1}: engine_version={fp[0]!r} rows={len(fp[2])}")
        if len(set(fps_sr)) != 1:
            print(f"[FAIL] 同参扫描 {args.repeat} 次指纹不一致")
            for i, fp in enumerate(fps_sr):
                print(f"    {i}: {fp!r}")
            return 1
        print("[OK] scan-repeat: 多次扫描排序与逐 code 收益一致")
        return 0
    if args.mode == "scan-snapshot":
        return run_scan_snapshot(
            api,
            args.pool,
            args.out_dir,
            args.max_codes,
            args.sort_by,
            args.fast,
            args.slow,
            args.limit,
            args.commission_rate,
            args.slippage_rate,
            args.max_concurrent,
            start_d,
            end_d,
        )
    if args.mode == "fee-sweep":
        return run_fee_sweep(
            api,
            code,
            args.slippage_rate,
            args.fast,
            args.slow,
            args.limit,
            start_d,
            end_d,
        )
    if args.mode == "fee-sweep-buy-hold":
        return run_fee_sweep_buy_hold(
            api,
            code,
            args.slippage_rate,
            args.limit,
            start_d,
            end_d,
        )
    return 1


def main() -> int:
    p = argparse.ArgumentParser(description="趋势 v0 束 D：回测对比与导出")
    p.add_argument("--base-url", default="http://127.0.0.1:8000", help="API 根地址")
    p.add_argument("--pool", type=Path, default=project_root / "config" / "trend_v0_pool.txt")
    p.add_argument(
        "--mode",
        choices=[
            "single-repeat",
            "buy-hold-repeat",
            "scan-repeat",
            "scan-snapshot",
            "fee-sweep",
            "fee-sweep-buy-hold",
        ],
        default="single-repeat",
        help=(
            "single-repeat / buy-hold-repeat=D1（MA 或 buy_hold 同参指纹）；"
            "scan-repeat=D2 同参两次；scan-snapshot=D2 导出；"
            "fee-sweep / fee-sweep-buy-hold=D3（MA 或 buy_hold 三档佣金）"
        ),
    )
    p.add_argument(
        "--repeat",
        type=int,
        default=2,
        help="single-repeat / buy-hold-repeat / scan-repeat 次数",
    )
    p.add_argument("--code", default="", help="单标的 code；默认池内第一只")
    p.add_argument("--fast", type=int, default=5)
    p.add_argument("--slow", type=int, default=20)
    p.add_argument("--limit", type=int, default=500)
    p.add_argument("--commission-rate", type=float, default=0.00015)
    p.add_argument("--slippage-rate", type=float, default=0.00005)
    p.add_argument("--max-codes", type=int, default=10)
    p.add_argument("--sort-by", default="total_return")
    p.add_argument("--max-concurrent", type=int, default=8)
    p.add_argument(
        "--out-dir",
        type=Path,
        default=project_root / "artifacts" / "trend_v0",
        help="scan-snapshot 输出目录",
    )
    p.add_argument(
        "--start-date",
        default="",
        metavar="YYYY-MM-DD",
        help="写入 params.start_date（束 D4 样本外等）",
    )
    p.add_argument(
        "--end-date",
        default="",
        metavar="YYYY-MM-DD",
        help="写入 params.end_date",
    )
    p.add_argument(
        "--in-process",
        action="store_true",
        help="使用 FastAPI TestClient（无需 uvicorn；需 .env 可连数据库）",
    )
    args = p.parse_args()
    try:
        sd = parse_cli_iso_date("--start-date", args.start_date or None)
        ed = parse_cli_iso_date("--end-date", args.end_date or None)
    except ValueError as e:
        print(f"[FAIL] {e}", file=sys.stderr)
        return 1
    bad_order = check_cli_date_order(sd, ed)
    if bad_order:
        print(f"[FAIL] {bad_order}", file=sys.stderr)
        return 1
    start_d = sd.isoformat() if sd else None
    end_d = ed.isoformat() if ed else None

    if not args.pool.is_file():
        print(f"股票池不存在: {args.pool}", file=sys.stderr)
        return 1

    codes = _load_codes(args.pool)
    if not codes:
        print("股票池为空", file=sys.stderr)
        return 1
    code = (args.code or codes[0]).strip().lower()

    if args.in_process:
        try:
            from fastapi.testclient import TestClient

            from src.api.main import app

            with TestClient(app) as tc:
                api = _TestClientApiBridge(tc)
                return _run_all_modes(api, args, code, codes, start_d, end_d)
        except Exception as e:
            print(f"[FAIL] {e}", file=sys.stderr)
            return 1

    base = args.base_url.rstrip("/")
    try:
        with httpx.Client(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
            api = _HttpxApiBridge(client, base)
            return _run_all_modes(api, args, code, codes, start_d, end_d)
    except httpx.ConnectError as e:
        print(f"无法连接 {base}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
