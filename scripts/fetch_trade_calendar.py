#!/usr/bin/env python3
"""
将 Baostock `query_trade_dates` 写入 `trade_calendar` 表（幂等 upsert）。

依赖项目根 `.env` 数据库配置；仅使用 Baostock 同步接口（在 asyncio.to_thread 中执行）。

用法（项目根）:
  python scripts/fetch_trade_calendar.py --start 2020-01-01 --end 2025-12-31
  python scripts/fetch_trade_calendar.py --start 2024-01-01 --end 2024-12-31 --exchange cn --chunk-days 120
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


async def _run(
    start: date,
    end: date,
    exchange: str,
    chunk_days: int,
) -> None:
    from src.common import describe_database_write_target, get_logger
    from src.data.ingest import ingest_trade_calendar_from_baostock
    from src.data.storage import dispose_database

    log = get_logger("fetch_trade_calendar")
    log.info(f"写入目标: {describe_database_write_target()} exchange={exchange}")
    if start > end:
        raise SystemExit("start 不能晚于 end")

    try:
        await ingest_trade_calendar_from_baostock(
            start=start,
            end=end,
            exchange=exchange,
            chunk_days=chunk_days,
        )
    finally:
        await dispose_database()


def main() -> None:
    p = argparse.ArgumentParser(description="Baostock 交易日历 → trade_calendar")
    p.add_argument("--start", required=True, help="起始日 YYYY-MM-DD（含）")
    p.add_argument("--end", required=True, help="结束日 YYYY-MM-DD（含）")
    p.add_argument(
        "--exchange",
        default="cn",
        help="日历分区键，默认 cn（沪深北统一 Baostock 口径）",
    )
    p.add_argument(
        "--chunk-days",
        type=int,
        default=400,
        help="单次 query_trade_dates 覆盖的自然日跨度，避免单次过大",
    )
    args = p.parse_args()
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    asyncio.run(_run(start, end, args.exchange.strip().lower(), args.chunk_days))


if __name__ == "__main__":
    main()
