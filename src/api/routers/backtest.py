"""
最小回测 API：双均线（日线）。
"""

import asyncio
import uuid
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse, Response

from src.backtest.runner import (
    ENGINE_VERSION,
    STRATEGY_ID_BUY_HOLD,
    STRATEGY_ID_LIMIT_UP_PULLBACK,
    STRATEGY_ID_LIMIT_UP_PULLBACK_SCAN,
    STRATEGY_ID_MA_CROSS,
    STRATEGY_ID_MA_CROSS_SCAN,
    build_ma_cross_scan_assumptions,
    execute_buy_hold_single,
    execute_limit_up_pullback_scan,
    execute_limit_up_pullback_single,
    execute_ma_cross_scan,
    execute_ma_cross_single,
    limit_up_pullback_scan_items,
    parse_scan_codes,
)
from src.backtest.runner.portfolio_executor import (
    STRATEGY_ID_PORTFOLIO_EQUAL,
    STRATEGY_ID_PORTFOLIO_VALUE,
    execute_portfolio_backtest,
)
from src.strategies import compute_ma_cross_signal
from src.backtest.limit_up_pullback import (
    LimitUpPullbackParamGrid,
    run_limit_up_pullback_param_grid,
)
from src.backtest.scan import ma_cross_scan_csv_bytes, parse_scan_codes
from src.backtest.trend_following import trend_following_backtest
from src.backtest.mean_reversion import mean_reversion_backtest
from src.backtest.async_job_backend import (
    JOB_CANCELLED_MSG,
    QUEUE_KEY,
    STALE_RUNNING_RECLAIM_MSG,
    cancel_redis_pending_job,
    catalog_async_job_persistence,
    effective_redis_async_jobs,
    enqueue_redis_async_job,
    enforce_redis_job_store_or_503,
    is_running_stale,
    reclaim_stale_running_redis,
    redis_job_status_snapshot,
    run_mvp_job_execution,
    utc_now_iso_z,
)
from src.common.redis_client import get_redis_client
from src.data.models import StockType
from src.data.storage import KlineRepository, StockRepository, get_database, get_session
from src.api.dependencies import get_current_user
from src.data.storage.backtest_run_repository import (
    BacktestRunRepository,
    assert_run_payload_size,
    build_summary,
)

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
    excess_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    signal_changes: int
    annualized_return_pct: float
    buy_hold_annualized_return_pct: float
    annualized_volatility_pct: float
    sortino_ratio: float
    calmar_ratio: float
    long_trades_count: int
    win_rate_pct: float
    avg_holding_return_pct: float
    underlying_beta: float
    underlying_alpha_ann_pct: float
    benchmark_code: str | None = Field(
        None,
        description="若请求传入 benchmark_code，则为小写回显；β/α 相对该基准日收益，否则为 null（相对标的自身）",
    )
    note: str
    equity_curve: list[dict] = Field(default_factory=list)
    trades: list[dict] = Field(default_factory=list, description="交易明细列表（涨停回调策略等支持）")


class MaCrossScanRow(BaseModel):
    code: str
    error: str | None = None
    bars_used: int | None = None
    total_return_pct: float | None = None
    buy_hold_return_pct: float | None = None
    excess_return_pct: float | None = None
    max_drawdown_pct: float | None = None
    sharpe_ratio: float | None = None
    signal_changes: int | None = None
    annualized_return_pct: float | None = None
    buy_hold_annualized_return_pct: float | None = None
    annualized_volatility_pct: float | None = None
    sortino_ratio: float | None = None
    calmar_ratio: float | None = None
    long_trades_count: int | None = None
    win_rate_pct: float | None = None
    avg_holding_return_pct: float | None = None
    underlying_beta: float | None = None
    underlying_alpha_ann_pct: float | None = None


class MaCrossScanResponse(BaseModel):
    fast_period: int
    slow_period: int
    limit: int
    commission_rate: float
    slippage_rate: float
    sort_by: str
    max_concurrent: int
    start_date: str | None = None
    end_date: str | None = None
    benchmark_code: str | None = Field(
        None,
        description="请求中的基准代码（小写）或未传 null；各行列的 β/α 均相对同一基准对齐序列",
    )
    items: list[MaCrossScanRow]


class MaCrossSignalResponse(BaseModel):
    code: str
    fast_period: int
    slow_period: int
    bars_used: int
    as_of_date: str
    position: str = Field(..., description="long 或 flat（收盘后 MA 比较）")
    close: float
    ma_fast: float
    ma_slow: float
    note: str


class MaCrossScanRunParamsBody(BaseModel):
    """POST /api/backtest/run 在 strategy_id=ma_cross_scan 时的 params 形状（与 GET ma-cross/scan 查询参数同义）。"""

    codes: str = Field(..., description="逗号或换行分隔的标的列表")
    fast: int = Field(5, ge=1, le=120)
    slow: int = Field(20, ge=2, le=500)
    limit: int = Field(500, ge=30, le=5000)
    start_date: date | None = None
    end_date: date | None = None
    commission_rate: float = Field(0.0, ge=0.0, le=0.05)
    slippage_rate: float = Field(0.0, ge=0.0, le=0.05)
    max_codes: int = Field(25, ge=1, le=40)
    sort_by: str = Field("total_return", min_length=1, max_length=64)
    max_concurrent: int = Field(8, ge=1, le=20)
    benchmark_code: str | None = None
    adjust_flag: str = Field("3", description="复权类型: 1=后复权 2=前复权 3=不复权")


class MaCrossRunParamsBody(BaseModel):
    """POST /api/backtest/run 在 strategy_id=ma_cross 时的 params 形状。"""

    code: str
    fast: int = Field(5, ge=1, le=120)
    slow: int = Field(20, ge=2, le=500)
    limit: int = Field(500, ge=30, le=5000)
    start_date: date | None = None
    end_date: date | None = None
    commission_rate: float = Field(0.0, ge=0.0, le=0.05)
    slippage_rate: float = Field(0.0, ge=0.0, le=0.05)
    benchmark_code: str | None = None
    adjust_flag: str = Field("3", description="复权类型: 1=后复权 2=前复权 3=不复权")


class BuyHoldRunParamsBody(BaseModel):
    """POST /api/backtest/run 在 strategy_id=buy_hold 时的 params 形状（无 fast/slow）。"""

    code: str
    limit: int = Field(500, ge=30, le=5000)
    start_date: date | None = None
    end_date: date | None = None
    commission_rate: float = Field(0.0, ge=0.0, le=0.05)
    slippage_rate: float = Field(0.0, ge=0.0, le=0.05)
    benchmark_code: str | None = None
    adjust_flag: str = Field("3", description="复权类型: 1=后复权 2=前复权 3=不复权")


class LimitUpPullbackRunParamsBody(BaseModel):
    """POST /api/backtest/run 在 strategy_id=limit_up_pullback 时的 params 形状。"""

    code: str
    limit: int = Field(500, ge=30, le=5000)
    start_date: date | None = None
    end_date: date | None = None
    commission_rate: float = Field(0.0, ge=0.0, le=0.05)
    slippage_rate: float = Field(0.0, ge=0.0, le=0.05)
    benchmark_code: str | None = None
    adjust_flag: str = Field("3", description="复权类型: 1=后复权 2=前复权 3=不复权")
    pullback_days: int = Field(10, ge=1, le=60)
    entry_type: str = Field("neutral", min_length=1, max_length=32)
    volume_shrink_ratio: float = Field(0.5, ge=0.1, le=1.0)
    max_hold_days: int = Field(0, ge=0, le=120, description="最大持仓天数（0=不限制）")
    time_stop_days: int = Field(0, ge=0, le=120, description="时间止损天数（建仓后N天；0=不启用）")
    time_stop_pct: float = Field(0.0, ge=-0.5, le=0.5, description="时间止损盈利阈值（如-0.02=-2%）")
    market_index_code: str | None = Field(None, description="大盘指数代码（如 sh.000001），传入后启用大盘过滤")
    require_market_bull: bool = Field(False, description="是否要求大盘多头（close>MA20>MA60）才允许建仓")
    market_strict: bool = Field(False, description="大盘严格模式：额外要求MA20斜率向上")

    @model_validator(mode="after")
    def _check_entry_type(self) -> "LimitUpPullbackRunParamsBody":
        if self.entry_type not in {"aggressive", "neutral", "conservative"}:
            raise ValueError("entry_type 须为 aggressive / neutral / conservative 之一")
        return self


