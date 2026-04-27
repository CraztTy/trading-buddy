"""API Key 管理 — 创建、列出、删除程序化调用密钥。"""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_user
from src.data.storage.database import get_session
from src.data.storage.models import ApiKeyModel

router = APIRouter()

API_KEY_PREFIX = "tbak_"


class ApiKeyCreate(BaseModel):
    label: str = Field("default", min_length=1, max_length=64)


class ApiKeyItem(BaseModel):
    id: int
    label: str
    last_used_at: str | None
    created_at: str


class ApiKeyCreateResponse(BaseModel):
    id: int
    key: str
    label: str
    created_at: str


class ApiKeyListResponse(BaseModel):
    items: list[ApiKeyItem]
    total: int


def _hash_key(key: str) -> str:
    """对 API Key 做简单 hash（非安全 hash，仅用于防误泄露后的快速比对）。"""
    import hashlib

    return hashlib.sha256(key.encode()).hexdigest()[:64]


def _generate_key() -> str:
    """生成随机 API Key。"""
    return f"{API_KEY_PREFIX}{secrets.token_urlsafe(32)}"


@router.post("/keys", response_model=ApiKeyCreateResponse, status_code=201)
async def create_api_key(
    body: ApiKeyCreate,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> ApiKeyCreateResponse:
    """创建新的 API Key。返回的 key 明文**仅显示一次**，请妥善保存。"""
    user_id = current_user.get("id")
    if user_id is None or user_id == 0:
        raise HTTPException(status_code=400, detail="系统用户不支持 API Key")

    key_plain = _generate_key()
    key_hash = _hash_key(key_plain)

    row = ApiKeyModel(
        user_id=user_id,
        key_hash=key_hash,
        label=body.label,
    )
    session.add(row)
    await session.flush()

    return ApiKeyCreateResponse(
        id=row.id,
        key=key_plain,
        label=row.label,
        created_at=row.created_at.isoformat() if row.created_at else "",
    )


@router.get("/keys", response_model=ApiKeyListResponse)
async def list_api_keys(
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> ApiKeyListResponse:
    """列出当前用户的所有 API Keys（不返回 key 明文）。"""
    user_id = current_user.get("id")
    if user_id is None or user_id == 0:
        return ApiKeyListResponse(items=[], total=0)

    stmt = (
        select(ApiKeyModel)
        .where(ApiKeyModel.user_id == user_id)
        .order_by(desc(ApiKeyModel.created_at))
    )
    result = await session.execute(stmt)
    rows = result.scalars().all()

    items = [
        ApiKeyItem(
            id=r.id,
            label=r.label,
            last_used_at=r.last_used_at.isoformat() if r.last_used_at else None,
            created_at=r.created_at.isoformat() if r.created_at else "",
        )
        for r in rows
    ]

    return ApiKeyListResponse(items=items, total=len(items))


@router.delete("/keys/{key_id}", status_code=204)
async def delete_api_key(
    key_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> Response:
    """删除指定 API Key。"""
    user_id = current_user.get("id")
    if user_id is None or user_id == 0:
        raise HTTPException(status_code=400, detail="系统用户不支持 API Key")

    result = await session.execute(
        select(ApiKeyModel).where(ApiKeyModel.id == key_id, ApiKeyModel.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="API Key 不存在")

    await session.delete(row)
    await session.flush()
    return Response(status_code=204)
