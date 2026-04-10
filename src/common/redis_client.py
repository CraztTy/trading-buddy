"""可选异步 Redis 客户端，由 FastAPI lifespan 创建与关闭。"""

from __future__ import annotations

from redis.asyncio import Redis

_client: Redis | None = None


def get_redis_client() -> Redis | None:
    return _client


async def init_redis_client(
    host: str,
    port: int,
    db: int,
    password: str | None,
) -> Redis:
    global _client
    if _client is not None:
        return _client
    _client = Redis(
        host=host,
        port=port,
        db=db,
        password=password or None,
        decode_responses=True,
    )
    await _client.ping()
    return _client


async def close_redis_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
