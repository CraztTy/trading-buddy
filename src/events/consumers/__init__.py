"""事件消费者集合。

- RiskMonitorConsumer: 实时风控监控（行情变化 → 持仓风险检查）
- AuditLogConsumer: 审计日志（订单/风控事件 → 审计日志表）
- AlertConsumer: 告警通知（风控违规 → 告警）
"""

from __future__ import annotations

from src.events.consumers.audit_consumer import AuditLogConsumer
from src.events.consumers.risk_consumer import RiskMonitorConsumer

__all__ = [
    "AuditLogConsumer",
    "RiskMonitorConsumer",
]