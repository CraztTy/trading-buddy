#!/usr/bin/env python3
"""Test DB persistence with raw SQL"""
import asyncio
import sys
from pathlib import Path
from datetime import date
from sqlalchemy import text

project_root = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(project_root))

from src.data.storage import get_database


async def test_raw_sql():
    db = get_database()
    print("[TEST] Inserting with raw SQL...")

    async with db.session() as session:
        # Raw SQL insert
        result = await session.execute(text("""
            INSERT INTO daily_kline (code, trade_date, open, high, low, close, volume, amount, change_pct, turnover_rate)
            VALUES (:code, :trade_date, :open, :high, :low, :close, :volume, :amount, :change_pct, :turnover_rate)
        """), {
            "code": "sh.600000",
            "trade_date": date(2026, 3, 2),
            "open": 10.0,
            "high": 10.5,
            "low": 9.8,
            "close": 10.2,
            "volume": 1000000,
            "amount": 10200000.0,
            "change_pct": 2.0,
            "turnover_rate": 2.5,
        })
        print(f"[TEST] Raw SQL insert, rows affected: {result.rowcount}")

    # Verify
    print("[TEST] Verifying with raw SQL query...")
    async with db.session() as session:
        result = await session.execute(text("SELECT id, code, trade_date, close, change_pct FROM daily_kline ORDER BY id DESC LIMIT 5"))
        rows = result.fetchall()
        print(f"[TEST] Found {len(rows)} rows:")
        for row in rows:
            print(f"  id={row[0]} code={row[1]} date={row[2]} close={row[3]} pct={row[4]}")

    await db.close()


if __name__ == "__main__":
    asyncio.run(test_raw_sql())
