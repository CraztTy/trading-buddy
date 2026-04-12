"""纸交易：默认账户、持仓、按最近日 K 收盘价撮合；A 股 100 股整数倍、卖出 T+1（FIFO 批）。"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.common import get_logger
from .models import PaperAccountModel, PaperLotModel, PaperOrderModel, PaperPositionModel

logger = get_logger("paper_repository")

DEFAULT_ACCOUNT_LABEL = "default"
DEFAULT_INITIAL_CASH = 1_000_000.0
LOT_SIZE = 100


def assert_a_share_lot(quantity: int) -> None:
    if quantity < LOT_SIZE or quantity % LOT_SIZE != 0:
        raise ValueError("股数须为 100 的整数倍且不少于 100")


class PaperRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_or_create_default_account(self) -> PaperAccountModel:
        stmt = select(PaperAccountModel).where(PaperAccountModel.label == DEFAULT_ACCOUNT_LABEL)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row:
            return row
        acc = PaperAccountModel(
            label=DEFAULT_ACCOUNT_LABEL,
            cash=DEFAULT_INITIAL_CASH,
            initial_cash=DEFAULT_INITIAL_CASH,
        )
        self._session.add(acc)
        await self._session.flush()
        logger.info("paper account created label=%s id=%s", acc.label, acc.id)
        return acc

    async def list_positions(self, account_id: int) -> list[PaperPositionModel]:
        stmt = select(PaperPositionModel).where(PaperPositionModel.account_id == account_id)
        r = await self._session.execute(stmt)
        return list(r.scalars().all())

    async def get_position(self, account_id: int, code: str) -> PaperPositionModel | None:
        stmt = select(PaperPositionModel).where(
            PaperPositionModel.account_id == account_id,
            PaperPositionModel.code == code,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def count_orders(self, account_id: int, code: str | None = None) -> int:
        stmt = select(func.count()).select_from(PaperOrderModel).where(PaperOrderModel.account_id == account_id)
        if code is not None:
            stmt = stmt.where(PaperOrderModel.code == code)
        return int((await self._session.execute(stmt)).scalar_one())

    async def list_orders(
        self,
        account_id: int,
        *,
        limit: int,
        offset: int,
        code: str | None = None,
    ) -> list[PaperOrderModel]:
        stmt = select(PaperOrderModel).where(PaperOrderModel.account_id == account_id)
        if code is not None:
            stmt = stmt.where(PaperOrderModel.code == code)
        stmt = stmt.order_by(desc(PaperOrderModel.id)).offset(offset).limit(limit)
        r = await self._session.execute(stmt)
        return list(r.scalars().all())

    async def _list_lots_ordered(self, account_id: int, code: str) -> list[PaperLotModel]:
        stmt = (
            select(PaperLotModel)
            .where(
                PaperLotModel.account_id == account_id,
                PaperLotModel.code == code,
                PaperLotModel.quantity > 0,
            )
            .order_by(PaperLotModel.buy_trade_date.asc(), PaperLotModel.id.asc())
        )
        r = await self._session.execute(stmt)
        return list(r.scalars().all())

    async def sellable_quantity(self, account_id: int, code: str, pricing_trade_date: date) -> int:
        """T+1：仅统计 buy_trade_date < 定价日 的批（同日买入不可用最近一根日 K 卖出）。"""
        lots = await self._list_lots_ordered(account_id, code)
        return sum(l.quantity for l in lots if l.buy_trade_date < pricing_trade_date)

    async def _upsert_position_from_lots(self, account_id: int, code: str) -> None:
        lots = await self._list_lots_ordered(account_id, code)
        pos = await self.get_position(account_id, code)
        if not lots:
            if pos is not None:
                await self._session.delete(pos)
            return
        total = sum(l.quantity for l in lots)
        cost = sum(l.quantity * l.buy_price for l in lots)
        avg = round(cost / total, 4) if total else 0.0
        if pos is None:
            self._session.add(
                PaperPositionModel(
                    account_id=account_id,
                    code=code,
                    quantity=total,
                    avg_price=avg,
                )
            )
        else:
            pos.quantity = total
            pos.avg_price = avg

    async def _consume_lots_fifo(
        self,
        account_id: int,
        code: str,
        quantity: int,
        pricing_trade_date: date,
    ) -> None:
        """按 FIFO 扣减可卖批（buy_trade_date < pricing_trade_date）。"""
        remaining = quantity
        while remaining > 0:
            stmt = (
                select(PaperLotModel)
                .where(
                    PaperLotModel.account_id == account_id,
                    PaperLotModel.code == code,
                    PaperLotModel.quantity > 0,
                    PaperLotModel.buy_trade_date < pricing_trade_date,
                )
                .order_by(PaperLotModel.buy_trade_date.asc(), PaperLotModel.id.asc())
                .limit(1)
            )
            lot = (await self._session.execute(stmt)).scalar_one_or_none()
            if lot is None:
                sellable = await self.sellable_quantity(account_id, code, pricing_trade_date)
                raise ValueError(
                    "卖出 T+1：仅可卖「买入日早于当前定价日 K 线交易日」的持仓；"
                    f"当前可卖 {sellable} 股，请求共卖出 {quantity} 股（尚未足额扣减 {remaining} 股）"
                )
            take = min(lot.quantity, remaining)
            lot.quantity -= take
            remaining -= take
            if lot.quantity <= 0:
                await self._session.delete(lot)

    async def place_market_order(
        self,
        *,
        account_id: int,
        code: str,
        side: str,
        quantity: int,
        fill_price: float,
        trade_date: date,
        fill_amount: float,
    ) -> PaperOrderModel:
        side_l = side.strip().lower()
        if side_l not in ("buy", "sell"):
            raise ValueError("side 须为 buy 或 sell")
        assert_a_share_lot(quantity)

        acc = await self._session.get(PaperAccountModel, account_id)
        if acc is None:
            raise ValueError("账户不存在")

        if side_l == "buy":
            if acc.cash + 1e-9 < fill_amount:
                raise ValueError("现金不足")
            acc.cash = round(acc.cash - fill_amount, 4)
            lot = PaperLotModel(
                account_id=account_id,
                code=code,
                quantity=quantity,
                buy_trade_date=trade_date,
                buy_price=round(fill_price, 4),
            )
            self._session.add(lot)
            await self._upsert_position_from_lots(account_id, code)
        else:
            sellable = await self.sellable_quantity(account_id, code, trade_date)
            if sellable < quantity:
                raise ValueError(
                    "卖出 T+1：仅可卖「买入日早于当前定价日 K 线交易日」的持仓；"
                    f"当前可卖 {sellable} 股，请求卖出 {quantity} 股"
                )
            await self._consume_lots_fifo(account_id, code, quantity, trade_date)
            acc.cash = round(acc.cash + fill_amount, 4)
            await self._upsert_position_from_lots(account_id, code)

        order = PaperOrderModel(
            account_id=account_id,
            code=code,
            side=side_l,
            quantity=quantity,
            fill_price=round(fill_price, 4),
            fill_amount=round(fill_amount, 4),
            trade_date=trade_date,
            created_at=datetime.now(),
        )
        self._session.add(order)
        await self._session.flush()
        return order

    async def reset_account(self, account_id: int) -> None:
        await self._session.execute(delete(PaperOrderModel).where(PaperOrderModel.account_id == account_id))
        await self._session.execute(delete(PaperLotModel).where(PaperLotModel.account_id == account_id))
        await self._session.execute(delete(PaperPositionModel).where(PaperPositionModel.account_id == account_id))
        acc = await self._session.get(PaperAccountModel, account_id)
        if acc:
            acc.cash = acc.initial_cash
        await self._session.flush()
