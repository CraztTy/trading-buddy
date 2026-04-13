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
    args = p.parse_args()

    if not args.pool.is_file():
        raise SystemExit(f"股票池文件不存在: {args.pool}")

    codes = _load_codes(args.pool)
    if not codes:
        raise SystemExit("股票池为空（仅注释或无有效行）")

    print(f"数据目标: {describe_database_write_target()}")
    print(f"池文件: {args.pool}（共 {len(codes)} 只）\n")

    db = get_database()
    ok = 0
    bad: list[tuple[str, str]] = []
    try:
        async with db.session() as session:
            repo = KlineRepository(session)
            for code in codes:
                rows = await repo.get_daily(code=code, limit=max(args.min_bars, 1))
                if len(rows) < args.min_bars:
                    bad.append(
                        (code, f"仅有 {len(rows)} 根，需要 >= {args.min_bars}")
                    )
                else:
                    ok += 1
                    latest = rows[-1]
                    pct = latest.pct_change
                    pct_s = f"{pct:.2f}%" if pct is not None else "null"
                    print(f"  OK  {code}  最新 {latest.trade_date}  close={latest.close}  pct={pct_s}")
    finally:
        await dispose_database()

    print()
    if bad:
        print("缺失或不足的代码:")
        for code, msg in bad:
            print(f"  !!  {code}  {msg}")
        raise SystemExit(1)

    print(f"全部通过: {ok}/{len(codes)}")
    return


if __name__ == "__main__":
    asyncio.run(main())