class LimitUpPullbackScanRunParamsBody(BaseModel):
    """POST /api/backtest/run 在 strategy_id=limit_up_pullback_scan 时的 params 形状。"""

    codes: str = Field(..., description="逗号或换行分隔的标的列表")
    limit: int = Field(500, ge=30, le=5000)
    start_date: date | None = None
    end_date: date | None = None
    commission_rate: float = Field(0.0, ge=0.0, le=0.05)
    slippage_rate: float = Field(0.0, ge=0.0, le=0.05)
    max_codes: int = Field(25, ge=1, le=40)
    sort_by: str = Field("total_return", min_length=1, max_length=64)
    max_concurrent: int = Field(8, ge=1, le=20)
    benchmark_code: str | None = None
    adjust_flag: str = Field("3", description="复权类型: 1=后复权 2=前复权 3=不复权")
    pullback_days: int = Field(10, ge=1, le=60)
    entry_type: str = Field("neutral", min_length=1, max_length=32)
    volume_shrink_ratio: float = Field(0.5, ge=0.1, le=1.0)
    max_hold_days: int = Field(0, ge=0, le=120, description="最大持仓天数（0=不限制）")
    time_stop_days: int = Field(0, ge=0, le=120, description="时间止损天数（建仓后N天；0=不启用）")
    time_stop_pct: float = Field(0.0, ge=-0.5, le=0.5, description="时间止损盈利阈值（如-0.02=-2%）")
    market_index_code: str | None = Field(None, description="大盘指数代码（如 sh.000001），传入后启用大盘过滤")
    require_market_bull: bool = Field(False, description="是否要求大盘多头（close>MA20>MA60）才允许建仓")
    market_strict: bool = Field(False, description="大盘严格模式：额外要求MA20斜率向上")

    @model_validator(mode="after")
    def _check_entry_type(self) -> "LimitUpPullbackScanRunParamsBody":
        if self.entry_type not in {"aggressive", "neutral", "conservative"}:
            raise ValueError("entry_type 须为 aggressive / neutral / conservative 之一")
        return self


class LimitUpPullbackOptimizeParamsBody(BaseModel):
    """POST /api/backtest/limit-up-pullback/optimize 请求体。"""

    code: str = Field(..., description="标的代码，如 sh.600000")
    limit: int = Field(500, ge=30, le=5000)
    start_date: date | None = None
    end_date: date | None = None
    commission_rate: float = Field(0.0, ge=0.0, le=0.05)
    slippage_rate: float = Field(0.0, ge=0.0, le=0.05)
    benchmark_code: str | None = None
    adjust_flag: str = Field("3", description="复权类型: 1=后复权 2=前复权 3=不复权")
    # 参数网格
    entry_types: list[str] = Field(default_factory=lambda: ["neutral"], description="买点类型列表")
    pullback_days_min: int = Field(5, ge=1, le=60)
    pullback_days_max: int = Field(15, ge=1, le=60)
    pullback_days_step: int = Field(1, ge=1, le=10)
    volume_shrink_ratios: list[float] = Field(default_factory=lambda: [0.5], description="缩量比例列表")
    max_hold_days_list: list[int] = Field(default_factory=lambda: [0], description="最大持仓天数列表")
    time_stop_days_list: list[int] = Field(default_factory=lambda: [0], description="时间止损天数列表")
    time_stop_pcts: list[float] = Field(default_factory=lambda: [0.0], description="时间止损盈利阈值列表")
    ma_strict_values: list[bool] = Field(default_factory=lambda: [False], description="均线严格多头排列开关列表")
    max_combinations: int = Field(100, ge=1, le=500, description="最大参数组合数")
    sort_by: str = Field("sharpe", description="排序指标：total_return/sharpe/sortino/calmar/win_rate/max_drawdown/trades_count")
    top_n: int = Field(10, ge=1, le=100)

    @model_validator(mode="after")
    def _check_ranges(self) -> "LimitUpPullbackOptimizeParamsBody":
        for et in self.entry_types:
            if et not in {"aggressive", "neutral", "conservative"}:
                raise ValueError(f"entry_type 须为 aggressive / neutral / conservative 之一，got {et}")
        if self.pullback_days_min > self.pullback_days_max:
            raise ValueError("pullback_days_min 不能大于 pullback_days_max")
        if self.commission_rate + self.slippage_rate > 0.08:
            raise ValueError("commission_rate 与 slippage_rate 之和勿超过 0.08")
        return self


class PortfolioRunParamsBody(BaseModel):
    """POST /api/backtest/run 在 strategy_id=portfolio_equal_weight/value_weight 时的 params 形状。"""

    codes: str = Field(..., description="逗号或换行分隔的标的列表")
    limit: int = Field(500, ge=30, le=5000)
    start_date: date | None = None
    end_date: date | None = None
    commission_rate: float = Field(0.0, ge=0.0, le=0.05)
    slippage_rate: float = Field(0.0, ge=0.0, le=0.05)
    max_codes: int = Field(25, ge=1, le=40)
    benchmark_code: str | None = None
    adjust_flag: str = Field("3", description="复权类型: 1=后复权 2=前复权 3=不复权")
    strategy_for_signal: str = Field("ma_cross", description="生成信号的策略: ma_cross / buy_hold")
    weights_scheme: str = Field("equal", description="权重方案: equal / value")
    rebalance_freq: str = Field("monthly", description="再平衡频率: daily / weekly / monthly")
    fast: int = Field(5, ge=1, le=120)
    slow: int = Field(20, ge=2, le=500)
    max_concurrent: int = Field(8, ge=1, le=20)
    position_sizing_method: str = Field("equal", description="仓位算法: equal / fixed_amount / volatility_target")
    position_sizing_params: dict[str, Any] = Field(default_factory=dict, description="仓位算法参数")

    @model_validator(mode="after")
    def _check_portfolio(self) -> "PortfolioRunParamsBody":
        if self.strategy_for_signal not in {"ma_cross", "buy_hold"}:
            raise ValueError("strategy_for_signal 须为 ma_cross / buy_hold 之一")
        if self.weights_scheme not in {"equal", "value"}:
            raise ValueError("weights_scheme 须为 equal / value 之一")
        if self.rebalance_freq not in {"daily", "weekly", "monthly"}:
            raise ValueError("rebalance_freq 须为 daily / weekly / monthly 之一")
        if self.position_sizing_method not in {"equal", "fixed_amount", "volatility_target"}:
            raise ValueError("position_sizing_method 须为 equal / fixed_amount / volatility_target 之一")
        if self.commission_rate + self.slippage_rate > 0.08:
            raise ValueError("commission_rate 与 slippage_rate 之和勿超过 0.08")
        return self


class BacktestRunMvpRequest(BaseModel):
    """通用回测 MVP：同步执行；注册 ma_cross / buy_hold / ma_cross_scan v1。"""

    model_config = ConfigDict(extra="ignore")

    strategy_id: str = Field("ma_cross", min_length=1, max_length=64)
    strategy_version: str = Field("1", min_length=1, max_length=32)
    params: dict[str, Any] = Field(default_factory=dict)

    universe: Any | None = Field(
        None,
        description=(
            "**MVP 占位、不参与调度**：草案中的标的范围（列表/映射/表达式等）；"
            "实际调度仅看 strategy_id 与 params"
        ),
    )
    interval: str | None = Field(
        None,
        max_length=64,
        description="**MVP 占位、不参与调度**：草案中的周期/采样粒度等",
    )
    start: str | None = Field(
        None,
        max_length=32,
        description=(
            "**MVP 占位、不参与调度**：通用区间起点示意；"
            "MA MVP 请使用 params.start_date / params.end_date"
        ),
    )
    end: str | None = Field(
        None,
        max_length=32,
        description="**MVP 占位、不参与调度**：通用区间终点示意；MA MVP 请见 params.end_date",
    )
    initial_cash: float | None = Field(
        None,
        ge=0,
        description="**MVP 占位、不参与调度**：初始资金等；MA 回测未读取",
    )
    commission: float | None = Field(
        None,
        ge=0,
        description="**MVP 占位、不参与调度**：与 params.commission_rate 无关",
    )
    slippage: float | None = Field(
        None,
        ge=0,
        description="**MVP 占位、不参与调度**：与 params.slippage_rate 无关",
    )


class BacktestRunMvpResponse(BaseModel):
    engine_version: str = Field(
        ...,
        description="执行器版本，见 src/backtest/runner/ma_cross_executor.py",
    )
    strategy_id: str
    strategy_version: str
    assumptions: list[str] = Field(
        default_factory=list,
        description="与本次结果绑定的口径与数据假设，供审计与复现",
    )
    result: Any | None = Field(
        None,
        description="strategy_id=ma_cross/buy_hold 时为 MaCrossBacktestResponse；portfolio_* 时为 PortfolioBacktestResult；通用 dict",
    )
    scan_result: MaCrossScanResponse | None = Field(
        None,
        description="strategy_id=ma_cross_scan 时非空，与 GET /api/backtest/ma-cross/scan JSON 一致",
    )

    @model_validator(mode="after")
    def _exactly_one_payload(self) -> BacktestRunMvpResponse:
        has_r = self.result is not None
        has_s = self.scan_result is not None
        if has_r == has_s:
            raise ValueError("须恰好提供 result 或 scan_result 之一")
        return self


class BacktestRunJobAcceptedResponse(BaseModel):
    """``POST /api/backtest/run?async=1`` 受理后返回；结果经 ``GET /api/backtest/jobs/{job_id}`` 轮询。"""

    job_id: str
    status: Literal["accepted"] = "accepted"
    status_path: str = Field(
        ...,
        description="GET 轮询路径（含 /api 前缀，不含 host）",
    )


class BacktestJobCancelResponse(BaseModel):
    """``POST /api/backtest/jobs/{job_id}/cancel`` 成功时仅 ``pending`` 可取消。"""

    job_id: str
    status: Literal["cancelled"] = "cancelled"


MvpJobStatus = Literal["pending", "running", "completed", "failed", "cancelled"]


