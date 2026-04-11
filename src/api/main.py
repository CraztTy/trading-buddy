"""
Trading Buddy - FastAPI 主入口
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from src.common import __version__, cors_allow_origins, setup_logger, get_settings
from src.common.redis_client import (
    close_redis_client,
    get_redis_client,
    init_redis_client,
)
from src.data.storage import dispose_database, get_database
from .routers import stocks, klines, realtime, dashboard, backtest


# 初始化日志
setup_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    settings = get_settings()
    print(f"Starting Trading Buddy API on {settings.api.host}:{settings.api.port}")
    print(f"Database mode: {settings.database.mode}, Redis enabled: {settings.redis.enabled}")

    if settings.redis.enabled:
        redis = await init_redis_client(
            settings.redis.host,
            settings.redis.port,
            settings.redis.db,
            settings.redis.password,
        )
        app.state.redis = redis
        print(f"Redis connected: {settings.redis.host}:{settings.redis.port}")

    yield

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

# 注册路由
app.include_router(stocks.router, prefix="/api/stocks", tags=["股票"])
app.include_router(klines.router, prefix="/api/klines", tags=["K线"])
app.include_router(realtime.router, prefix="/api/realtime", tags=["实时行情"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["看板"])
app.include_router(backtest.router, prefix="/api/backtest", tags=["回测"])


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
    return {
        "status": "healthy",
        "app_version": __version__,
        "database_mode": settings.database.mode,
        "redis_enabled": settings.redis.enabled,
    }


@app.get("/health/ready")
async def health_ready(request: Request):
    """就绪探针：执行 DB `SELECT 1`；若启用 Redis 则 PING。失败返回 503。"""
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

    ok = db_state == "ok" and (
        not settings.redis.enabled or redis_state == "ok"
    )
    body: dict = {
        "status": "ready" if ok else "not_ready",
        "database": db_state,
        "redis": redis_state,
    }
    if db_detail:
        body["database_error"] = db_detail
    if redis_detail:
        body["redis_error"] = redis_detail

    if not ok:
        return JSONResponse(status_code=503, content=body)
    return body
