"""Rate limiting — 按 IP + 按用户，支持分布式 Redis 计数器。

用法：
    from src.api.rate_limit import RateLimiter
    limiter = RateLimiter()
    await limiter.check(request, user_id=123, rpm=60)
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from src.common import get_settings
from src.common.redis_client import get_redis_client

_lock = asyncio.Lock()
# client_key -> 单调时钟时间戳队列（内存回退）
_buckets: dict[str, deque[float]] = defaultdict(deque)

_limiter_rpm: int | None = None


class RateLimiter:
    """统一的限流器：优先 Redis（分布式），回退内存（单机）。"""

    def __init__(self):
        self._settings = get_settings()

    def _client_key(self, request: Request) -> str:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip() or "unknown"
        if request.client:
            return request.client.host
        return "unknown"

    def _user_key(self, user_id: int | None) -> str | None:
        return f"user:{user_id}" if user_id else None

    async def _check_redis(self, key: str, rpm: int, window: int = 60) -> bool:
        """Redis 滑动窗口计数器。返回 True 表示允许通过。"""
        r = get_redis_client()
        if r is None:
            return True  # Redis 不可用时放行（由内存回退处理）

        redis_key = f"tb:ratelimit:{key}"
        now = time.time()
        cutoff = now - window

        try:
            pipe = r.pipeline()
            pipe.zremrangebyscore(redis_key, 0, cutoff)
            pipe.zcard(redis_key)
            pipe.zadd(redis_key, {str(now): now})
            pipe.expire(redis_key, window)
            _, count, _, _ = await pipe.execute()
            return count < rpm
        except Exception:
            return True  # Redis 异常时放行（由内存回退处理）

    async def _check_memory(self, key: str, rpm: int, window: float = 60.0) -> bool:
        """内存滑动窗口计数器。返回 True 表示允许通过。"""
        now = time.monotonic()
        async with _lock:
            dq = _buckets[key]
            cutoff = now - window
            while dq and dq[0] < cutoff:
                dq.popleft()
            if len(dq) >= rpm:
                return False
            dq.append(now)
            return True

    async def check(
        self,
        request: Request,
        *,
        user_id: int | None = None,
        rpm: int | None = None,
    ) -> None:
        """检查限流。超过配额返回 429。

        :param request: FastAPI Request 对象
        :param user_id: 用户 ID（有则优先按用户限流）
        :param rpm: 每分钟请求上限（None 时使用配置默认值）
        """
        rpm = rpm or self._settings.api.realtime_rate_per_minute or 60
        if rpm <= 0:
            return

        # 优先按用户限流，其次按 IP
        user_key = self._user_key(user_id)
        ip_key = self._client_key(request)

        allowed = True

        # 用户级限流（Redis 优先）
        if user_key:
            redis_allowed = await self._check_redis(user_key, rpm)
            if not redis_allowed:
                allowed = False
            elif not await self._check_memory(user_key, rpm):
                allowed = False

        # IP 级限流（更严格，即使用户级通过也检查）
        if allowed:
            redis_allowed = await self._check_redis(ip_key, rpm)
            if not redis_allowed:
                allowed = False
            elif not await self._check_memory(ip_key, rpm):
                allowed = False

        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="请求过于频繁，请稍后再试",
                headers={"Retry-After": "60"},
            )


# 兼容旧接口：按 IP 限流（用于 realtime 等已有端点）
async def enforce_realtime_rate_limit(request: Request) -> None:
    """超过配额返回 429。"""
    limiter = RateLimiter()
    await limiter.check(request)
