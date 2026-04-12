"""`trade_calendar` 全表行数摘要（按 exchange 分组）。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.data.storage.models import TradingCalendarModel


async def trade_calendar_table_summary(session: AsyncSession) -> dict[str, Any]:
    """
    Returns:
        ``table``, ``total_row_count``, ``distinct_exchange_count``,
        ``by_exchange``（每项 ``exchange`` + ``row_count``，按 exchange 升序）。
    """
    total = await session.scalar(select(func.count()).select_from(TradingCalendarModel))
    total = int(total or 0)

    stmt = (
        select(TradingCalendarModel.exchange, func.count().label("n"))
        .group_by(TradingCalendarModel.exchange)
        .order_by(TradingCalendarModel.exchange)
    )
    rows = (await session.execute(stmt)).all()
    by_exchange = [{"exchange": str(r[0]), "row_count": int(r[1])} for r in rows]

    return {
        "table": "trade_calendar",
        "total_row_count": total,
        "distinct_exchange_count": len(by_exchange),
        "by_exchange": by_exchange,
    }