class BacktestRunJobStatusResponse(BaseModel):
    job_id: str
    status: MvpJobStatus
    async_job_persistence: Literal["memory", "redis"] = Field(
        ...,
        description="与 GET /api/backtest/catalog 同源；本条任务所在存储后端",
    )
    result: BacktestRunMvpResponse | None = None
    error: str | None = Field(
        None,
        description="status=failed 时为错误文案；cancelled 时多为 cancelled",
    )
    queued_at: str | None = Field(
        None,
        description="任务入队/受理时间（UTC，ISO-8601 Z）；无则 null",
    )
    started_at: str | None = Field(
        None,
        description="执行开始时间（UTC）；pending 时为 null",
    )
    finished_at: str | None = Field(
        None,
        description="终态时间（UTC）；completed/failed 时有值",
    )


MAX_MVP_ASYNC_JOBS = 2000
_mvp_jobs: dict[str, dict[str, Any]] = {}
_mvp_jobs_lock = asyncio.Lock()


async def _mvp_register_job(job_id: str) -> None:
    async with _mvp_jobs_lock:
        while len(_mvp_jobs) >= MAX_MVP_ASYNC_JOBS:
            oldest = next(iter(_mvp_jobs))
            del _mvp_jobs[oldest]
        _mvp_jobs[job_id] = {
            "status": "pending",
            "queued_at": utc_now_iso_z(),
            "started_at": None,
            "finished_at": None,
            "result": None,
            "error": None,
        }


async def _mvp_job_worker(job_id: str, body: BacktestRunMvpRequest) -> None:
    async with _mvp_jobs_lock:
        rec = _mvp_jobs.get(job_id)
        if rec is None:
            return
        if rec.get("status") == "cancelled":
            return
        if rec.get("status") != "pending":
            return
        rec["status"] = "running"
        rec["started_at"] = utc_now_iso_z()
    status, payload, err = await run_mvp_job_execution(body)
    async with _mvp_jobs_lock:
        if job_id not in _mvp_jobs:
            return
        cur = _mvp_jobs[job_id]
        if cur.get("status") in ("failed", "cancelled") and cur.get("finished_at"):
            return
        if cur.get("status") != "running":
            return
        fin = utc_now_iso_z()
        if status == "completed":
            cur["status"] = "completed"
            cur["result"] = payload
            cur["finished_at"] = fin
            cur["error"] = None
        else:
            cur["status"] = "failed"
            cur["error"] = err or "failed"
            cur["finished_at"] = fin
            cur["result"] = None


async def _cancel_memory_job(job_id: str) -> Literal["absent", "ok", "bad_state"]:
    async with _mvp_jobs_lock:
        rec = _mvp_jobs.get(job_id)
        if rec is None:
            return "absent"
        if rec.get("status") != "pending":
            return "bad_state"
        rec["status"] = "cancelled"
        rec["error"] = JOB_CANCELLED_MSG
        rec["result"] = None
        rec["finished_at"] = utc_now_iso_z()
        return "ok"


def _validate_mvp_request(body: BacktestRunMvpRequest) -> None:
    supported = (
        STRATEGY_ID_MA_CROSS,
        STRATEGY_ID_BUY_HOLD,
        STRATEGY_ID_MA_CROSS_SCAN,
        STRATEGY_ID_LIMIT_UP_PULLBACK,
        STRATEGY_ID_LIMIT_UP_PULLBACK_SCAN,
        STRATEGY_ID_PORTFOLIO_EQUAL,
        STRATEGY_ID_PORTFOLIO_VALUE,
    )
    if body.strategy_id not in supported or body.strategy_version != "1":
        raise HTTPException(
            status_code=400,
            detail=(
                f"仅支持 strategy_id in {supported!r} 且 strategy_version='1'，"
                f"当前 strategy_id={body.strategy_id!r} strategy_version={body.strategy_version!r}"
            ),
        )
    if body.strategy_id == STRATEGY_ID_MA_CROSS:
        try:
            MaCrossRunParamsBody.model_validate(body.params)
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=jsonable_encoder(e.errors())) from e
        return
    if body.strategy_id == STRATEGY_ID_BUY_HOLD:
        try:
            BuyHoldRunParamsBody.model_validate(body.params)
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=jsonable_encoder(e.errors())) from e
        return
    if body.strategy_id == STRATEGY_ID_LIMIT_UP_PULLBACK:
        try:
            LimitUpPullbackRunParamsBody.model_validate(body.params)
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=jsonable_encoder(e.errors())) from e
        return
    if body.strategy_id == STRATEGY_ID_LIMIT_UP_PULLBACK_SCAN:
        try:
            p = LimitUpPullbackScanRunParamsBody.model_validate(body.params)
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=jsonable_encoder(e.errors())) from e
        parsed = parse_scan_codes(p.codes, p.max_codes)
        if not parsed:
            raise HTTPException(status_code=400, detail="codes 解析后为空")
        return
    if body.strategy_id in (STRATEGY_ID_PORTFOLIO_EQUAL, STRATEGY_ID_PORTFOLIO_VALUE):
        try:
            p = PortfolioRunParamsBody.model_validate(body.params)
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=jsonable_encoder(e.errors())) from e
        parsed = parse_scan_codes(p.codes, p.max_codes)
        if not parsed:
            raise HTTPException(status_code=400, detail="codes 解析后为空")
        return
    # ma_cross_scan
    try:
        p = MaCrossScanRunParamsBody.model_validate(body.params)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors()) from e
    parsed = parse_scan_codes(p.codes, p.max_codes)
    if not parsed:
        raise HTTPException(status_code=400, detail="codes 解析后为空")


