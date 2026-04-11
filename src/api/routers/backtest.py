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
    slippage_rate: float = 0.0
    first_trade_date: str | None
    last_trade_date: str | None
    total_return_pct: float
    buy_hold_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    signal_changes: int
    note: str
    equity_curve: list[dict] = Field(default_factory=list)


class MaCrossScanRow(BaseModel):
    code: str
    error: str | None = None
    bars_used: int | None = None
    total_return_pct: float | None = None
    buy_hold_return_pct: float | None = None
    max_drawdown_pct: float | None = None
    sharpe_ratio: float | None = None
    signal_changes: int | None = None


class MaCrossScanResponse(BaseModel):
    fast_period: int
    slow_period: int
    limit: int
    commission_rate: float
    slippage_rate: float
    items: list[MaCrossScanRow]


def _parse_codes(raw: str, cap: int) -> list[str]:
    parts = raw.replace("\n", ",").replace(";", ",").split(",")
    out: list[str] = []
    for p in parts:
        c = p.strip().lower()
        if c and c not in out:
            out.append(c)
        if len(out) >= cap:
            break
    return out


@router.get("/ma-cross/scan", response_model=MaCrossScanResponse)
async def ma_cross_scan(
    codes: str = Query(
        ...,
        description="逗号或换行分隔的标的列表，如 sh.600519,sz.000001",
    ),
    fast: int = Query(5, ge=1, le=120),
    slow: int = Query(20, ge=2, le=500),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    limit: int = Query(500, ge=30, le=5000),
    commission_rate: float = Query(0.0, ge=0.0, le=0.05),
    slippage_rate: float = Query(0.0, ge=0.0, le=0.05),
    max_codes: int = Query(25, ge=1, le=40),
    session: AsyncSession = Depends(get_session),
):
    if fast >= slow:
        raise HTTPException(status_code=400, detail="fast 必须小于 slow")
    if commission_rate + slippage_rate > 0.08:
        raise HTTPException(
            status_code=400,
            detail="commission_rate 与 slippage_rate 之和勿超过 0.08",
        )

    parsed = _parse_codes(codes, max_codes)
    if not parsed:
        raise HTTPException(status_code=400, detail="codes 解析后为空")

    repo = KlineRepository(session)
    rows: list[MaCrossScanRow] = []

    for c in parsed:
        klines = await repo.get_daily(
            code=c,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
        if len(klines) < slow + 1:
            rows.append(
                MaCrossScanRow(
                    code=c,
                    error=f"K 线不足（{len(klines)}<{slow + 1}）",
                )
            )
            continue
        try:
            res, _ = run_ma_cross_backtest(
                klines,
                fast=fast,
                slow=slow,
                commission_rate=commission_rate,
                slippage_rate=slippage_rate,
                include_equity_curve=False,
            )
        except ValueError as e:
            rows.append(MaCrossScanRow(code=c, error=str(e)))
            continue

        rows.append(
            MaCrossScanRow(
                code=res.code,
                bars_used=res.bars_used,
                total_return_pct=round(res.total_return_pct, 4),
                buy_hold_return_pct=round(res.buy_hold_return_pct, 4),
                max_drawdown_pct=round(res.max_drawdown_pct, 4),
                sharpe_ratio=round(res.sharpe_ratio, 4),
                signal_changes=res.signal_changes,
            )
        )

    def sort_key(r: MaCrossScanRow) -> float:
        if r.error or r.total_return_pct is None:
            return float("-inf")
        return float(r.total_return_pct)

    rows.sort(key=sort_key, reverse=True)

    return MaCrossScanResponse(
        fast_period=fast,
        slow_period=slow,
        limit=limit,
        commission_rate=round(commission_rate, 8),
        slippage_rate=round(slippage_rate, 8),
        items=rows,
    )


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
    slippage_rate: float = Query(
        0.0,
        ge=0.0,
        le=0.05,
        description="滑点率（与手续费同口径，在调仓翻转日扣减）",
    ),
    session: AsyncSession = Depends(get_session),
):
    if fast >= slow:
        raise HTTPException(status_code=400, detail="fast 必须小于 slow")
    if commission_rate + slippage_rate > 0.08:
        raise HTTPException(
            status_code=400,
            detail="commission_rate 与 slippage_rate 之和勿超过 0.08",
        )

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
            klines,
            fast=fast,
            slow=slow,
            commission_rate=commission_rate,
            slippage_rate=slippage_rate,
            include_equity_curve=True,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    body = result.to_api_dict()
    body["equity_curve"] = curve
    return MaCrossBacktestResponse(**body)
