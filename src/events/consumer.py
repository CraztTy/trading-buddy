"""事件消费者基类 — 异步事件消费框架。

用法:
    class MyConsumer(EventConsumer):
        def __init__(self):
            super().__init__("my_consumer", ["market_data_change"])

        async def handle(self, event: BaseEvent):
            if event.event_type.value == "market_data_change":
                print(f"Price update: {event.payload['code']} = {event.payload['price']}")

    consumer = MyConsumer()
    await consumer.start()
    # ...
    await consumer.stop()
"""

from __future__ import annotations

import asyncio
from typing import Any

from src.common import get_logger
from src.events.bus import EventBus
from src.events.models import BaseEvent

logger = get_logger("event_consumer")

# 消费者默认配置
_DEFAULT_BATCH_SIZE = 10
_DEFAULT_POLL_INTERVAL = 1.0
_DEFAULT_BLOCK_MS = 5000


class EventConsumer:
    """事件消费者基类。

    子类须覆盖 `handle(event)` 方法处理事件。
    """

    def __init__(
        self,
        name: str,
        event_types: list[str],
        batch_size: int = _DEFAULT_BATCH_SIZE,
        poll_interval: float = _DEFAULT_POLL_INTERVAL,
        block_ms: int = _DEFAULT_BLOCK_MS,
    ):
        """
        Args:
            name: 消费者名称（用于消费者组）
            event_types: 订阅的事件类型列表
            batch_size: 每次消费的最大事件数
            poll_interval: 轮询间隔（秒）
            block_ms: Redis XREADGROUP 阻塞时间（毫秒）
        """
        self._name = name
        self._event_types = event_types
        self._batch_size = batch_size
        self._poll_interval = poll_interval
        self._block_ms = block_ms
        self._bus = EventBus()
        self._task: asyncio.Task | None = None
        self._running = False
        self._stats = {
            "processed": 0,
            "failed": 0,
            "started_at": None,
        }

    @property
    def name(self) -> str:
        return self._name

    @property
    def stats(self) -> dict[str, Any]:
        return dict(self._stats)

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """启动消费者（在后台任务中运行）。"""
        if self._running:
            return
        self._running = True
        self._stats["started_at"] = asyncio.get_event_loop().time()
        self._task = asyncio.create_task(
            self._consume_loop(),
            name=f"consumer:{self._name}",
        )
        logger.info("consumer started: %s", self._name)

    async def stop(self) -> None:
        """停止消费者。"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("consumer stopped: %s", self._name)

    # ------------------------------------------------------------------
    # 消费循环
    # ------------------------------------------------------------------

    async def _consume_loop(self) -> None:
        """后台消费循环。"""
        while self._running:
            try:
                for event_type in self._event_types:
                    if not self._running:
                        break
                    events = await self._bus.consume(
                        event_type=event_type,
                        consumer_name=self._name,
                        count=self._batch_size,
                        block_ms=self._block_ms,
                    )
                    for event in events:
                        await self._process_event(event)

                # 如果没有事件，短暂休息
                await asyncio.sleep(self._poll_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("consumer loop error [%s]: %s", self._name, e)
                await asyncio.sleep(self._poll_interval)

    async def _process_event(self, event: BaseEvent) -> None:
        """处理单个事件（含异常处理和 ACK）。"""
        try:
            await self.handle(event)
            self._stats["processed"] += 1
        except Exception as e:
            self._stats["failed"] += 1
            logger.error("event handle failed [%s]: %s, event=%s", self._name, e, event)
        finally:
            # 无论处理成功还是失败，都 ACK
            await self._bus.ack(event)

    # ------------------------------------------------------------------
    # 子类须覆盖
    # ------------------------------------------------------------------

    async def handle(self, event: BaseEvent) -> None:
        """处理事件。子类须覆盖此方法。

        Args:
            event: 消费到的事件

        Raises:
            可抛出异常，会被 _process_event 捕获并记录
        """
        raise NotImplementedError(f"Consumer {self._name} must implement handle()")
