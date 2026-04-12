"""trade_calendar 仓储（SQLite upsert）。"""

from __future__ import annotations

from datetime import date

from src.data.storage import TradeCalendarRepository


async def test_trade_calendar_bulk_upsert_idempotent(empty_sqlite_db):
    rows = [(date(2024, 2, 1), True), (date(2024, 2, 2), False)]
    async with empty_sqlite_db.session() as session:
        repo = TradeCalendarRepository(session)
        n1 = await repo.bulk_upsert_days("cn", rows)
        n2 = await repo.bulk_upsert_days("cn", [(date(2024, 2, 1), False)])
        c = await repo.row_count("cn")
    assert n1 == 2
    assert n2 == 1
    assert c == 2


async def test_trade_calendar_trading_days_set(empty_sqlite_db):
    rows = [
        (date(2024, 3, 4), True),
        (date(2024, 3, 5), True),
        (date(2024, 3, 6), False),
    ]
    async with empty_sqlite_db.session() as session:
        repo = TradeCalendarRepository(session)
        await repo.bulk_upsert_days("cn", rows)
        s = await repo.trading_days_set("cn", date(2024, 3, 1), date(2024, 3, 10))
    assert s == {date(2024, 3, 4), date(2024, 3, 5)}
