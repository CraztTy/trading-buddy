"""
股票代码 -> 名称：优先读 Redis，未命中再批量查库并回写，减少重复查库（云 MySQL 往返）。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis.asyncio import Redis

    from .repositories import StockRepository

KEY_PREFIX = "tb:stkname:"
DEFAULT_TTL_SEC = 86400


async def resolve_stock_names(
    stock_repo: StockRepository,
    codes: Sequence[str],
    *,
    redis_client: Redis | None = None,
    ttl_sec: int = DEFAULT_TTL_SEC,
) -> dict[str, str]:
    """返回 code -> 显示名称；无记录时回退为代码本身。"""
    ordered = list(dict.fromkeys(c.strip() for c in codes if c and c.strip()))
    if not ordered:
        return {}

    resolved: dict[str, str] = {}
    need_db = list(ordered)

    if redis_client is not None:
        keys = [f"{KEY_PREFIX}{c}" for c in ordered]
        vals = await redis_client.mget(keys)
        need_db = []
        for code, raw in zip(ordered, vals, strict=True):
            if raw is not None:
                resolved[code] = raw
            else:
                need_db.append(code)

    if need_db:
        db_map = await stock_repo.get_name_map(need_db)
        resolved.update(db_map)
        if redis_client is not None and db_map:
            pipe = redis_client.pipeline(transaction=False)
            for c, name in db_map.items():
                if name:
                    pipe.setex(f"{KEY_PREFIX}{c}", ttl_sec, name)
            await pipe.execute()

    return {c: resolved.get(c, c) for c in ordered}
