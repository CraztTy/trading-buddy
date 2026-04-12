"""daily_kline 数据质量报告（路线图阶段 A）。"""

from __future__ import annotations

from datetime import date, timedelta

from src.data.models import KLine
from src.data.quality.daily_kline import daily_kline_quality_report
from src.data.storage import KlineRepository


def _bar(code: str, d: date, close: float) -> KLine:
    o = close - 0.1
    return KLine(
        code=code,
        trade_date=d,
        open=o,
        high=close + 0.2,
        low=o - 0.1,
        close=close,
        volume=1000,
        amount=close * 1000,
        turnover_rate=None,
        pct_change=None,
    )


async def test_daily_kline_quality_report_empty(empty_sqlite_db):
    async with empty_sqlite_db.session() as session:
        r = await daily_kline_quality_report(session)
    assert r["table"] == "daily_kline"
    assert r["row_count"] == 0
    assert r["distinct_codes"] == 0
    assert r["codes_with_single_bar"] == 0
    assert r["orphan_kline_rows"] == 0
    assert r["duplicate_code_date_groups"] == 0
    assert r["stock_info_row_count"] == 0
    assert r["stock_info_codes_without_kline"] == 0
    assert r["trade_date_min"] is None
    assert r.get("invalid_ohlc_rows", 0) == 0
    assert r.get("negative_volume_rows", 0) == 0


async def test_daily_kline_quality_report_no_duplicates(empty_sqlite_db):
    code = "sh.q1"
    base = date(2024, 1, 2)
    rows = [_bar(code, base + timedelta(days=i), 10.0 + i * 0.1) for i in range(5)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)
        r = await daily_kline_quality_report(session)
    assert r["row_count"] == 5
    assert r["distinct_codes"] == 1
    assert r["codes_with_single_bar"] == 0
    assert r["orphan_kline_rows"] == 5
    assert r["stock_info_row_count"] == 0
    assert r["stock_info_codes_without_kline"] == 0
    assert r["duplicate_code_date_groups"] == 0
    assert r["trade_date_min"] == str(base)
    assert r["trade_date_max"] == str(base + timedelta(days=4))
    assert r["rows_on_max_trade_date"] == 1
    assert r.get("invalid_ohlc_rows", 0) == 0
    assert r.get("negative_volume_rows", 0) == 0


async def test_daily_kline_quality_invalid_ohlc_counted(empty_sqlite_db):
    bad = KLine(
        code="sh.bad",
        trade_date=date(2024, 6, 1),
        open=10.0,
        high=9.0,
        low=11.0,
        close=10.0,
        volume=100,
        amount=1000.0,
        turnover_rate=None,
        pct_change=None,
    )
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert([bad])
        r = await daily_kline_quality_report(session)
    assert r["row_count"] == 1
    assert r["invalid_ohlc_rows"] >= 1


async def test_daily_kline_quality_negative_volume_counted(empty_sqlite_db):
    bad = KLine(
        code="sh.negv",
        trade_date=date(2024, 6, 2),
        open=10.0,
        high=11.0,
        low=9.0,
        close=10.0,
        volume=-1,
        amount=1000.0,
        turnover_rate=None,
        pct_change=None,
    )
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert([bad])
        r = await daily_kline_quality_report(session)
    assert r["negative_volume_rows"] >= 1


async def test_daily_kline_quality_orphan_zero_when_stock_present(empty_sqlite_db):
    from src.data.models import Market, StockInfo, StockType
    from src.data.storage import StockRepository

    code = "sh.q2"
    base = date(2024, 2, 1)
    rows = [_bar(code, base + timedelta(days=i), 5.0) for i in range(3)]
    async with empty_sqlite_db.session() as session:
        await StockRepository(session).bulk_upsert(
            [
                StockInfo(
                    code=code,
                    name="测",
                    market=Market.SH,
                    stock_type=StockType.COMMON,
                    is_trading=True,
                ),
            ]
        )
        await KlineRepository(session).bulk_insert(rows)
        r = await daily_kline_quality_report(session)
    assert r["orphan_kline_rows"] == 0
    assert r["distinct_codes"] == 1
    assert r["codes_with_single_bar"] == 0
    assert r["stock_info_row_count"] == 1
    assert r["stock_info_codes_without_kline"] == 0


async def test_stock_info_without_kline_counted(empty_sqlite_db):
    from src.data.models import Market, StockInfo, StockType
    from src.data.storage import StockRepository

    async with empty_sqlite_db.session() as session:
        await StockRepository(session).bulk_upsert(
            [
                StockInfo(
                    code="sh.nok",
                    name="无K",
                    market=Market.SH,
                    stock_type=StockType.COMMON,
                    is_trading=True,
                ),
            ]
        )
        r = await daily_kline_quality_report(session)
    assert r["stock_info_row_count"] == 1
    assert r["stock_info_codes_without_kline"] == 1


async def test_daily_kline_quality_single_bar_code(empty_sqlite_db):
    from src.data.models import Market, StockInfo, StockType
    from src.data.storage import StockRepository

    async with empty_sqlite_db.session() as session:
        await StockRepository(session).bulk_upsert(
            [
                StockInfo(
                    code="sh.one",
                    name="单",
                    market=Market.SH,
                    stock_type=StockType.COMMON,
                    is_trading=True,
                ),
            ]
        )
        await KlineRepository(session).bulk_insert([_bar("sh.one", date(2024, 3, 1), 1.0)])
        await KlineRepository(session).bulk_insert(
            [_bar("sh.two", date(2024, 3, 1), 2.0), _bar("sh.two", date(2024, 3, 2), 2.1)]
        )
        r = await daily_kline_quality_report(session)
    assert r["row_count"] == 3
    assert r["distinct_codes"] == 2
    assert r["codes_with_single_bar"] == 1
    assert r["orphan_kline_rows"] == 2
    assert r["stock_info_row_count"] == 1
    assert r["stock_info_codes_without_kline"] == 0
