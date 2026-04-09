"""
Trading Buddy - 股票相关API
"""

from typing import Annotated
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.data.storage import get_session, StockRepository
from src.data.models import StockInfo


router = APIRouter()


@router.get("/list")
async def get_stock_list(
    market: str | None = Query(None, description="市场: sh/sz/bj"),
    industry: str | None = Query(None, description="行业"),
    stock_type: str | None = Query(None, description="类型: common/star/growth/st"),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """获取股票列表"""
    repo = StockRepository(session)
    codes = await repo.get_all_codes(market=market)
    
    # 返回基本信息（简化版，实际可扩展）
    return [{"code": code, "status": "ok"} for code in codes[:100]]


@router.get("/{code}")
async def get_stock(
    code: str,
    session: AsyncSession = Depends(get_session),
) -> StockInfo | dict:
    """获取股票详情"""
    repo = StockRepository(session)
    stock = await repo.get_by_code(code)
    
    if stock is None:
        return {"error": "Stock not found", "code": code}
    
    return stock


@router.get("/industry/{industry}")
async def get_stocks_by_industry(
    industry: str,
    session: AsyncSession = Depends(get_session),
) -> list[StockInfo]:
    """根据行业获取股票"""
    repo = StockRepository(session)
    return await repo.get_by_industry(industry)
