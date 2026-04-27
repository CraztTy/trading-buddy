"""
Trading Buddy - 认证路由
提供注册、登录、获取当前用户信息
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from jose import jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_user, require_admin
from src.common import get_logger, get_settings
from src.data.storage import get_session
from src.data.storage.models import UserModel

logger = get_logger(__name__)
router = APIRouter()

# 密码哈希上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 用户名正则：字母、数字、下划线
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]+$")


def _hash_password(password: str) -> str:
    return pwd_context.hash(password)


def _verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def _create_access_token(user_id: int, username: str) -> str:
    settings = get_settings().auth
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )
    payload = {
        "sub": str(user_id),
        "username": username,
        "exp": expire,
    }
    return jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


# ---------- Pydantic 请求/响应模型 ----------


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=6, max_length=128)

    @field_validator("username")
    @classmethod
    def username_alphanumeric_underscore(cls, v: str) -> str:
        if not _USERNAME_RE.match(v):
            raise ValueError("用户名只能包含字母、数字和下划线")
        return v


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    username: str


class UserMeResponse(BaseModel):
    id: int
    username: str
    is_active: bool
    role: str = "user"

# ---------- 路由 ----------


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """用户注册。用户名 3-32 位，仅允许字母/数字/下划线；密码至少 6 位。"""
    # 检查用户名是否已存在
    result = await session.execute(
        select(UserModel).where(UserModel.username == body.username)
    )
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="用户名已存在",
        )

    user = UserModel(
        username=body.username,
        password_hash=_hash_password(body.password),
        is_active=True,
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)

    logger.info(f"用户注册成功: id={user.id}, username={user.username}")
    return {"id": user.id, "username": user.username}


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """用户登录，验证密码后返回 JWT access_token。"""
    result = await session.execute(
        select(UserModel).where(UserModel.username == body.username)
    )
    user = result.scalar_one_or_none()

    if user is None or not _verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户已被禁用",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = _create_access_token(user.id, user.username)
    logger.info(f"用户登录成功: id={user.id}, username={user.username}")
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        username=user.username,
    )


@router.get("/me", response_model=UserMeResponse)
async def me(current_user: dict = Depends(get_current_user)) -> UserMeResponse:
    """获取当前登录用户信息。"""
    return UserMeResponse(
        id=current_user["id"],
        username=current_user["username"],
        is_active=current_user["is_active"],
        role=current_user.get("role", "user"),
    )


# ---------------------------------------------------------------------------
# Admin 用户管理
# ---------------------------------------------------------------------------


class UserAdminItem(BaseModel):
    id: int
    username: str
    is_active: bool
    role: str
    created_at: str


class UserRoleUpdate(BaseModel):
    role: str = Field(..., pattern="^(admin|user)$")
    is_active: bool | None = None


@router.get("/users", response_model=list[UserAdminItem])
async def list_users(
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(require_admin),
) -> list[UserAdminItem]:
    """列出所有用户（admin 专用）。"""
    result = await session.execute(select(UserModel).order_by(UserModel.id))
    rows = result.scalars().all()
    return [
        UserAdminItem(
            id=r.id,
            username=r.username,
            is_active=r.is_active,
            role=r.role,
            created_at=r.created_at.isoformat() if r.created_at else "",
        )
        for r in rows
    ]


@router.put("/users/{user_id}/role", response_model=UserAdminItem)
async def update_user_role(
    user_id: int,
    body: UserRoleUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(require_admin),
) -> UserAdminItem:
    """修改用户角色或状态（admin 专用）。"""
    result = await session.execute(select(UserModel).where(UserModel.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")

    user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    await session.flush()

    return UserAdminItem(
        id=user.id,
        username=user.username,
        is_active=user.is_active,
        role=user.role,
        created_at=user.created_at.isoformat() if user.created_at else "",
    )
