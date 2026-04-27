"""实时行情接入层 — 统一行情数据源接口。

支持：
- HTTP 轮询（新浪财经、腾讯财经）
- WebSocket 推送（后端聚合后推送前端）
- 多级缓存（内存 + Redis）

用法：
    from src.market_data import MarketDataManager
    mgr = MarketDataManager()
    await mgr.start()
    await mgr.subscribe("sh.600000", ws_connection)
    quote = await mgr.get_quote("sh.600000")
"""

from __future__ import annotations

from src.market_data.base import BaseMarketDataSource, MarketQuote, Subscription
from src.market_data.manager import MarketDataManager
from src.market_data.sina_source import SinaMarketDataSource

__all__ = [
    "BaseMarketDataSource",
    "MarketQuote",
    "Subscription",
    "MarketDataManager",
    "SinaMarketDataSource",
]
