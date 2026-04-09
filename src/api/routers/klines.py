"""
Trading Buddy - K线数据API
"""

from datetime import date
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.data.storage import get_session, KlineRepository
from src.data.models import KLine


router = APIRouter()


@router.get("/{code}")
async def get_kline(
    code: str,
    start_date: date | None = Query(None, description="开始日期"),
    end_date: date | None = Query(None, description="结束日期"),
    period: str = Query("daily", description="周期: daily/weekly/monthly"),
    limit: int = Query(100, le=500, description="返回数量"),
    session: AsyncSession = Depends(get_session),
) -> list[KLine]:
    """获取K线数据"""
    repo = KlineRepository(session)
    return await repo.get_daily(
        code=code,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )


@router.get("/latest/{code}")
async def get_latest_kline(
    code: str,
    session: AsyncSession = Depends(get_session),
) -> KLine | dict:
    """获取最新一根K线"""
    repo = KlineRepository(session)
    klines = await repo.get_daily(code=code, limit=1)
    
    if not klines:
        return {"error": "No kline data", "code": code}
    
    return klines[-1]


@router.get("/analysis/{code}")
async def get_kline_analysis(
    code: str,
    limit: int = Query(60, le=250, description="用于计算均线的数据量"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """获取K线分析（包含技术指标）"""
    repo = KlineRepository(session)
    klines = await repo.get_daily(code=code, limit=limit)
    
    if not klines:
        return {"error": "No kline data", "code": code}
    
    # 计算简单技术指标
    closes = [k.close for k in klines]
    
    return {
        "code": code,
        "count": len(klines),
        "latest": klines[-1] if klines else None,
        "indicators": {
            "ma5": round(sum(closes[-5:]) / 5, 2) if len(closes) >= 5 else None,
            "ma10": round(sum(closes[-10:]) / 10, 2) if len(closes) >= 10 else None,
            "ma20": round(sum(closes[-20:]) / 20, 2) if len(closes) >= 20 else None,
            "ma60": round(sum(closes[-60:]) / 60, 2) if len(closes) >= 60 else None,
        },
        "history": klines[-30:],  # 最近30根K线用于画图
    }
