#!/usr/bin/env python3
"""
一键把数据写入当前配置的数据库，让 Vue 看板有内容可展示。

拉数策略（建议）:
  · quick / standard / full — 首次或要大范围补历史时用（全窗口日K，耗时长）。
  · daily — 日常定时用：刷新股票列表 + 指数/个股按库中最新交易日增量补数（省流量、省时间）。

**交易日历**：非 ``--skip-calendar`` 时，在首刷（quick/standard/full）末尾执行 ``fetch_data.py --mode calendar --source baostock``；
``daily`` 则在同一条命令上加 ``--with-calendar``（仅 Baostock 会写库，其它数据源由 fetch_data 打日志跳过）。不需要日历或无外网时用 ``--skip-calendar``。

必须在项目根目录配置好 .env，并由你在本机执行。

用法（在项目根目录）:
  python scripts/feed_dashboard.py
  python scripts/feed_dashboard.py --profile quick
  python scripts/feed_dashboard.py --profile daily --skip-init
  python scripts/feed_dashboard.py --profile full --source baostock
  python scripts/feed_dashboard.py --skip-calendar
  python scripts/feed_dashboard.py --dry-run
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent


def _print_db_target() -> None:
    sys.path.insert(0, str(project_root))
    from src.common.config import describe_database_write_target

    print(f"  数据写入目标: {describe_database_write_target()}")


def run_step(description: str, argv: list[str], dry_run: bool) -> float:
    """执行一步子进程；dry-run 返回 0；否则返回 wall-clock 耗时（秒）。"""
    print(f"\n>>> {description}")
    print(f"    {' '.join(argv)}")
    if dry_run:
        return 0.0
    t0 = time.perf_counter()
    r = subprocess.run(argv, cwd=str(project_root))
    elapsed = time.perf_counter() - t0
    if r.returncode != 0:
        print(f"    (失败，已运行 {elapsed:.1f}s，exit {r.returncode})")
        raise SystemExit(r.returncode)
    print(f"    (本步耗时 {elapsed:.1f}s)")
    return elapsed


def main() -> None:
    parser = argparse.ArgumentParser(description="建表 + 拉数，喂饱看板")
    parser.add_argument(
        "--profile",
        choices=("quick", "standard", "full", "daily"),
        default="standard",
        help="quick/standard/full=首刷或补历史; daily=日常增量(适合计划任务)",
    )
    parser.add_argument(
        "--skip-init",
        action="store_true",
        help="跳过建表（表已存在时用）",
    )
    parser.add_argument(
        "--source",
        default=None,
        help="覆盖 .env 的 DATA_SOURCE，如 baostock / mock",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印将执行的命令，不真正运行",
    )
    parser.add_argument(
        "--skip-calendar",
        action="store_true",
        help="跳过 trade_calendar 灌数（不跑 calendar 模式，也不在 daily 上加 --with-calendar）",
    )
    args = parser.parse_args()

    py = sys.executable
    base = [py, str(project_root / "scripts" / "fetch_data.py")]
    if args.source:
        base += ["--source", args.source]

    if args.profile == "quick":
        k_days, k_limit, index_days = 30, 50, 240
    elif args.profile == "standard":
        k_days, k_limit, index_days = 90, 120, 730
    elif args.profile == "daily":
        k_days, k_limit, index_days = 90, 0, 730
    else:
        k_days, k_limit, index_days = 365, 0, 730

    print("Trading Buddy — 看板喂数")
    print(f"  项目根目录: {project_root}")
    if args.profile == "daily":
        print(
            f"  profile=daily  日常增量（--mode daily，新代码回退窗口 {k_days} 天，指数首刷最多 {index_days} 天）"
        )
    else:
        print(f"  profile={args.profile}  klines: days={k_days}, limit={k_limit or '无限制'}")
    if not args.dry_run:
        _print_db_target()
    print("  请确认已配置 .env 且能访问数据库与数据源（baostock 需外网）。")

    step_seconds: list[float] = []

    if not args.skip_init:
        step_seconds.append(
            run_step(
                "初始化表结构",
                [py, str(project_root / "scripts" / "init_db.py")],
                args.dry_run,
            )
        )

    if args.profile == "daily":
        daily_argv = base + [
            "--mode",
            "daily",
            "--days",
            str(k_days),
            "--index-days",
            str(index_days),
            "--overlap-days",
            "7",
        ]
        if not args.skip_calendar:
            daily_argv.append("--with-calendar")
        step_seconds.append(
            run_step("日常增量拉数（股票表+指数+全市场日K）", daily_argv, args.dry_run)
        )
    else:
        step_seconds.append(run_step("拉取股票列表", base + ["--mode", "stocks"], args.dry_run))
        step_seconds.append(
            run_step(
                "拉取主要指数K线",
                base + ["--mode", "indices", "--index-days", str(index_days)],
                args.dry_run,
            )
        )
        k_argv = base + ["--mode", "klines", "--days", str(k_days)]
        if k_limit > 0:
            k_argv += ["--limit", str(k_limit)]
        step_seconds.append(run_step("拉取股票日K（样本）", k_argv, args.dry_run))
        if not args.skip_calendar:
            step_seconds.append(
                run_step(
                    "灌交易日历 trade_calendar（Baostock）",
                    [
                        py,
                        str(project_root / "scripts" / "fetch_data.py"),
                        "--mode",
                        "calendar",
                        "--source",
                        "baostock",
                    ],
                    args.dry_run,
                )
            )

    if args.dry_run:
        print("\n(dry-run 结束，未执行任何命令)")
    else:
        total_s = sum(step_seconds)
        print(f"\n喂数各步合计 wall-clock 约 {total_s:.1f}s（不含本脚本自身开销）。")
        print("完成。请保持 API 与 Vue dev 运行，刷新看板即可。")


if __name__ == "__main__":
    main()
