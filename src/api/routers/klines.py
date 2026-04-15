"""
Trading Buddy - K线数据API
"""

from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.data.storage import (
    KlineRepository,
    StockRepository,
    get_session,
    resolve_stock_names,
)
from src.data.models import KLine


router = APIRouter()

# 与看板主要指数一致（不在 stock_info 里，需单独映射）
_MAJOR_INDEX_NAMES: dict[str, str] = {
    "sh.000001": "上证指数",
    "sz.399001": "深证成指",
    "sz.399006": "创业板指",
    "sh.000300": "沪深300",
}


async def _chart_display_name(
    request: Request,
    session: AsyncSession,
    code: str,
) -> str:
    c = (code or "").strip()
    if c in _MAJOR_INDEX_NAMES:
        return _MAJOR_INDEX_NAMES[c]
    stock_repo = StockRepository(session)
    redis = getattr(request.app.state, "redis", None)
    m = await resolve_stock_names(stock_repo, [c], redis_client=redis)
    return m.get(c, c)


# 具体路径须先于 /{code} 注册，避免部分环境下被单段路由抢占
@router.get("/analysis/{code}")
async def get_kline_analysis(
    request: Request,
    code: str,
    limit: int = Query(60, le=250, description="用于计算均线的数据量"),
    adjust_flag: str = Query("3", description="复权类型: 1=后复权 2=前复权 3=不复权"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """获取K线分析（包含技术指标与展示名称）"""
    repo = KlineRepository(session)
    klines = await repo.get_daily(code=code, limit=limit, adjust_flag=adjust_flag)
    name = await _chart_display_name(request, session, code)

    if not klines:
        return {"error": "No kline data", "code": code, "name": name}

    # 计算简单技术指标
    closes = [k.close for k in klines]

    return {
        "code": code,
        "name": name,
        "count": len(klines),
        "latest": klines[-1] if klines else None,
        "indicators": {
            "ma5": round(sum(closes[-5:]) / 5, 2) if len(closes) >= 5 else None,
            "ma10": round(sum(closes[-10:]) / 10, 2) if len(closes) >= 10 else None,
            "ma20": round(sum(closes[-20:]) / 20, 2) if len(closes) >= 20 else None,
            "ma60": round(sum(closes[-60:]) / 60, 2) if len(closes) >= 60 else None,
        },
        "history": klines,
    }


@router.get("/latest/{code}")
async def get_latest_kline(
    code: str,
    adjust_flag: str = Query("3", description="复权类型: 1=后复权 2=前复权 3=不复权"),
    session: AsyncSession = Depends(get_session),
) -> KLine | dict:
    """获取最新一根K线"""
    repo = KlineRepository(session)
    klines = await repo.get_daily(code=code, limit=1, adjust_flag=adjust_flag)

    if not klines:
        return {"error": "No kline data", "code": code}

    return klines[-1]


@router.get("/{code}")
async def get_kline(
    code: str,
    start_date: date | None = Query(None, description="开始日期"),
    end_date: date | None = Query(None, description="结束日期"),
    period: str = Query("daily", description="周期: daily/weekly/monthly"),
    limit: int = Query(100, le=500, description="返回数量"),
    adjust_flag: str = Query("3", description="复权类型: 1=后复权 2=前复权 3=不复权"),
    session: AsyncSession = Depends(get_session),
) -> list[KLine]:
    """获取K线数据"""
    repo = KlineRepository(session)
    return await repo.get_daily(
        code=code,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        adjust_flag=adjust_flag,
    )
