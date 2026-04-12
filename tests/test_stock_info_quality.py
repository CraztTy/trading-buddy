"""stock_info 数据质量报告。"""

from __future__ import annotations

from src.data.models import Market, StockInfo, StockType
from src.data.quality.stock_info import stock_info_quality_report
from src.data.storage import StockRepository


async def test_stock_info_quality_empty(empty_sqlite_db):
    async with empty_sqlite_db.session() as session:
        r = await stock_info_quality_report(session)
    assert r["table"] == "stock_info"
    assert r["row_count"] == 0
    assert r["empty_name_rows"] == 0
    assert r["is_trading_rows_missing_list_date"] == 0


async def test_stock_info_quality_empty_name(empty_sqlite_db):
    async with empty_sqlite_db.session() as session:
        await StockRepository(session).bulk_upsert(
            [
                StockInfo(
                    code="sh.nn",
                    name="",
                    market=Market.SH,
                    stock_type=StockType.COMMON,
                    is_trading=True,
                ),
                StockInfo(
                    code="sh.ok",
                    name="正常",
                    market=Market.SH,
                    stock_type=StockType.COMMON,
                    is_trading=True,
                ),
            ]
        )
        r = await stock_info_quality_report(session)
    assert r["row_count"] == 2
    assert r["empty_name_rows"] == 1
    assert r["is_trading_rows_missing_list_date"] == 2
