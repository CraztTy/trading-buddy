"""券商适配层 — 统一订单/持仓/资金接口，支持纸交易与实盘切换。"""

from __future__ import annotations

from src.broker.base import (
    BaseBrokerAdapter,
    BrokerOrderRequest,
    BrokerOrderResponse,
    BrokerPosition,
    BrokerBalance,
    BrokerTrade,
    OrderStatus,
    OrderSide,
    OrderType,
)
from src.broker.factory import BrokerAdapterFactory
from src.broker.paper_adapter import PaperBrokerAdapter

__all__ = [
    "BaseBrokerAdapter",
    "BrokerAdapterFactory",
    "BrokerOrderRequest",
    "BrokerOrderResponse",
    "BrokerPosition",
    "BrokerBalance",
    "BrokerTrade",
    "OrderStatus",
    "OrderSide",
    "OrderType",
    "PaperBrokerAdapter",
]
