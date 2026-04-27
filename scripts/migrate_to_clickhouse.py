"""数据迁移脚本：从 SQLite/MySQL 导入日K线到 ClickHouse。

用法:
    python scripts/migrate_to_clickhouse.py --codes sh.600000,sz.000001
    python scripts/migrate_to_clickhouse.py --all  # 全量迁移

环境变量:
    CLICKHOUSE_ENABLED=true
    CLICKHOUSE_HOST=localhost
    CLICKHOUSE_PORT=8123
    CLICKHOUSE_USER=default
    CLICKHOUSE_PASSWORD=
    CLICKHOUSE_DATABASE=trading
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date

from sqlalchemy import select

# 添加项目根目录到路径
sys.path.insert(0, str(__file__).replace("\\", "/").rsplit("/scripts/", 1)[0])

from src.common.config import get_settings
from src.data.clickhouse.client import get_ch_client
from src.data.clickhouse.repository import ClickHouseRepository
from src.data.clickhouse.schema import ALL_TABLES
from src.data.models import KLine
from src.data.storage import get_database
from src.data.storage.models import DailyKlineModel


def parse_args():
    parser = argparse.ArgumentParser(description="Migrate K-line data to ClickHouse")
    parser.add_argument("--codes", type=str, help="Comma-separated stock codes")
    parser.add_argument("--all", action="store_true", help="Migrate all codes")
    parser.add_argument("--batch", type=int, default=5000, help="Batch size")
    parser.add_argument("--create-tables", action="store_true", help="Create tables first")
    return parser.parse_args()


async def migrate_code(repo: ClickHouseRepository, code: str, batch_size: int) -> int:
    """迁移单个标的的日K线数据。"""
    db = get_database()
    total = 0

    async with db.session() as session:
        stmt = (
            select(DailyKlineModel)
            .where(DailyKlineModel.code == code)
            .order_by(DailyKlineModel.trade_date.asc())
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()

        if not rows:
            print(f"  {code}: no data")
            return 0

        # 分批插入
        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            klines = [
                KLine(
                    code=r.code,
                    trade_date=r.trade_date,
                    open=float(r.open),
                    high=float(r.high),
                    low=float(r.low),
                    close=float(r.close),
                    pre_close=float(r.pre_close) if r.pre_close else None,
                    volume=r.volume or 0,
                    amount=float(r.amount) if r.amount else 0.0,
                    turnover_rate=float(r.turnover_rate) if r.turnover_rate else None,
                    pct_change=float(r.change_pct) if r.change_pct else None,
                    adjust_flag=r.adjust_flag or "3",
                )
                for r in batch
            ]
            inserted = repo.insert_daily(klines)
            total += inserted

    print(f"  {code}: migrated {total} rows")
    return total


async def get_all_codes() -> list[str]:
    """获取所有有日K数据的标的代码。"""
    db = get_database()
    async with db.session() as session:
        from sqlalchemy import distinct, func
        stmt = select(distinct(DailyKlineModel.code)).order_by(DailyKlineModel.code)
        result = await session.execute(stmt)
        return [row[0] for row in result.all() if row[0]]


async def main():
    args = parse_args()
    settings = get_settings()

    if not settings.clickhouse.enabled:
        print("Error: ClickHouse not enabled. Set CLICKHOUSE_ENABLED=true")
        sys.exit(1)

    # 创建表
    if args.create_tables:
        repo = ClickHouseRepository()
        repo.create_tables()
        print("ClickHouse tables created")

    # 验证连接
    client = get_ch_client()
    if client is None:
        print("Error: ClickHouse connection failed")
        sys.exit(1)

    repo = ClickHouseRepository()

    # 确定要迁移的代码
    if args.codes:
        codes = [c.strip() for c in args.codes.split(",") if c.strip()]
    elif args.all:
        print("Fetching all codes...")
        codes = await get_all_codes()
        print(f"Found {len(codes)} codes")
    else:
        print("Error: specify --codes or --all")
        sys.exit(1)

    # 迁移
    print(f"Migrating {len(codes)} codes to ClickHouse...")
    total = 0
    for i, code in enumerate(codes):
        count = await migrate_code(repo, code, args.batch)
        total += count
        if (i + 1) % 10 == 0:
            print(f"Progress: {i + 1}/{len(codes)} codes, {total} rows")

    print(f"\nMigration complete: {total} rows inserted")


if __name__ == "__main__":
    asyncio.run(main())
