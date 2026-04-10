"""按 IP 的滑动窗口限流（用于实时行情等易被打爆的接口）。"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from src.common import get_settings

_lock = asyncio.Lock()
# client_key -> 单调时钟时间戳队列
_buckets: dict[str, deque[float]] = defaultdict(deque)

_limiter_rpm: int | None = None


def _client_key(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip() or "unknown"
    if request.client:
        return request.client.host
    return "unknown"


async def enforce_realtime_rate_limit(request: Request) -> None:
    """超过配额返回 429。"""
    global _limiter_rpm
    rpm = get_settings().api.realtime_rate_per_minute
    if _limiter_rpm != rpm:
        _limiter_rpm = rpm
        async with _lock:
            _buckets.clear()

    key = _client_key(request)
    now = time.monotonic()
    window = 60.0

    async with _lock:
        dq = _buckets[key]
        cutoff = now - window
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= rpm:
            raise HTTPException(
                status_code=429,
                detail="请求过于频繁，请稍后再试",
                headers={"Retry-After": "60"},
            )
        dq.append(now)
