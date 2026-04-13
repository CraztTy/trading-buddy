#!/usr/bin/env python3
"""
趋势 v0 束 E1：纸交易仅允许 ``config/trend_v0_pool.txt`` 内标的；调用与 README 一致的 API。

流程（默认）：``GET /api/paper/state`` → 对池内前 N 只各 ``POST /api/paper/orders`` 买入一手（100 股）→
对第一只已买入标的尝试 **当日再卖** 一手，预期 **400**（T+1 拒单）→ ``GET /api/paper/orders`` 摘要。

可选 ``--reset``：先 ``POST /api/paper/account/reset``（**开发/自测**，会清空纸单与持仓）。

用法::

    python scripts/trend_v0_paper_smoke.py --base-url http://127.0.0.1:8000
    python scripts/trend_v0_paper_smoke.py --reset --sample 1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

project_root = Path(__file__).resolve().parent.parent


def _load_pool_set(path: Path) -> tuple[list[str], frozenset[str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    ordered: list[str] = []
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        ordered.append(s.lower())
    seen: list[str] = []
    for c in ordered:
        if c not in seen:
            seen.append(c)
    return seen, frozenset(seen)


def main() -> int:
    p = argparse.ArgumentParser(description="趋势 v0 纸交易池内冒烟（束 E1）")
    p.add_argument("--base-url", default="http://127.0.0.1:8000")
    p.add_argument("--pool", type=Path, default=project_root / "config" / "trend_v0_pool.txt")
    p.add_argument("--sample", type=int, default=2, help="池内前 N 只各买一手")
    p.add_argument("--quantity", type=int, default=100, help="股数，须为 100 整数倍")
    p.add_argument(
        "--reset",
        action="store_true",
        help="开始前清空纸账户（开发/自测；生产勿用）",
    )
    p.add_argument(
        "--skip-sell-probe",
        action="store_true",
        help="不尝试 T+1 卖出拒单探测",
    )
    p.add_argument(
        "--code",
        default="",
        help="仅操作该 code（仍须在池内）；与 --sample 互斥优先",
    )
    args = p.parse_args()

    if args.quantity < 100 or args.quantity % 100 != 0:
        print("--quantity 须 >=100 且为 100 整数倍", file=sys.stderr)
        return 1

    if not args.pool.is_file():
        print(f"池文件不存在: {args.pool}", file=sys.stderr)
        return 1

    codes_ordered, pool_set = _load_pool_set(args.pool)
    if not codes_ordered:
        print("股票池为空", file=sys.stderr)
        return 1

    if args.code.strip():
        c = args.code.strip().lower()
        if c not in pool_set:
            print(f"[FAIL] {c} 不在趋势 v0 池内，拒绝请求（束 E1 门控）", file=sys.stderr)
            return 1
        targets = [c]
    else:
        targets = codes_ordered[: max(1, args.sample)]

    base = args.base_url.rstrip("/")
    orders_url = f"{base}/api/paper/orders"
    state_url = f"{base}/api/paper/state"
    reset_url = f"{base}/api/paper/account/reset"

    try:
        with httpx.Client(timeout=60.0) as client:
            if args.reset:
                r0 = client.post(reset_url)
                if r0.status_code != 200:
                    print(f"[FAIL] reset HTTP {r0.status_code} {r0.text[:200]!r}")
                    return 1
                print(f"  reset: {r0.json()}")

            rs = client.get(state_url)
            if rs.status_code != 200:
                print(f"[FAIL] state HTTP {rs.status_code}")
                return 1
            st = rs.json()
            cash = (st.get("account") or {}).get("cash")
            print(f"  state: cash={cash}")

            first_bought: str | None = None
            for code in targets:
                rb = client.post(orders_url, json={"code": code, "side": "buy", "quantity": args.quantity})
                if rb.status_code != 200:
                    print(f"[FAIL] buy {code} HTTP {rb.status_code} {rb.text[:300]!r}")
                    return 1
                j = rb.json()
                print(
                    f"  buy OK {code} fill_price={j.get('fill_price')} "
                    f"trade_date={j.get('trade_date')} cash_after={j.get('cash_after')}"
                )
                if first_bought is None:
                    first_bought = code

            if not args.skip_sell_probe and first_bought:
                rsell = client.post(
                    orders_url,
                    json={"code": first_bought, "side": "sell", "quantity": args.quantity},
                )
                if rsell.status_code == 400:
                    detail: object = rsell.text
                    try:
                        if "application/json" in (rsell.headers.get("content-type") or ""):
                            detail = rsell.json().get("detail", rsell.text)
                    except Exception:
                        pass
                    print(f"  sell probe (expected 400 T+1): {detail!r}")
                else:
                    print(
                        f"[WARN] sell probe expected HTTP 400, got {rsell.status_code} {rsell.text[:200]!r}"
                    )

            ro = client.get(orders_url, params={"limit": 10, "offset": 0})
            if ro.status_code != 200:
                print(f"[FAIL] list orders HTTP {ro.status_code}")
                return 1
            oj = ro.json()
            print(f"  orders total={oj.get('total')} recent={len(oj.get('items') or [])}")

    except httpx.ConnectError as e:
        print(f"无法连接 {base}: {e}", file=sys.stderr)
        return 1

    print("[OK] trend_v0_paper_smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
