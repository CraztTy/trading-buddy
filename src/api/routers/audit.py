"""审计日志 API — 查询交易操作、风控变更等审计记录。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_user
from src.data.storage.database import get_session
from src.data.storage.models import AuditLogModel

router = APIRouter()


class AuditLogItem(BaseModel):
    id: int
    action: str
    resource_type: str
    resource_id: str | None
    detail: dict[str, Any]
    user_id: int | None
    ip_address: str | None
    success: bool
    error_message: str | None
    created_at: str


class AuditLogListResponse(BaseModel):
    items: list[AuditLogItem]
    total: int
    limit: int
    offset: int


def _user_id_or_system(current_user: dict) -> int | None:
    uid = current_user.get("id", 0)
    return None if uid == 0 else uid


@router.get("/logs", response_model=AuditLogListResponse)
async def list_audit_logs(
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    action: str | None = Query(None, description="操作类型过滤，如 paper_order, backtest_run"),
    resource_type: str | None = Query(None, description="资源类型过滤"),
    success: bool | None = Query(None, description="是否成功"),
    start_date: date | None = Query(None, description="起始日期（含）"),
    end_date: date | None = Query(None, description="结束日期（含）"),
) -> AuditLogListResponse:
    """查询审计日志列表。系统用户可查看全部，普通用户只能查看自己的记录。"""
    user_id = _user_id_or_system(current_user)

    # 基础查询
    stmt = select(AuditLogModel)
    count_stmt = select(func.count()).select_from(AuditLogModel)

    # admin 可查看全部，普通用户只能查看自己的记录
    is_admin = current_user.get("role") == "admin"
    if user_id is not None and not is_admin:
        stmt = stmt.where(AuditLogModel.user_id == user_id)
        count_stmt = count_stmt.where(AuditLogModel.user_id == user_id)

    if action:
        stmt = stmt.where(AuditLogModel.action == action)
        count_stmt = count_stmt.where(AuditLogModel.action == action)
    if resource_type:
        stmt = stmt.where(AuditLogModel.resource_type == resource_type)
        count_stmt = count_stmt.where(AuditLogModel.resource_type == resource_type)
    if success is not None:
        stmt = stmt.where(AuditLogModel.success == success)
        count_stmt = count_stmt.where(AuditLogModel.success == success)
    if start_date:
        stmt = stmt.where(AuditLogModel.created_at >= datetime.combine(start_date, datetime.min.time()))
        count_stmt = count_stmt.where(AuditLogModel.created_at >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        stmt = stmt.where(AuditLogModel.created_at <= datetime.combine(end_date, datetime.max.time()))
        count_stmt = count_stmt.where(AuditLogModel.created_at <= datetime.combine(end_date, datetime.max.time()))

    # 排序和分页
    stmt = stmt.order_by(desc(AuditLogModel.created_at)).offset(offset).limit(limit)

    result = await session.execute(stmt)
    rows = result.scalars().all()

    total_result = await session.execute(count_stmt)
    total = total_result.scalar_one()

    items = [
        AuditLogItem(
            id=r.id,
            action=r.action,
            resource_type=r.resource_type,
            resource_id=r.resource_id,
            detail=dict(r.detail or {}),
            user_id=r.user_id,
            ip_address=r.ip_address,
            success=r.success,
            error_message=r.error_message,
            created_at=r.created_at.isoformat() if r.created_at else "",
        )
        for r in rows
    ]

    return AuditLogListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/stats")
async def audit_stats(
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
    days: int = Query(7, ge=1, le=90, description="统计最近 N 天"),
) -> dict:
    """审计统计：最近 N 天的操作分布。"""
    user_id = _user_id_or_system(current_user)

    from datetime import timedelta

    since = datetime.now() - timedelta(days=days)

    # 总记录数
    count_stmt = select(func.count()).select_from(AuditLogModel).where(AuditLogModel.created_at >= since)
    if user_id is not None:
        count_stmt = count_stmt.where(AuditLogModel.user_id == user_id)
    total_result = await session.execute(count_stmt)
    total = total_result.scalar_one()

    # 成功/失败数
    success_stmt = (
        select(func.count())
        .select_from(AuditLogModel)
        .where(AuditLogModel.created_at >= since, AuditLogModel.success == True)
    )
    if user_id is not None:
        success_stmt = success_stmt.where(AuditLogModel.user_id == user_id)
    success_result = await session.execute(success_stmt)
    success_count = success_result.scalar_one()

    # 按 action 分组
    action_stmt = (
        select(AuditLogModel.action, func.count())
        .where(AuditLogModel.created_at >= since)
        .group_by(AuditLogModel.action)
        .order_by(desc(func.count()))
    )
    if user_id is not None:
        action_stmt = action_stmt.where(AuditLogModel.user_id == user_id)
    action_result = await session.execute(action_stmt)
    action_breakdown = {action: count for action, count in action_result.all()}

    return {
        "period_days": days,
        "total": total,
        "success": success_count,
        "failed": total - success_count,
        "action_breakdown": action_breakdown,
    }
