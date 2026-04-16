#!/usr/bin/env python3
"""
MVP 占位脚本：向 stock_sector / policy_event 灌入示例板块和政策数据，
支持从 CSV/JSON 导入，也可直接运行生成内置示例。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(project_root))

from src.common import get_logger
from src.data.storage import get_database, SectorRepository, PolicyRepository
from src.data.storage.models import StockSectorModel, PolicyEventModel

logger = get_logger("seed_sectors_policies")


# 内置示例：热门板块（仅示例，无真实成分股映射）
BUILTIN_SECTORS = {
    "AI": ["sh.603019", "sz.002230", "sz.300418"],
    "新能源": ["sz.002594", "sh.600519", "sh.601012"],
    "半导体": ["sh.688981", "sh.603501", "sz.300782"],
}

# 内置示例：政策事件
BUILTIN_POLICIES = [
    {
        "sector_code": "AI",
        "title": "国家人工智能产业发展规划发布",
        "source": "国务院",
        "event_date": "2026-04-01",
    },
    {
        "sector_code": "新能源",
        "title": "新能源汽车购置税减免延续至2027年",
        "source": "工信部",
        "event_date": "2026-04-05",
    },
]


async def seed_builtin() -> None:
    db = get_database()
    async with db.session() as session:
        # 板块关联
        total_sectors = 0
        for sector_code, stock_codes in BUILTIN_SECTORS.items():
            for stock_code in stock_codes:
                session.add(
                    StockSectorModel(
                        stock_code=stock_code,
                        sector_code=sector_code,
                    )
                )
                total_sectors += 1

        # 政策事件
        total_policies = 0
        for p in BUILTIN_POLICIES:
            from datetime import date
            session.add(
                PolicyEventModel(
                    sector_code=p.get("sector_code"),
                    title=p["title"],
                    source=p.get("source"),
                    event_date=date.fromisoformat(p["event_date"]) if p.get("event_date") else None,
                )
            )
            total_policies += 1

        await session.commit()
    logger.info(f"内置示例灌入完成: stock_sector={total_sectors}, policy_event={total_policies}")


async def seed_from_json(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    db = get_database()
    async with db.session() as session:
        total_sectors = 0
        for item in data.get("stock_sectors", []):
            session.add(
                StockSectorModel(
                    stock_code=item["stock_code"],
                    sector_code=item["sector_code"],
                )
            )
            total_sectors += 1

        total_policies = 0
        from datetime import date
        for item in data.get("policy_events", []):
            session.add(
                PolicyEventModel(
                    sector_code=item.get("sector_code"),
                    title=item["title"],
                    source=item.get("source"),
                    event_date=date.fromisoformat(item["event_date"]) if item.get("event_date") else None,
                )
            )
            total_policies += 1

        await session.commit()
    logger.info(f"JSON 导入完成: stock_sector={total_sectors}, policy_event={total_policies}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="灌入板块成分股与政策事件示例数据")
    p.add_argument("--json", type=Path, default=None, help="从 JSON 文件导入（含 stock_sectors / policy_events）")
    p.add_argument("--builtin", action="store_true", help="灌入内置示例数据")
    return p


async def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.json:
        if not args.json.exists():
            raise SystemExit(f"文件不存在: {args.json}")
        await seed_from_json(args.json)
    else:
        await seed_builtin()


if __name__ == "__main__":
    asyncio.run(main())
