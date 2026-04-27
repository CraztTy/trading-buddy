"""事件模型 — 统一的事件数据结构。

所有事件都有：
- event_id: 唯一 ID（UUID）
- event_type: 事件类型枚举
- timestamp: ISO 格式时间戳
- source: 事件来源（模块名）
- payload: 事件具体数据
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4


class EventType(str, Enum):
    """事件类型枚举。"""

    # 行情数据
    MARKET_DATA = "market_data"          # 实时行情快照
    MARKET_DATA_CHANGE = "market_data_change"  # 行情变化

    # 订单生命周期
    ORDER_CREATED = "order_created"      # 订单创建
    ORDER_SUBMITTED = "order_submitted"  # 订单已提交
    ORDER_FILLED = "order_filled"        # 订单成交
    ORDER_CANCELLED = "order_cancelled"  # 订单撤销
    ORDER_REJECTED = "order_rejected"    # 订单被拒

    # 风控
    RISK_VIOLATION = "risk_violation"    # 风控违规
    RISK_WARNING = "risk_warning"        # 风控预警
    RISK_BLOCKED = "risk_blocked"        # 风控拦截

    # 持仓/资金
    POSITION_CHANGED = "position_changed"  # 持仓变化
    BALANCE_CHANGED = "balance_changed"    # 资金变化

    # 系统
    SYSTEM_STARTUP = "system_startup"    # 系统启动
    SYSTEM_SHUTDOWN = "system_shutdown"  # 系统关闭
    SYSTEM_ERROR = "system_error"        # 系统错误


class BaseEvent:
    """事件基类。"""

    def __init__(
        self,
        event_type: EventType,
        payload: dict[str, Any],
        source: str = "unknown",
        event_id: str | None = None,
        timestamp: str | None = None,
    ):
        self.event_id = event_id or str(uuid4())
        self.event_type = event_type
        self.timestamp = timestamp or datetime.now().isoformat()
        self.source = source
        self.payload = payload

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典（供 Redis Streams 使用）。"""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "source": self.source,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BaseEvent:
        """从字典反序列化。"""
        return cls(
            event_type=EventType(data["event_type"]),
            payload=data.get("payload", {}),
            source=data.get("source", "unknown"),
            event_id=data.get("event_id"),
            timestamp=data.get("timestamp"),
        )

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} type={self.event_type.value} id={self.event_id}>"


class MarketDataEvent(BaseEvent):
    """行情数据事件。"""

    def __init__(
        self,
        code: str,
        price: float,
        change_pct: float = 0.0,
        volume: int = 0,
        amount: float = 0.0,
        bid1: float = 0.0,
        ask1: float = 0.0,
        source: str = "market_data",
        **kwargs: Any,
    ):
        super().__init__(
            event_type=EventType.MARKET_DATA_CHANGE,
            payload={
                "code": code,
                "price": price,
                "change_pct": change_pct,
                "volume": volume,
                "amount": amount,
                "bid1": bid1,
                "ask1": ask1,
                **kwargs,
            },
            source=source,
        )


class OrderEvent(BaseEvent):
    """订单事件。"""

    def __init__(
        self,
        order_id: str,
        code: str,
        side: str,
        quantity: int,
        price: float,
        status: str,
        account_label: str = "default",
        source: str = "order",
        **kwargs: Any,
    ):
        event_type = EventType(f"order_{status}") if f"order_{status}" in [e.value for e in EventType] else EventType.ORDER_CREATED
        super().__init__(
            event_type=event_type,
            payload={
                "order_id": order_id,
                "code": code,
                "side": side,
                "quantity": quantity,
                "price": price,
                "status": status,
                "account_label": account_label,
                **kwargs,
            },
            source=source,
        )


class RiskEvent(BaseEvent):
    """风控事件。"""

    def __init__(
        self,
        rule_name: str,
        rule_type: str,
        severity: str,  # "violation" | "warning" | "blocked"
        detail: str,
        context: dict[str, Any] | None = None,
        source: str = "risk",
        **kwargs: Any,
    ):
        event_type = {
            "violation": EventType.RISK_VIOLATION,
            "warning": EventType.RISK_WARNING,
            "blocked": EventType.RISK_BLOCKED,
        }.get(severity, EventType.RISK_WARNING)

        super().__init__(
            event_type=event_type,
            payload={
                "rule_name": rule_name,
                "rule_type": rule_type,
                "severity": severity,
                "detail": detail,
                "context": context or {},
                **kwargs,
            },
            source=source,
        )


class SystemEvent(BaseEvent):
    """系统事件。"""

    def __init__(
        self,
        event_type: EventType,
        message: str,
        detail: dict[str, Any] | None = None,
        source: str = "system",
        **kwargs: Any,
    ):
        super().__init__(
            event_type=event_type,
            payload={
                "message": message,
                "detail": detail or {},
                **kwargs,
            },
            source=source,
        )
