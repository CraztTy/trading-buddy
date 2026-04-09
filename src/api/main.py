"""
Trading Buddy - FastAPI 主入口
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.common import setup_logger, get_settings
from src.data.storage import get_database
from .routers import stocks, klines, realtime, dashboard


# 初始化日志
setup_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    settings = get_settings()
    print(f"Starting Trading Buddy API on {settings.api.host}:{settings.api.port}")
    
    yield
    
    # 关闭时
    db = get_database()
    await db.close()
    print("Trading Buddy API shutdown complete")


# 创建应用
app = FastAPI(
    title="Trading Buddy API",
    description="A股量化交易数据基础设施",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(stocks.router, prefix="/api/stocks", tags=["股票"])
app.include_router(klines.router, prefix="/api/klines", tags=["K线"])
app.include_router(realtime.router, prefix="/api/realtime", tags=["实时行情"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["看板"])


@app.get("/")
async def root():
    """根路径"""
    return {
        "name": "Trading Buddy API",
        "version": "1.0.0",
        "status": "running",
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy"}
