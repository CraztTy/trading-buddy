"""
策略目录与 JSON 模板驱动的统一信号（V2 切片）。
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from src.data.storage import get_session
from src.strategies import compute_ma_cross_signal, list_strategy_catalog

from .backtest import MaCrossSignalResponse

router = APIRouter()

_SIGNAL_KINDS: frozenset[str] = frozenset({"ma_cross"})


class MaCrossSignalParams(BaseModel):
    fast: int = Field(5, ge=1, le=120)
    slow: int = Field(20, ge=2, le=500)
    limit: int = Field(500, ge=30, le=5000, description="须 ≥ slow")
    start_date: date | None = None
    end_date: date | None = None


class StrategySignalRequest(BaseModel):
    """POST /api/strategies/signal 请求体；params 按 kind 解析。"""

    code: str = Field(..., min_length=1, max_length=64, description="标的代码")
    kind: str = Field("ma_cross", min_length=1, max_length=64)
    params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("code")
    @classmethod
    def strip_code(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("code 不能为空")
        return s

    @field_validator("kind")
    @classmethod
    def norm_kind(cls, v: str) -> str:
        return v.strip()


class StrategySignalResponse(BaseModel):
    kind: str
    signal: MaCrossSignalResponse


class StrategyCatalogResponse(BaseModel):
    """GET /api/strategies/catalog 响应外壳（条目为 JSON 友好 dict，与 ``list_strategy_catalog`` 一致）。"""

    strategies: list[dict[str, Any]] = Field(
        ...,
        description=(
            "各条目含 id、title、signal_params、backtest_run（含 strategy_id、strategy_version、"
            "archive_kind、params_schema）、backtest_archive_kinds、strategy_contract_version 等；"
            "字段语义见 docs/STRATEGY_CONTRACT.md"
        ),
    )


@router.get(
    "/catalog",
    response_model=StrategyCatalogResponse,
    description=(
        "列出已注册策略：signal_params（试算信号）、backtest_run（POST /api/backtest/run 信封与 params_schema）、"
        "backtest_archive_kinds（与结果存档 kind 对齐）"
    ),
)
async def get_strategy_catalog():
    return StrategyCatalogResponse(strategies=list_strategy_catalog())


@router.post("/signal", response_model=StrategySignalResponse)
async def post_strategy_signal(
    body: StrategySignalRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    用 JSON 模板请求最新策略信号（当前仅 `ma_cross`）。
    与 `GET /api/backtest/ma-cross/signal` 语义一致，便于自动化与后续多策略扩展。
    """
    if body.kind == "ma_cross_scan":
        raise HTTPException(
            status_code=400,
            detail=(
                "kind=ma_cross_scan 不支持 POST /api/strategies/signal；"
                "请对单代码使用 kind=ma_cross，或 GET /api/backtest/ma-cross/signal；"
                "catalog 中 ma_cross_scan.signal_params 已标注 maxProperties=0。"
            ),
        )
    if body.kind not in _SIGNAL_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的 kind={body.kind!r}；当前可选: {sorted(_SIGNAL_KINDS)}",
        )

    try:
        p = MaCrossSignalParams.model_validate(body.params)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors()) from e

    try:
        raw = await compute_ma_cross_signal(
            session,
            code=body.code,
            fast=p.fast,
            slow=p.slow,
            start_date=p.start_date,
            end_date=p.end_date,
            limit=p.limit,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return StrategySignalResponse(kind=body.kind, signal=MaCrossSignalResponse(**raw))
