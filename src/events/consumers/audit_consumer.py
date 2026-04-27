"""审计日志消费者 — 将订单/风控事件写入审计日志表。

订阅:
- order_created / order_filled / order_cancelled / order_rejected
- risk_violation / risk_warning / risk_blocked

用法:
    consumer = AuditLogConsumer()
    await consumer.start()
"""

from __future__ import annotations

from src.common import get_logger
from src.common.audit_log import AuditLogLevel, log_audit
from src.events.consumer import EventConsumer
from src.events.models import BaseEvent

logger = get_logger("audit_consumer")


class AuditLogConsumer(EventConsumer):
    """审计日志消费者。"""

    def __init__(self):
        super().__init__(
            name="audit_log",
            event_types=[
                "order_created",
                "order_filled",
                "order_cancelled",
                "order_rejected",
                "risk_violation",
                "risk_warning",
                "risk_blocked",
            ],
            batch_size=20,
            poll_interval=1.0,
        )

    async def handle(self, event: BaseEvent) -> None:
        """将事件写入审计日志。"""
        event_type = event.event_type.value
        payload = event.payload

        # 映射事件类型到审计动作
        action_map = {
            "order_created": "ORDER_CREATE",
            "order_filled": "ORDER_FILL",
            "order_cancelled": "ORDER_CANCEL",
            "order_rejected": "ORDER_REJECT",
            "risk_violation": "RISK_VIOLATION",
            "risk_warning": "RISK_WARNING",
            "risk_blocked": "RISK_BLOCK",
        }
        action = action_map.get(event_type, "UNKNOWN")

        # 确定日志级别
        level = AuditLogLevel.INFO
        if "risk_violation" in event_type or "risk_blocked" in event_type:
            level = AuditLogLevel.WARNING
        if "order_rejected" in event_type:
            level = AuditLogLevel.WARNING

        # 构建审计详情
        detail = {
            "event_id": event.event_id,
            "event_type": event_type,
            "timestamp": event.timestamp,
            "source": event.source,
            "payload": payload,
        }

        # 写入审计日志
        log_audit(
            action=action,
            resource_type="event",
            resource_id=event.event_id,
            detail=detail,
            level=level,
        )

        logger.debug("audit log written: %s %s", action, event.event_id)
