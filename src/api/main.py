"""
Trading Buddy - FastAPI 主入口
"""

import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from src.common import __version__, cors_allow_origins, setup_logger, get_settings
from src.backtest.async_job_backend import (
    start_backtest_async_job_consumer,
    stop_backtest_async_job_consumer,
)
from src.common.kill_switch import is_killed
from src.common.redis_client import (
    close_redis_client,
    get_redis_client,
    init_redis_client,
)
from src.api.request_id_middleware import RequestIdMiddleware
from src.data.storage import dispose_database, get_database
from .routers import (
    auth,
    stocks,
    klines,
    realtime,
    dashboard,
    backtest,
    paper,
    watchlist,
    strategies,
    factors,
    trade_calendar,
    risk,
    kill_switch,
    audit,
    api_keys,
    metrics,
    experiments,
    stress,
    broker,
    websocket,
    ml,
)

# 进程启动时刻（lifespan 进入时设置，供浅层 /health 展示 uptime，无 DB 开销）
_PROCESS_STARTED_MONO: float | None = None


# 初始化日志
setup_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global _PROCESS_STARTED_MONO
    _PROCESS_STARTED_MONO = time.perf_counter()

    # 设置 metrics 进程启动时间
    from src.api.routers.metrics import set_process_start_time
    set_process_start_time(_PROCESS_STARTED_MONO)

    settings = get_settings()
    print(f"Starting Trading Buddy API on {settings.api.host}:{settings.api.port}")
    print(f"Database mode: {settings.database.mode}, Redis enabled: {settings.redis.enabled}")

    # JWT 默认密钥生产环境检测
    _DEFAULT_JWT_SECRET = "trading-buddy-dev-secret-change-in-production"
    if settings.auth.jwt_secret == _DEFAULT_JWT_SECRET:
        import logging

        logging.getLogger("uvicorn.error").error(
            "SECURITY WARNING: JWT_SECRET is using the default dev value. "
            "Set JWT_SECRET environment variable to a strong random secret before production deployment."
        )

    # 事件总线消费者（需 Redis）
    app.state.event_consumers = []
    if settings.redis.enabled:
        redis = await init_redis_client(
            settings.redis.host,
            settings.redis.port,
            settings.redis.db,
            settings.redis.password,
        )
        app.state.redis = redis
        print(f"Redis connected: {settings.redis.host}:{settings.redis.port}")
        await start_backtest_async_job_consumer(app)

        # 启动事件消费者
        from src.events.consumers import AuditLogConsumer, RiskMonitorConsumer

        consumers = [RiskMonitorConsumer(), AuditLogConsumer()]
        for consumer in consumers:
            await consumer.start()
        app.state.event_consumers = consumers
        print(f"Event consumers started: {len(consumers)}")

    yield

    # 关闭事件消费者
    for consumer in getattr(app.state, "event_consumers", []):
        await consumer.stop()

    await stop_backtest_async_job_consumer(app)
    await close_redis_client()
    await dispose_database()
    print("Trading Buddy API shutdown complete")


# 创建应用
app = FastAPI(
    title="Trading Buddy API",
    description="A股量化交易数据基础设施",
    version=__version__,
    lifespan=lifespan,
)

# CORS（CORS_ORIGINS=* 或 https://a.com,https://b.com）
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allow_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_api = get_settings().api
if _api.slow_request_warn_ms > 0:
    from src.api.slow_request_middleware import SlowRequestWarningMiddleware

    app.add_middleware(
        SlowRequestWarningMiddleware,
        threshold_ms=_api.slow_request_warn_ms,
        ignore_prefixes=_api.slow_request_ignore_prefixes,
    )

if _api.access_log:
    from src.api.access_log_middleware import AccessLogMiddleware

    app.add_middleware(
        AccessLogMiddleware, ignore_prefixes=_api.access_log_ignore_prefixes
    )

# 审计日志中间件（记录交易操作）
from src.api.audit_middleware import AuditLogMiddleware

app.add_middleware(AuditLogMiddleware)

# 最外层：为下游（含访问日志 / 慢请求 WARN）提供 request.state.request_id 与响应头 X-Request-ID
app.add_middleware(RequestIdMiddleware)

