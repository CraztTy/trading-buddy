"""全局 Kill Switch — 紧急停止所有交易与回测执行。

Redis 可用时持久化到 `tb:kill_switch:global`；
否则退回到进程内变量（重启即恢复）。
"""

from __future__ import annotations

from src.common import get_logger
from src.common.redis_client import get_redis_client

logger = get_logger("kill_switch")

_DEFAULT_KEY = "tb:kill_switch:global"

# 内存回退状态（进程级）
_memory_killed = False


async def is_killed(key: str = _DEFAULT_KEY) -> bool:
    """返回当前 kill switch 是否被激活。"""
    r = get_redis_client()
    if r is not None:
        try:
            val = await r.get(key)
            return val == "1"
        except Exception as e:
            logger.warning("Redis kill_switch read failed: %s", e)
            return _memory_killed
    return _memory_killed


async def set_killed(value: bool, key: str = _DEFAULT_KEY) -> None:
    """设置 kill switch 状态。"""
    global _memory_killed
    _memory_killed = value
    r = get_redis_client()
    if r is not None:
        try:
            if value:
                await r.set(key, "1")
            else:
                await r.delete(key)
        except Exception as e:
            logger.warning("Redis kill_switch write failed: %s", e)
    logger.info("Kill switch set to %s", value)


async def check_or_raise(key: str = _DEFAULT_KEY) -> None:
    """检查 kill switch；若已激活则抛出 HTTPException。"""
    from fastapi import HTTPException

    if await is_killed(key):
        raise HTTPException(status_code=503, detail="Kill switch 已激活：交易与回测服务暂停")
