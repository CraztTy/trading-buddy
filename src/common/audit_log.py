"""审计日志工具 — 记录交易操作、风控变更、系统管理事件。

用法：
    from src.common.audit_log import log_audit
    await log_audit(session, action="paper_order", resource_type="order", ...)

或通过中间件自动记录 API 请求。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.data.storage.models import AuditLogModel
from src.common import get_logger

logger = get_logger("audit")


async def log_audit(
    session: AsyncSession,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    detail: dict[str, Any] | None = None,
    user_id: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    success: bool = True,
    error_message: str | None = None,
) -> AuditLogModel:
    """写入一条审计日志。

    :param action: 操作类型，如 paper_order, backtest_run, risk_rule_update
    :param resource_type: 资源类型，如 order, backtest, risk_rule
    :param resource_id: 资源标识
    :param detail: JSON 详情
    :param user_id: 用户 ID
    :param ip_address: 客户端 IP
    :param user_agent: 客户端 UA
    :param success: 是否成功
    :param error_message: 错误信息
    """
    row = AuditLogModel(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=detail or {},
        ip_address=ip_address,
        user_agent=user_agent,
        success=success,
        error_message=error_message,
        created_at=datetime.now(),
    )
    session.add(row)
    await session.flush()
    logger.debug("audit_log %s %s uid=%s", action, resource_type, user_id)
    return row
