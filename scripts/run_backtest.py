#!/usr/bin/env python3
"""
日线双均线最小回测（读当前 .env 配置的数据库）。

用法（项目根目录）:
  python scripts/run_backtest.py --code sh.000001
  python scripts/run_backtest.py --code sh.600519 --fast 10 --slow 60 --limit 800
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent


async def _async_main(code: str, fast: int, slow: int, limit: int) -> int:
    sys.path.insert(0, str(project_root))
    from src.backtest import run_ma_cross_backtest
    from src.common.config import describe_database_write_target
    from src.data.storage import KlineRepository, dispose_database, get_database

    print(f"数据读取目标: {describe_database_write_target()}")
    db = get_database()
    try:
        async with db.session() as session:
            repo = KlineRepository(session)
            klines = await repo.get_daily(code=code, limit=limit)
    finally:
        await dispose_database()

    if len(klines) < slow + 1:
        print(f"错误: K 线不足（需要 >= {slow + 1}），当前 {len(klines)}", file=sys.stderr)
        return 2

    res, curve = run_ma_cross_backtest(klines, fast=fast, slow=slow)
    out = res.to_api_dict()
    out["equity_curve"] = curve
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="双均线日线最小回测")
    p.add_argument("--code", required=True, help="标的代码，如 sh.000001")
    p.add_argument("--fast", type=int, default=5, help="快线周期")
    p.add_argument("--slow", type=int, default=20, help="慢线周期")
    p.add_argument("--limit", type=int, default=500, help="使用最近多少根日 K")
    args = p.parse_args()
    if args.fast >= args.slow:
        print("错误: fast 必须小于 slow", file=sys.stderr)
        return 2
    return asyncio.run(_async_main(args.code, args.fast, args.slow, args.limit))


if __name__ == "__main__":
    raise SystemExit(main())
