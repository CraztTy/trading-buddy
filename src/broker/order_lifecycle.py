"""订单生命周期状态机 — 管理订单从创建到结算的完整状态转换。

状态转换规则：
    PENDING → SUBMITTED → [PARTIAL_FILLED →] FILLED → SETTLED
    PENDING → SUBMITTED → CANCELLED
    PENDING → SUBMITTED → REJECTED
    PENDING → EXPIRED
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.broker.base import BrokerOrderResponse, OrderStatus


@dataclass
class OrderLifecycleEvent:
    """订单生命周期事件。"""

    timestamp: datetime
    from_status: OrderStatus | None
    to_status: OrderStatus
    reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class OrderLifecycleManager:
    """管理单个订单的生命周期和状态转换。

    用法：
        mgr = OrderLifecycleManager(order_response)
        mgr.transition_to(OrderStatus.SUBMITTED, reason="风控通过")
        mgr.transition_to(OrderStatus.FILLED, reason="全部成交")
        print(mgr.current_status)  # FILLED
        print(mgr.history)  # 事件列表
    """

    # 合法的状态转换
    _VALID_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
        OrderStatus.PENDING: {
            OrderStatus.SUBMITTED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
            OrderStatus.CANCELLED,
        },
        OrderStatus.SUBMITTED: {
            OrderStatus.PARTIAL_FILLED,
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
        },
        OrderStatus.PARTIAL_FILLED: {
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
        },
        OrderStatus.FILLED: {
            OrderStatus.SETTLED,
        },
        OrderStatus.SETTLED: set(),  # 终态
        OrderStatus.CANCELLED: set(),  # 终态
        OrderStatus.REJECTED: set(),  # 终态
        OrderStatus.EXPIRED: set(),  # 终态
    }

    def __init__(self, order: BrokerOrderResponse):
        self._order = order
        self._history: list[OrderLifecycleEvent] = []
        self._record_event(None, order.status, "订单创建")

    @property
    def current_status(self) -> OrderStatus:
        return self._order.status

    @property
    def history(self) -> list[OrderLifecycleEvent]:
        return list(self._history)

    @property
    def is_terminal(self) -> bool:
        """是否已到达终态。"""
        return self.current_status in {
            OrderStatus.SETTLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
        }

    def can_transition_to(self, new_status: OrderStatus) -> bool:
        """检查是否允许转换到目标状态。"""
        if self.is_terminal:
            return False
        allowed = self._VALID_TRANSITIONS.get(self.current_status, set())
        return new_status in allowed

    def transition_to(
        self,
        new_status: OrderStatus,
        *,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """执行状态转换。返回是否成功。"""
        if not self.can_transition_to(new_status):
            return False

        old_status = self.current_status
        self._order.status = new_status
        self._order.updated_at = datetime.now()
        self._record_event(old_status, new_status, reason, metadata)
        return True

    def _record_event(
        self,
        from_status: OrderStatus | None,
        to_status: OrderStatus,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._history.append(
            OrderLifecycleEvent(
                timestamp=datetime.now(),
                from_status=from_status,
                to_status=to_status,
                reason=reason,
                metadata=metadata or {},
            )
        )

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典（供日志/审计使用）。"""
        return {
            "order_id": self._order.order_id,
            "current_status": self.current_status.value,
            "is_terminal": self.is_terminal,
            "history": [
                {
                    "timestamp": e.timestamp.isoformat(),
                    "from": e.from_status.value if e.from_status else None,
                    "to": e.to_status.value,
                    "reason": e.reason,
                }
                for e in self._history
            ],
        }
