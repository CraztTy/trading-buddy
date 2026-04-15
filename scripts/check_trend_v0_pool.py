#!/usr/bin/env python3
"""
检查 config/trend_v0_pool.txt（或自定义路径）中各 code 在库内是否有日 K。

用于趋势 v0 束 B 前置；需已配置 .env 且已灌数。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.common import describe_database_write_target
from src.data.storage import KlineRepository, dispose_database, get_database


def _load_codes(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        out.append(s.lower())
    return list(dict.fromkeys(out))


async def main() -> None:
    p = argparse.ArgumentParser(description="检查趋势 v0 股票池日 K 是否存在")
    p.add_argument(
        "--pool",
        type=Path,
        default=project_root / "config" / "trend_v0_pool.txt",
        help="股票池文件路径（一行一 code）",
    )
    p.add_argument(
        "--min-bars",
        type=int,
        default=1,
        help="至少要有多少根日 K 才算通过（默认 1）",
    )
    p.add_argument(
        "--adjust-flag",
        type=str,
        default="3",
        help="复权类型: 1=后复权 2=前复权 3=不复权（默认 3）",
    )
    p.add_argument(
        "--check-pct",
        action="store_true",
        help="检查 change_pct 缺失比例",
    )
    p.add_argument(
        "--max-age-days",
        type=int,
        default=None,
        help="最新日 K 距今天数上限（超过则告警；用于识别长期停牌/缺数据）",
    )
    args = p.parse_args()

    if not args.pool.is_file():
        raise SystemExit(f"股票池文件不存在: {args.pool}")

    codes = _load_codes(args.pool)
    if not codes:
        raise SystemExit("股票池为空（仅注释或无有效行）")

    from datetime import date

    today = date.today()
    print(f"数据目标: {describe_database_write_target()}")
    print(f"池文件: {args.pool}（共 {len(codes)} 只）")
    print(f"复权档: {args.adjust_flag}  检查日: {today}\n")

    db = get_database()
    ok = 0
    bad: list[tuple[str, str]] = []
    pct_missing: list[tuple[str, float]] = []
    stale: list[tuple[str, int]] = []
    try:
        async with db.session() as session:
            repo = KlineRepository(session)
            for code in codes:
                rows = await repo.get_daily(
                    code=code, limit=max(args.min_bars, 1), adjust_flag=args.adjust_flag
                )
                if len(rows) < args.min_bars:
                    bad.append(
                        (code, f"仅有 {len(rows)} 根，需要 >= {args.min_bars}")
                    )
                    continue

                latest = rows[-1]
                age = (today - latest.trade_date).days
                if args.max_age_days is not None and age > args.max_age_days:
                    stale.append((code, age))

                if args.check_pct:
                    missing = sum(1 for r in rows if r.pct_change is None)
                    ratio = missing / len(rows)
                    if ratio > 0:
                        pct_missing.append((code, ratio))

                ok += 1
                pct_s = f"{latest.pct_change:.2f}%" if latest.pct_change is not None else "null"
                stale_tag = f"  [stale {age}d]" if (args.max_age_days is not None and age > args.max_age_days) else ""
                print(f"  OK  {code}  最新 {latest.trade_date}  close={latest.close}  pct={pct_s}{stale_tag}")
    finally:
        await dispose_database()

    print()
    if bad:
        print("缺失或不足的代码:")
        for code, msg in bad:
            print(f"  !!  {code}  {msg}")

    if stale:
        print(f"\n最新 K 线超过 {args.max_age_days} 天的代码:")
        for code, age in stale:
            print(f"  !!  {code}  距今 {age} 天")

    if pct_missing:
        print("\nchange_pct 存在缺失的代码:")
        for code, ratio in pct_missing:
            print(f"  !!  {code}  缺失比例 {ratio*100:.1f}%")

    if bad:
        raise SystemExit(1)

    print(f"\n全部通过: {ok}/{len(codes)}")
    if stale:
        print(f"但有 {len(stale)} 只最新 K 线较旧（可能停牌或缺数据）")
    if pct_missing:
        print(f"有 {len(pct_missing)} 只存在 change_pct 缺失")
    return


if __name__ == "__main__":
    asyncio.run(main())
