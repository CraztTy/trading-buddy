"""
纸交易 API：研究 / 回测之后，用最近一根日 K 收盘价做市价撮合（MVP）。
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field, field_validator
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_user
from src.common.kill_switch import check_or_raise
from src.data.models.stock import StockType
from src.data.storage import KlineRepository, StockRepository, get_session
from src.data.storage.backtest_run_repository import BacktestRunRepository
from src.data.storage.paper_repository import LOT_SIZE, PaperRepository
from src.risk.defaults import create_default_engine
from src.risk.models import PortfolioState

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
    account_label: str = Field("default", min_length=1, max_length=32, description="纸交易账户标签")

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
    stamp_tax: float = Field(0.0, description="印花税（卖出时 0.05%，买入为 0）")


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


class PaperAccountCreateRequest(BaseModel):
    label: str = Field(..., min_length=1, max_length=32, description="账户标签")
    initial_cash: float = Field(1_000_000.0, ge=0, description="初始资金")


class PaperAccountOut(BaseModel):
    id: int
    label: str
    cash: float
    initial_cash: float


class PaperAccountsListResponse(BaseModel):
    items: list[PaperAccountOut]


class PaperOrdersFromBacktestRequest(BaseModel):
    run_id: int = Field(..., description="回测存档记录 ID")
    account_label: str = Field("default", min_length=1, max_length=32, description="纸交易账户标签")


class PaperOrderFromBacktestItem(BaseModel):
    code: str
    side: str
    quantity: int
    fill_price: float
    fill_amount: float
    trade_date: str | None


class PaperOrdersFromBacktestResponse(BaseModel):
    account_id: int
    account_label: str
    orders: list[PaperOrderFromBacktestItem]
    total_value: float


def _norm_code(raw: str) -> str:
    c = (raw or "").strip().lower()
    if not c:
        raise HTTPException(status_code=400, detail="code 不能为空")
    return c


def _limit_pct(stock_type: StockType) -> float:
    """A 股各类型涨跌停幅度。"""
    limits = {
        StockType.COMMON: 0.10,
        StockType.ST: 0.05,
        StockType.STAR: 0.20,
        StockType.GROWTH: 0.20,
        StockType.BEIJING: 0.30,
    }
    return limits.get(stock_type, 0.10)


async def _check_limit_up_down(
    session,
    code: str,
    side: str,
    price: float,
    pre_close: float | None,
) -> str | None:
    """涨跌停检查；触限时返回错误描述，否则返回 None。"""
    if not pre_close or pre_close <= 0:
        return None

    stock_repo = StockRepository(session)
    stock_info = await stock_repo.get_by_code(code)
    stock_type = stock_info.stock_type if stock_info else StockType.COMMON
    limit = _limit_pct(stock_type)
    change_pct = (price - pre_close) / pre_close

    if side == "buy" and change_pct >= limit - 1e-9:
        return f"涨停不可买入（涨幅 {change_pct * 100:.2f}% >= {limit * 100:.0f}%）"
    if side == "sell" and change_pct <= -limit + 1e-9:
        return f"跌停不可卖出（跌幅 {change_pct * 100:.2f}% <= -{limit * 100:.0f}%）"
    return None


def _calc_stamp_tax(side: str, amount: float) -> float:
    """A 股印花税：卖出时单边征收 0.05%。"""
    if side == "sell":
        return round(amount * 0.0005, 4)
    return 0.0


def _user_id_or_system(current_user: dict) -> int | None:
    """将系统用户（id=0）映射为 None，以便与 user_id=NULL 的旧数据兼容。"""
    uid = current_user.get("id", 0)
    return None if uid == 0 else uid


def _check_risk_for_paper(
    acc,
    positions: list[dict],
    side: str,
    code: str,
    quantity: int,
    price: float,
) -> None:
    """纸交易下单前风控检查；不通过时抛出 ValueError。"""
    total_equity = acc.cash + sum(p["market_value"] for p in positions)
    sim_positions = []
    for p in positions:
        cp = dict(p)
        if side == "buy" and cp["code"] == code:
            cp["quantity"] += quantity
            cp["market_value"] = cp["quantity"] * price
        elif side == "sell" and cp["code"] == code:
            cp["quantity"] = max(0, cp["quantity"] - quantity)
            cp["market_value"] = cp["quantity"] * price
        if cp["quantity"] > 0:
            sim_positions.append(cp)
    if side == "buy":
        sim_cash = max(0.0, acc.cash - price * quantity)
    else:
        sim_cash = acc.cash + price * quantity
    sim_equity = sim_cash + sum(p["market_value"] for p in sim_positions)
    for p in sim_positions:
        p["weight"] = (p["market_value"] / sim_equity) if sim_equity > 0 else 0.0

    state = PortfolioState(
        cash=sim_cash,
        total_equity=sim_equity,
        positions=sim_positions,
    )
    engine = create_default_engine()
    passed, errors = engine.check_all_passed(state)
    if not passed:
        raise ValueError("风控拦截：" + "；".join(errors))


@router.get("/state")
async def paper_state(
    adjust_flag: str = Query("3", description="复权类型: 1=后复权 2=前复权 3=不复权"),
    account_label: str = Query("default", min_length=1, max_length=32, description="纸交易账户标签"),
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """账户现金、持仓、按最新日 K 估算的权益（成交列表见 GET /paper/orders）。"""
    repo = PaperRepository(session)
    user_id = _user_id_or_system(current_user)
    acc = await repo.get_or_create_account(user_id=user_id, label=account_label)
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
    current_user: dict = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200, description="每页条数"),
    offset: int = Query(0, ge=0, description="跳过条数"),
    code: str | None = Query(None, max_length=24, description="可选：只查该标的"),
    account_label: str = Query("default", min_length=1, max_length=32, description="纸交易账户标签"),
) -> PaperOrdersListResponse:
    """分页查询成交记录（按订单 id 新→旧）。"""
    paper = PaperRepository(session)
    user_id = _user_id_or_system(current_user)
    acc = await paper.get_or_create_account(user_id=user_id, label=account_label)
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
    current_user: dict = Depends(get_current_user),
) -> PaperOrderResponse:
    await check_or_raise()

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

    # 涨跌停检查
    pre_close = float(last.pre_close) if last.pre_close else None
    limit_err = await _check_limit_up_down(session, code, side, price, pre_close)
    if limit_err:
        raise HTTPException(status_code=400, detail=limit_err)

    # 印花税：卖出时单边 0.05%
    stamp_tax = _calc_stamp_tax(side, price * qty)
    # 卖出时 fill_amount 为净收入（成交金额 - 税费）；买入为成交金额
    gross = round(price * qty - stamp_tax, 4) if side == "sell" else round(price * qty, 4)

    paper = PaperRepository(session)
    user_id = _user_id_or_system(current_user)
    acc = await paper.get_or_create_account(user_id=user_id, label=body.account_label)

    # 风控检查（基于成交金额）
    positions = await paper.list_positions(acc.id)
    pos_dicts = [
        {
            "code": p.code,
            "quantity": p.quantity,
            "avg_price": p.avg_price,
            "market_value": p.avg_price * p.quantity,
        }
        for p in positions
    ]
    try:
        _check_risk_for_paper(acc, pos_dicts, side, code, qty, price)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

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

    # 发布订单事件到事件总线
    try:
        from src.events.publisher import EventPublisher
        pub = EventPublisher()
        await pub.order_filled(
            order_id=str(order.id),
            code=order.code,
            side=order.side,
            quantity=order.quantity,
            price=order.fill_price,
            filled_quantity=order.quantity,
            account_label=body.account_label,
            stamp_tax=stamp_tax,
        )
    except Exception:
        pass  # 事件发布失败不影响订单响应

    return PaperOrderResponse(
        id=order.id,
        code=order.code,
        side=order.side,
        quantity=order.quantity,
        fill_price=order.fill_price,
        fill_amount=order.fill_amount,
        trade_date=str(order.trade_date) if order.trade_date else None,
        cash_after=round(acc.cash, 2),
        stamp_tax=stamp_tax,
    )


class PaperAccountResetRequest(BaseModel):
    account_label: str = Field("default", min_length=1, max_length=32, description="纸交易账户标签")


@router.post("/account/reset")
async def paper_reset(
    body: PaperAccountResetRequest,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """清空纸单与持仓，现金回到 initial（开发/自测用）。"""
    paper = PaperRepository(session)
    user_id = _user_id_or_system(current_user)
    acc = await paper.get_or_create_account(user_id=user_id, label=body.account_label)
    await paper.reset_account(acc.id)
    await session.refresh(acc)
    return {"ok": True, "cash": round(acc.cash, 2)}


@router.post("/account/create")
async def paper_create_account(
    body: PaperAccountCreateRequest,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """创建命名账户（自定义初始资金）。"""
    paper = PaperRepository(session)
    user_id = _user_id_or_system(current_user)
    acc = await paper.get_or_create_account(user_id=user_id, label=body.label)
    # 如果账户是刚创建的，按请求设置初始资金
    if acc.initial_cash == 1_000_000.0 and body.initial_cash != 1_000_000.0:
        acc.initial_cash = body.initial_cash
        acc.cash = body.initial_cash
        await session.flush()
    return {
        "ok": True,
        "account": {
            "id": acc.id,
            "label": acc.label,
            "cash": round(acc.cash, 2),
            "initial_cash": round(acc.initial_cash, 2),
        },
    }


@router.get("/accounts", response_model=PaperAccountsListResponse)
async def paper_list_accounts(
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> PaperAccountsListResponse:
    """列出当前用户的所有纸交易账户。"""
    paper = PaperRepository(session)
    user_id = _user_id_or_system(current_user)
    accounts = await paper.list_accounts(user_id)
    items = [
        PaperAccountOut(
            id=a.id,
            label=a.label,
            cash=round(a.cash, 2),
            initial_cash=round(a.initial_cash, 2),
        )
        for a in accounts
    ]
    return PaperAccountsListResponse(items=items)


@router.post("/orders/from-backtest", response_model=PaperOrdersFromBacktestResponse)
async def create_orders_from_backtest(
    body: PaperOrdersFromBacktestRequest,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> PaperOrdersFromBacktestResponse:
    """Create paper trading orders from a backtest result's final positions.

    1. Fetch the backtest run from archive
    2. Extract the final positions from response_payload.result.positions_history
    3. For each position with positive quantity, create a market order (buy)
    4. Return created orders list
    """
    await check_or_raise()

    user_id = _user_id_or_system(current_user)

    # Fetch backtest run
    run_repo = BacktestRunRepository(session)
    run = await run_repo.get(body.run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="回测存档不存在")
    if run.user_id != user_id:
        raise HTTPException(status_code=404, detail="回测存档不存在")

    # Extract positions from response payload
    response_payload = dict(run.response_payload or {})
    result = response_payload.get("result") or {}

    # Try to get final positions from positions_history (last date's positions)
    positions_history = result.get("positions_history") or []

    # Group by trade_date and get the latest date's positions
    final_positions: list[dict] = []
    if positions_history:
        # Sort by trade_date descending, take positions from last date
        by_date: dict[str, list[dict]] = {}
        for pos in positions_history:
            if not isinstance(pos, dict):
                continue
            td = pos.get("trade_date") or ""
            by_date.setdefault(td, []).append(pos)
        if by_date:
            last_date = max(by_date.keys())
            final_positions = by_date[last_date]

    # Fallback: try equity_curve last entry
    if not final_positions:
        equity_curve = result.get("equity_curve") or []
        if equity_curve:
            last_entry = equity_curve[-1]
            # equity_curve may not have per-code positions, so we can't use it
            pass

    if not final_positions:
        raise HTTPException(status_code=400, detail="该回测存档无可用持仓数据")

    # Get paper account
    paper = PaperRepository(session)
    acc = await paper.get_or_create_account(user_id=user_id, label=body.account_label)

    # Get kline repo for pricing
    kline_repo = KlineRepository(session)

    created_orders: list[PaperOrderFromBacktestItem] = []
    total_value = 0.0

    for pos in final_positions:
        if not isinstance(pos, dict):
            continue
        code = pos.get("code")
        quantity_raw = pos.get("quantity", 0)
        if not code or not quantity_raw:
            continue

        code_norm = _norm_code(code)
        # Round down to lot size
        qty = int(math.floor(float(quantity_raw) / LOT_SIZE) * LOT_SIZE)
        if qty < LOT_SIZE:
            continue

        # Get latest price
        kl = await kline_repo.get_daily(code_norm, limit=1, adjust_flag="3")
        if not kl:
            continue
        last = kl[-1]
        price = float(last.close)
        td = last.trade_date
        gross = round(price * qty, 4)

        # Check if enough cash
        if acc.cash + 1e-9 < gross:
            # Skip if not enough cash
            continue

        # Place market buy order
        try:
            order = await paper.place_market_order(
                account_id=acc.id,
                code=code_norm,
                side="buy",
                quantity=qty,
                fill_price=price,
                trade_date=td,
                fill_amount=gross,
            )
            created_orders.append(
                PaperOrderFromBacktestItem(
                    code=order.code,
                    side=order.side,
                    quantity=order.quantity,
                    fill_price=order.fill_price,
                    fill_amount=order.fill_amount,
                    trade_date=str(order.trade_date) if order.trade_date else None,
                )
            )
            total_value += gross
        except ValueError:
            # Skip on error (e.g. cash insufficient, risk check)
            continue

    await session.refresh(acc)
    return PaperOrdersFromBacktestResponse(
        account_id=acc.id,
        account_label=acc.label,
        orders=created_orders,
        total_value=round(total_value, 2),
    )
