"""
Trading Buddy - 认证路由
提供注册、登录、获取当前用户信息、密码重置、JWT 刷新等功能
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from jose import jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_user, require_admin
from src.common import get_logger, get_settings
from src.common.redis_client import get_redis_client
from src.data.storage import get_session
from src.data.storage.models import UserModel, PasswordResetTokenModel

logger = get_logger(__name__)
router = APIRouter()

# 密码哈希上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 用户名正则：字母、数字、下划线
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]+$")

# 登录失败限制配置
_MAX_LOGIN_ATTEMPTS = 5
_LOGIN_LOCKOUT_MINUTES = 30


def _hash_password(password: str) -> str:
    return pwd_context.hash(password)


def _verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def _create_access_token(user_id: int, username: str, role: str = "user") -> str:
    settings = get_settings().auth
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "type": "access",
        "exp": expire,
    }
    return jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def _create_refresh_token(user_id: int) -> str:
    """创建刷新令牌（有效期更长）。"""
    settings = get_settings().auth
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.jwt_refresh_token_expire_days
    )
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "exp": expire,
    }
    return jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def _verify_refresh_token(token: str) -> int | None:
    """验证刷新令牌，返回用户 ID。"""
    settings = get_settings().auth
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        if payload.get("type") != "refresh":
            return None
        return int(payload.get("sub"))
    except JWTError:
        return None


async def _check_login_attempts(username: str) -> tuple[bool, int]:
    """检查登录失败次数，返回 (是否允许登录, 剩余尝试次数)。"""
    redis = get_redis_client()
    if redis is None:
        return True, _MAX_LOGIN_ATTEMPTS

    key = f"login_attempts:{username}"
    attempts = await redis.get(key)
    if attempts is None:
        return True, _MAX_LOGIN_ATTEMPTS

    count = int(attempts)
    if count >= _MAX_LOGIN_ATTEMPTS:
        ttl = await redis.ttl(key)
        return False, 0

    return True, _MAX_LOGIN_ATTEMPTS - count


async def _record_login_attempt(username: str, success: bool = False) -> None:
    """记录登录尝试。"""
    redis = get_redis_client()
    if redis is None:
        return

    key = f"login_attempts:{username}"

    if success:
        # 登录成功，清除失败记录
        await redis.delete(key)
        return

    # 登录失败，增加计数
    pipe = redis.pipeline()
    pipe.incr(key)
    pipe.expire(key, _LOGIN_LOCKOUT_MINUTES * 60)
    await pipe.execute()


# ---------- Pydantic 请求/响应模型 ----------


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=6, max_length=128)
    email: str | None = Field(None, max_length=128)

    @field_validator("username")
    @classmethod
    def username_alphanumeric_underscore(cls, v: str) -> str:
        if not _USERNAME_RE.match(v):
            raise ValueError("用户名只能包含字母、数字和下划线")
        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        if v is None:
            return v
        # 简单邮箱验证
        email_pattern = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
        if not email_pattern.match(v):
            raise ValueError("邮箱格式不正确")
        return v


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    username: str
    expires_in: int  # access_token 有效期（秒）


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class UserMeResponse(BaseModel):
    id: int
    username: str
    email: str | None
    is_active: bool
    role: str = "user"
    created_at: str | None


class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=6, max_length=128)


class PasswordResetRequest(BaseModel):
    email: str


class PasswordResetConfirmRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=6, max_length=128)


class LogoutResponse(BaseModel):
    message: str


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

    # 检查邮箱是否已存在（如果提供了）
    if body.email:
        result = await session.execute(
            select(UserModel).where(UserModel.email == body.email)
        )
        if result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="邮箱已被注册",
            )

    user = UserModel(
        username=body.username,
        password_hash=_hash_password(body.password),
        email=body.email,
        is_active=True,
        role="user",
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)

    logger.info(f"用户注册成功: id={user.id}, username={user.username}")
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
    }


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    body: LoginRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """用户登录，验证密码后返回 JWT access_token 和 refresh_token。"""
    # 检查登录失败次数
    allowed, remaining = await _check_login_attempts(body.username)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"登录失败次数过多，请 {_LOGIN_LOCKOUT_MINUTES} 分钟后重试",
        )

    result = await session.execute(
        select(UserModel).where(UserModel.username == body.username)
    )
    user = result.scalar_one_or_none()

    if user is None or not _verify_password(body.password, user.password_hash):
        await _record_login_attempt(body.username, success=False)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"用户名或密码错误（剩余尝试次数：{remaining - 1}）",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户已被禁用",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 登录成功，清除失败记录
    await _record_login_attempt(body.username, success=True)

    # 更新最后登录时间
    user.last_login_at = datetime.now(timezone.utc)
    await session.flush()

    access_token = _create_access_token(user.id, user.username, user.role)
    refresh_token = _create_refresh_token(user.id)

    settings = get_settings().auth

    logger.info(f"用户登录成功: id={user.id}, username={user.username}, ip={request.client.host if request.client else 'unknown'}")
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        username=user.username,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    body: RefreshTokenRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """使用刷新令牌获取新的访问令牌。"""
    user_id = _verify_refresh_token(body.refresh_token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的刷新令牌",
        )

    result = await session.execute(
        select(UserModel).where(UserModel.id == user_id)
    )
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已被禁用",
        )

    access_token = _create_access_token(user.id, user.username, user.role)
    refresh_token = _create_refresh_token(user.id)
    settings = get_settings().auth

    logger.info(f"令牌刷新成功: id={user.id}, username={user.username}")
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        username=user.username,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    request: Request,
    current_user: dict = Depends(get_current_user),
) -> LogoutResponse:
    """用户登出（将当前令牌加入黑名单）。"""
    # 获取当前令牌
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        # 将令牌加入黑名单（有效期与令牌相同）
        redis = get_redis_client()
        if redis:
            try:
                payload = jwt.decode(
                    token,
                    get_settings().auth.jwt_secret,
                    algorithms=[get_settings().auth.jwt_algorithm],
                )
                exp = payload.get("exp")
                if exp:
                    ttl = int(exp - datetime.now(timezone.utc).timestamp())
                    if ttl > 0:
                        await redis.setex(f"token_blacklist:{token}", ttl, "1")
            except JWTError:
                pass

    logger.info(f"用户登出: id={current_user['id']}, username={current_user['username']}")
    return LogoutResponse(message="登出成功")


@router.get("/me", response_model=UserMeResponse)
async def me(current_user: dict = Depends(get_current_user)) -> UserMeResponse:
    """获取当前登录用户信息。"""
    return UserMeResponse(
        id=current_user["id"],
        username=current_user["username"],
        email=current_user.get("email"),
        is_active=current_user["is_active"],
        role=current_user.get("role", "user"),
        created_at=current_user.get("created_at"),
    )


@router.post("/password/change")
async def change_password(
    body: PasswordChangeRequest,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """修改当前用户密码。"""
    user_id = current_user["id"]
    if user_id == 0:
        raise HTTPException(status_code=400, detail="系统用户不支持修改密码")

    result = await session.execute(
        select(UserModel).where(UserModel.id == user_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 验证旧密码
    if not _verify_password(body.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="旧密码错误")

    # 更新密码
    user.password_hash = _hash_password(body.new_password)
    await session.flush()

    logger.info(f"密码修改成功: id={user.id}, username={user.username}")
    return {"message": "密码修改成功"}


@router.post("/password/reset-request")
async def request_password_reset(
    body: PasswordResetRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """请求密码重置（发送重置链接到邮箱）。"""
    # 查找用户
    result = await session.execute(
        select(UserModel).where(UserModel.email == body.email)
    )
    user = result.scalar_one_or_none()

    # 无论用户是否存在，都返回相同消息（防止邮箱枚举）
    if user is None:
        return {"message": "如果该邮箱已注册，重置链接将发送到您的邮箱"}

    # 生成重置令牌
    import secrets
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

    reset_token = PasswordResetTokenModel(
        user_id=user.id,
        token=token,
        expires_at=expires_at,
    )
    session.add(reset_token)
    await session.flush()

    # TODO: 发送邮件（实际项目中需要集成邮件服务）
    logger.info(f"密码重置请求: user_id={user.id}, email={body.email}, token={token}")

    return {"message": "如果该邮箱已注册，重置链接将发送到您的邮箱"}


@router.post("/password/reset-confirm")
async def confirm_password_reset(
    body: PasswordResetConfirmRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """确认密码重置（使用令牌设置新密码）。"""
    # 查找有效令牌
    result = await session.execute(
        select(PasswordResetTokenModel)
        .where(
            PasswordResetTokenModel.token == body.token,
            PasswordResetTokenModel.used == False,
            PasswordResetTokenModel.expires_at > datetime.now(timezone.utc),
        )
    )
    reset_token = result.scalar_one_or_none()

    if reset_token is None:
        raise HTTPException(status_code=400, detail="无效或已过期的重置令牌")

    # 查找用户
    result = await session.execute(
        select(UserModel).where(UserModel.id == reset_token.user_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 更新密码
    user.password_hash = _hash_password(body.new_password)
    reset_token.used = True
    await session.flush()

    logger.info(f"密码重置成功: id={user.id}, username={user.username}")
    return {"message": "密码重置成功"}


# ---------------------------------------------------------------------------
# Admin 用户管理
# ---------------------------------------------------------------------------


class UserAdminItem(BaseModel):
    id: int
    username: str
    email: str | None
    is_active: bool
    role: str
    last_login_at: str | None
    created_at: str


class UserRoleUpdate(BaseModel):
    role: str = Field(..., pattern="^(admin|user)$")
    is_active: bool | None = None


class UserCreateByAdmin(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=6, max_length=128)
    email: str | None = Field(None, max_length=128)
    role: str = Field("user", pattern="^(admin|user)$")
    is_active: bool = True


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
            email=r.email,
            is_active=r.is_active,
            role=r.role,
            last_login_at=r.last_login_at.isoformat() if r.last_login_at else None,
            created_at=r.created_at.isoformat() if r.created_at else "",
        )
        for r in rows
    ]


@router.post("/users", response_model=UserAdminItem, status_code=201)
async def create_user_by_admin(
    body: UserCreateByAdmin,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(require_admin),
) -> UserAdminItem:
    """管理员创建用户。"""
    # 检查用户名是否已存在
    result = await session.execute(
        select(UserModel).where(UserModel.username == body.username)
    )
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="用户名已存在",
        )

    # 检查邮箱是否已存在
    if body.email:
        result = await session.execute(
            select(UserModel).where(UserModel.email == body.email)
        )
        if result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="邮箱已被注册",
            )

    user = UserModel(
        username=body.username,
        password_hash=_hash_password(body.password),
        email=body.email,
        role=body.role,
        is_active=body.is_active,
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)

    logger.info(f"管理员创建用户: admin={current_user['username']}, new_user={user.username}")
    return UserAdminItem(
        id=user.id,
        username=user.username,
        email=user.email,
        is_active=user.is_active,
        role=user.role,
        last_login_at=None,
        created_at=user.created_at.isoformat() if user.created_at else "",
    )


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

    # 防止管理员禁用自己
    if user_id == current_user["id"] and body.is_active is False:
        raise HTTPException(status_code=400, detail="不能禁用当前登录的管理员账户")

    user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    await session.flush()

    logger.info(f"管理员修改用户: admin={current_user['username']}, target={user.username}, role={body.role}")
    return UserAdminItem(
        id=user.id,
        username=user.username,
        email=user.email,
        is_active=user.is_active,
        role=user.role,
        last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
        created_at=user.created_at.isoformat() if user.created_at else "",
    )


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(require_admin),
) -> None:
    """删除用户（admin 专用）。"""
    # 防止删除自己
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="不能删除当前登录的管理员账户")

    result = await session.execute(select(UserModel).where(UserModel.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")

    await session.delete(user)
    await session.flush()

    logger.info(f"管理员删除用户: admin={current_user['username']}, deleted={user.username}")
