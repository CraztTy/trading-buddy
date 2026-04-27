"""实时行情管理器 — 订阅管理 + WebSocket 广播。

用法:
    from src.market_data import MarketDataManager
    mgr = MarketDataManager()
    await mgr.start()
    await mgr.subscribe("sh.600000", ws_connection)
    quote = await mgr.get_quote("sh.600000")
    await mgr.unsubscribe("sh.600000", ws_connection)
    await mgr.stop()

设计:
- 每个 WebSocket 连接可订阅多个标的
- 后台任务定期拉取行情，有变化时广播给订阅者
- 支持多数据源（优先 sina，fallback baostock）
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket

from src.common import get_logger
from src.market_data.base import MarketQuote
from src.market_data.sina_source import SinaMarketDataSource

logger = get_logger("market_data_manager")

# 行情拉取间隔（秒）
_POLL_INTERVAL = 3.0

# 无订阅者时的空闲等待（秒）
_IDLE_INTERVAL = 5.0


class MarketDataManager:
    """实时行情管理器 — 连接管理 + 订阅管理 + 广播。"""

    def __init__(self):
        self._source = SinaMarketDataSource()
        self._subscribers: dict[str, set[WebSocket]] = {}  # code -> {ws1, ws2, ...}
        self._last_quotes: dict[str, MarketQuote] = {}
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._running = False

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """启动行情管理器。"""
        if self._running:
            return
        self._running = True
        await self._source.connect()
        self._task = asyncio.create_task(self._poll_loop(), name="md_poll_loop")
        logger.info("market data manager started")

    async def stop(self) -> None:
        """停止行情管理器。"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self._source.disconnect()
        self._subscribers.clear()
        self._last_quotes.clear()
        logger.info("market data manager stopped")

    # ------------------------------------------------------------------
    # 订阅管理
    # ------------------------------------------------------------------

    async def subscribe(self, code: str, ws: WebSocket) -> None:
        """为指定 WebSocket 连接订阅标的。"""
        code = code.strip().lower()
        async with self._lock:
            if code not in self._subscribers:
                self._subscribers[code] = set()
            self._subscribers[code].add(ws)
            await self._source.subscribe(code)

        logger.debug("subscribed %s, total subs for code: %d", code, len(self._subscribers[code]))

        # 立即推送最新数据（如果有缓存）
        last = self._last_quotes.get(code)
        if last:
            await self._send_quote(ws, last)

    async def unsubscribe(self, code: str, ws: WebSocket) -> None:
        """为指定 WebSocket 连接取消订阅。"""
        code = code.strip().lower()
        async with self._lock:
            subs = self._subscribers.get(code)
            if subs:
                subs.discard(ws)
                if not subs:
                    del self._subscribers[code]
                    self._last_quotes.pop(code, None)

        logger.debug("unsubscribed %s", code)

    async def unsubscribe_all(self, ws: WebSocket) -> None:
        """取消指定 WebSocket 的所有订阅（连接断开时调用）。"""
        async with self._lock:
            empty_codes = []
            for code, subs in self._subscribers.items():
                subs.discard(ws)
                if not subs:
                    empty_codes.append(code)
            for code in empty_codes:
                del self._subscribers[code]
                self._last_quotes.pop(code, None)

        logger.debug("unsubscribed all for ws")

    def subscribed_codes(self, ws: WebSocket | None = None) -> list[str]:
        """返回已订阅的标的列表。"""
        if ws is None:
            return list(self._subscribers.keys())
        return [
            code for code, subs in self._subscribers.items() if ws in subs
        ]

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    async def get_quote(self, code: str) -> MarketQuote | None:
        """获取单标的最新行情。"""
        code = code.strip().lower()
        cached = self._last_quotes.get(code)
        if cached:
            return cached

        # 实时拉取
        quote = await self._source.get_snapshot(code)
        if quote:
            self._last_quotes[code] = quote
        return quote

    # ------------------------------------------------------------------
    # 后台轮询
    # ------------------------------------------------------------------

    async def _poll_loop(self) -> None:
        """后台轮询循环：定期拉取行情，有变化时广播。"""
        while self._running:
            try:
                codes = list(self._subscribers.keys())
                if not codes:
                    await asyncio.sleep(_IDLE_INTERVAL)
                    continue

                # 批量拉取
                quotes = await self._source.get_snapshots(codes)

                # 检查变化并广播
                for code, quote in quotes.items():
                    last = self._last_quotes.get(code)
                    if self._quote_changed(last, quote):
                        self._last_quotes[code] = quote
                        await self._broadcast(code, quote)

                await asyncio.sleep(_POLL_INTERVAL)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("poll loop error: %s", e)
                await asyncio.sleep(_POLL_INTERVAL)

    @staticmethod
    def _quote_changed(old: MarketQuote | None, new: MarketQuote) -> bool:
        """检查行情是否有有意义的变化（价格或成交量变化）。"""
        if old is None:
            return True
        if old.price != new.price:
            return True
        if old.volume != new.volume:
            return True
        if old.bid1 != new.bid1:
            return True
        if old.ask1 != new.ask1:
            return True
        return False

    # ------------------------------------------------------------------
    # 广播
    # ------------------------------------------------------------------

    async def _broadcast(self, code: str, quote: MarketQuote) -> None:
        """向订阅了该标的的所有 WebSocket 广播行情，并发布到事件总线。"""
        # WebSocket 广播
        subs = self._subscribers.get(code, set()).copy()
        if not subs:
            return

        dead_ws = set()
        for ws in subs:
            try:
                await self._send_quote(ws, quote)
            except Exception:
                dead_ws.add(ws)

        # 清理已断开的连接
        if dead_ws:
            async with self._lock:
                for ws in dead_ws:
                    for c, s in self._subscribers.items():
                        s.discard(ws)

        # 发布到事件总线（Redis Streams）
        try:
            from src.events.publisher import EventPublisher
            pub = EventPublisher()
            await pub.market_data_changed(
                code=quote.code,
                price=quote.price,
                change_pct=quote.change_pct or 0.0,
                volume=quote.volume,
                amount=quote.amount,
                bid1=quote.bid1,
                ask1=quote.ask1,
                high=quote.high,
                low=quote.low,
                open=quote.open,
                pre_close=quote.pre_close,
            )
        except Exception:
            # 事件发布失败不影响行情广播
            pass

    @staticmethod
    async def _send_quote(ws: WebSocket, quote: MarketQuote) -> None:
        """向单个 WebSocket 发送行情数据。"""
        await ws.send_json({
            "type": "quote",
            "code": quote.code,
            "name": quote.name,
            "price": quote.price,
            "open": quote.open,
            "high": quote.high,
            "low": quote.low,
            "pre_close": quote.pre_close,
            "change": quote.change,
            "change_pct": quote.change_pct,
            "volume": quote.volume,
            "amount": quote.amount,
            "bid1": quote.bid1,
            "ask1": quote.ask1,
            "bid1_vol": quote.bid1_vol,
            "ask1_vol": quote.ask1_vol,
            "timestamp": quote.timestamp.isoformat() if quote.timestamp else None,
            "source": quote.source,
        })

    async def health_check(self) -> dict[str, Any]:
        """健康检查。"""
        source_health = await self._source.health_check()
        return {
            "manager": "ok",
            "running": self._running,
            "subscribed_codes": len(self._subscribers),
            "total_subscribers": sum(len(s) for s in self._subscribers.values()),
            "source": source_health,
        }
