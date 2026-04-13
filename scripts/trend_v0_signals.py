#!/usr/bin/env python3
"""
对趋势 v0 股票池抽样调用 GET /api/backtest/ma-cross/signal，验证 HTTP 与 JSON 形状。

需本机已启动 API（默认 http://127.0.0.1:8000）。对应 backlog 束 C1。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

project_root = Path(__file__).resolve().parent.parent


def _load_codes(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        out.append(s.lower())
    return list(dict.fromkeys(out))


def main() -> int:
    p = argparse.ArgumentParser(description="抽样验证 ma-cross/signal 与池文件")
    p.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="API 根地址（无尾斜杠）",
    )
    p.add_argument(
        "--pool",
        type=Path,
        default=project_root / "config" / "trend_v0_pool.txt",
        help="股票池文件路径",
    )
    p.add_argument(
        "--sample",
        type=int,
        default=5,
        metavar="N",
        help="最多检查池内前 N 只（按文件顺序去重后）",
    )
    p.add_argument("--fast", type=int, default=5)
    p.add_argument("--slow", type=int, default=20)
    p.add_argument("--limit", type=int, default=500)
    args = p.parse_args()

    if not args.pool.is_file():
        print(f"股票池文件不存在: {args.pool}", file=sys.stderr)
        return 1

    codes = _load_codes(args.pool)[: max(0, args.sample)]
    if not codes:
        print("股票池为空", file=sys.stderr)
        return 1

    base = args.base_url.rstrip("/")
    url = f"{base}/api/backtest/ma-cross/signal"
    required = ("code", "position", "bars_used", "as_of_date", "ma_fast", "ma_slow")

    ok = 0
    with httpx.Client(timeout=30.0) as client:
        for code in codes:
            r = client.get(
                url,
                params={
                    "code": code,
                    "fast": args.fast,
                    "slow": args.slow,
                    "limit": args.limit,
                },
            )
            if r.status_code != 200:
                print(f"FAIL {code} HTTP {r.status_code} {r.text[:200]!r}")
                return 1
            try:
                data = r.json()
            except Exception as e:
                print(f"FAIL {code} invalid JSON: {e}")
                return 1
            missing = [k for k in required if k not in data]
            if missing:
                print(f"FAIL {code} missing keys: {missing}")
                return 1
            print(f"OK {code} position={data['position']} bars_used={data['bars_used']} as_of={data['as_of_date']}")
            ok += 1

    print(f"done: {ok}/{len(codes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
