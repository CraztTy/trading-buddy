#!/usr/bin/env python3
"""
A3 基线存档自动化：``POST /api/backtest/run``（单标的 MA + 同标的 buy_hold + 扫描）→ ``POST /api/backtest/runs``，
打印返回的 **run id**（便于回填 **TREND_V0_SPEC.md** 检查表）。

默认与规格一致：池内第一只 ``ma_cross`` 与 ``buy_hold``；池前 ``--max-codes`` 只 ``ma_cross_scan``。
可选 ``--start-date`` / ``--end-date``（ISO，写入 ``params``，用于束 D4 样本外窗口）。
``--skip-buy-hold`` 时仅保留 MA 单标的 + 扫描两步（兼容旧 JSON 消费方）。

用法::

    python scripts/trend_v0_archive_baseline.py --base-url http://127.0.0.1:8000
    python scripts/trend_v0_archive_baseline.py --in-process
    python scripts/trend_v0_archive_baseline.py --in-process --json-out artifacts/trend_v0/a3_run_ids.json
    python scripts/trend_v0_archive_baseline.py --start-date 2023-01-01 --end-date 2024-06-30 --in-process
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.common.cli_iso_date import (  # noqa: E402
    check_cli_date_order,
    parse_cli_iso_date,
)


def _load_codes(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        out.append(s.lower())
    return list(dict.fromkeys(out))


def _single_run_request(
    code: str,
    *,
    fast: int,
    slow: int,
    limit: int,
    commission_rate: float,
    slippage_rate: float,
    start_date: str | None,
    end_date: str | None,
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


def _scan_run_request(
    codes_csv: str,
    *,
    max_codes: int,
    fast: int,
    slow: int,
    limit: int,
    commission_rate: float,
    slippage_rate: float,
    sort_by: str,
    max_concurrent: int,
    start_date: str | None,
    end_date: str | None,
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


def _buy_hold_run_request(
    code: str,
    *,
    limit: int,
    commission_rate: float,
    slippage_rate: float,
    start_date: str | None,
    end_date: str | None,
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


def main() -> int:
    p = argparse.ArgumentParser(description="A3：单标的 MA + buy_hold + 扫描回测并写入 backtest/runs")
    p.add_argument("--base-url", default="http://127.0.0.1:8000")
    p.add_argument("--pool", type=Path, default=project_root / "config" / "trend_v0_pool.txt")
    p.add_argument("--max-codes", type=int, default=10)
    p.add_argument("--fast", type=int, default=5)
    p.add_argument("--slow", type=int, default=20)
    p.add_argument("--limit", type=int, default=500)
    p.add_argument("--commission-rate", type=float, default=0.00015)
    p.add_argument("--slippage-rate", type=float, default=0.00005)
    p.add_argument("--sort-by", default="total_return")
    p.add_argument("--max-concurrent", type=int, default=8)
    p.add_argument("--start-date", default="", help="ISO 日期，可选")
    p.add_argument("--end-date", default="", help="ISO 日期，可选")
    p.add_argument("--dry-run", action="store_true", help="只打印请求体，不写库")
    p.add_argument(
        "--skip-buy-hold",
        action="store_true",
        help="不跑 buy_hold 单标的存档（仅 ma_cross 单 + scan）",
    )
    p.add_argument("--json-out", type=Path, default=None, help="将 id 等写入 JSON 文件")
    p.add_argument(
        "--in-process",
        action="store_true",
        help="用 FastAPI TestClient（无需 uvicorn；需可连 .env 数据库）",
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
        print(f"池文件不存在: {args.pool}", file=sys.stderr)
        return 1
    codes = _load_codes(args.pool)
    if not codes:
        print("股票池为空", file=sys.stderr)
        return 1

    n = min(args.max_codes, len(codes))
    codes_csv = ",".join(codes[:n])
    single_req = _single_run_request(
        codes[0],
        fast=args.fast,
        slow=args.slow,
        limit=args.limit,
        commission_rate=args.commission_rate,
        slippage_rate=args.slippage_rate,
        start_date=start_d,
        end_date=end_d,
    )
    scan_req = _scan_run_request(
        codes_csv,
        max_codes=n,
        fast=args.fast,
        slow=args.slow,
        limit=args.limit,
        commission_rate=args.commission_rate,
        slippage_rate=args.slippage_rate,
        sort_by=args.sort_by,
        max_concurrent=args.max_concurrent,
        start_date=start_d,
        end_date=end_d,
    )
    buy_req = _buy_hold_run_request(
        codes[0],
        limit=args.limit,
        commission_rate=args.commission_rate,
        slippage_rate=args.slippage_rate,
        start_date=start_d,
        end_date=end_d,
    )

    if args.dry_run:
        payload: dict[str, Any] = {"single": single_req, "scan": scan_req}
        if not args.skip_buy_hold:
            payload["buy_hold"] = buy_req
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    def run_with(client: Any) -> tuple[int, int, int | None]:
        r1 = client.post("/api/backtest/run", json=single_req)
        if r1.status_code != 200:
            raise RuntimeError(f"single run HTTP {r1.status_code}: {r1.text[:500]}")
        single_payload = r1.json()
        arch1 = {
            "kind": "ma_cross_single",
            "request_params": single_req,
            "response_payload": single_payload,
        }
        a1 = client.post("/api/backtest/runs", json=arch1)
        if a1.status_code != 201:
            raise RuntimeError(f"archive single HTTP {a1.status_code}: {a1.text[:500]}")
        id1 = int(a1.json()["id"])

        r2 = client.post("/api/backtest/run", json=scan_req)
        if r2.status_code != 200:
            raise RuntimeError(f"scan run HTTP {r2.status_code}: {r2.text[:500]}")
        scan_payload = r2.json()
        arch2 = {
            "kind": "ma_cross_scan",
            "request_params": scan_req,
            "response_payload": scan_payload,
        }
        a2 = client.post("/api/backtest/runs", json=arch2)
        if a2.status_code != 201:
            raise RuntimeError(f"archive scan HTTP {a2.status_code}: {a2.text[:500]}")
        id2 = int(a2.json()["id"])

        id3: int | None = None
        if not args.skip_buy_hold:
            r3 = client.post("/api/backtest/run", json=buy_req)
            if r3.status_code != 200:
                raise RuntimeError(f"buy_hold run HTTP {r3.status_code}: {r3.text[:500]}")
            buy_payload = r3.json()
            arch3 = {
                "kind": "buy_hold_single",
                "request_params": buy_req,
                "response_payload": buy_payload,
            }
            a3 = client.post("/api/backtest/runs", json=arch3)
            if a3.status_code != 201:
                raise RuntimeError(f"archive buy_hold HTTP {a3.status_code}: {a3.text[:500]}")
            id3 = int(a3.json()["id"])
        return id1, id2, id3

    try:
        if args.in_process:
            from fastapi.testclient import TestClient

            from src.api.main import app

            with TestClient(app) as client:
                sid, zid, bhid = run_with(client)
        else:
            import httpx

            base = args.base_url.rstrip("/")
            with httpx.Client(base_url=base, timeout=300.0) as client:

                class _Wrap:
                    def post(self, path: str, json: dict) -> Any:
                        return client.post(path, json=json)

                sid, zid, bhid = run_with(_Wrap())
    except Exception as e:
        print(f"[FAIL] {e}", file=sys.stderr)
        return 1

    out: dict[str, Any] = {
        "ma_cross_single_run_id": sid,
        "ma_cross_scan_run_id": zid,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "start_date": start_d,
        "end_date": end_d,
    }
    if bhid is not None:
        out["buy_hold_single_run_id"] = bhid
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {args.json_out}")
    print("[OK] trend_v0_archive_baseline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
