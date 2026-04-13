#!/usr/bin/env python3
"""
日线最小回测（读当前 .env 配置的数据库）：双均线（默认）或买入持有（``--buy-hold``）。

用法（项目根目录）:
  python scripts/run_backtest.py --code sh.000001
  python scripts/run_backtest.py --code sh.600519 --fast 10 --slow 60 --limit 800
  python scripts/run_backtest.py --code sh.600519 --buy-hold --limit 500 -o bh.json
  python scripts/run_backtest.py --code sh.600519 --buy-hold --start-date 2023-01-01 --end-date 2024-06-30 --limit 500
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
_root_s = str(project_root)
if _root_s not in sys.path:
    sys.path.insert(0, _root_s)

from src.common.cli_iso_date import (  # noqa: E402
    check_cli_date_order,
    parse_cli_iso_date,
)


async def _async_main_ma_cross(
    code: str,
    fast: int,
    slow: int,
    limit: int,
    start_date: date | None,
    end_date: date | None,
    commission_rate: float,
    slippage_rate: float,
    benchmark_code: str | None,
    output_path: Path | None,
) -> int:
    sys.path.insert(0, str(project_root))
    from src.backtest import run_ma_cross_backtest
    from src.common.config import describe_database_write_target
    from src.data.storage import KlineRepository, dispose_database, get_database

    print(f"数据读取目标: {describe_database_write_target()}", file=sys.stderr)
    bench_norm = (benchmark_code or "").strip().lower() or None
    db = get_database()
    try:
        async with db.session() as session:
            repo = KlineRepository(session)
            klines = await repo.get_daily(
                code=code,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
            )
            bench_klines = None
            if bench_norm:
                bench_klines = await repo.get_daily(
                    code=bench_norm,
                    start_date=start_date,
                    end_date=end_date,
                    limit=limit,
                )
                if not bench_klines:
                    print(f"错误: 基准 {bench_norm} 无可用日 K", file=sys.stderr)
                    return 2
    finally:
        await dispose_database()

    if len(klines) < slow + 1:
        print(f"错误: K 线不足（需要 >= {slow + 1}），当前 {len(klines)}", file=sys.stderr)
        return 2

    res, curve = run_ma_cross_backtest(
        klines,
        fast=fast,
        slow=slow,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        benchmark_klines=bench_klines,
    )
    out = res.to_api_dict()
    out["equity_curve"] = curve
    text = json.dumps(out, ensure_ascii=False, indent=2)
    if output_path:
        output_path.write_text(text, encoding="utf-8")
        print(f"已写入 {output_path.resolve()}", file=sys.stderr)
    else:
        print(text)
    return 0


async def _async_main_buy_hold(
    code: str,
    limit: int,
    start_date: date | None,
    end_date: date | None,
    commission_rate: float,
    slippage_rate: float,
    benchmark_code: str | None,
    output_path: Path | None,
) -> int:
    sys.path.insert(0, str(project_root))
    from src.backtest.buy_hold import run_buy_hold_backtest
    from src.common.config import describe_database_write_target
    from src.data.storage import KlineRepository, dispose_database, get_database

    print(f"数据读取目标: {describe_database_write_target()}", file=sys.stderr)
    bench_norm = (benchmark_code or "").strip().lower() or None
    db = get_database()
    try:
        async with db.session() as session:
            repo = KlineRepository(session)
            klines = await repo.get_daily(
                code=code.strip().lower(),
                start_date=start_date,
                end_date=end_date,
                limit=limit,
            )
            bench_klines = None
            if bench_norm:
                bench_klines = await repo.get_daily(
                    code=bench_norm,
                    start_date=start_date,
                    end_date=end_date,
                    limit=limit,
                )
                if not bench_klines:
                    print(f"错误: 基准 {bench_norm} 无可用日 K", file=sys.stderr)
                    return 2
    finally:
        await dispose_database()

    if len(klines) < 2:
        print(f"错误: K 线不足（买入持有至少需要 2 根），当前 {len(klines)}", file=sys.stderr)
        return 2

    res, curve = run_buy_hold_backtest(
        klines,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        include_equity_curve=True,
        benchmark_klines=bench_klines,
    )
    out = res.to_api_dict()
    out["equity_curve"] = curve
    text = json.dumps(out, ensure_ascii=False, indent=2)
    if output_path:
        output_path.write_text(text, encoding="utf-8")
        print(f"已写入 {output_path.resolve()}", file=sys.stderr)
    else:
        print(text)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="日线最小回测（双均线或买入持有）")
    p.add_argument("--code", required=True, help="标的代码，如 sh.000001")
    p.add_argument(
        "--buy-hold",
        action="store_true",
        help="买入持有（忽略 --fast / --slow；与 API strategy_id=buy_hold 同核）",
    )
    p.add_argument("--fast", type=int, default=5, help="快线周期（仅双均线）")
    p.add_argument("--slow", type=int, default=20, help="慢线周期（仅双均线）")
    p.add_argument("--limit", type=int, default=500, help="使用最近多少根日 K（与日期区间组合时先区间再 limit）")
    p.add_argument(
        "--start-date",
        type=str,
        default=None,
        metavar="YYYY-MM-DD",
        help="可选，含端点；与 GET/POST 回测 params.start_date 一致",
    )
    p.add_argument(
        "--end-date",
        type=str,
        default=None,
        metavar="YYYY-MM-DD",
        help="可选，含端点；与 GET/POST 回测 params.end_date 一致",
    )
    p.add_argument(
        "--commission-rate",
        type=float,
        default=0.0,
        help="单边手续费率，如万1.5为 0.00015（每次调仓翻转扣一次）",
    )
    p.add_argument(
        "--slippage-rate",
        type=float,
        default=0.0,
        help="滑点率（与手续费同口径，调仓日扣减）；与 commission-rate 之和勿超过 0.08",
    )
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="将完整 JSON（含 equity_curve）写入文件；省略则打印到 stdout",
    )
    p.add_argument(
        "--benchmark-code",
        type=str,
        default=None,
        help="可选，β/α 对基准日收益回归，如 sh.000300",
    )
    args = p.parse_args()
    try:
        start_d = parse_cli_iso_date("--start-date", args.start_date)
        end_d = parse_cli_iso_date("--end-date", args.end_date)
    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 2
    bad_order = check_cli_date_order(start_d, end_d)
    if bad_order:
        print(f"错误: {bad_order}", file=sys.stderr)
        return 2
    if args.commission_rate + args.slippage_rate > 0.08:
        print("错误: commission-rate 与 slippage-rate 之和勿超过 0.08", file=sys.stderr)
        return 2
    if args.buy_hold:
        return asyncio.run(
            _async_main_buy_hold(
                args.code,
                args.limit,
                start_d,
                end_d,
                args.commission_rate,
                args.slippage_rate,
                args.benchmark_code,
                args.output,
            )
        )
    if args.fast >= args.slow:
        print("错误: fast 必须小于 slow", file=sys.stderr)
        return 2
    return asyncio.run(
        _async_main_ma_cross(
            args.code,
            args.fast,
            args.slow,
            args.limit,
            start_d,
            end_d,
            args.commission_rate,
            args.slippage_rate,
            args.benchmark_code,
            args.output,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
