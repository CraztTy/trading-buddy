"""压力测试 API — 历史场景压力测试。"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_user
from src.data.storage.database import get_session
from src.data.storage.models import StressScenarioModel, StressTestResultModel

router = APIRouter()


def _user_id_or_system(current_user: dict) -> int | None:
    uid = current_user.get("id", 0)
    return None if uid == 0 else uid


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class StressScenarioItem(BaseModel):
    id: int
    name: str
    description: str | None
    start_date: str
    end_date: str
    benchmark_drop_pct: float | None
    tags: str | None
    is_builtin: bool


class StressTestRequest(BaseModel):
    scenario_id: int
    strategy_id: str = Field(..., min_length=1, max_length=64)
    code: str = Field(..., min_length=4, max_length=24)
    params: dict[str, Any] = Field(default_factory=dict)


class StressTestResultItem(BaseModel):
    id: int
    scenario_id: int
    scenario_name: str
    strategy_id: str
    code: str
    portfolio_return_pct: float | None
    max_drawdown_pct: float | None
    vs_benchmark_excess_pct: float | None
    result: dict[str, Any]
    created_at: str


# ---------------------------------------------------------------------------
# Endpoints — Scenarios
# ---------------------------------------------------------------------------


@router.get("/scenarios", response_model=list[StressScenarioItem])
async def list_scenarios(
    session: AsyncSession = Depends(get_session),
) -> list[StressScenarioItem]:
    """列出所有压力测试场景（含内置）。"""
    stmt = select(StressScenarioModel).order_by(StressScenarioModel.start_date.desc())
    result = await session.execute(stmt)
    rows = result.scalars().all()
    return [_scenario_to_item(r) for r in rows]


# ---------------------------------------------------------------------------
# Endpoints — Stress Test
# ---------------------------------------------------------------------------


@router.post("/test", response_model=StressTestResultItem)
async def run_stress_test(
    body: StressTestRequest,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> StressTestResultItem:
    """在指定压力场景下运行回测并记录结果。"""
    from src.backtest.runner.buy_hold_executor import execute_buy_hold_single
    from src.backtest.runner.ma_cross_executor import execute_ma_cross_single

    user_id = _user_id_or_system(current_user)

    # 获取场景
    scenario = await session.get(StressScenarioModel, body.scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="场景不存在")

    # 构造回测参数
    params = {
        "code": body.code.strip(),
        "limit": 5000,
        "start_date": scenario.start_date,
        "end_date": scenario.end_date,
        "commission_rate": body.params.get("commission_rate", 0.0),
        "slippage_rate": body.params.get("slippage_rate", 0.0),
        "adjust_flag": body.params.get("adjust_flag", "3"),
        "benchmark_code": None,
    }

    if body.strategy_id == "ma_cross":
        params["fast"] = body.params.get("fast", 5)
        params["slow"] = body.params.get("slow", 20)

    try:
        if body.strategy_id == "buy_hold":
            payload, _ = await execute_buy_hold_single(session, **params)
        elif body.strategy_id == "ma_cross":
            payload, _ = await execute_ma_cross_single(session, **params)
        else:
            raise HTTPException(status_code=400, detail=f"不支持的 strategy_id: {body.strategy_id}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"回测执行失败: {e}")

    total_return = payload.get("total_return_pct")
    max_dd = payload.get("max_drawdown_pct")

    row = StressTestResultModel(
        scenario_id=body.scenario_id,
        user_id=user_id,
        strategy_id=body.strategy_id,
        code=body.code,
        params=body.params,
        result=payload,
        portfolio_return_pct=total_return,
        max_drawdown_pct=max_dd,
        vs_benchmark_excess_pct=payload.get("excess_return_pct"),
    )
    session.add(row)
    await session.flush()

    return StressTestResultItem(
        id=row.id,
        scenario_id=scenario.id,
        scenario_name=scenario.name,
        strategy_id=body.strategy_id,
        code=body.code,
        portfolio_return_pct=total_return,
        max_drawdown_pct=max_dd,
        vs_benchmark_excess_pct=payload.get("excess_return_pct"),
        result=dict(payload),
        created_at=row.created_at.isoformat() if row.created_at else "",
    )


@router.get("/results", response_model=list[StressTestResultItem])
async def list_stress_results(
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
    limit: int = Query(30, ge=1, le=100),
) -> list[StressTestResultItem]:
    """列出压力测试历史结果。"""
    user_id = _user_id_or_system(current_user)

    from sqlalchemy import desc

    stmt = select(StressTestResultModel).order_by(desc(StressTestResultModel.created_at)).limit(limit)
    if user_id is not None:
        stmt = stmt.where(StressTestResultModel.user_id == user_id)

    result = await session.execute(stmt)
    rows = result.scalars().all()

    out: list[StressTestResultItem] = []
    for r in rows:
        scenario = await session.get(StressScenarioModel, r.scenario_id)
        out.append(StressTestResultItem(
            id=r.id,
            scenario_id=r.scenario_id,
            scenario_name=scenario.name if scenario else "",
            strategy_id=r.strategy_id,
            code=r.code,
            portfolio_return_pct=r.portfolio_return_pct,
            max_drawdown_pct=r.max_drawdown_pct,
            vs_benchmark_excess_pct=r.vs_benchmark_excess_pct,
            result=dict(r.result or {}),
            created_at=r.created_at.isoformat() if r.created_at else "",
        ))
    return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _scenario_to_item(row: StressScenarioModel) -> StressScenarioItem:
    return StressScenarioItem(
        id=row.id,
        name=row.name,
        description=row.description,
        start_date=row.start_date.isoformat(),
        end_date=row.end_date.isoformat(),
        benchmark_drop_pct=row.benchmark_drop_pct,
        tags=row.tags,
        is_builtin=row.is_builtin,
    )