async def _execute_run_mvp(
    session: AsyncSession, body: BacktestRunMvpRequest
) -> BacktestRunMvpResponse:
    """已校验的 ``body``；同步与异步后台任务共用。"""
    if body.strategy_id == STRATEGY_ID_MA_CROSS:
        p = MaCrossRunParamsBody.model_validate(body.params)
        try:
            payload, assumptions = await execute_ma_cross_single(
                session,
                code=p.code.strip(),
                fast=p.fast,
                slow=p.slow,
                limit=p.limit,
                start_date=p.start_date,
                end_date=p.end_date,
                commission_rate=p.commission_rate,
                slippage_rate=p.slippage_rate,
                benchmark_code=p.benchmark_code,
                adjust_flag=p.adjust_flag,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        return BacktestRunMvpResponse(
            engine_version=ENGINE_VERSION,
            strategy_id=body.strategy_id,
            strategy_version=body.strategy_version,
            assumptions=assumptions,
            result=MaCrossBacktestResponse(**payload),
            scan_result=None,
        )

    if body.strategy_id == STRATEGY_ID_BUY_HOLD:
        p = BuyHoldRunParamsBody.model_validate(body.params)
        try:
            payload, assumptions = await execute_buy_hold_single(
                session,
                code=p.code.strip(),
                limit=p.limit,
                start_date=p.start_date,
                end_date=p.end_date,
                commission_rate=p.commission_rate,
                slippage_rate=p.slippage_rate,
                benchmark_code=p.benchmark_code,
                adjust_flag=p.adjust_flag,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return BacktestRunMvpResponse(
            engine_version=ENGINE_VERSION,
            strategy_id=body.strategy_id,
            strategy_version=body.strategy_version,
            assumptions=assumptions,
            result=MaCrossBacktestResponse(**payload),
            scan_result=None,
        )

    if body.strategy_id == STRATEGY_ID_LIMIT_UP_PULLBACK:
        p = LimitUpPullbackRunParamsBody.model_validate(body.params)
        try:
            payload, assumptions = await execute_limit_up_pullback_single(
                session,
                code=p.code.strip(),
                limit=p.limit,
                start_date=p.start_date,
                end_date=p.end_date,
                commission_rate=p.commission_rate,
                slippage_rate=p.slippage_rate,
                benchmark_code=p.benchmark_code,
                adjust_flag=p.adjust_flag,
                pullback_days=p.pullback_days,
                entry_type=p.entry_type,
                volume_shrink_ratio=p.volume_shrink_ratio,
                max_hold_days=p.max_hold_days,
                time_stop_days=p.time_stop_days,
                time_stop_pct=p.time_stop_pct,
                market_index_code=p.market_index_code,
                require_market_bull=p.require_market_bull,
                market_strict=p.market_strict,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return BacktestRunMvpResponse(
            engine_version=ENGINE_VERSION,
            strategy_id=body.strategy_id,
            strategy_version=body.strategy_version,
            assumptions=assumptions,
            result=MaCrossBacktestResponse(**payload),
            scan_result=None,
        )

    if body.strategy_id == STRATEGY_ID_LIMIT_UP_PULLBACK_SCAN:
        p = LimitUpPullbackScanRunParamsBody.model_validate(body.params)
        parsed = parse_scan_codes(p.codes, p.max_codes)
        try:
            items, sort_norm, bench_key = await execute_limit_up_pullback_scan(
                session,
                codes=parsed,
                limit=p.limit,
                start_date=p.start_date,
                end_date=p.end_date,
                commission_rate=p.commission_rate,
                slippage_rate=p.slippage_rate,
                sort_by=p.sort_by,
                max_concurrent=p.max_concurrent,
                benchmark_code=p.benchmark_code,
                adjust_flag=p.adjust_flag,
                pullback_days=p.pullback_days,
                entry_type=p.entry_type,
                volume_shrink_ratio=p.volume_shrink_ratio,
                max_hold_days=p.max_hold_days,
                time_stop_days=p.time_stop_days,
                time_stop_pct=p.time_stop_pct,
                market_index_code=p.market_index_code,
                require_market_bull=p.require_market_bull,
                market_strict=p.market_strict,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        bench_norm = bench_key or None
        rows = [MaCrossScanRow.model_validate(x) for x in items]
        scan = MaCrossScanResponse(
            fast_period=0,
            slow_period=0,
            limit=p.limit,
            commission_rate=round(p.commission_rate, 8),
            slippage_rate=round(p.slippage_rate, 8),
            sort_by=sort_norm,
            max_concurrent=p.max_concurrent,
            start_date=p.start_date.isoformat() if p.start_date else None,
            end_date=p.end_date.isoformat() if p.end_date else None,
            benchmark_code=bench_norm,
            items=rows,
        )
        assumptions = [
            (
                f"涨停回调策略批量扫描（entry_type={p.entry_type}, pullback_days={p.pullback_days}）；"
                "涨停检测后观察回调窗口并逐只回测。"
            ),
            f"共 {len(parsed)} 只标的（按 max_codes 截断后）。",
            f"结果按 {sort_norm} 降序；失败行沉底。",
            f"拉取日 K 最大并发 max_concurrent={p.max_concurrent}。",
        ]
        if bench_norm:
            assumptions.append(f"各标的 β/α 相对基准 {bench_norm}。")
        else:
            assumptions.append("各标的 β/α 为对标的自身日收益的回归。")
        if p.start_date or p.end_date:
            assumptions.append(
                f"日期约束：start_date={p.start_date or '∅'}，end_date={p.end_date or '∅'}（含端点）。"
            )
        return BacktestRunMvpResponse(
            engine_version=ENGINE_VERSION,
            strategy_id=body.strategy_id,
            strategy_version=body.strategy_version,
            assumptions=assumptions,
            result=None,
            scan_result=scan,
        )

    if body.strategy_id in (STRATEGY_ID_PORTFOLIO_EQUAL, STRATEGY_ID_PORTFOLIO_VALUE):
        p = PortfolioRunParamsBody.model_validate(body.params)
        try:
            payload, assumptions = await execute_portfolio_backtest(
                session,
                codes=p.codes,
                strategy_for_signal=p.strategy_for_signal,
                weights_scheme=p.weights_scheme,
                rebalance_freq=p.rebalance_freq,
                limit=p.limit,
                start_date=p.start_date,
                end_date=p.end_date,
                commission_rate=p.commission_rate,
                slippage_rate=p.slippage_rate,
                benchmark_code=p.benchmark_code,
                adjust_flag=p.adjust_flag,
                fast=p.fast,
                slow=p.slow,
                max_codes=p.max_codes,
                max_concurrent=p.max_concurrent,
                position_sizing_method=p.position_sizing_method,
                position_sizing_params=p.position_sizing_params,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return BacktestRunMvpResponse(
            engine_version=ENGINE_VERSION,
            strategy_id=body.strategy_id,
            strategy_version=body.strategy_version,
            assumptions=assumptions,
            result=payload,
            scan_result=None,
        )

    p = MaCrossScanRunParamsBody.model_validate(body.params)
    parsed = parse_scan_codes(p.codes, p.max_codes)
    try:
        items, sort_norm, bench_key = await execute_ma_cross_scan(
            session,
            codes=parsed,
            fast=p.fast,
            slow=p.slow,
            limit=p.limit,
            start_date=p.start_date,
            end_date=p.end_date,
            commission_rate=p.commission_rate,
            slippage_rate=p.slippage_rate,
            sort_by=p.sort_by,
            max_concurrent=p.max_concurrent,
            benchmark_code=p.benchmark_code,
            adjust_flag=p.adjust_flag,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    bench_norm = bench_key or None
    rows = [MaCrossScanRow.model_validate(x) for x in items]
    scan = MaCrossScanResponse(
        fast_period=p.fast,
        slow_period=p.slow,
        limit=p.limit,
        commission_rate=round(p.commission_rate, 8),
        slippage_rate=round(p.slippage_rate, 8),
        sort_by=sort_norm,
        max_concurrent=p.max_concurrent,
        start_date=p.start_date.isoformat() if p.start_date else None,
        end_date=p.end_date.isoformat() if p.end_date else None,
        benchmark_code=bench_norm,
        items=rows,
    )
    assumptions = build_ma_cross_scan_assumptions(
        n_codes=len(parsed),
        sort_by=sort_norm,
        max_concurrent=p.max_concurrent,
        bench=bench_norm,
        start_date=p.start_date,
        end_date=p.end_date,
        adjust_flag=p.adjust_flag,
    )
    return BacktestRunMvpResponse(
        engine_version=ENGINE_VERSION,
        strategy_id=body.strategy_id,
        strategy_version=body.strategy_version,
        assumptions=assumptions,
        result=None,
        scan_result=scan,
    )


class BacktestStrategyCatalogEntry(BaseModel):
    """POST /api/backtest/run 可提交的已注册策略（与内核常量对齐）。"""

    strategy_id: str
    strategy_version: str
    title: str
    description: str
    response_shape: Literal["result", "scan_result"] = Field(
        ...,
        description="成功响应中 BacktestRunMvpResponse 的非空字段名",
    )
    archive_kind: str = Field(
        ...,
        description="与 POST /api/backtest/runs 及 GET /api/backtest/runs?kind= 的 kind 字段一致",
    )
    get_equivalent_paths: list[str] = Field(
        default_factory=list,
        description="与本次执行同义的只读 GET 路径（不含 host）",
    )


class BacktestEngineCatalogResponse(BaseModel):
    engine_version: str
    strategies: list[BacktestStrategyCatalogEntry]
    post_run_path: str = Field(
        "/api/backtest/run",
        description="统一执行入口；默认同步 POST 返回 200；附加查询参数见 async_run_query_param",
    )
    doc_ref: str = Field(
        "docs/GENERIC_BACKTEST_DRAFT.md",
        description="接口草案与迁移路径",
    )
    async_run_query_param: str = Field(
        "async",
        description="POST 到 post_run_path 时 ?async=1（或 true）受理异步任务（202 + job_id）",
    )
    async_job_status_path_template: str = Field(
        "/api/backtest/jobs/{job_id}",
        description="将 {job_id} 替换为 202 响应中的 job_id 后 GET 轮询状态",
    )
    async_job_persistence: Literal["memory", "redis"] = Field(
        "memory",
        description="异步任务状态存储：memory=进程内（重启丢失）；redis=Redis 列表队列 + JSON 记录（见 BACKTEST_ASYNC_JOB_STORE）",
    )
    async_job_queue_key: str | None = Field(
        None,
        description="Redis 异步时 BRPOP 的列表键；memory 时为 null",
    )
    async_job_queue_depth: int | None = Field(
        None,
        description="Redis 异步时队列中待消费 job_id 条数（LLEN）；memory 时为 null",
    )


def _backtest_engine_catalog_payload() -> BacktestEngineCatalogResponse:
    return BacktestEngineCatalogResponse(
        engine_version=ENGINE_VERSION,
        async_job_persistence=catalog_async_job_persistence(),
        strategies=[
            BacktestStrategyCatalogEntry(
                strategy_id=STRATEGY_ID_MA_CROSS,
                strategy_version="1",
                title="双均线 · 单标的",
                description=(
                    "params 与 GET /api/backtest/ma-cross 查询参数同义（code, fast, slow, limit, "
                    "start_date, end_date, commission_rate, slippage_rate, benchmark_code）。"
                ),
                response_shape="result",
                archive_kind="ma_cross_single",
                get_equivalent_paths=["/api/backtest/ma-cross"],
            ),
            BacktestStrategyCatalogEntry(
                strategy_id=STRATEGY_ID_MA_CROSS_SCAN,
                strategy_version="1",
                title="双均线 · 批量扫描",
                description=(
                    "params 与 GET /api/backtest/ma-cross/scan 同义（codes, fast, slow, limit, "
                    "start_date, end_date, commission_rate, slippage_rate, max_codes, sort_by, "
                    "max_concurrent, benchmark_code）。"
                ),
                response_shape="scan_result",
                archive_kind="ma_cross_scan",
                get_equivalent_paths=["/api/backtest/ma-cross/scan"],
            ),
            BacktestStrategyCatalogEntry(
                strategy_id=STRATEGY_ID_BUY_HOLD,
                strategy_version="1",
                title="买入持有 · 单标的",
                description=(
                    "params 与 GET /api/backtest/buy-hold 查询参数同义（code, limit, "
                    "start_date, end_date, commission_rate, slippage_rate, benchmark_code）；"
                    "无 fast/slow；响应中 fast_period/slow_period 为占位。"
                ),
                response_shape="result",
                archive_kind="buy_hold_single",
                get_equivalent_paths=["/api/backtest/buy-hold"],
            ),
            BacktestStrategyCatalogEntry(
                strategy_id=STRATEGY_ID_LIMIT_UP_PULLBACK,
                strategy_version="1",
                title="涨停回调 · 单标的",
                description=(
                    "params: code, limit, start_date, end_date, commission_rate, slippage_rate, "
                    "benchmark_code, pullback_days, entry_type, volume_shrink_ratio；"
                    "响应中 fast_period/slow_period/signal_changes 为占位 0。"
                ),
                response_shape="result",
                archive_kind="limit_up_pullback_single",
                get_equivalent_paths=["/api/backtest/limit-up-pullback"],
            ),
            BacktestStrategyCatalogEntry(
                strategy_id=STRATEGY_ID_LIMIT_UP_PULLBACK_SCAN,
                strategy_version="1",
                title="涨停回调 · 批量扫描",
                description=(
                    "params: codes, limit, start_date, end_date, commission_rate, slippage_rate, "
                    "max_codes, sort_by, max_concurrent, benchmark_code, pullback_days, "
                    "entry_type, volume_shrink_ratio；扫描响应中 fast_period/slow_period 为占位 0。"
                ),
                response_shape="scan_result",
                archive_kind="limit_up_pullback_scan",
                get_equivalent_paths=["/api/backtest/limit-up-pullback/scan"],
            ),
            BacktestStrategyCatalogEntry(
                strategy_id=STRATEGY_ID_PORTFOLIO_EQUAL,
                strategy_version="1",
                title="组合回测 · 等权",
                description=(
                    "多标的组合回测，等权分配，支持日/周/月频再平衡。"
                    "params: codes, limit, start_date, end_date, commission_rate, slippage_rate, "
                    "max_codes, benchmark_code, strategy_for_signal, weights_scheme, rebalance_freq, fast, slow。"
                ),
                response_shape="result",
                archive_kind="portfolio_equal_weight",
                get_equivalent_paths=[],
            ),
            BacktestStrategyCatalogEntry(
                strategy_id=STRATEGY_ID_PORTFOLIO_VALUE,
                strategy_version="1",
                title="组合回测 · 市值加权",
                description=(
                    "多标的组合回测，市值加权分配，支持日/周/月频再平衡。"
                    "params: codes, limit, start_date, end_date, commission_rate, slippage_rate, "
                    "max_codes, benchmark_code, strategy_for_signal, weights_scheme, rebalance_freq, fast, slow。"
                ),
                response_shape="result",
                archive_kind="portfolio_value_weight",
                get_equivalent_paths=[],
            ),
        ],
    )


@router.get("/catalog", response_model=BacktestEngineCatalogResponse)
async def backtest_engine_catalog():
    """列出通用回测 MVP 已注册策略，供客户端与脚本发现 POST /run 契约。"""
    base = _backtest_engine_catalog_payload()
    r = get_redis_client()
    if r is None or not effective_redis_async_jobs():
        return base
    try:
        depth = int(await r.llen(QUEUE_KEY))
    except Exception:
        depth = 0
    return base.model_copy(
        update={
            "async_job_queue_key": QUEUE_KEY,
            "async_job_queue_depth": max(0, depth),
        }
    )


@router.get("/ma-cross/signal", response_model=MaCrossSignalResponse)
async def ma_cross_signal(
    code: str = Query(..., description="标的代码"),
    fast: int = Query(5, ge=1, le=120),
    slow: int = Query(20, ge=2, le=500),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    limit: int = Query(500, ge=30, le=5000, description="与单标的回测一致；须 ≥ slow"),
    adjust_flag: Literal["1", "2", "3"] = Query("3", description="复权类型: 1=后复权 2=前复权 3=不复权"),
    session: AsyncSession = Depends(get_session),
):
    """最近一根有效 K 上的双均线多空状态（无权益曲线、无费率）。"""
    try:
        body = await compute_ma_cross_signal(
            session,
            code=code.strip(),
            fast=fast,
            slow=slow,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            adjust_flag=adjust_flag,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return MaCrossSignalResponse(**body)


@router.get("/ma-cross/scan")
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
    export: str = Query(
        "json",
        description="json（默认）或 csv；csv 带 UTF-8 BOM，适合 Excel",
    ),
    sort_by: str = Query(
        "total_return",
        description=(
            "排序：total_return | excess_return | sharpe | buy_hold | "
            "ann_return | sortino | calmar | win_rate（额权）| avg_holding | "
            "underlying_beta | underlying_alpha"
        ),
    ),
    max_concurrent: int = Query(
        8,
        ge=1,
        le=20,
        description="并行拉取 K 线的最大并发数",
    ),
    benchmark_code: str | None = Query(
        None,
        description=(
            "可选，如 sh.000300；各标的 β/α 相对同一基准（按各标的交易日对齐）。"
            "不传则对标的自身日收益。无该基准日 K 时 400。"
        ),
    ),
    adjust_flag: Literal["1", "2", "3"] = Query("3", description="复权类型: 1=后复权 2=前复权 3=不复权"),
    session: AsyncSession = Depends(get_session),
):
    if export not in ("json", "csv"):
        raise HTTPException(status_code=400, detail="export 须为 json 或 csv")
    if fast >= slow:
        raise HTTPException(status_code=400, detail="fast 必须小于 slow")
    if commission_rate + slippage_rate > 0.08:
        raise HTTPException(
            status_code=400,
            detail="commission_rate 与 slippage_rate 之和勿超过 0.08",
        )
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date 不能晚于 end_date")

    parsed = parse_scan_codes(codes, max_codes)
    if not parsed:
        raise HTTPException(status_code=400, detail="codes 解析后为空")

    try:
        items, sort_norm, bench_key = await execute_ma_cross_scan(
            session,
            codes=parsed,
            fast=fast,
            slow=slow,
            limit=limit,
            start_date=start_date,
            end_date=end_date,
            commission_rate=commission_rate,
            slippage_rate=slippage_rate,
            sort_by=sort_by,
            max_concurrent=max_concurrent,
            benchmark_code=benchmark_code,
            adjust_flag=adjust_flag,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    bench_norm = bench_key or None

    if export == "csv":
        body = ma_cross_scan_csv_bytes(
            items,
            fast=fast,
            slow=slow,
            limit=limit,
            commission_rate=round(commission_rate, 8),
            slippage_rate=round(slippage_rate, 8),
            sort_by=sort_norm,
            start_date=start_date,
            end_date=end_date,
            benchmark_code=bench_norm,
        )
        return Response(
            content=body,
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="ma_cross_scan.csv"'
            },
        )

    rows = [MaCrossScanRow.model_validate(x) for x in items]
    return MaCrossScanResponse(
        fast_period=fast,
        slow_period=slow,
        limit=limit,
        commission_rate=round(commission_rate, 8),
        slippage_rate=round(slippage_rate, 8),
        sort_by=sort_norm,
        max_concurrent=max_concurrent,
        start_date=start_date.isoformat() if start_date else None,
        end_date=end_date.isoformat() if end_date else None,
        benchmark_code=bench_norm,
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
    benchmark_code: str | None = Query(
        None,
        description=(
            "可选，如 sh.000300；β/α 为策略日收益对基准日收益的 OLS（标的交易日对齐、仅前向填充）。"
            "不传则对标的自身日收益。无该基准日 K 时 400。"
        ),
    ),
    adjust_flag: Literal["1", "2", "3"] = Query("3", description="复权类型: 1=后复权 2=前复权 3=不复权"),
    session: AsyncSession = Depends(get_session),
):
    if fast >= slow:
        raise HTTPException(status_code=400, detail="fast 必须小于 slow")
    if commission_rate + slippage_rate > 0.08:
        raise HTTPException(
            status_code=400,
            detail="commission_rate 与 slippage_rate 之和勿超过 0.08",
        )
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date 不能晚于 end_date")

    try:
        body, _assumptions = await execute_ma_cross_single(
            session,
            code=code.strip(),
            fast=fast,
            slow=slow,
            limit=limit,
            start_date=start_date,
            end_date=end_date,
            commission_rate=commission_rate,
            slippage_rate=slippage_rate,
            benchmark_code=benchmark_code,
            adjust_flag=adjust_flag,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return MaCrossBacktestResponse(**body)


@router.get("/buy-hold", response_model=MaCrossBacktestResponse)
async def buy_hold_backtest(
    code: str = Query(..., description="标的代码，如 sh.000001"),
    start_date: date | None = Query(None, description="起始日（含）"),
    end_date: date | None = Query(None, description="结束日（含）"),
    limit: int = Query(500, ge=30, le=5000, description="最多使用多少根日 K（从新到旧取，再按时间正序回测）"),
    commission_rate: float = Query(
        0.0,
        ge=0.0,
        le=0.05,
        description="单边手续费率；买入持有用双边一次近似，见 assumptions / note",
    ),
    slippage_rate: float = Query(
        0.0,
        ge=0.0,
        le=0.05,
        description="滑点率（与手续费同口径）",
    ),
    benchmark_code: str | None = Query(
        None,
        description=(
            "可选，如 sh.000300；β/α 为策略日收益对基准日收益的 OLS（标的交易日对齐、仅前向填充）。"
            "不传则对标的自身日收益。无该基准日 K 时 400。"
        ),
    ),
    adjust_flag: Literal["1", "2", "3"] = Query("3", description="复权类型: 1=后复权 2=前复权 3=不复权"),
    session: AsyncSession = Depends(get_session),
):
    if commission_rate + slippage_rate > 0.08:
        raise HTTPException(
            status_code=400,
            detail="commission_rate 与 slippage_rate 之和勿超过 0.08",
        )
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date 不能晚于 end_date")

    try:
        body, _assumptions = await execute_buy_hold_single(
            session,
            code=code.strip(),
            limit=limit,
            start_date=start_date,
            end_date=end_date,
            commission_rate=commission_rate,
            slippage_rate=slippage_rate,
            benchmark_code=benchmark_code,
            adjust_flag=adjust_flag,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return MaCrossBacktestResponse(**body)


@router.get("/limit-up-pullback", response_model=MaCrossBacktestResponse)
async def limit_up_pullback_backtest(
    code: str = Query(..., description="标的代码，如 sh.000001"),
    start_date: date | None = Query(None, description="起始日（含）"),
    end_date: date | None = Query(None, description="结束日（含）"),
    limit: int = Query(500, ge=30, le=5000, description="最多使用多少根日 K"),
    commission_rate: float = Query(0.0, ge=0.0, le=0.05),
    slippage_rate: float = Query(0.0, ge=0.0, le=0.05),
    benchmark_code: str | None = Query(None),
    adjust_flag: Literal["1", "2", "3"] = Query("3", description="复权类型: 1=后复权 2=前复权 3=不复权"),
    pullback_days: int = Query(10, ge=1, le=60),
    entry_type: str = Query("neutral", min_length=1, max_length=32),
    volume_shrink_ratio: float = Query(0.5, ge=0.1, le=1.0),
    max_hold_days: int = Query(0, ge=0, le=120, description="最大持仓天数（0=不限制）"),
    time_stop_days: int = Query(0, ge=0, le=120, description="时间止损天数（建仓后N天；0=不启用）"),
    time_stop_pct: float = Query(0.0, ge=-0.5, le=0.5, description="时间止损盈利阈值（如-0.02=-2%）"),
    market_index_code: str | None = Query(None, description="大盘指数代码（如 sh.000001），传入后启用大盘过滤"),
    require_market_bull: bool = Query(False, description="是否要求大盘多头（close>MA20>MA60）才允许建仓"),
    market_strict: bool = Query(False, description="大盘严格模式：额外要求MA20斜率向上"),
    session: AsyncSession = Depends(get_session),
):
    if entry_type not in {"aggressive", "neutral", "conservative"}:
        raise HTTPException(status_code=400, detail="entry_type 须为 aggressive / neutral / conservative 之一")
    if commission_rate + slippage_rate > 0.08:
        raise HTTPException(status_code=400, detail="commission_rate 与 slippage_rate 之和勿超过 0.08")
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date 不能晚于 end_date")

    try:
        body, _assumptions = await execute_limit_up_pullback_single(
            session,
            code=code.strip(),
            limit=limit,
            start_date=start_date,
            end_date=end_date,
            commission_rate=commission_rate,
            slippage_rate=slippage_rate,
            benchmark_code=benchmark_code,
            adjust_flag=adjust_flag,
            pullback_days=pullback_days,
            entry_type=entry_type,
            volume_shrink_ratio=volume_shrink_ratio,
            max_hold_days=max_hold_days,
            time_stop_days=time_stop_days,
            time_stop_pct=time_stop_pct,
            market_index_code=market_index_code,
            require_market_bull=require_market_bull,
            market_strict=market_strict,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return MaCrossBacktestResponse(**body)


@router.get("/limit-up-pullback/scan")
async def limit_up_pullback_scan(
    codes: str = Query(..., description="逗号或换行分隔的标的列表"),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    limit: int = Query(500, ge=30, le=5000),
    commission_rate: float = Query(0.0, ge=0.0, le=0.05),
    slippage_rate: float = Query(0.0, ge=0.0, le=0.05),
    max_codes: int = Query(25, ge=1, le=40),
    export: str = Query("json", description="json 或 csv"),
    sort_by: str = Query("total_return"),
    max_concurrent: int = Query(8, ge=1, le=20),
    benchmark_code: str | None = Query(None),
    adjust_flag: Literal["1", "2", "3"] = Query("3", description="复权类型: 1=后复权 2=前复权 3=不复权"),
    pullback_days: int = Query(10, ge=1, le=60),
    entry_type: str = Query("neutral", min_length=1, max_length=32),
    volume_shrink_ratio: float = Query(0.5, ge=0.1, le=1.0),
    max_hold_days: int = Query(0, ge=0, le=120, description="最大持仓天数（0=不限制）"),
    time_stop_days: int = Query(0, ge=0, le=120, description="时间止损天数（建仓后N天；0=不启用）"),
    time_stop_pct: float = Query(0.0, ge=-0.5, le=0.5, description="时间止损盈利阈值（如-0.02=-2%）"),
    market_index_code: str | None = Query(None, description="大盘指数代码（如 sh.000001），传入后启用大盘过滤"),
    require_market_bull: bool = Query(False, description="是否要求大盘多头（close>MA20>MA60）才允许建仓"),
    market_strict: bool = Query(False, description="大盘严格模式：额外要求MA20斜率向上"),
    session: AsyncSession = Depends(get_session),
):
    if entry_type not in {"aggressive", "neutral", "conservative"}:
        raise HTTPException(status_code=400, detail="entry_type 须为 aggressive / neutral / conservative 之一")
    if commission_rate + slippage_rate > 0.08:
        raise HTTPException(status_code=400, detail="commission_rate 与 slippage_rate 之和勿超过 0.08")
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date 不能晚于 end_date")
    if export not in ("json", "csv"):
        raise HTTPException(status_code=400, detail="export 须为 json 或 csv")

    parsed = parse_scan_codes(codes, max_codes)
    if not parsed:
        raise HTTPException(status_code=400, detail="codes 解析后为空")

    try:
        items, sort_norm, bench_key = await execute_limit_up_pullback_scan(
            session,
            codes=parsed,
            limit=limit,
            start_date=start_date,
            end_date=end_date,
            commission_rate=commission_rate,
            slippage_rate=slippage_rate,
            sort_by=sort_by,
            max_concurrent=max_concurrent,
            benchmark_code=benchmark_code,
            adjust_flag=adjust_flag,
            pullback_days=pullback_days,
            entry_type=entry_type,
            volume_shrink_ratio=volume_shrink_ratio,
            max_hold_days=max_hold_days,
            time_stop_days=time_stop_days,
            time_stop_pct=time_stop_pct,
            market_index_code=market_index_code,
            require_market_bull=require_market_bull,
            market_strict=market_strict,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    bench_norm = bench_key or None

    if export == "csv":
        # 复用 ma_cross 的 CSV 生成器（字段形状一致）
        from src.backtest.scan import ma_cross_scan_csv_bytes

        body = ma_cross_scan_csv_bytes(
            items,
            fast=0,
            slow=0,
            limit=limit,
            commission_rate=round(commission_rate, 8),
            slippage_rate=round(slippage_rate, 8),
            sort_by=sort_norm,
            start_date=start_date,
            end_date=end_date,
            benchmark_code=bench_norm,
        )
        return Response(
            content=body,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="limit_up_pullback_scan.csv"'},
        )

    rows = [MaCrossScanRow.model_validate(x) for x in items]
    return MaCrossScanResponse(
        fast_period=0,
        slow_period=0,
        limit=limit,
        commission_rate=round(commission_rate, 8),
        slippage_rate=round(slippage_rate, 8),
        sort_by=sort_norm,
        max_concurrent=max_concurrent,
        start_date=start_date.isoformat() if start_date else None,
        end_date=end_date.isoformat() if end_date else None,
        benchmark_code=bench_norm,
        items=rows,
    )


@router.post("/limit-up-pullback/optimize")
async def limit_up_pullback_optimize(
    body: LimitUpPullbackOptimizeParamsBody,
    session: AsyncSession = Depends(get_session),
):
    """
    涨停回调策略参数网格优化：扫描多个参数组合，返回 Top-N 最优结果。
    """
    c = body.code.strip()
    repo = KlineRepository(session)
    klines = await repo.get_daily(
        code=c,
        start_date=body.start_date,
        end_date=body.end_date,
        limit=body.limit,
        adjust_flag=body.adjust_flag,
    )
    if len(klines) < 30:
        raise HTTPException(
            status_code=400,
            detail=f"K 线不足：涨停回调策略至少需要 30 根，当前 {len(klines)}"
        )

    stock_repo = StockRepository(session)
    stock_info = await stock_repo.get_by_code(c)
    stock_type = stock_info.stock_type if stock_info else StockType.COMMON

    bench_norm = (body.benchmark_code or "").strip().lower() or None
    bench_klines = None
    if bench_norm:
        bench_klines = await repo.get_daily(
            code=bench_norm,
            start_date=body.start_date,
            end_date=body.end_date,
            limit=body.limit,
            adjust_flag=body.adjust_flag,
        )

    grid = LimitUpPullbackParamGrid(
        entry_types=body.entry_types,
        pullback_days_list=list(
            range(body.pullback_days_min, body.pullback_days_max + 1, body.pullback_days_step)
        ),
        volume_shrink_ratios=body.volume_shrink_ratios,
        max_hold_days_list=body.max_hold_days_list,
        time_stop_days_list=body.time_stop_days_list,
        time_stop_pcts=body.time_stop_pcts,
        ma_strict_values=body.ma_strict_values,
        max_combinations=body.max_combinations,
    )

    try:
        results = run_limit_up_pullback_param_grid(
            klines,
            stock_type=stock_type,
            grid=grid,
            commission_rate=body.commission_rate,
            slippage_rate=body.slippage_rate,
            benchmark_klines=bench_klines,
            stock_info=stock_info,
            sort_by=body.sort_by,
            top_n=body.top_n,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return {
        "code": c,
        "bars_used": len(klines),
        "combinations_tested": len(results),
        "sort_by": body.sort_by,
        "top_n": body.top_n,
        "results": results,
    }


@router.post(
    "/jobs/{job_id}/cancel",
    response_model=BacktestJobCancelResponse,
    responses={
        404: {"description": "job_id 不存在"},
        409: {"description": "仅 pending 可取消；running 请等待或依赖超时回收"},
    },
    summary="取消排队中的异步回测任务",
)
async def backtest_run_mvp_job_cancel(job_id: str):
    """
    仅 **``pending``** 可取消并进入 **``cancelled``**；**``running`` / 终态** 返回 **409**。
    Redis 模式下已入队的任务仍会被 worker **BRPOP** 到，但执行前发现 **``cancelled``** 即跳过。
    """
    r = get_redis_client()
    if effective_redis_async_jobs() and r is not None:
        out = await cancel_redis_pending_job(r, job_id)
    else:
        out = await _cancel_memory_job(job_id)
    if out == "absent":
        raise HTTPException(status_code=404, detail="job_id 不存在或已淘汰")
    if out == "bad_state":
        raise HTTPException(
            status_code=409,
            detail="仅 pending 状态可取消；running 请等待结束或由 GET 轮询触发超时回收",
        )
    return BacktestJobCancelResponse(job_id=job_id)


@router.get(
    "/jobs/{job_id}",
    response_model=BacktestRunJobStatusResponse,
    summary="查询异步回测任务状态",
)
async def backtest_run_mvp_job_status(job_id: str):
    """
    轮询 ``POST /api/backtest/run?async=1`` 返回的 ``job_id``。
    响应体含 **``async_job_persistence``**，与 **``GET /api/backtest/catalog``** 同源，便于轮询端无需额外拉目录。
    **``running``** 若超过 **``BACKTEST_ASYNC_JOB_STUCK_SEC``**（默认 1800，``0`` 关闭）未结束，本接口可将任务置为 **``failed``** 并写 ``finished_at``。
    """
    r = get_redis_client()
    if effective_redis_async_jobs() and r is not None:
        raw = await redis_job_status_snapshot(r, job_id)
        if raw is not None:
            raw = await reclaim_stale_running_redis(r, job_id, raw)
    else:
        async with _mvp_jobs_lock:
            raw = _mvp_jobs.get(job_id)
            if raw is not None and is_running_stale(raw):
                raw["status"] = "failed"
                raw["error"] = STALE_RUNNING_RECLAIM_MSG
                raw["result"] = None
                raw["finished_at"] = utc_now_iso_z()
    if raw is None:
        raise HTTPException(status_code=404, detail="job_id 不存在或已淘汰")
    st_raw = raw["status"]
    if st_raw not in ("pending", "running", "completed", "failed", "cancelled"):
        st_raw = "failed"
    st: MvpJobStatus = st_raw  # type: ignore[assignment]
    err = raw.get("error")
    result: BacktestRunMvpResponse | None = None
    if st == "completed" and raw.get("result") is not None:
        result = BacktestRunMvpResponse.model_validate(raw["result"])
    elif st == "cancelled":
        result = None

    def _opt_ts(v: Any) -> str | None:
        return v.strip() if isinstance(v, str) and v.strip() else None

    return BacktestRunJobStatusResponse(
        job_id=job_id,
        status=st,
        async_job_persistence=catalog_async_job_persistence(),
        result=result,
        error=str(err) if err else None,
        queued_at=_opt_ts(raw.get("queued_at")),
        started_at=_opt_ts(raw.get("started_at")),
        finished_at=_opt_ts(raw.get("finished_at")),
    )


@router.post(
    "/run",
    response_model=None,
    responses={
        200: {
            "description": "同步执行完成",
            "model": BacktestRunMvpResponse,
        },
        202: {
            "description": "已受理异步任务，请 GET /api/backtest/jobs/{job_id} 轮询",
            "model": BacktestRunJobAcceptedResponse,
        },
    },
    summary="通用回测 MVP（同步或异步）",
)
async def backtest_run_mvp(
    body: BacktestRunMvpRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    async_run: bool = Query(
        False,
        alias="async",
        description="为 true 时异步执行：返回 202 + job_id，通过 GET /api/backtest/jobs/{job_id} 取结果",
    ),
):
    """
    通用回测 MVP：与 GET /api/backtest/ma-cross* / buy-hold 共用内核，额外返回 assumptions / engine_version。
    支持 strategy_id=`ma_cross`（单标的）、`buy_hold`（买入持有单标的）或 `ma_cross_scan`（批量），strategy_version=`1`。

    默认同步 200；**``?async=1``** 时返回 **202** 及 ``job_id``，由 **GET /api/backtest/jobs/{job_id}** 轮询
    ``pending`` / ``running`` / ``completed`` / ``failed`` / ``cancelled``（取消）。
    若 ``REDIS_ENABLED`` 且 ``BACKTEST_ASYNC_JOB_STORE`` 为 ``auto``（默认），任务入 **Redis 队列** 并持久化记录；
    否则为进程内表（重启清空）。``BACKTEST_ASYNC_JOB_STORE=redis`` 且 Redis 不可用时返回 **503**。
    """
    from src.common.kill_switch import check_or_raise

    await check_or_raise()
    _validate_mvp_request(body)
    if async_run:
        enforce_redis_job_store_or_503()
        job_id = uuid.uuid4().hex
        r = get_redis_client()
        if effective_redis_async_jobs() and r is not None:
            await enqueue_redis_async_job(r, job_id, body)
        else:
            await _mvp_register_job(job_id)
            background_tasks.add_task(_mvp_job_worker, job_id, body)
        path = f"/api/backtest/jobs/{job_id}"
        accepted = BacktestRunJobAcceptedResponse(job_id=job_id, status_path=path)
        return JSONResponse(status_code=202, content=accepted.model_dump())

    return await _execute_run_mvp(session, body)


class BacktestRunCreate(BaseModel):
    kind: Literal[
        "ma_cross_single",
        "ma_cross_scan",
        "buy_hold_single",
        "limit_up_pullback_single",
        "limit_up_pullback_scan",
        "portfolio_equal_weight",
        "portfolio_value_weight",
    ]
    request_params: dict[str, Any] = Field(default_factory=dict)
    response_payload: dict[str, Any] = Field(default_factory=dict)


class BacktestRunListItem(BaseModel):
    id: int
    kind: str
    summary: str
    created_at: str


class BacktestRunsListResponse(BaseModel):
    items: list[BacktestRunListItem]
    total: int
    limit: int
    offset: int


class BacktestRunDetailResponse(BaseModel):
    id: int
    kind: str
    summary: str
    created_at: str
    request_params: dict[str, Any]
    response_payload: dict[str, Any]


def _user_id_or_system(current_user: dict) -> int | None:
    """将系统用户（id=0）映射为 None，以便与 user_id=NULL 的旧数据兼容。"""
    uid = current_user.get("id", 0)
    return None if uid == 0 else uid


@router.post("/runs", status_code=201)
async def backtest_run_create(
    body: BacktestRunCreate,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """保存一次单标的回测或批量扫描的完整请求/响应 JSON（供日后查阅）。"""
    if not isinstance(body.request_params, dict) or not isinstance(body.response_payload, dict):
        raise HTTPException(status_code=400, detail="request_params 与 response_payload 须为 JSON 对象")
    try:
        assert_run_payload_size(body.request_params, body.response_payload)
    except ValueError as e:
        raise HTTPException(status_code=413, detail=str(e)) from e
    summary = build_summary(body.kind, body.response_payload)
    user_id = _user_id_or_system(current_user)
    repo = BacktestRunRepository(session)
    row = await repo.create(
        kind=body.kind,
        summary=summary,
        request_params=body.request_params,
        response_payload=body.response_payload,
        user_id=user_id,
    )
    return {"id": row.id, "summary": row.summary}


@router.get("/runs", response_model=BacktestRunsListResponse)
async def backtest_runs_list(
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    kind: Literal[
        "ma_cross_single",
        "ma_cross_scan",
        "buy_hold_single",
        "limit_up_pullback_single",
        "limit_up_pullback_scan",
        "portfolio_equal_weight",
        "portfolio_value_weight",
    ] | None = Query(
        None, description="仅列出该类型的存档；不传则全部"
    ),
    q: str | None = Query(None, max_length=120, description="摘要子串过滤（LIKE %q%）"),
) -> BacktestRunsListResponse:
    q_norm = (q.strip() if q else "") or None
    user_id = _user_id_or_system(current_user)
    repo = BacktestRunRepository(session)
    total = await repo.count_all(kind=kind, q=q_norm, user_id=user_id)
    rows = await repo.list_recent(limit=limit, offset=offset, kind=kind, q=q_norm, user_id=user_id)
    items = [
        BacktestRunListItem(
            id=r.id,
            kind=r.kind,
            summary=r.summary,
            created_at=r.created_at.isoformat() if r.created_at else "",
        )
        for r in rows
    ]
    return BacktestRunsListResponse(items=items, total=total, limit=limit, offset=offset)


@router.delete("/runs/{run_id}", status_code=204)
async def backtest_run_delete(
    run_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> Response:
    """删除一条存档（不可恢复）；只能删除自己的记录。"""
    user_id = _user_id_or_system(current_user)
    repo = BacktestRunRepository(session)
    row = await repo.get(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    if row.user_id != user_id:
        raise HTTPException(status_code=404, detail="记录不存在")
    if not await repo.delete_by_id(run_id):
        raise HTTPException(status_code=404, detail="记录不存在")
    return Response(status_code=204)


@router.get("/runs/{run_id}", response_model=BacktestRunDetailResponse)
async def backtest_run_detail(
    run_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> BacktestRunDetailResponse:
    user_id = _user_id_or_system(current_user)
    repo = BacktestRunRepository(session)
    row = await repo.get(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    if row.user_id != user_id:
        raise HTTPException(status_code=404, detail="记录不存在")
    return BacktestRunDetailResponse(
        id=row.id,
        kind=row.kind,
        summary=row.summary,
        created_at=row.created_at.isoformat() if row.created_at else "",
        request_params=dict(row.request_params or {}),
        response_payload=dict(row.response_payload or {}),
    )


# ---------------------------------------------------------------------------
# Walk-forward 分析
# ---------------------------------------------------------------------------


class WalkForwardRequest(BaseModel):
    """Walk-forward 分析请求。"""

    code: str = Field(..., description="标的代码")
    strategy_id: str = Field("buy_hold", description="策略 ID：buy_hold / ma_cross")
    fast: int = Field(5, ge=1, le=120, description="ma_cross 快线周期")
    slow: int = Field(20, ge=2, le=500, description="ma_cross 慢线周期")
    train_days: int = Field(252, ge=60, le=1000, description="训练期交易日数")
    test_days: int = Field(63, ge=20, le=252, description="测试期交易日数")
    step_days: int = Field(63, ge=20, le=252, description="滑动步长")
    commission_rate: float = Field(0.0, ge=0.0, le=0.05)
    slippage_rate: float = Field(0.0, ge=0.0, le=0.05)
    adjust_flag: str = Field("3", description="复权类型")
    limit: int = Field(5000, ge=100, le=5000, description="单期最多 K 线数")


class WalkForwardFoldResult(BaseModel):
    fold: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    test_total_return: float | None = None
    test_sharpe: float | None = None
    test_max_drawdown: float | None = None


class WalkForwardResponse(BaseModel):
    code: str
    strategy_id: str
    folds: list[WalkForwardFoldResult]
    aggregated: dict[str, Any]


@router.post("/walk-forward", response_model=WalkForwardResponse)
async def backtest_walk_forward(
    body: WalkForwardRequest,
    session: AsyncSession = Depends(get_session),
) -> WalkForwardResponse:
    """Walk-forward 分析：滚动窗口训练+验证，防止过拟合。"""
    from src.backtest.walk_forward import aggregate_results, generate_windows

    # 获取数据时间范围
    from src.data.storage import KlineRepository

    repo = KlineRepository(session)
    klines = await repo.get_daily(
        code=body.code.strip(),
        limit=body.limit * 3,
        adjust_flag=body.adjust_flag,
    )
    if len(klines) < 100:
        raise HTTPException(status_code=400, detail="K 线不足，无法生成 walk-forward 窗口")

    data_start = klines[0].trade_date
    data_end = klines[-1].trade_date

    windows = generate_windows(
        start_date=data_start,
        end_date=data_end,
        train_days=body.train_days,
        test_days=body.test_days,
        step_days=body.step_days,
    )

    if not windows:
        raise HTTPException(status_code=400, detail="窗口参数与数据范围不匹配，无法生成窗口")

    folds: list[WalkForwardFoldResult] = []
    test_results: list[dict[str, Any]] = []

    for w in windows:
        # 构造回测参数
        params = {
            "code": body.code.strip(),
            "limit": body.limit,
            "start_date": w.test_start,
            "end_date": w.test_end,
            "commission_rate": body.commission_rate,
            "slippage_rate": body.slippage_rate,
            "adjust_flag": body.adjust_flag,
            "benchmark_code": None,
        }
        if body.strategy_id == STRATEGY_ID_MA_CROSS:
            params["fast"] = body.fast
            params["slow"] = body.slow

        try:
            if body.strategy_id == STRATEGY_ID_BUY_HOLD:
                payload, _ = await execute_buy_hold_single(session, **params)
            elif body.strategy_id == STRATEGY_ID_MA_CROSS:
                payload, _ = await execute_ma_cross_single(session, **params)
            else:
                raise HTTPException(status_code=400, detail=f"不支持的 strategy_id: {body.strategy_id}")

            # payload 为回测结果 dict，字段名含 _pct 后缀
            total_return = payload.get("total_return_pct")
            sharpe = payload.get("sharpe_ratio")
            max_dd = payload.get("max_drawdown_pct")

            folds.append(WalkForwardFoldResult(
                fold=w.fold,
                train_start=w.train_start.isoformat(),
                train_end=w.train_end.isoformat(),
                test_start=w.test_start.isoformat(),
                test_end=w.test_end.isoformat(),
                test_total_return=total_return,
                test_sharpe=sharpe,
                test_max_drawdown=max_dd,
            ))

            test_results.append({
                "total_return": total_return or 0,
                "sharpe_ratio": sharpe,
                "max_drawdown": max_dd,
            })
        except Exception as e:
            import logging
            logging.getLogger("walk_forward").warning("Fold %d failed: %s", w.fold, e)
            folds.append(WalkForwardFoldResult(
                fold=w.fold,
                train_start=w.train_start.isoformat(),
                train_end=w.train_end.isoformat(),
                test_start=w.test_start.isoformat(),
                test_end=w.test_end.isoformat(),
            ))
            test_results.append({"total_return": 0})

    aggregated = aggregate_results(test_results)

    return WalkForwardResponse(
        code=body.code,
        strategy_id=body.strategy_id,
        folds=folds,
        aggregated=aggregated,
    )


@router.get("/trend-following", response_model=MaCrossBacktestResponse)
async def trend_following_backtest_endpoint(
    code: str = Query(..., description="标的代码，如 sh.000001"),
    ma_period: int = Query(50, ge=10, le=200, description="移动平均线周期"),
    atr_period: int = Query(14, ge=5, le=50, description="ATR周期"),
    atr_multiplier: float = Query(1.5, ge=0.5, le=3.0, description="ATR乘数"),
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
    benchmark_code: str | None = Query(
        None,
        description=(
            "可选，如 sh.000300；β/α 为策略日收益对基准日收益的 OLS。"
            "不传则对标的自身日收益。"
        ),
    ),
    adjust_flag: Literal["1", "2", "3"] = Query("3", description="复权类型: 1=后复权 2=前复权 3=不复权"),
    session: AsyncSession = Depends(get_session),
):
    """趋势跟踪策略回测：基于移动平均线和ATR波动率。"""
    if commission_rate + slippage_rate > 0.08:
        raise HTTPException(
            status_code=400,
            detail="commission_rate 与 slippage_rate 之和勿超过 0.08",
        )
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date 不能晚于 end_date")

    repo = KlineRepository(session)
    klines = await repo.get_daily(
        code=code.strip(),
        limit=limit,
        start_date=start_date,
        end_date=end_date,
        adjust_flag=adjust_flag,
    )
    
    if len(klines) < ma_period + atr_period:
        raise HTTPException(
            status_code=400,
            detail=f"K 线不足，需要至少 {ma_period + atr_period} 根"
        )

    df = pd.DataFrame([
        {
            "trade_date": k.trade_date,
            "open": k.open,
            "high": k.high,
            "low": k.low,
            "close": k.close,
        }
        for k in klines
    ])
    
    try:
        result, equity, _ = trend_following_backtest(
            df,
            code=code.strip(),
            ma_period=ma_period,
            atr_period=atr_period,
            atr_multiplier=atr_multiplier,
            commission_rate=commission_rate,
            slippage_rate=slippage_rate,
            benchmark_klines=None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    body = result.to_api_dict()
    body["equity_curve"] = [
        {"date": str(df["trade_date"].iloc[i]), "equity": float(equity.iloc[i])}
        for i in range(len(df))
    ]
    
    return MaCrossBacktestResponse(**body)


@router.get("/mean-reversion", response_model=MaCrossBacktestResponse)
async def mean_reversion_backtest_endpoint(
    code: str = Query(..., description="标的代码，如 sh.000001"),
    bb_period: int = Query(20, ge=10, le=100, description="布林带周期"),
    bb_std: float = Query(2.0, ge=0.5, le=3.0, description="标准差倍数"),
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
    benchmark_code: str | None = Query(
        None,
        description=(
            "可选，如 sh.000300；β/α 为策略日收益对基准日收益的 OLS。"
            "不传则对标的自身日收益。"
        ),
    ),
    adjust_flag: Literal["1", "2", "3"] = Query("3", description="复权类型: 1=后复权 2=前复权 3=不复权"),
    session: AsyncSession = Depends(get_session),
):
    """均值回归策略回测：基于布林带指标。"""
    if commission_rate + slippage_rate > 0.08:
        raise HTTPException(
            status_code=400,
            detail="commission_rate 与 slippage_rate 之和勿超过 0.08",
        )
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date 不能晚于 end_date")

    repo = KlineRepository(session)
    klines = await repo.get_daily(
        code=code.strip(),
        limit=limit,
        start_date=start_date,
        end_date=end_date,
        adjust_flag=adjust_flag,
    )
    
    if len(klines) < bb_period:
        raise HTTPException(
            status_code=400,
            detail=f"K 线不足，需要至少 {bb_period} 根"
        )

    df = pd.DataFrame([
        {
            "trade_date": k.trade_date,
            "close": k.close,
        }
        for k in klines
    ])
    
    try:
        result, equity, _ = mean_reversion_backtest(
            df,
            code=code.strip(),
            bb_period=bb_period,
            bb_std=bb_std,
            commission_rate=commission_rate,
            slippage_rate=slippage_rate,
            benchmark_klines=None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    body = result.to_api_dict()
    body["equity_curve"] = [
        {"date": str(df["trade_date"].iloc[i]), "equity": float(equity.iloc[i])}
        for i in range(len(df))
    ]
    
    return MaCrossBacktestResponse(**body)
