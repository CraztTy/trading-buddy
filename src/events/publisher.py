"""事件发布器 — 统一的事件发布接口。

为现有代码提供简洁的事件发布入口，无需直接操作 EventBus。

用法:
    from src.events import EventPublisher
    pub = EventPublisher()
    await pub.market_data_changed(code="sh.600000", price=10.55, change_pct=0.48)
    await pub.order_filled(order_id="12345", code="sh.600000", side="buy", quantity=100, price=10.55)
    await pub.risk_blocked(rule_name="position_limit", detail="持仓超限")
"""

from __future__ import annotations

from typing import Any

from src.common import get_logger
from src.events.bus import EventBus
from src.events.models import (
    BaseEvent,
    MarketDataEvent,
    OrderEvent,
    RiskEvent,
    SystemEvent,
)

logger = get_logger("event_publisher")


class EventPublisher:
    """事件发布器。"""

    def __init__(self):
        self._bus = EventBus()

    # ------------------------------------------------------------------
    # 行情事件
    # ------------------------------------------------------------------

    async def market_data_changed(
        self,
        code: str,
        price: float,
        change_pct: float = 0.0,
        volume: int = 0,
        amount: float = 0.0,
        bid1: float = 0.0,
        ask1: float = 0.0,
        **kwargs: Any,
    ) -> str | None:
        """发布行情变化事件。"""
        event = MarketDataEvent(
            code=code,
            price=price,
            change_pct=change_pct,
            volume=volume,
            amount=amount,
            bid1=bid1,
            ask1=ask1,
            **kwargs,
        )
        return await self._bus.publish(event)

    # ------------------------------------------------------------------
    # 订单事件
    # ------------------------------------------------------------------

    async def order_created(
        self,
        order_id: str,
        code: str,
        side: str,
        quantity: int,
        price: float,
        account_label: str = "default",
        **kwargs: Any,
    ) -> str | None:
        """发布订单创建事件。"""
        event = OrderEvent(
            order_id=order_id,
            code=code,
            side=side,
            quantity=quantity,
            price=price,
            status="created",
            account_label=account_label,
            **kwargs,
        )
        return await self._bus.publish(event)

    async def order_filled(
        self,
        order_id: str,
        code: str,
        side: str,
        quantity: int,
        price: float,
        filled_quantity: int,
        account_label: str = "default",
        **kwargs: Any,
    ) -> str | None:
        """发布订单成交事件。"""
        event = OrderEvent(
            order_id=order_id,
            code=code,
            side=side,
            quantity=quantity,
            price=price,
            status="filled",
            account_label=account_label,
            filled_quantity=filled_quantity,
            **kwargs,
        )
        return await self._bus.publish(event)

    async def order_cancelled(
        self,
        order_id: str,
        code: str,
        side: str,
        quantity: int,
        account_label: str = "default",
        **kwargs: Any,
    ) -> str | None:
        """发布订单撤销事件。"""
        event = OrderEvent(
            order_id=order_id,
            code=code,
            side=side,
            quantity=quantity,
            price=0.0,
            status="cancelled",
            account_label=account_label,
            **kwargs,
        )
        return await self._bus.publish(event)

    async def order_rejected(
        self,
        order_id: str,
        code: str,
        side: str,
        quantity: int,
        reason: str,
        account_label: str = "default",
        **kwargs: Any,
    ) -> str | None:
        """发布订单被拒事件。"""
        event = OrderEvent(
            order_id=order_id,
            code=code,
            side=side,
            quantity=quantity,
            price=0.0,
            status="rejected",
            account_label=account_label,
            rejected_reason=reason,
            **kwargs,
        )
        return await self._bus.publish(event)

    # ------------------------------------------------------------------
    # 风控事件
    # ------------------------------------------------------------------

    async def risk_violation(
        self,
        rule_name: str,
        rule_type: str,
        detail: str,
        context: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str | None:
        """发布风控违规事件。"""
        event = RiskEvent(
            rule_name=rule_name,
            rule_type=rule_type,
            severity="violation",
            detail=detail,
            context=context,
            **kwargs,
        )
        return await self._bus.publish(event)

    async def risk_warning(
        self,
        rule_name: str,
        rule_type: str,
        detail: str,
        context: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str | None:
        """发布风控预警事件。"""
        event = RiskEvent(
            rule_name=rule_name,
            rule_type=rule_type,
            severity="warning",
            detail=detail,
            context=context,
            **kwargs,
        )
        return await self._bus.publish(event)

    async def risk_blocked(
        self,
        rule_name: str,
        rule_type: str,
        detail: str,
        context: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str | None:
        """发布风控拦截事件。"""
        event = RiskEvent(
            rule_name=rule_name,
            rule_type=rule_type,
            severity="blocked",
            detail=detail,
            context=context,
            **kwargs,
        )
        return await self._bus.publish(event)

    # ------------------------------------------------------------------
    # 系统事件
    # ------------------------------------------------------------------

    async def system_startup(self, **kwargs: Any) -> str | None:
        """发布系统启动事件。"""
        from src.events.models import EventType
        event = SystemEvent(
            event_type=EventType.SYSTEM_STARTUP,
            message="Trading Buddy API 已启动",
            **kwargs,
        )
        return await self._bus.publish(event)

    async def system_shutdown(self, **kwargs: Any) -> str | None:
        """发布系统关闭事件。"""
        from src.events.models import EventType
        event = SystemEvent(
            event_type=EventType.SYSTEM_SHUTDOWN,
            message="Trading Buddy API 即将关闭",
            **kwargs,
        )
        return await self._bus.publish(event)

    async def system_error(self, message: str, **kwargs: Any) -> str | None:
        """发布系统错误事件。"""
        from src.events.models import EventType
        event = SystemEvent(
            event_type=EventType.SYSTEM_ERROR,
            message=message,
            **kwargs,
        )
        return await self._bus.publish(event)

    # ------------------------------------------------------------------
    # 通用发布
    # ------------------------------------------------------------------

    async def publish(self, event: BaseEvent) -> str | None:
        """发布任意事件。"""
        return await self._bus.publish(event)
