"""实时行情 JSON 短缓存：优先 Redis，否则进程内内存。"""

from __future__ import annotations

import asyncio
import json
import time
from src.common import get_settings
from src.common.redis_client import get_redis_client

_mem: dict[str, tuple[float, str]] = {}
_mem_lock = asyncio.Lock()

REDIS_PREFIX = "tb:rt:"


async def cache_get(key: str) -> str | None:
    r = get_redis_client()
    if r is not None:
        return await r.get(f"{REDIS_PREFIX}{key}")
    now = time.monotonic()
    async with _mem_lock:
        hit = _mem.get(key)
        if not hit:
            return None
        exp_mono, payload = hit
        if now > exp_mono:
            del _mem[key]
            return None
        return payload


async def cache_set(key: str, payload: str, ttl_sec: int) -> None:
    r = get_redis_client()
    if r is not None:
        await r.setex(f"{REDIS_PREFIX}{key}", ttl_sec, payload)
        return
    async with _mem_lock:
        _mem[key] = (time.monotonic() + float(ttl_sec), payload)
        if len(_mem) > 5000:
            # 简单瘦身：删掉已过期项
            now = time.monotonic()
            dead = [k for k, (exp, _) in _mem.items() if now > exp]
            for k in dead[:2000]:
                _mem.pop(k, None)


def cache_ttl() -> int:
    return max(1, get_settings().api.realtime_cache_ttl_sec)


def stable_key_quote(codes: list[str]) -> str:
    return "q:" + "|".join(sorted(codes))


def stable_key_batch() -> str:
    return "batch:main_indices"
