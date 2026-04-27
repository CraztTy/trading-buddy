"""Broker 统一交易 API — 通过适配器下单/查持仓/查资金。

与具体券商解耦：请求体使用统一接口，
底层由 BrokerAdapter 实现（当前仅 paper）。
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_user
from src.broker import (
    BrokerBalance,
    BrokerOrderRequest,
    BrokerOrderResponse,
    BrokerPosition,
    BrokerTrade,
    OrderSide,
    OrderType,
)
from src.broker.factory import BrokerAdapterFactory
from src.common.config import get_settings
from src.data.storage import get_session
from src.data.storage.paper_repository import LOT_SIZE

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class PlaceOrderRequest(BaseModel):
    code: str = Field(..., min_length=4, max_length=24)
    side: str = Field(..., pattern="^(buy|sell)$")
    quantity: int = Field(..., ge=LOT_SIZE, le=1_000_000)
    order_type: str = Field("market", pattern="^(market|limit)$")
    limit_price: float | None = Field(None, ge=0)
    account_label: str = Field("default", min_length=1, max_length=32)
    tag: str | None = Field(None, max_length=64)
    adapter_type: str = Field("paper", pattern="^(paper|xtquant)$", description="适配器类型: paper(纸交易) 或 xtquant(迅投QMT)")


class OrderResponse(BaseModel):
    order_id: str
    code: str
    side: str
    quantity: int
    filled_quantity: int
    avg_fill_price: float | None
    status: str
    rejected_reason: str | None


class BalanceResponse(BaseModel):
    cash: float
    available_cash: float
    frozen_cash: float
    market_value: float
    total_equity: float
    initial_cash: float


class PositionResponse(BaseModel):
    code: str
    quantity: int
    available_quantity: int
    avg_cost: float
    market_value: float


class TradeResponse(BaseModel):
    trade_id: str
    order_id: str
    code: str
    side: str
    quantity: int
    price: float
    amount: float
    trade_date: str | None


def _user_id_or_system(current_user: dict) -> int | None:
    uid = current_user.get("id", 0)
    return None if uid == 0 else uid


def _to_order_response(r: BrokerOrderResponse) -> OrderResponse:
    return OrderResponse(
        order_id=r.order_id,
        code=r.code,
        side=r.side.value,
        quantity=r.quantity,
        filled_quantity=r.filled_quantity,
        avg_fill_price=r.avg_fill_price,
        status=r.status.value,
        rejected_reason=r.rejected_reason,
    )


def _to_balance_response(b: BrokerBalance) -> BalanceResponse:
    return BalanceResponse(
        cash=b.cash,
        available_cash=b.available_cash,
        frozen_cash=b.frozen_cash,
        market_value=b.market_value,
        total_equity=b.total_equity,
        initial_cash=b.initial_cash,
    )


def _to_position_response(p: BrokerPosition) -> PositionResponse:
    return PositionResponse(
        code=p.code,
        quantity=p.quantity,
        available_quantity=p.available_quantity,
        avg_cost=p.avg_cost,
        market_value=p.market_value,
    )


def _to_trade_response(t: BrokerTrade) -> TradeResponse:
    return TradeResponse(
        trade_id=t.trade_id,
        order_id=t.order_id,
        code=t.code,
        side=t.side.value,
        quantity=t.quantity,
        price=t.price,
        amount=t.amount,
        trade_date=t.trade_date.isoformat() if t.trade_date else None,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


def _create_adapter(
    adapter_type: str,
    session: AsyncSession,
    user_id: int | None,
    account_label: str,
) -> Any:
    """根据 adapter_type 创建对应的 BrokerAdapter。"""
    settings = get_settings()
    adapter_type = adapter_type.strip().lower()

    if adapter_type == "paper":
        return BrokerAdapterFactory.create(
            "paper",
            session=session,
            user_id=user_id,
            account_label=account_label,
        )
    elif adapter_type == "xtquant":
        if not settings.broker.xtquant_account_id or not settings.broker.xtquant_qmt_path:
            raise HTTPException(
                status_code=400,
                detail="xtquant 未配置。请设置 XTQUANT_ACCOUNT_ID 和 XTQUANT_QMT_PATH 环境变量。",
            )
        return BrokerAdapterFactory.create(
            "xtquant",
            account_id=settings.broker.xtquant_account_id,
            qmt_path=settings.broker.xtquant_qmt_path,
            session_id=settings.broker.xtquant_session_id,
        )
    else:
        raise HTTPException(status_code=400, detail=f"未知的 broker adapter: {adapter_type}")


@router.post("/orders", response_model=OrderResponse)
async def broker_place_order(
    body: PlaceOrderRequest,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> OrderResponse:
    """通过 Broker Adapter 提交订单。支持 paper（纸交易）和 xtquant（迅投QMT）。"""
    user_id = _user_id_or_system(current_user)
    adapter = _create_adapter(body.adapter_type, session, user_id, body.account_label)

    req = BrokerOrderRequest(
        code=body.code.strip().lower(),
        side=OrderSide(body.side),
        quantity=body.quantity,
        order_type=OrderType(body.order_type),
        limit_price=body.limit_price,
        account_label=body.account_label,
        tag=body.tag,
    )

    resp = await adapter.place_order(req)
    return _to_order_response(resp)


@router.get("/positions", response_model=list[PositionResponse])
async def broker_positions(
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
    account_label: str = "default",
    adapter_type: str = Query("paper", pattern="^(paper|xtquant)$"),
) -> list[PositionResponse]:
    """查询持仓。"""
    user_id = _user_id_or_system(current_user)
    adapter = _create_adapter(adapter_type, session, user_id, account_label)
    positions = await adapter.get_positions()
    return [_to_position_response(p) for p in positions]


@router.get("/balance", response_model=BalanceResponse)
async def broker_balance(
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
    account_label: str = "default",
    adapter_type: str = Query("paper", pattern="^(paper|xtquant)$"),
) -> BalanceResponse:
    """查询资金。"""
    user_id = _user_id_or_system(current_user)
    adapter = _create_adapter(adapter_type, session, user_id, account_label)
    balance = await adapter.get_balance()
    return _to_balance_response(balance)


@router.get("/trades", response_model=list[TradeResponse])
async def broker_trades(
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
    account_label: str = "default",
    adapter_type: str = Query("paper", pattern="^(paper|xtquant)$"),
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[TradeResponse]:
    """查询成交记录。"""
    user_id = _user_id_or_system(current_user)
    adapter = _create_adapter(adapter_type, session, user_id, account_label)
    trades = await adapter.get_trades(start_date=start_date, end_date=end_date)
    return [_to_trade_response(t) for t in trades]


@router.get("/health", response_model=dict[str, Any])
async def broker_health(
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
    account_label: str = "default",
    adapter_type: str = Query("paper", pattern="^(paper|xtquant)$"),
) -> dict[str, Any]:
    """Broker 适配器健康检查。"""
    user_id = _user_id_or_system(current_user)
    adapter = _create_adapter(adapter_type, session, user_id, account_label)
    return await adapter.health_check()
