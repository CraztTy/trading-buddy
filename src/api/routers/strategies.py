"""
策略目录与 JSON 模板驱动的统一信号（V2 切片）。
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from src.data.storage import get_session
from src.strategies import compute_ma_cross_signal, list_strategy_catalog
from src.strategies.limit_up_pullback_scan import (
    LimitUpPullbackScanParams,
    scan_stocks as limit_up_pullback_scan_stocks,
)

from .backtest import MaCrossSignalResponse

router = APIRouter()

_SIGNAL_KINDS: frozenset[str] = frozenset({"ma_cross"})


class LimitUpPullbackScanRequest(BaseModel):
    """涨停回调选股扫描请求"""

    codes: str = Field(..., description="逗号或换行分隔的标的列表")
    as_of_date: date | None = Field(None, description="基准日期，默认为最近交易日")
    max_codes: int = Field(100, ge=1, le=200)
    # 个股基础
    min_market_cap: float | None = Field(5_000_000_000.0, ge=0)
    max_market_cap: float | None = Field(50_000_000_000.0, ge=0)
    exclude_st: bool = Field(True)
    min_limit_up_3m: int = Field(1, ge=0)
    max_limit_up_3m: int = Field(3, ge=0)
    # 技术形态
    limit_up_lookback_min: int = Field(5, ge=1)
    limit_up_lookback_max: int = Field(10, ge=1)
    ma_strict: bool = Field(False)
    adjustment_days_min: int = Field(5, ge=1)
    # 买点
    buy_point_types: list[str] = Field(default_factory=lambda: ["neutral"])
    # 板块/政策
    sector_codes: list[str] | None = Field(None)
    require_policy: bool = Field(False)
    policy_lookback_days: int = Field(14, ge=1)

    @field_validator("codes")
    @classmethod
    def strip_codes(cls, v: str) -> str:
        return v.strip()

    @model_validator(mode="after")
    def _check_lookback(self) -> "LimitUpPullbackScanRequest":
        if self.limit_up_lookback_min > self.limit_up_lookback_max:
            raise ValueError("limit_up_lookback_min 不能大于 limit_up_lookback_max")
        return self


class LimitUpPullbackMatchItem(BaseModel):
    code: str
    name: str
    buy_point_type: str
    buy_point_price: float
    stop_loss_price: float
    limit_up_date: str
    limit_up_close: float
    limit_up_open: float
    limit_up_low: float
    current_close: float
    matched_rules: list[str]
    note: str


class LimitUpPullbackScanResponse(BaseModel):
    as_of_date: str
    total_scanned: int
    matches: list[LimitUpPullbackMatchItem]
    note: str = "选股结果基于日线数据与技术面过滤，不构成投资建议"


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


@router.post("/limit-up-pullback/scan", response_model=LimitUpPullbackScanResponse)
async def post_limit_up_pullback_scan(
    body: LimitUpPullbackScanRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    涨停回调选股策略批量扫描。
    按文档 v2.0 的五层过滤（当前实现第3~5层技术面，第1~2层通过可选参数控制）。
    """
    parsed = _parse_codes(body.codes, body.max_codes)
    if not parsed:
        raise HTTPException(status_code=400, detail="codes 解析后为空")

    as_of = body.as_of_date or date.today()
    params = LimitUpPullbackScanParams(
        as_of_date=as_of,
        min_market_cap=body.min_market_cap,
        max_market_cap=body.max_market_cap,
        exclude_st=body.exclude_st,
        min_limit_up_3m=body.min_limit_up_3m,
        max_limit_up_3m=body.max_limit_up_3m,
        limit_up_lookback_min=body.limit_up_lookback_min,
        limit_up_lookback_max=body.limit_up_lookback_max,
        ma_strict=body.ma_strict,
        adjustment_days_min=body.adjustment_days_min,
        buy_point_types=tuple(body.buy_point_types or ["neutral"]),
        sector_codes=body.sector_codes,
        require_policy=body.require_policy,
        policy_lookback_days=body.policy_lookback_days,
    )

    try:
        matches = await limit_up_pullback_scan_stocks(session, parsed, params)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return LimitUpPullbackScanResponse(
        as_of_date=as_of.isoformat(),
        total_scanned=len(parsed),
        matches=[LimitUpPullbackMatchItem(**m.to_api_dict()) for m in matches],
    )
