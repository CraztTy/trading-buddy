"""因子截面数据仓库 — 保存/查询每日因子快照。"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.data.storage.models import FactorSnapshotModel


class FactorSnapshotRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def upsert(
        self,
        trade_date: date,
        code: str,
        **kwargs: Any,
    ) -> FactorSnapshotModel:
        """插入或更新因子快照。"""
        stmt = select(FactorSnapshotModel).where(
            FactorSnapshotModel.trade_date == trade_date,
            FactorSnapshotModel.code == code,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()

        if row is None:
            row = FactorSnapshotModel(trade_date=trade_date, code=code, **kwargs)
            self._session.add(row)
        else:
            for k, v in kwargs.items():
                if hasattr(row, k) and v is not None:
                    setattr(row, k, v)

        await self._session.flush()
        return row

    async def get_by_date(
        self,
        trade_date: date,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[FactorSnapshotModel]:
        """查询某日的全部因子快照。"""
        stmt = (
            select(FactorSnapshotModel)
            .where(FactorSnapshotModel.trade_date == trade_date)
            .order_by(FactorSnapshotModel.code)
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_code(
        self,
        code: str,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 500,
    ) -> list[FactorSnapshotModel]:
        """查询某标的一段时间内的因子快照。"""
        stmt = select(FactorSnapshotModel).where(FactorSnapshotModel.code == code)
        if start_date:
            stmt = stmt.where(FactorSnapshotModel.trade_date >= start_date)
        if end_date:
            stmt = stmt.where(FactorSnapshotModel.trade_date <= end_date)
        stmt = stmt.order_by(FactorSnapshotModel.trade_date.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_date(self, trade_date: date) -> int:
        """统计某日因子快照数量。"""
        stmt = select(FactorSnapshotModel).where(FactorSnapshotModel.trade_date == trade_date)
        result = await self._session.execute(stmt)
        return len(result.scalars().all())

    async def delete_by_date(self, trade_date: date) -> int:
        """删除某日全部因子快照。"""
        stmt = delete(FactorSnapshotModel).where(FactorSnapshotModel.trade_date == trade_date)
        result = await self._session.execute(stmt)
        return result.rowcount or 0

    async def list_available_dates(
        self,
        limit: int = 30,
    ) -> list[date]:
        """列出有数据的交易日（去重，最近优先）。"""
        from sqlalchemy import distinct, desc

        stmt = (
            select(distinct(FactorSnapshotModel.trade_date))
            .order_by(desc(FactorSnapshotModel.trade_date))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [r[0] for r in result.all()]
