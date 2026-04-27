"""事件驱动架构 — 统一事件总线、发布/消费。

基于 Redis Streams 实现轻量级消息队列，无需额外部署 Kafka。

用法:
    # 发布事件
    from src.events import EventBus, MarketDataEvent
    bus = EventBus()
    await bus.publish(MarketDataEvent(code="sh.600000", price=10.55))

    # 消费事件
    from src.events import EventConsumer
    class MyConsumer(EventConsumer):
        async def handle(self, event: BaseEvent):
            print(event)
    consumer = MyConsumer(bus)
    await consumer.start()
"""

from __future__ import annotations

from src.events.bus import EventBus
from src.events.consumer import EventConsumer
from src.events.models import (
    BaseEvent,
    EventType,
    MarketDataEvent,
    OrderEvent,
    RiskEvent,
    SystemEvent,
)
from src.events.publisher import EventPublisher

__all__ = [
    "BaseEvent",
    "EventBus",
    "EventConsumer",
    "EventPublisher",
    "EventType",
    "MarketDataEvent",
    "OrderEvent",
    "RiskEvent",
    "SystemEvent",
]