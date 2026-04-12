"""
最小回测 API：双均线（日线）。
"""

import asyncio
import uuid
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse, Response

from src.backtest.runner import (
    ENGINE_VERSION,
    STRATEGY_ID_MA_CROSS,
    STRATEGY_ID_MA_CROSS_SCAN,
    build_ma_cross_scan_assumptions,
    execute_ma_cross_scan,
    execute_ma_cross_single,
)
from src.strategies import compute_ma_cross_signal
from src.backtest.scan import ma_cross_scan_csv_bytes, parse_scan_codes
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
from src.data.storage import get_database, get_session
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


class BacktestRunMvpRequest(BaseModel):
    """通用回测 MVP：同步执行；注册 ma_cross / ma_cross_scan v1。"""

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
    result: MaCrossBacktestResponse | None = Field(
        None,
        description="strategy_id=ma_cross 时非空，与 GET /api/backtest/ma-cross 一致",
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
    supported = (STRATEGY_ID_MA_CROSS, STRATEGY_ID_MA_CROSS_SCAN)
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
            raise HTTPException(status_code=422, detail=e.errors()) from e
        return
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
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return MaCrossBacktestResponse(**body)


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
    通用回测 MVP：与 GET /api/backtest/ma-cross* 共用内核，额外返回 assumptions / engine_version。
    支持 strategy_id=`ma_cross`（单标的）或 `ma_cross_scan`（批量），strategy_version=`1`。

    默认同步 200；**``?async=1``** 时返回 **202** 及 ``job_id``，由 **GET /api/backtest/jobs/{job_id}** 轮询
    ``pending`` / ``running`` / ``completed`` / ``failed`` / ``cancelled``（取消）。
    若 ``REDIS_ENABLED`` 且 ``BACKTEST_ASYNC_JOB_STORE`` 为 ``auto``（默认），任务入 **Redis 队列** 并持久化记录；
    否则为进程内表（重启清空）。``BACKTEST_ASYNC_JOB_STORE=redis`` 且 Redis 不可用时返回 **503**。
    """
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
    kind: Literal["ma_cross_single", "ma_cross_scan"]
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


@router.post("/runs", status_code=201)
async def backtest_run_create(
    body: BacktestRunCreate,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """保存一次单标的回测或批量扫描的完整请求/响应 JSON（供日后查阅）。"""
    if not isinstance(body.request_params, dict) or not isinstance(body.response_payload, dict):
        raise HTTPException(status_code=400, detail="request_params 与 response_payload 须为 JSON 对象")
    try:
        assert_run_payload_size(body.request_params, body.response_payload)
    except ValueError as e:
        raise HTTPException(status_code=413, detail=str(e)) from e
    summary = build_summary(body.kind, body.response_payload)
    repo = BacktestRunRepository(session)
    row = await repo.create(
        kind=body.kind,
        summary=summary,
        request_params=body.request_params,
        response_payload=body.response_payload,
    )
    return {"id": row.id, "summary": row.summary}


@router.get("/runs", response_model=BacktestRunsListResponse)
async def backtest_runs_list(
    session: AsyncSession = Depends(get_session),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    kind: Literal["ma_cross_single", "ma_cross_scan"] | None = Query(
        None, description="仅列出该类型的存档；不传则全部"
    ),
    q: str | None = Query(None, max_length=120, description="摘要子串过滤（LIKE %q%）"),
) -> BacktestRunsListResponse:
    q_norm = (q.strip() if q else "") or None
    repo = BacktestRunRepository(session)
    total = await repo.count_all(kind=kind, q=q_norm)
    rows = await repo.list_recent(limit=limit, offset=offset, kind=kind, q=q_norm)
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
) -> Response:
    """删除一条存档（不可恢复）。"""
    repo = BacktestRunRepository(session)
    if not await repo.delete_by_id(run_id):
        raise HTTPException(status_code=404, detail="记录不存在")
    return Response(status_code=204)


@router.get("/runs/{run_id}", response_model=BacktestRunDetailResponse)
async def backtest_run_detail(
    run_id: int,
    session: AsyncSession = Depends(get_session),
) -> BacktestRunDetailResponse:
    repo = BacktestRunRepository(session)
    row = await repo.get(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return BacktestRunDetailResponse(
        id=row.id,
        kind=row.kind,
        summary=row.summary,
        created_at=row.created_at.isoformat() if row.created_at else "",
        request_params=dict(row.request_params or {}),
        response_payload=dict(row.response_payload or {}),
    )
