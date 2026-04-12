"""trade_calendar 全表摘要（质量脚本 JSON 用）。"""

from __future__ import annotations

from datetime import date

from src.data.quality.trade_calendar_table import trade_calendar_table_summary
from src.data.storage import TradeCalendarRepository


async def test_trade_calendar_table_summary_empty(empty_sqlite_db):
    async with empty_sqlite_db.session() as session:
        r = await trade_calendar_table_summary(session)
    assert r["table"] == "trade_calendar"
    assert r["total_row_count"] == 0
    assert r["distinct_exchange_count"] == 0
    assert r["by_exchange"] == []


async def test_trade_calendar_table_summary_by_exchange(empty_sqlite_db):
    async with empty_sqlite_db.session() as session:
        await TradeCalendarRepository(session).bulk_upsert_days(
            "cn",
            [(date(2024, 1, 1), True), (date(2024, 1, 2), False)],
        )
        await TradeCalendarRepository(session).bulk_upsert_days(
            "hk",
            [(date(2024, 1, 1), True)],
        )
    async with empty_sqlite_db.session() as session:
        r = await trade_calendar_table_summary(session)
    assert r["total_row_count"] == 3
    assert r["distinct_exchange_count"] == 2
    assert r["by_exchange"] == [
        {"exchange": "cn", "row_count": 2},
        {"exchange": "hk", "row_count": 1},
    ]
