"""事件驱动架构测试。"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.events.models import (
    BaseEvent,
    EventType,
    MarketDataEvent,
    OrderEvent,
    RiskEvent,
    SystemEvent,
)
from src.events.publisher import EventPublisher


# ===========================================================================
# 事件模型测试
# ===========================================================================


def test_base_event_creation():
    event = BaseEvent(
        event_type=EventType.MARKET_DATA_CHANGE,
        payload={"code": "sh.600000", "price": 10.5},
        source="test",
    )
    assert event.event_type == EventType.MARKET_DATA_CHANGE
    assert event.payload["code"] == "sh.600000"
    assert event.source == "test"
    assert event.event_id is not None
    assert event.timestamp is not None


def test_base_event_to_dict():
    event = BaseEvent(
        event_type=EventType.ORDER_FILLED,
        payload={"order_id": "123"},
        source="order",
        event_id="test-id",
        timestamp="2024-01-01T00:00:00",
    )
    d = event.to_dict()
    assert d["event_id"] == "test-id"
    assert d["event_type"] == "order_filled"
    assert d["timestamp"] == "2024-01-01T00:00:00"
    assert d["source"] == "order"
    assert d["payload"]["order_id"] == "123"


def test_base_event_from_dict():
    data = {
        "event_id": "abc",
        "event_type": "market_data_change",
        "timestamp": "2024-01-01T00:00:00",
        "source": "sina",
        "payload": {"code": "sh.600000", "price": 10.5},
    }
    event = BaseEvent.from_dict(data)
    assert event.event_id == "abc"
    assert event.event_type == EventType.MARKET_DATA_CHANGE
    assert event.payload["price"] == 10.5


def test_market_data_event():
    event = MarketDataEvent(
        code="sh.600000",
        price=10.55,
        change_pct=0.48,
        volume=1000,
    )
    assert event.event_type == EventType.MARKET_DATA_CHANGE
    assert event.payload["code"] == "sh.600000"
    assert event.payload["price"] == 10.55
    assert event.payload["change_pct"] == 0.48


def test_order_event():
    event = OrderEvent(
        order_id="12345",
        code="sh.600000",
        side="buy",
        quantity=100,
        price=10.5,
        status="filled",
    )
    assert event.payload["order_id"] == "12345"
    assert event.payload["status"] == "filled"


def test_risk_event():
    event = RiskEvent(
        rule_name="max_drawdown",
        rule_type="position",
        severity="warning",
        detail="回撤超限",
        context={"drawdown_pct": 0.15},
    )
    assert event.event_type == EventType.RISK_WARNING
    assert event.payload["severity"] == "warning"
    assert event.payload["context"]["drawdown_pct"] == 0.15


def test_system_event():
    event = SystemEvent(
        event_type=EventType.SYSTEM_STARTUP,
        message="系统启动",
    )
    assert event.event_type == EventType.SYSTEM_STARTUP
    assert event.payload["message"] == "系统启动"


# ===========================================================================
# EventBus 测试（mock Redis）
# ===========================================================================


@pytest.mark.asyncio
async def test_bus_publish_redis_disabled():
    """Redis 未启用时，事件被静默丢弃。"""
    from src.events.bus import EventBus

    bus = EventBus()
    event = MarketDataEvent(code="sh.600000", price=10.5)

    with patch("src.events.bus.get_redis_client", return_value=None):
        result = await bus.publish(event)

    assert result is None


@pytest.mark.asyncio
async def test_bus_publish_success():
    """Redis 启用时，事件成功发布。"""
    from src.events.bus import EventBus

    bus = EventBus()
    event = MarketDataEvent(code="sh.600000", price=10.5)

    mock_redis = AsyncMock()
    mock_redis.xadd.return_value = "1234567890-0"

    with patch("src.events.bus.get_redis_client", return_value=mock_redis):
        result = await bus.publish(event)

    assert result == "1234567890-0"
    mock_redis.xadd.assert_called_once()


@pytest.mark.asyncio
async def test_bus_consume():
    """从 Redis Streams 消费事件。"""
    from src.events.bus import EventBus

    bus = EventBus()

    mock_redis = AsyncMock()
    mock_redis.xgroup_create.return_value = True
    mock_redis.xreadgroup.return_value = [
        (
            "tb:event:market_data_change",
            [
                (
                    "123-0",
                    {
                        "event_id": "evt-1",
                        "event_type": "market_data_change",
                        "timestamp": "2024-01-01T00:00:00",
                        "source": "sina",
                        "payload": json.dumps({"code": "sh.600000", "price": 10.5}),
                    },
                ),
            ],
        ),
    ]

    with patch("src.events.bus.get_redis_client", return_value=mock_redis):
        events = await bus.consume("market_data_change", "test_consumer", count=1)

    assert len(events) == 1
    assert events[0].event_id == "evt-1"
    assert events[0].payload["code"] == "sh.600000"


@pytest.mark.asyncio
async def test_bus_ack():
    """确认事件已处理。"""
    from src.events.bus import EventBus

    bus = EventBus()
    event = MarketDataEvent(code="sh.600000", price=10.5)
    event._msg_id = "123-0"
    event._stream = "tb:event:market_data_change"
    event._cg = "tb:cg:test"

    mock_redis = AsyncMock()

    with patch("src.events.bus.get_redis_client", return_value=mock_redis):
        await bus.ack(event)

    mock_redis.xack.assert_called_once()


# ===========================================================================
# EventPublisher 测试
# ===========================================================================


@pytest.mark.asyncio
async def test_publisher_market_data_changed():
    pub = EventPublisher()

    mock_bus = AsyncMock()
    mock_bus.publish.return_value = "123-0"

    with patch.object(pub, "_bus", mock_bus):
        result = await pub.market_data_changed(
            code="sh.600000",
            price=10.55,
            change_pct=0.48,
        )

    assert result == "123-0"
    mock_bus.publish.assert_called_once()
    event = mock_bus.publish.call_args[0][0]
    assert event.event_type == EventType.MARKET_DATA_CHANGE
    assert event.payload["code"] == "sh.600000"


@pytest.mark.asyncio
async def test_publisher_order_filled():
    pub = EventPublisher()

    mock_bus = AsyncMock()
    mock_bus.publish.return_value = "456-0"

    with patch.object(pub, "_bus", mock_bus):
        result = await pub.order_filled(
            order_id="12345",
            code="sh.600000",
            side="buy",
            quantity=100,
            price=10.5,
            filled_quantity=100,
        )

    assert result == "456-0"
    event = mock_bus.publish.call_args[0][0]
    assert event.payload["order_id"] == "12345"
    assert event.payload["status"] == "filled"


@pytest.mark.asyncio
async def test_publisher_risk_blocked():
    pub = EventPublisher()

    mock_bus = AsyncMock()
    mock_bus.publish.return_value = "789-0"

    with patch.object(pub, "_bus", mock_bus):
        result = await pub.risk_blocked(
            rule_name="position_limit",
            rule_type="position",
            detail="持仓超限",
        )

    assert result == "789-0"
    event = mock_bus.publish.call_args[0][0]
    assert event.event_type == EventType.RISK_BLOCKED


# ===========================================================================
# EventConsumer 测试
# ===========================================================================


class TestConsumer:
    """测试用的消费者类。"""

    @pytest.mark.asyncio
    async def test_consumer_lifecycle(self):
        from src.events.consumer import EventConsumer

        class DummyConsumer(EventConsumer):
            async def handle(self, event: BaseEvent) -> None:
                pass

        consumer = DummyConsumer("test", ["market_data_change"])
        assert consumer.name == "test"
        assert not consumer._running

        # 启动
        await consumer.start()
        assert consumer._running

        # 停止
        await consumer.stop()
        assert not consumer._running

    @pytest.mark.asyncio
    async def test_consumer_handle_called(self):
        from src.events.consumer import EventConsumer

        handled_events = []

        class RecordingConsumer(EventConsumer):
            async def handle(self, event: BaseEvent) -> None:
                handled_events.append(event)

        consumer = RecordingConsumer("recorder", ["market_data_change"])

        # 模拟消费事件
        event = MarketDataEvent(code="sh.600000", price=10.5)
        event._msg_id = "123-0"
        event._stream = "tb:event:market_data_change"
        event._cg = "tb:cg:recorder"

        mock_bus = AsyncMock()
        mock_bus.consume.return_value = [event]

        with patch.object(consumer, "_bus", mock_bus):
            await consumer._process_event(event)

        assert len(handled_events) == 1
        assert handled_events[0].payload["code"] == "sh.600000"
        mock_bus.ack.assert_called_once()
