"""抽样 code 的日 K 公历缺口（相邻 trade_date）统计。"""

from __future__ import annotations

from datetime import date, timedelta

from src.data.models import KLine
from src.data.quality.kline_calendar_gaps import (
    calendar_gap_sample_report,
    max_interior_gap_calendar_days,
    max_missing_trading_sessions_between_klines,
)
from src.data.storage import KlineRepository, TradeCalendarRepository


def test_max_missing_trading_sessions_between_klines():
    d0 = date(2024, 1, 3)
    d1 = date(2024, 1, 8)
    trading = {date(2024, 1, 4), date(2024, 1, 5)}
    assert max_missing_trading_sessions_between_klines([d0, d1], trading) == 2


def test_max_interior_gap_calendar_days():
    assert max_interior_gap_calendar_days([date(2024, 1, 1)]) is None
    assert max_interior_gap_calendar_days([date(2024, 1, 1), date(2024, 1, 2)]) == 0
    assert max_interior_gap_calendar_days([date(2024, 1, 1), date(2024, 1, 10)]) == 8


async def test_calendar_gap_sample_empty(empty_sqlite_db):
    async with empty_sqlite_db.session() as session:
        r = await calendar_gap_sample_report(session, sample_size=5, seed_offset=0)
    assert r["enabled"] is True
    assert r["codes_sampled"] == 0
    assert r["max_interior_gap_calendar_days_in_sample"] is None


async def test_calendar_gap_sample_worst_and_top(empty_sqlite_db):
    d0 = date(2024, 1, 1)
    bars = [
        KLine(
            code="sh.aa",
            trade_date=d0,
            open=1,
            high=2,
            low=0.5,
            close=1,
            volume=1,
            amount=1.0,
            turnover_rate=None,
            pct_change=None,
        ),
        KLine(
            code="sh.aa",
            trade_date=d0 + timedelta(days=1),
            open=1,
            high=2,
            low=0.5,
            close=1,
            volume=1,
            amount=1.0,
            turnover_rate=None,
            pct_change=None,
        ),
        KLine(
            code="sh.bb",
            trade_date=d0,
            open=1,
            high=2,
            low=0.5,
            close=1,
            volume=1,
            amount=1.0,
            turnover_rate=None,
            pct_change=None,
        ),
        KLine(
            code="sh.bb",
            trade_date=d0 + timedelta(days=9),
            open=1,
            high=2,
            low=0.5,
            close=1,
            volume=1,
            amount=1.0,
            turnover_rate=None,
            pct_change=None,
        ),
        KLine(
            code="sh.zz",
            trade_date=d0,
            open=1,
            high=2,
            low=0.5,
            close=1,
            volume=1,
            amount=1.0,
            turnover_rate=None,
            pct_change=None,
        ),
    ]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(bars)
        r = await calendar_gap_sample_report(session, sample_size=10, seed_offset=0, top_k=5)
    assert r["codes_sampled"] == 3
    assert r["codes_with_at_least_two_bars"] == 2
    assert r["max_interior_gap_calendar_days_in_sample"] == 8
    assert r["worst_code_in_sample"] == "sh.bb"
    assert r["trading_calendar_row_count"] == 0
    assert r["max_missing_trading_sessions_in_sample"] is None
    assert len(r["top_by_max_gap"]) == 2
    assert r["top_by_max_gap"][0]["code"] == "sh.bb"
    assert r["top_by_max_gap"][0]["max_interior_gap_calendar_days"] == 8


async def test_calendar_gap_sample_with_trade_calendar(empty_sqlite_db):
    d0 = date(2024, 1, 3)
    cal_days = [
        (date(2024, 1, 3), True),
        (date(2024, 1, 4), True),
        (date(2024, 1, 5), True),
        (date(2024, 1, 6), False),
        (date(2024, 1, 7), False),
        (date(2024, 1, 8), True),
    ]
    bars = [
        KLine(
            code="sh.gc",
            trade_date=d0,
            open=1,
            high=2,
            low=0.5,
            close=1,
            volume=1,
            amount=1.0,
            turnover_rate=None,
            pct_change=None,
        ),
        KLine(
            code="sh.gc",
            trade_date=date(2024, 1, 8),
            open=1,
            high=2,
            low=0.5,
            close=1,
            volume=1,
            amount=1.0,
            turnover_rate=None,
            pct_change=None,
        ),
    ]
    async with empty_sqlite_db.session() as session:
        await TradeCalendarRepository(session).bulk_upsert_days("cn", cal_days)
        await KlineRepository(session).bulk_insert(bars)
        r = await calendar_gap_sample_report(
            session, sample_size=10, seed_offset=0, top_k=5, gap_exchange="cn"
        )
    assert r["trading_calendar_row_count"] == 6
    assert r["max_missing_trading_sessions_in_sample"] == 2
    assert r["worst_code_trading_gap_in_sample"] == "sh.gc"


async def test_calendar_gap_sample_disabled(empty_sqlite_db):
    async with empty_sqlite_db.session() as session:
        r = await calendar_gap_sample_report(session, sample_size=0)
    assert r["enabled"] is False
