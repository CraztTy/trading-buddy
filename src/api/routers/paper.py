"""
纸交易 API：研究 / 回测之后，用最近一根日 K 收盘价做市价撮合（MVP）。
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.data.storage import KlineRepository, get_session
from src.data.storage.paper_repository import LOT_SIZE, PaperRepository

router = APIRouter()


class PaperOrderRequest(BaseModel):
    code: str = Field(..., min_length=4, max_length=24, description="标的代码，如 sh.600000")
    side: str = Field(..., description="buy 或 sell")
    quantity: int = Field(
        ...,
        ge=LOT_SIZE,
        le=1_000_000,
        description="股数：须为 100 的整数倍（A 股一手）",
    )
    adjust_flag: str = Field("3", description="复权类型: 1=后复权 2=前复权 3=不复权")

    @field_validator("quantity")
    @classmethod
    def lot_step(cls, v: int) -> int:
        if v % LOT_SIZE != 0:
            raise ValueError("股数须为 100 的整数倍且不少于 100")
        return v


class PaperOrderResponse(BaseModel):
    id: int
    code: str
    side: str
    quantity: int
    fill_price: float
    fill_amount: float
    trade_date: str | None
    cash_after: float


class PaperOrderListItem(BaseModel):
    id: int
    code: str
    side: str
    quantity: int
    fill_price: float
    fill_amount: float
    trade_date: str | None
    created_at: str | None


class PaperOrdersListResponse(BaseModel):
    items: list[PaperOrderListItem]
    total: int
    limit: int
    offset: int


def _norm_code(raw: str) -> str:
    c = (raw or "").strip().lower()
    if not c:
        raise HTTPException(status_code=400, detail="code 不能为空")
    return c


@router.get("/state")
async def paper_state(
    adjust_flag: str = Query("3", description="复权类型: 1=后复权 2=前复权 3=不复权"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """账户现金、持仓、按最新日 K 估算的权益（成交列表见 GET /paper/orders）。"""
    repo = PaperRepository(session)
    acc = await repo.get_or_create_default_account()
    kline_repo = KlineRepository(session)
    positions = await repo.list_positions(acc.id)

    mv_total = 0.0
    pos_out = []
    for p in positions:
        kl = await kline_repo.get_daily(p.code, limit=1, adjust_flag=adjust_flag)
        last = float(kl[-1].close) if kl else float(p.avg_price)
        td_k = kl[-1].trade_date if kl else None
        sellable = await repo.sellable_quantity(acc.id, p.code, td_k) if td_k is not None else 0
        mv = last * p.quantity
        mv_total += mv
        pos_out.append(
            {
                "code": p.code,
                "quantity": p.quantity,
                "avg_price": p.avg_price,
                "last_close": last,
                "market_value": round(mv, 2),
                "sellable_quantity": sellable,
                "locked_quantity": max(0, p.quantity - sellable),
            }
        )

    equity = round(acc.cash + mv_total, 2)
    return {
        "account": {
            "id": acc.id,
            "label": acc.label,
            "cash": round(acc.cash, 2),
            "initial_cash": round(acc.initial_cash, 2),
        },
        "positions": pos_out,
        "equity": equity,
    }


@router.get("/orders", response_model=PaperOrdersListResponse)
async def paper_list_orders(
    session: AsyncSession = Depends(get_session),
    limit: int = Query(50, ge=1, le=200, description="每页条数"),
    offset: int = Query(0, ge=0, description="跳过条数"),
    code: str | None = Query(None, max_length=24, description="可选：只查该标的"),
) -> PaperOrdersListResponse:
    """分页查询成交记录（按订单 id 新→旧）。"""
    paper = PaperRepository(session)
    acc = await paper.get_or_create_default_account()
    code_norm = _norm_code(code.strip()) if code and code.strip() else None
    total = await paper.count_orders(acc.id, code=code_norm)
    rows = await paper.list_orders(acc.id, limit=limit, offset=offset, code=code_norm)
    items = [
        PaperOrderListItem(
            id=o.id,
            code=o.code,
            side=o.side,
            quantity=o.quantity,
            fill_price=o.fill_price,
            fill_amount=o.fill_amount,
            trade_date=str(o.trade_date) if o.trade_date else None,
            created_at=o.created_at.isoformat() if o.created_at else None,
        )
        for o in rows
    ]
    return PaperOrdersListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post("/orders", response_model=PaperOrderResponse)
async def paper_place_order(
    body: PaperOrderRequest,
    session: AsyncSession = Depends(get_session),
) -> PaperOrderResponse:
    code = _norm_code(body.code)
    side = body.side.strip().lower()
    if side not in ("buy", "sell"):
        raise HTTPException(status_code=400, detail="side 须为 buy 或 sell")

    kline_repo = KlineRepository(session)
    kl = await kline_repo.get_daily(code, limit=1, adjust_flag=body.adjust_flag)
    if not kl:
        raise HTTPException(status_code=400, detail=f"无日 K 数据，无法为 {code} 定价")

    last = kl[-1]
    price = float(last.close)
    td = last.trade_date
    qty = int(body.quantity)
    gross = round(price * qty, 4)

    paper = PaperRepository(session)
    acc = await paper.get_or_create_default_account()
    try:
        order = await paper.place_market_order(
            account_id=acc.id,
            code=code,
            side=side,
            quantity=qty,
            fill_price=price,
            trade_date=td,
            fill_amount=gross,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    await session.refresh(acc)
    return PaperOrderResponse(
        id=order.id,
        code=order.code,
        side=order.side,
        quantity=order.quantity,
        fill_price=order.fill_price,
        fill_amount=order.fill_amount,
        trade_date=str(order.trade_date) if order.trade_date else None,
        cash_after=round(acc.cash, 2),
    )


@router.post("/account/reset")
async def paper_reset(session: AsyncSession = Depends(get_session)) -> dict:
    """清空纸单与持仓，现金回到 initial（开发/自测用）。"""
    paper = PaperRepository(session)
    acc = await paper.get_or_create_default_account()
    await paper.reset_account(acc.id)
    await session.refresh(acc)
    return {"ok": True, "cash": round(acc.cash, 2)}
