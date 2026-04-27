"""实时行情数据源基类 — 定义统一的行情数据接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class MarketQuote:
    """统一行情快照。"""

    code: str
    name: str | None = None
    price: float = 0.0
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    pre_close: float = 0.0
    change: float = 0.0
    change_pct: float = 0.0
    volume: int = 0
    amount: float = 0.0
    bid1: float = 0.0
    ask1: float = 0.0
    bid1_vol: int = 0
    ask1_vol: int = 0
    timestamp: datetime | None = None
    source: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Subscription:
    """订阅信息。"""

    code: str
    callback: Any | None = None
    created_at: datetime = field(default_factory=datetime.now)


class BaseMarketDataSource(ABC):
    """实时行情数据源抽象基类。

    所有行情源（新浪财经、腾讯财经、东方财富 WebSocket 等）须实现此接口。
    """

    name: str = "base"
    supports_websocket: bool = False
    supports_snapshot: bool = True
    max_subscriptions: int = 1000

    @abstractmethod
    async def connect(self) -> None:
        """建立与数据源的连接。"""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """断开连接。"""
        ...

    @abstractmethod
    async def subscribe(self, code: str) -> bool:
        """订阅标的实时行情。"""
        ...

    @abstractmethod
    async def unsubscribe(self, code: str) -> bool:
        """取消订阅。"""
        ...

    @abstractmethod
    async def get_snapshot(self, code: str) -> MarketQuote | None:
        """获取单标的一次性行情快照。"""
        ...

    @abstractmethod
    async def get_snapshots(self, codes: list[str]) -> dict[str, MarketQuote]:
        """批量获取行情快照。"""
        ...

    async def health_check(self) -> dict[str, Any]:
        """健康检查。"""
        return {"source": self.name, "status": "unknown"}
