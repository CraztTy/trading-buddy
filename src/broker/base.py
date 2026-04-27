"""券商适配层基类 — 定义统一的订单/持仓/资金接口。

订单生命周期：
    pending → submitted → partial_filled → filled → settled
    pending → submitted → cancelled
    pending → submitted → rejected
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any


class OrderStatus(str, Enum):
    """订单状态机。"""

    PENDING = "pending"           # 待提交
    SUBMITTED = "submitted"       # 已提交到券商
    PARTIAL_FILLED = "partial_filled"  # 部分成交
    FILLED = "filled"             # 全部成交
    SETTLED = "settled"           # 已结算（T+1）
    CANCELLED = "cancelled"       # 已撤单
    REJECTED = "rejected"         # 被拒单
    EXPIRED = "expired"           # 已过期


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


@dataclass
class BrokerOrderRequest:
    """统一订单请求。"""

    code: str
    side: OrderSide
    quantity: int
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None
    stop_price: float | None = None
    account_label: str = "default"
    strategy_id: str | None = None
    strategy_version: str | None = None
    tag: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BrokerOrderResponse:
    """统一订单响应。"""

    order_id: str
    code: str
    side: OrderSide
    quantity: int
    filled_quantity: int = 0
    avg_fill_price: float | None = None
    status: OrderStatus = OrderStatus.PENDING
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None
    commission: float = 0.0
    slippage: float = 0.0
    created_at: datetime | None = None
    updated_at: datetime | None = None
    rejected_reason: str | None = None
    broker_raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class BrokerPosition:
    """统一持仓。"""

    code: str
    quantity: int = 0
    available_quantity: int = 0   # 可卖数量（A股 T+1）
    avg_cost: float = 0.0
    market_value: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    updated_at: datetime | None = None


@dataclass
class BrokerBalance:
    """统一资金账户。"""

    cash: float = 0.0
    available_cash: float = 0.0   # 可用资金
    frozen_cash: float = 0.0      # 冻结资金
    market_value: float = 0.0
    total_equity: float = 0.0
    initial_cash: float = 0.0
    margin_used: float = 0.0
    updated_at: datetime | None = None


@dataclass
class BrokerTrade:
    """统一成交记录。"""

    trade_id: str
    order_id: str
    code: str
    side: OrderSide
    quantity: int
    price: float
    amount: float
    commission: float = 0.0
    trade_date: date | None = None
    trade_time: datetime | None = None


class BaseBrokerAdapter(ABC):
    """券商适配器抽象基类。

    所有实盘/模拟/纸交易适配器须实现此接口，
    确保策略代码与具体券商解耦。
    """

    name: str = "base"
    supports_market_order: bool = True
    supports_limit_order: bool = False
    supports_stop_order: bool = False
    supports_cancel: bool = True
    t_plus_n: int = 1  # A股 T+1

    @abstractmethod
    async def connect(self) -> None:
        """建立与券商的连接（如需要）。"""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """断开连接。"""
        ...

    @abstractmethod
    async def place_order(self, request: BrokerOrderRequest) -> BrokerOrderResponse:
        """提交订单。"""
        ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> BrokerOrderResponse:
        """撤单。"""
        ...

    @abstractmethod
    async def get_order(self, order_id: str) -> BrokerOrderResponse | None:
        """查询订单状态。"""
        ...

    @abstractmethod
    async def get_positions(self) -> list[BrokerPosition]:
        """查询持仓。"""
        ...

    @abstractmethod
    async def get_balance(self) -> BrokerBalance:
        """查询资金。"""
        ...

    @abstractmethod
    async def get_trades(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[BrokerTrade]:
        """查询成交记录。"""
        ...

    async def health_check(self) -> dict[str, Any]:
        """适配器健康检查，子类可覆盖。"""
        return {"adapter": self.name, "status": "unknown"}
