#!/usr/bin/env python3
"""
对趋势 v0 股票池抽样调用 GET /api/factors/preview，走通 2 个价量趋势相关算子（与 FACTORS.md 一致）。

默认组合（v0 最小验收）：
  - roc + window=12 + close：N 期简单收益 %（动量）
  - obv + close：能量潮（价 + 量，无 window）

需本机已启动 API（默认 http://127.0.0.1:8000）。对应 backlog 束 C2。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

project_root = Path(__file__).resolve().parent.parent

# (op, query_params)；obv 不传 window（累计能量，见 FACTORS.md）
_DEFAULT_CHECKS: tuple[tuple[str, dict[str, object]], ...] = (
    ("roc", {"column": "close", "window": 12}),
    ("obv", {"column": "close"}),
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


def _validate_preview(data: dict[str, object], op: str) -> str | None:
    req_top = ("code", "op", "bars", "trade_dates", "series")
    for k in req_top:
        if k not in data:
            return f"missing key {k!r}"
    bars = data["bars"]
    dates = data["trade_dates"]
    series = data["series"]
    if not isinstance(bars, int) or not isinstance(dates, list) or not isinstance(series, dict):
        return "bars/trade_dates/series type mismatch"
    if bars != len(dates):
        return f"bars={bars} != len(trade_dates)={len(dates)}"
    if op in ("roc", "obv", "atr", "cci", "williams_r", "mfi", "trix"):
        vals = series.get("value")
        if not isinstance(vals, list) or len(vals) != bars:
            return f'series["value"] length != bars for op={op!r}'
    elif op == "macd":
        for k in ("dif", "dea", "hist"):
            v = series.get(k)
            if not isinstance(v, list) or len(v) != bars:
                return f'series[{k!r}] invalid for macd'
    else:
        if not series:
            return "empty series"
    return None


def main() -> int:
    p = argparse.ArgumentParser(description="抽样验证 factors/preview（趋势 v0 C2）")
    p.add_argument("--base-url", default="http://127.0.0.1:8000", help="API 根地址（无尾斜杠）")
    p.add_argument(
        "--pool",
        type=Path,
        default=project_root / "config" / "trend_v0_pool.txt",
        help="股票池文件路径",
    )
    p.add_argument("--sample", type=int, default=3, metavar="N", help="最多检查池内前 N 只")
    p.add_argument("--limit", type=int, default=500, help="preview limit（须 ≥30）")
    args = p.parse_args()

    if not args.pool.is_file():
        print(f"股票池文件不存在: {args.pool}", file=sys.stderr)
        return 1

    codes = _load_codes(args.pool)[: max(0, args.sample)]
    if not codes:
        print("股票池为空", file=sys.stderr)
        return 1

    base = args.base_url.rstrip("/")
    url = f"{base}/api/factors/preview"

    try:
        with httpx.Client(timeout=60.0) as client:
            for code in codes:
                for op, extra in _DEFAULT_CHECKS:
                    params: dict[str, object] = {"code": code, "op": op, "limit": args.limit, **extra}
                    r = client.get(url, params=params)
                    if r.status_code != 200:
                        print(f"FAIL {code} {op} HTTP {r.status_code} {r.text[:240]!r}")
                        return 1
                    try:
                        data = r.json()
                    except Exception as e:
                        print(f"FAIL {code} {op} JSON: {e}")
                        return 1
                    err = _validate_preview(data, op)
                    if err:
                        print(f"FAIL {code} {op}: {err}")
                        return 1
                    bars = data["bars"]
                    print(f"OK {code} op={op} bars={bars} response_op={data.get('op')}")
    except httpx.ConnectError as e:
        print(f"无法连接 {base}: {e}", file=sys.stderr)
        return 1

    total = len(codes) * len(_DEFAULT_CHECKS)
    print(f"done: {total} requests ({len(codes)} codes x {len(_DEFAULT_CHECKS)} ops)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
