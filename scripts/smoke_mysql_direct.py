#!/usr/bin/env python3
"""本地冒烟：直连 MySQL（硬编码 URL，仅本机调试；勿用于 CI）。"""
from __future__ import annotations

import asyncio
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


async def main() -> None:
    url = "mysql+aiomysql://root:trading2024@127.0.0.1:3306/trading"
    print(f"[smoke] Connecting to: {url}")

    engine = create_async_engine(url, echo=False)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        result = await session.execute(
            text("""
            INSERT INTO daily_kline (code, trade_date, open, high, low, close, volume, amount, change_pct, turnover_rate)
            VALUES (:code, :trade_date, :open, :high, :low, :close, :volume, :amount, :change_pct, :turnover_rate)
        """),
            {
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
            },
        )
        await session.commit()
        print(f"[smoke] Rows affected: {result.rowcount}")

    async with async_session() as session:
        result = await session.execute(
            text("SELECT id, code, trade_date, close, change_pct FROM daily_kline LIMIT 5")
        )
        rows = result.fetchall()
        print(f"[smoke] Found {len(rows)} rows in DB")
        for row in rows:
            print(f"  id={row[0]} code={row[1]} date={row[2]} close={row[3]} pct={row[4]}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
