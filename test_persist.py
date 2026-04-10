#!/usr/bin/env python3
"""快速测试数据库持久化"""
import asyncio
import sys
from pathlib import Path
from datetime import date

project_root = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(project_root))

from src.data.storage import dispose_database, get_database, KlineRepository
from src.data.models import KLine


async def test():
    db = get_database()

    # Insert test data
    test_klines = [
        KLine(
            code='sh.600000', trade_date=date(2026, 3, 2),
            open=10.0, high=10.5, low=9.8, close=10.2,
            volume=1000000, amount=10200000.0, turnover_rate=2.5, pct_change=2.0,
        ),
        KLine(
            code='sh.600000', trade_date=date(2026, 3, 3),
            open=10.2, high=10.8, low=10.1, close=10.6,
            volume=1200000, amount=12600000.0, turnover_rate=3.0, pct_change=3.92,
        ),
    ]

    print("[TEST] Inserting 2 klines...")
    async with db.session() as session:
        repo = KlineRepository(session)
        count = await repo.bulk_insert(test_klines)
        print(f"[TEST] bulk_insert returned: {count}")

    # Verify
    print("[TEST] Verifying data in DB...")
    async with db.session() as session:
        repo = KlineRepository(session)
        result = await repo.get_daily(code='sh.600000', limit=10)
        print(f"[TEST] Found {len(result)} rows in DB:")
        for k in result:
            print(f"  {k.trade_date} close={k.close} pct={k.pct_change}")

    await dispose_database()


if __name__ == "__main__":
    asyncio.run(test())
