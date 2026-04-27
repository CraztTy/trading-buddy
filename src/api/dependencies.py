"""
Trading Buddy - FastAPI 依赖
提供 get_current_user 等通用依赖注入
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.common import get_logger, get_settings
from src.data.storage import get_session
from src.data.storage.models import UserModel

logger = get_logger(__name__)

# FastAPI 安全 scheme（文档中显示 Bearer token）
security = HTTPBearer(auto_error=False)

# 当 AUTH_REQUIRED=false 时返回的默认系统用户
SYSTEM_USER = {"id": 0, "username": "system", "is_active": True}


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    session: AsyncSession = Depends(get_session),
) -> dict:
    """FastAPI 依赖：从 Authorization: Bearer <token> 中解析当前用户。

    - AUTH_REQUIRED=false（默认）时，无 token 返回系统用户（id=0）。
    - AUTH_REQUIRED=true 时，无 token 或 token 无效均抛 401。
    - token 有效时返回 {"id": int, "username": str, "is_active": bool}。
    """
    settings = get_settings().auth

    # AUTH_REQUIRED=false 且无 token -> 返回系统用户
    if not settings.auth_required and (credentials is None or not credentials.credentials):
        user = SYSTEM_USER.copy()
        request.state.current_user = user
        return user

    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        user_id: int | None = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的认证令牌",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    # 查询数据库确认用户存在且有效
    result = await session.execute(
        select(UserModel).where(UserModel.id == user_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户已被禁用",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_dict = {"id": user.id, "username": user.username, "is_active": user.is_active, "role": user.role}
    request.state.current_user = user_dict
    return user_dict


async def require_admin(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """要求当前用户为 admin 角色，否则抛 403。"""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return current_user