# 注册路由
app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
app.include_router(stocks.router, prefix="/api/stocks", tags=["股票"])
app.include_router(klines.router, prefix="/api/klines", tags=["K线"])
app.include_router(realtime.router, prefix="/api/realtime", tags=["实时行情"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["看板"])
app.include_router(backtest.router, prefix="/api/backtest", tags=["回测"])
app.include_router(paper.router, prefix="/api/paper", tags=["纸交易"])
app.include_router(watchlist.router, prefix="/api/watchlist", tags=["自选"])
app.include_router(strategies.router, prefix="/api/strategies", tags=["策略"])
app.include_router(factors.router, prefix="/api/factors", tags=["因子"])
app.include_router(trade_calendar.router, prefix="/api/data", tags=["数据"])
app.include_router(risk.router, prefix="/api/risk", tags=["风控"])
app.include_router(kill_switch.router, prefix="/api/kill-switch", tags=["紧急停止"])
app.include_router(audit.router, prefix="/api/audit", tags=["审计日志"])
app.include_router(api_keys.router, prefix="/api/api-keys", tags=["API密钥"])
app.include_router(metrics.router, prefix="", tags=["指标"])
app.include_router(experiments.router, prefix="/api/experiments", tags=["实验追踪"])
app.include_router(stress.router, prefix="/api/stress", tags=["压力测试"])
app.include_router(broker.router, prefix="/api/broker", tags=["交易接口"])
app.include_router(ml.router, prefix="/api/ml", tags=["ML / 因子挖掘"])
app.include_router(websocket.router, prefix="/ws", tags=["WebSocket"])


@app.get("/")
async def root():
    """根路径"""
    return {
        "name": "Trading Buddy API",
        "version": __version__,
        "status": "running",
    }


@app.get("/health")
async def health_check():
    """健康检查（仅反映配置，不探测连接；深度探活见 /health/ready）。"""
    settings = get_settings()
    uptime_sec = None
    if _PROCESS_STARTED_MONO is not None:
        uptime_sec = round(time.perf_counter() - _PROCESS_STARTED_MONO, 3)
    killed = await is_killed()
    body = {
        "status": "healthy",
        "app_version": __version__,
        "database_mode": settings.database.mode,
        "redis_enabled": settings.redis.enabled,
        "pid": os.getpid(),
        "uptime_sec": uptime_sec,
        "kill_switch": "killed" if killed else "normal",
    }
    # JWT 默认密钥警告
    _DEFAULT_JWT_SECRET = "trading-buddy-dev-secret-change-in-production"
    if settings.auth.jwt_secret == _DEFAULT_JWT_SECRET:
        body["warning"] = "JWT_SECRET uses default dev value — change before production"
    return body


@app.get("/health/ready")
async def health_ready(request: Request):
    """就绪探针：执行 DB `SELECT 1`；若启用 Redis 则 PING。失败返回 503。"""
    probe_t0 = time.perf_counter()
    settings = get_settings()
    db_state = "error"
    db_detail: str | None = None
    try:
        db = get_database()
        async with db.session() as session:
            await session.execute(text("SELECT 1"))
        db_state = "ok"
    except Exception as e:
        db_detail = str(e)[:300]

    redis_state = "skipped"
    redis_detail: str | None = None
    if settings.redis.enabled:
        client = getattr(request.app.state, "redis", None) or get_redis_client()
        if client is None:
            redis_state = "uninitialized"
            redis_detail = "lifespan 未创建 Redis 客户端"
        else:
            try:
                await client.ping()
                redis_state = "ok"
            except Exception as e:
                redis_state = "error"
                redis_detail = str(e)[:300]

    # 数据 freshness 检查
    data_freshness: dict = {}
    if db_state == "ok":
        try:
            from datetime import date, timedelta

            from sqlalchemy import func, select

            from src.data.storage.models import DailyKlineModel, StockInfoModel

            db = get_database()
            async with db.session() as session:
                # daily_kline 最新日期
                result = await session.execute(
                    select(func.max(DailyKlineModel.trade_date))
                )
                latest_kline = result.scalar_one()
                if latest_kline:
                    days_old = (date.today() - latest_kline).days
                    data_freshness["daily_kline_latest"] = latest_kline.isoformat()
                    data_freshness["daily_kline_days_old"] = days_old
                    # 超过 3 天视为 stale
                    if days_old > 3:
                        data_freshness["daily_kline_stale"] = True
                        data_freshness["daily_kline_warning"] = f"日 K 数据已 {days_old} 天未更新"
                else:
                    data_freshness["daily_kline_warning"] = "日 K 表无数据"

                # stock_info 记录数
                result = await session.execute(select(func.count()).select_from(StockInfoModel))
                stock_count = result.scalar_one()
                data_freshness["stock_info_count"] = stock_count
                if stock_count == 0:
                    data_freshness["stock_info_warning"] = "stock_info 表无数据"
        except Exception as e:
            data_freshness["error"] = str(e)[:200]

    ok = db_state == "ok" and (
        not settings.redis.enabled or redis_state == "ok"
    )
    probe_ms = round((time.perf_counter() - probe_t0) * 1000.0, 2)
    body: dict = {
        "status": "ready" if ok else "not_ready",
        "database": db_state,
        "redis": redis_state,
        "probe_ms": probe_ms,
        "data_freshness": data_freshness,
    }
    if db_detail:
        body["database_error"] = db_detail
    if redis_detail:
        body["redis_error"] = redis_detail

    if not ok:
        return JSONResponse(status_code=503, content=body)
    return body
