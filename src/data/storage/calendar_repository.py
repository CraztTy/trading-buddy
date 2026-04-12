"""交易日历表 trade_calendar：读写与区间统计。"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.common import get_logger
from .models import TradingCalendarModel

logger = get_logger("calendar_repository")


class TradeCalendarRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def row_count(self, exchange: str) -> int:
        n = await self._session.scalar(
            select(func.count())
            .select_from(TradingCalendarModel)
            .where(TradingCalendarModel.exchange == exchange)
        )
        return int(n or 0)

    async def min_max_dates(self, exchange: str) -> tuple[date | None, date | None]:
        stmt = select(
            func.min(TradingCalendarModel.calendar_date),
            func.max(TradingCalendarModel.calendar_date),
        ).where(TradingCalendarModel.exchange == exchange)
        lo, hi = (await self._session.execute(stmt)).one()
        return lo, hi

    async def bulk_upsert_days(
        self,
        exchange: str,
        days: Iterable[tuple[date, bool]],
    ) -> int:
        rows = [
            {
                "exchange": exchange,
                "calendar_date": d,
                "is_trading_day": flag,
            }
            for d, flag in days
        ]
        if not rows:
            return 0
        dialect = self._session.bind.dialect.name
        if dialect == "sqlite":
            from sqlalchemy.dialects.sqlite import insert as dialect_insert

            ins = dialect_insert(TradingCalendarModel).values(rows)
            stmt = ins.on_conflict_do_update(
                index_elements=["exchange", "calendar_date"],
                set_={"is_trading_day": ins.excluded.is_trading_day},
            )
            await self._session.execute(stmt)
        elif dialect == "mysql":
            from sqlalchemy.dialects.mysql import insert as dialect_insert

            ins = dialect_insert(TradingCalendarModel).values(rows)
            stmt = ins.on_duplicate_key_update(
                is_trading_day=ins.inserted.is_trading_day,
            )
            await self._session.execute(stmt)
        else:
            for r in rows:
                m = TradingCalendarModel(
                    exchange=r["exchange"],
                    calendar_date=r["calendar_date"],
                    is_trading_day=r["is_trading_day"],
                )
                self._session.merge(m)
        await self._session.flush()
        logger.info(f"trade_calendar upsert {len(rows)} rows exchange={exchange}")
        return len(rows)

    async def trading_days_set(
        self,
        exchange: str,
        d_min: date,
        d_max: date,
    ) -> set[date]:
        stmt = select(TradingCalendarModel.calendar_date).where(
            TradingCalendarModel.exchange == exchange,
            TradingCalendarModel.calendar_date >= d_min,
            TradingCalendarModel.calendar_date <= d_max,
            TradingCalendarModel.is_trading_day.is_(True),
        )
        result = await self._session.execute(stmt)
        return {r[0] for r in result.all()}
