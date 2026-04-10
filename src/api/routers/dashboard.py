"""
Trading Buddy - 看板数据API
"""

from datetime import date, datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.data.storage import (
    KlineRepository,
    StockRepository,
    get_session,
    resolve_stock_names,
)


router = APIRouter()


def _change_from_pct(close: float, pct: float | None) -> float | None:
    """由收盘价与涨跌幅反推涨跌额（日线仓储未存涨跌额时）"""
    if pct is None:
        return None
    denom = 1 + pct / 100
    if abs(denom) < 1e-9:
        return None
    prev_close = close / denom
    return round(close - prev_close, 2)


@router.get("/overview")
async def get_market_overview(
    session: AsyncSession = Depends(get_session),
) -> dict:
    """获取市场概览（从数据库获取）"""
    # 模拟指数数据
    # 深证指数必须用 sz. 前缀（sh.399xxx 会错配或空数据）
    indices_codes = [
        "sh.000001",  # 上证指数
        "sz.399001",  # 深证成指
        "sz.399006",  # 创业板指
        "sh.000300",  # 沪深300
    ]
    index_names = {
        "sh.000001": "上证指数",
        "sz.399001": "深证成指",
        "sz.399006": "创业板指",
        "sh.000300": "沪深300",
    }
    
    repo = KlineRepository(session)
    result = []
    
    for code in indices_codes:
        klines = await repo.get_daily(code=code, limit=2)
        if len(klines) >= 2:
            latest = klines[-1]
            prev = klines[-2]
            change = round(latest.close - prev.close, 2)
            pct_change = round(change / prev.close * 100, 2) if prev.close else 0
        elif len(klines) == 1:
            latest = klines[-1]
            change = 0.0
            pct_change = 0.0
        else:
            continue

        result.append({
            "code": code,
            "name": index_names.get(code, code),
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
    request: Request,
    trade_date: date | None = Query(None, description="交易日期；省略则用库中最新交易日"),
    limit: int = Query(10, le=50, description="返回数量"),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """获取涨幅榜"""
    repo = KlineRepository(session)
    klines = await repo.get_top_gainers(trade_date, limit)

    stock_repo = StockRepository(session)
    redis = getattr(request.app.state, "redis", None)
    name_map = await resolve_stock_names(
        stock_repo, [k.code for k in klines], redis_client=redis
    )
    result = []
    for k in klines:
        chg = _change_from_pct(k.close, k.pct_change)
        result.append({
            "code": k.code,
            "name": name_map.get(k.code, k.code),
            "price": k.close,
            "change": chg,
            "pct_change": k.pct_change,
        })

    return result


@router.get("/losers")
async def get_top_losers(
    request: Request,
    trade_date: date | None = Query(None, description="交易日期；省略则用库中最新交易日"),
    limit: int = Query(10, le=50, description="返回数量"),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """获取跌幅榜"""
    repo = KlineRepository(session)
    klines = await repo.get_top_losers(trade_date, limit)

    stock_repo = StockRepository(session)
    redis = getattr(request.app.state, "redis", None)
    name_map = await resolve_stock_names(
        stock_repo, [k.code for k in klines], redis_client=redis
    )
    result = []
    for k in klines:
        chg = _change_from_pct(k.close, k.pct_change)
        result.append({
            "code": k.code,
            "name": name_map.get(k.code, k.code),
            "price": k.close,
            "change": chg,
            "pct_change": k.pct_change,
        })

    return result


@router.get("/turnover")
async def get_high_turnover(
    request: Request,
    limit: int = Query(10, le=50),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """获取成交额排行榜（简化版）"""
    stock_repo = StockRepository(session)
    stock_codes = await stock_repo.get_all_codes(is_trading=True)
    slice_codes = stock_codes[:limit]
    redis = getattr(request.app.state, "redis", None)
    name_map = await resolve_stock_names(stock_repo, slice_codes, redis_client=redis)

    repo = KlineRepository(session)
    results = []

    for code in slice_codes:
        klines = await repo.get_daily(code=code, limit=1)
        if klines:
            k = klines[-1]
            results.append({
                "code": code,
                "name": name_map.get(code, code),
                "price": k.close,
                "volume": k.volume,
                "amount": k.amount,
            })
    
    # 按成交额排序
    results.sort(key=lambda x: x["amount"], reverse=True)
    return {"stocks": results[:limit]}
