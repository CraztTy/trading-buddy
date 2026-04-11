"""
最小回测 API：双均线（日线）。
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.backtest import run_ma_cross_backtest
from src.data.storage import KlineRepository, get_session

router = APIRouter()


class MaCrossBacktestResponse(BaseModel):
    code: str
    fast_period: int
    slow_period: int
    bars_used: int
    commission_rate: float = 0.0
    first_trade_date: str | None
    last_trade_date: str | None
    total_return_pct: float
    buy_hold_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    signal_changes: int
    note: str
    equity_curve: list[dict] = Field(default_factory=list)


@router.get("/ma-cross", response_model=MaCrossBacktestResponse)
async def ma_cross_backtest(
    code: str = Query(..., description="标的代码，如 sh.000001"),
    fast: int = Query(5, ge=1, le=120, description="快线周期"),
    slow: int = Query(20, ge=2, le=500, description="慢线周期"),
    start_date: date | None = Query(None, description="起始日（含）"),
    end_date: date | None = Query(None, description="结束日（含）"),
    limit: int = Query(500, ge=30, le=5000, description="最多使用多少根日 K（从新到旧取，再按时间正序回测）"),
    commission_rate: float = Query(
        0.0,
        ge=0.0,
        le=0.05,
        description="单边手续费率（如万1.5填0.00015）；在持仓翻转日各扣一次",
    ),
    session: AsyncSession = Depends(get_session),
):
    if fast >= slow:
        raise HTTPException(status_code=400, detail="fast 必须小于 slow")

    repo = KlineRepository(session)
    klines = await repo.get_daily(
        code=code.strip(),
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
    if len(klines) < slow + 1:
        raise HTTPException(
            status_code=400,
            detail=f"K 线不足：需要至少 slow+1={slow + 1} 根，当前 {len(klines)}",
        )
    try:
        result, curve = run_ma_cross_backtest(
            klines, fast=fast, slow=slow, commission_rate=commission_rate
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    body = result.to_api_dict()
    body["equity_curve"] = curve
    return MaCrossBacktestResponse(**body)
