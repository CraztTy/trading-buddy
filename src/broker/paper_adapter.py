"""纸交易 Broker Adapter — 将现有纸交易逻辑封装为统一接口。

这是 BrokerAdapter 的第一个实现，也是默认实现。
后续实盘适配器（xtp、中泰等）遵循同一接口。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.broker.base import (
    BaseBrokerAdapter,
    BrokerBalance,
    BrokerOrderRequest,
    BrokerOrderResponse,
    BrokerPosition,
    BrokerTrade,
    OrderSide,
    OrderStatus,
    OrderType,
)
from src.data.storage.paper_repository import PaperRepository


class PaperBrokerAdapter(BaseBrokerAdapter):
    """纸交易适配器 — 用最近一根日 K 收盘价做市价撮合。"""

    name = "paper"
    supports_market_order = True
    supports_limit_order = False
    supports_stop_order = False
    supports_cancel = False
    t_plus_n = 1

    def __init__(self, session: AsyncSession, user_id: int | None = None, account_label: str = "default"):
        self._session = session
        self._user_id = user_id
        self._account_label = account_label
        self._repo = PaperRepository(session)

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        pass

    async def place_order(self, request: BrokerOrderRequest) -> BrokerOrderResponse:
        """提交纸交易订单。

        实际撮合由 PaperRepository.place_market_order 完成。
        这里做参数转换和响应封装。
        """
        from src.data.storage import KlineRepository

        if request.order_type != OrderType.MARKET:
            return BrokerOrderResponse(
                order_id="",
                code=request.code,
                side=request.side,
                quantity=request.quantity,
                status=OrderStatus.REJECTED,
                rejected_reason=f"纸交易仅支持市价单，不支持 {request.order_type.value}",
                created_at=datetime.now(),
            )

        kline_repo = KlineRepository(self._session)
        kl = await kline_repo.get_daily(request.code, limit=1)
        if not kl:
            return BrokerOrderResponse(
                order_id="",
                code=request.code,
                side=request.side,
                quantity=request.quantity,
                status=OrderStatus.REJECTED,
                rejected_reason="无日 K 数据，无法定价",
                created_at=datetime.now(),
            )

        last = kl[-1]
        price = float(last.close)
        td = last.trade_date
        qty = request.quantity

        # 涨跌停检查
        pre_close = float(last.pre_close) if last.pre_close else 0.0
        if pre_close > 0:
            from src.data.storage import StockRepository
            from src.data.models.stock import StockType

            stock_repo = StockRepository(self._session)
            stock_info = await stock_repo.get_by_code(request.code)
            stock_type = stock_info.stock_type if stock_info else StockType.COMMON

            # 涨跌停限制
            limits = {
                StockType.COMMON: 0.10,
                StockType.ST: 0.05,
                StockType.STAR: 0.20,
                StockType.GROWTH: 0.20,
                StockType.BEIJING: 0.30,
            }
            limit = limits.get(stock_type, 0.10)
            change_pct = (price - pre_close) / pre_close

            if request.side == OrderSide.BUY and change_pct >= limit - 1e-9:
                return BrokerOrderResponse(
                    order_id="",
                    code=request.code,
                    side=request.side,
                    quantity=request.quantity,
                    status=OrderStatus.REJECTED,
                    rejected_reason=f"涨停不可买入（涨幅 {change_pct*100:.2f}% >= {limit*100:.0f}%）",
                    created_at=datetime.now(),
                )
            if request.side == OrderSide.SELL and change_pct <= -limit + 1e-9:
                return BrokerOrderResponse(
                    order_id="",
                    code=request.code,
                    side=request.side,
                    quantity=request.quantity,
                    status=OrderStatus.REJECTED,
                    rejected_reason=f"跌停不可卖出（跌幅 {change_pct*100:.2f}% <= -{limit*100:.0f}%）",
                    created_at=datetime.now(),
                )

        # 印花税：卖出时 0.05%
        stamp_tax = 0.0
        if request.side == OrderSide.SELL:
            stamp_tax = round(price * qty * 0.0005, 4)

        gross = round(price * qty - stamp_tax, 4)

        acc = await self._repo.get_or_create_account(user_id=self._user_id, label=self._account_label)

        try:
            order = await self._repo.place_market_order(
                account_id=acc.id,
                code=request.code,
                side=request.side.value,
                quantity=qty,
                fill_price=price,
                trade_date=td,
                fill_amount=gross,
            )
        except ValueError as e:
            return BrokerOrderResponse(
                order_id="",
                code=request.code,
                side=request.side,
                quantity=request.quantity,
                status=OrderStatus.REJECTED,
                rejected_reason=str(e),
                created_at=datetime.now(),
            )

        return BrokerOrderResponse(
            order_id=str(order.id),
            code=order.code,
            side=OrderSide(order.side),
            quantity=order.quantity,
            filled_quantity=order.quantity,
            avg_fill_price=order.fill_price,
            status=OrderStatus.FILLED,
            order_type=OrderType.MARKET,
            commission=stamp_tax,
            slippage=0.0,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

    async def cancel_order(self, order_id: str) -> BrokerOrderResponse:
        """纸交易不支持撤单（已立即成交）。"""
        raise NotImplementedError("纸交易不支持撤单")

    async def get_order(self, order_id: str) -> BrokerOrderResponse | None:
        """查询纸交易订单。"""
        try:
            oid = int(order_id)
        except ValueError:
            return None

        # PaperRepository 没有按 ID 查订单的方法，简化返回
        return BrokerOrderResponse(
            order_id=order_id,
            code="",
            side=OrderSide.BUY,
            quantity=0,
            status=OrderStatus.FILLED,
            created_at=datetime.now(),
        )

    async def get_positions(self) -> list[BrokerPosition]:
        """查询纸交易持仓（T+1：available_quantity 为可卖数量）。"""
        from src.data.storage import KlineRepository

        acc = await self._repo.get_or_create_account(user_id=self._user_id, label=self._account_label)
        rows = await self._repo.list_positions(acc.id)
        kline_repo = KlineRepository(self._session)

        out: list[BrokerPosition] = []
        for r in rows:
            kl = await kline_repo.get_daily(r.code, limit=1)
            td = kl[-1].trade_date if kl else date.today()
            sellable = await self._repo.sellable_quantity(acc.id, r.code, td)
            out.append(
                BrokerPosition(
                    code=r.code,
                    quantity=r.quantity,
                    available_quantity=sellable,
                    avg_cost=r.avg_price,
                    market_value=r.avg_price * r.quantity,
                    updated_at=datetime.now(),
                )
            )
        return out

    async def get_balance(self) -> BrokerBalance:
        """查询纸交易资金。"""
        from src.data.storage import KlineRepository

        acc = await self._repo.get_or_create_account(user_id=self._user_id, label=self._account_label)
        positions = await self._repo.list_positions(acc.id)
        kline_repo = KlineRepository(self._session)

        mv_total = 0.0
        for p in positions:
            kl = await kline_repo.get_daily(p.code, limit=1)
            price = float(kl[-1].close) if kl else p.avg_price
            mv_total += price * p.quantity

        total_equity = acc.cash + mv_total
        return BrokerBalance(
            cash=acc.cash,
            available_cash=acc.cash,
            frozen_cash=0.0,
            market_value=mv_total,
            total_equity=total_equity,
            initial_cash=acc.initial_cash,
            updated_at=datetime.now(),
        )

    async def get_trades(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[BrokerTrade]:
        """查询纸交易成交记录。"""
        acc = await self._repo.get_or_create_account(user_id=self._user_id, label=self._account_label)
        orders = await self._repo.list_orders(acc.id)
        trades = []
        for o in orders:
            if start_date and o.trade_date and o.trade_date < start_date:
                continue
            if end_date and o.trade_date and o.trade_date > end_date:
                continue
            trades.append(
                BrokerTrade(
                    trade_id=str(o.id),
                    order_id=str(o.id),
                    code=o.code,
                    side=OrderSide(o.side),
                    quantity=o.quantity,
                    price=o.fill_price or 0.0,
                    amount=o.fill_amount or 0.0,
                    trade_date=o.trade_date,
                    trade_time=datetime.now(),
                )
            )
        return trades

    async def health_check(self) -> dict[str, Any]:
        return {"adapter": self.name, "status": "ok", "account_label": self._account_label}
