"""事件总线 — 基于 Redis Streams 的轻量级消息队列。

Redis Streams 特性：
- 持久化：消息不会丢失（直到显式删除）
- 消费者组：支持多个消费者并行消费
- 消息确认：支持 ACK 机制
- 自动创建：stream 不存在时自动创建

架构：
    stream 命名: tb:event:<event_type>
    消费者组:   tb:cg:<consumer_name>

用法:
    bus = EventBus()
    await bus.publish(event)
    events = await bus.consume("market_data_change", "risk_consumer", count=10)
"""

from __future__ import annotations

import json
from typing import Any

from src.common import get_logger
from src.common.redis_client import get_redis_client
from src.events.models import BaseEvent

logger = get_logger("event_bus")

# Stream 前缀
_STREAM_PREFIX = "tb:event:"
# 消费者组前缀
_CG_PREFIX = "tb:cg:"
# 默认最大 stream 长度（防止无限增长）
_MAX_STREAM_LEN = 10000


def _stream_key(event_type: str) -> str:
    """根据事件类型生成 stream key。"""
    return f"{_STREAM_PREFIX}{event_type}"


def _cg_key(consumer_name: str) -> str:
    """根据消费者名生成消费者组 key。"""
    return f"{_CG_PREFIX}{consumer_name}"


class EventBus:
    """基于 Redis Streams 的事件总线。"""

    def __init__(self):
        self._redis = None

    def _get_redis(self):
        """获取 Redis 客户端（延迟初始化）。"""
        if self._redis is None:
            self._redis = get_redis_client()
        return self._redis

    # ------------------------------------------------------------------
    # 发布
    # ------------------------------------------------------------------

    async def publish(self, event: BaseEvent) -> str | None:
        """发布事件到对应 stream。

        Returns:
            stream 消息 ID，如果 Redis 未启用则返回 None（事件被静默丢弃）。
        """
        r = self._get_redis()
        if r is None:
            # Redis 未启用时，事件被静默丢弃（日志记录）
            logger.debug("event dropped (redis disabled): %s", event)
            return None

        stream = _stream_key(event.event_type.value)
        data = event.to_dict()
        # payload 是 dict，需要 JSON 序列化
        data["payload"] = json.dumps(data["payload"], ensure_ascii=False, default=str)

        try:
            # XADD with MAXLEN 防止 stream 无限增长
            msg_id = await r.xadd(stream, data, maxlen=_MAX_STREAM_LEN, approximate=True)
            logger.debug("event published: %s -> %s", event, msg_id)
            return msg_id
        except Exception as e:
            logger.error("event publish failed: %s", e)
            return None

    # ------------------------------------------------------------------
    # 消费
    # ------------------------------------------------------------------

    async def consume(
        self,
        event_type: str,
        consumer_name: str,
        count: int = 10,
        block_ms: int = 5000,
    ) -> list[BaseEvent]:
        """从指定 stream 消费事件。

        Args:
            event_type: 事件类型（如 "market_data_change"）
            consumer_name: 消费者名称（用于消费者组）
            count: 每次最多读取多少条
            block_ms: 阻塞等待时间（毫秒）

        Returns:
            事件列表（可能为空）
        """
        r = self._get_redis()
        if r is None:
            return []

        stream = _stream_key(event_type)
        cg = _cg_key(consumer_name)
        consumer_id = f"{consumer_name}-0"

        # 确保消费者组存在
        try:
            await r.xgroup_create(stream, cg, id="0", mkstream=True)
        except Exception:
            # 消费者组已存在
            pass

        try:
            # XREADGROUP: 从消费者组读取
            raw = await r.xreadgroup(
                groupname=cg,
                consumername=consumer_id,
                streams={stream: ">"},
                count=count,
                block=block_ms,
            )
        except Exception as e:
            logger.error("event consume failed: %s", e)
            return []

        events: list[BaseEvent] = []
        if not raw:
            return events

        # raw 格式: [(stream_name, [(msg_id, {field: value}), ...]), ...]
        for stream_name, messages in raw:
            for msg_id, fields in messages:
                try:
                    # fields 是 dict，payload 需要 JSON 反序列化
                    data = dict(fields)
                    data["payload"] = json.loads(data.get("payload", "{}"))
                    event = BaseEvent.from_dict(data)
                    event._msg_id = msg_id  # 保存 msg_id 用于 ACK
                    event._stream = stream_name
                    event._cg = cg
                    events.append(event)
                except Exception as e:
                    logger.warning("event parse failed: %s", e)
                    # 解析失败的消息也要 ACK，避免阻塞
                    try:
                        await r.xack(stream, cg, msg_id)
                    except Exception:
                        pass

        return events

    async def ack(self, event: BaseEvent) -> None:
        """确认事件已处理（ACK）。"""
        r = self._get_redis()
        if r is None:
            return

        msg_id = getattr(event, "_msg_id", None)
        stream = getattr(event, "_stream", None)
        cg = getattr(event, "_cg", None)

        if msg_id and stream and cg:
            try:
                await r.xack(stream, cg, msg_id)
                logger.debug("event acked: %s", msg_id)
            except Exception as e:
                logger.warning("event ack failed: %s", e)

    # ------------------------------------------------------------------
    # 管理
    # ------------------------------------------------------------------

    async def stream_info(self, event_type: str) -> dict[str, Any]:
        """获取 stream 信息。"""
        r = self._get_redis()
        if r is None:
            return {"error": "redis not available"}

        stream = _stream_key(event_type)
        try:
            info = await r.xinfo_stream(stream)
            return {
                "length": info.get("length", 0),
                "radix-tree-keys": info.get("radix-tree-keys", 0),
                "groups": info.get("groups", 0),
                "last-generated-id": info.get("last-generated-id", ""),
                "first-entry": info.get("first-entry"),
                "last-entry": info.get("last-entry"),
            }
        except Exception as e:
            return {"error": str(e)}

    async def pending(self, event_type: str, consumer_name: str) -> int:
        """获取待处理（未 ACK）的消息数量。"""
        r = self._get_redis()
        if r is None:
            return 0

        stream = _stream_key(event_type)
        cg = _cg_key(consumer_name)
        try:
            info = await r.xpending(stream, cg)
            return info.get("pending", 0)
        except Exception:
            return 0
