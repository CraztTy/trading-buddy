#!/usr/bin/env python3
"""
批量双均线扫描，输出 CSV（UTF-8 BOM）到 stdout 或文件。

用法（项目根目录，需已配置 .env）:
  python scripts/scan_backtest.py --codes "sh.000001,sh.000300"
  python scripts/scan_backtest.py --codes-file codes.txt -o scan.csv

codes.txt 支持每行一个代码，或逗号分隔。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent


async def _async_main(
    codes_raw: str,
    fast: int,
    slow: int,
    limit: int,
    commission_rate: float,
    slippage_rate: float,
    max_codes: int,
    out_path: Path | None,
) -> int:
    sys.path.insert(0, str(project_root))
    from src.backtest.scan import ma_cross_scan_csv_bytes, ma_cross_scan_items, parse_scan_codes
    from src.common.config import describe_database_write_target
    from src.data.storage import dispose_database, get_database

    print(f"数据读取目标: {describe_database_write_target()}", file=sys.stderr)
    parsed = parse_scan_codes(codes_raw, max_codes)
    if not parsed:
        print("错误: 无有效代码", file=sys.stderr)
        return 2

    db = get_database()
    try:
        async with db.session() as session:
            items = await ma_cross_scan_items(
                session,
                parsed,
                fast=fast,
                slow=slow,
                limit=limit,
                start_date=None,
                end_date=None,
                commission_rate=commission_rate,
                slippage_rate=slippage_rate,
            )
    finally:
        await dispose_database()

    blob = ma_cross_scan_csv_bytes(
        items,
        fast=fast,
        slow=slow,
        limit=limit,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
    )
    if out_path:
        out_path.write_bytes(blob)
        print(f"已写入 {out_path.resolve()}", file=sys.stderr)
    else:
        sys.stdout.buffer.write(blob)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="双均线批量扫描 → CSV")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--codes", type=str, help="逗号或换行分隔的代码串")
    g.add_argument("--codes-file", type=Path, help="从文件读取代码（多行或逗号）")
    p.add_argument("--fast", type=int, default=5)
    p.add_argument("--slow", type=int, default=20)
    p.add_argument("--limit", type=int, default=500)
    p.add_argument("--commission-rate", type=float, default=0.0)
    p.add_argument("--slippage-rate", type=float, default=0.0)
    p.add_argument("--max-codes", type=int, default=25)
    p.add_argument("-o", "--output", type=Path, default=None, help="输出文件；省略则打印到 stdout")
    args = p.parse_args()

    if args.fast >= args.slow:
        print("错误: fast 必须小于 slow", file=sys.stderr)
        return 2
    if args.commission_rate + args.slippage_rate > 0.08:
        print("错误: commission-rate 与 slippage-rate 之和勿超过 0.08", file=sys.stderr)
        return 2

    if args.codes_file:
        raw = args.codes_file.read_text(encoding="utf-8")
    else:
        raw = args.codes or ""

    return asyncio.run(
        _async_main(
            raw,
            args.fast,
            args.slow,
            args.limit,
            args.commission_rate,
            args.slippage_rate,
            args.max_codes,
            args.output,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
