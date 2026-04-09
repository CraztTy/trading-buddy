"""
Trading Buddy - 看板数据API
"""

from datetime import date, datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.data.storage import get_session, KlineRepository, StockRepository


router = APIRouter()


@router.get("/overview")
async def get_market_overview(
    session: AsyncSession = Depends(get_session),
) -> dict:
    """获取市场概览（从数据库获取）"""
    # 模拟指数数据
    indices_codes = [
        "sh.000001",  # 上证指数
        "sh.399001",  # 深证成指
        "sh.399006",  # 创业板指
        "sh.000300",  # 沪深300
    ]
    
    repo = KlineRepository(session)
    result = []
    
    for code in indices_codes:
        klines = await repo.get_daily(code=code, limit=2)
        if len(klines) >= 2:
            latest = klines[-1]
            prev = klines[-2]
            change = round(latest.close - prev.close, 2)
            pct_change = round(change / prev.close * 100, 2) if prev.close else 0
            
            result.append({
                "code": code,
                "name": {"sh.000001": "上证指数", "sh.399001": "深证成指", 
                        "sh.399006": "创业板指", "sh.000300": "沪深300"}.get(code, code),
                "price": latest.close,
                "change": change,
                "pct_change": pct_change,
                "high": latest.high,
                "low": latest.low,
                "volume": latest.volume,
                "date": str(latest.trade_date),
            })
    
    return {"indices": result}


@router.get("/gainers")
async def get_top_gainers(
    trade_date: date | None = Query(None, description="交易日期，默认今天"),
    limit: int = Query(10, le=50, description="返回数量"),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """获取涨幅榜"""
    if trade_date is None:
        trade_date = date.today()
    
    repo = KlineRepository(session)
    klines = await repo.get_top_gainers(trade_date, limit)
    
    stock_repo = StockRepository(session)
    result = []
    for k in klines:
        stock = await stock_repo.get_by_code(k.code)
        result.append({
            "code": k.code,
            "name": stock.name if stock else k.code,
            "price": k.close,
            "change": k.change,
            "pct_change": k.pct_change,
        })
    
    return result


@router.get("/losers")
async def get_top_losers(
    trade_date: date | None = Query(None, description="交易日期，默认今天"),
    limit: int = Query(10, le=50, description="返回数量"),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """获取跌幅榜"""
    if trade_date is None:
        trade_date = date.today()
    
    repo = KlineRepository(session)
    klines = await repo.get_top_losers(trade_date, limit)
    
    stock_repo = StockRepository(session)
    result = []
    for k in klines:
        stock = await stock_repo.get_by_code(k.code)
        result.append({
            "code": k.code,
            "name": stock.name if stock else k.code,
            "price": k.close,
            "change": k.change,
            "pct_change": k.pct_change,
        })
    
    return result


@router.get("/turnover")
async def get_high_turnover(
    limit: int = Query(10, le=50),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """获取成交额排行榜（简化版）"""
    stock_repo = StockRepository(session)
    stock_codes = await stock_repo.get_all_codes(is_trading=True)
    
    repo = KlineRepository(session)
    results = []
    
    for code in stock_codes[:limit]:
        klines = await repo.get_daily(code=code, limit=1)
        if klines:
            k = klines[-1]
            stock = await stock_repo.get_by_code(code)
            results.append({
                "code": code,
                "name": stock.name if stock else code,
                "price": k.close,
                "volume": k.volume,
                "amount": k.amount,
            })
    
    # 按成交额排序
    results.sort(key=lambda x: x["amount"], reverse=True)
    return {"stocks": results[:limit]}
