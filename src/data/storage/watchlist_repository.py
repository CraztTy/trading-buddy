"""自选股：默认分组 + 代码列表（与 stock_info 可选关联名称）。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.common import get_logger

from .models import StockInfoModel, WatchlistItemModel, WatchlistModel

logger = get_logger("watchlist_repository")

DEFAULT_WATCHLIST_LABEL = "default"
MAX_ITEMS = 500


@dataclass(frozen=True)
class WatchlistItemRow:
    code: str
    name: str | None
    created_at: datetime | None


class WatchlistRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_or_create_watchlist(
        self, user_id: int | None = None, label: str = DEFAULT_WATCHLIST_LABEL
    ) -> WatchlistModel:
        """按 (user_id, label) 查找或创建自选股分组。

        - user_id 为 None 时查找 user_id IS NULL 的记录（兼容旧数据）。
        """
        if user_id is not None:
            stmt = select(WatchlistModel).where(
                WatchlistModel.user_id == user_id,
                WatchlistModel.label == label,
            )
        else:
            stmt = select(WatchlistModel).where(
                WatchlistModel.user_id.is_(None),
                WatchlistModel.label == label,
            )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row:
            return row
        wl = WatchlistModel(user_id=user_id, label=label)
        self._session.add(wl)
        await self._session.flush()
        logger.info("watchlist created user_id=%s label=%s id=%s", user_id, wl.label, wl.id)
        return wl

    async def get_or_create_default_watchlist(self) -> WatchlistModel:
        """向后兼容：无 user_id 时查找/创建 label='default' 且 user_id=NULL 的分组。"""
        return await self.get_or_create_watchlist(user_id=None, label=DEFAULT_WATCHLIST_LABEL)

    async def count_items(self, watchlist_id: int) -> int:
        stmt = select(func.count()).select_from(WatchlistItemModel).where(
            WatchlistItemModel.watchlist_id == watchlist_id
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def has_item(self, watchlist_id: int, code: str) -> bool:
        stmt = select(WatchlistItemModel.id).where(
            WatchlistItemModel.watchlist_id == watchlist_id,
            WatchlistItemModel.code == code,
        )
        return (await self._session.execute(stmt)).first() is not None

    async def list_items(self, watchlist_id: int) -> list[WatchlistItemRow]:
        stmt = (
            select(WatchlistItemModel, StockInfoModel.name)
            .outerjoin(StockInfoModel, StockInfoModel.code == WatchlistItemModel.code)
            .where(WatchlistItemModel.watchlist_id == watchlist_id)
            .order_by(desc(WatchlistItemModel.created_at), desc(WatchlistItemModel.id))
        )
        r = await self._session.execute(stmt)
        out: list[WatchlistItemRow] = []
        for item, name in r.all():
            out.append(WatchlistItemRow(code=item.code, name=name, created_at=item.created_at))
        return out

    async def add_item(self, watchlist_id: int, code: str) -> WatchlistItemModel:
        if await self.has_item(watchlist_id, code):
            raise ValueError("已在自选中")
        n = await self.count_items(watchlist_id)
        if n >= MAX_ITEMS:
            raise ValueError(f"自选最多 {MAX_ITEMS} 只")
        row = WatchlistItemModel(watchlist_id=watchlist_id, code=code)
        self._session.add(row)
        await self._session.flush()
        return row

    async def remove_item(self, watchlist_id: int, code: str) -> int:
        stmt = delete(WatchlistItemModel).where(
            WatchlistItemModel.watchlist_id == watchlist_id,
            WatchlistItemModel.code == code,
        )
        r = await self._session.execute(stmt)
        return int(r.rowcount or 0)
