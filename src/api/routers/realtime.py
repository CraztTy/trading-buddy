"""
Trading Buddy - 实时行情API
"""

from typing import Annotated
from fastapi import APIRouter, Query

from src.data.sources import DataSourceFactory
from src.data.models import RealtimeQuote


router = APIRouter()


@router.get("/quote")
async def get_realtime_quote(
    codes: Annotated[str, Query(description="股票代码，多个用逗号分隔")],
) -> list[RealtimeQuote]:
    """获取实时行情"""
    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    
    if not code_list:
        return []
    
    # 标准化代码格式
    code_list = [
        f"sh.{c}" if not c.startswith(("sh.", "sz.", "bj.")) else c
        for c in code_list
    ]
    
    # 使用 baostock 获取实时数据
    source = DataSourceFactory.create("baostock")
    try:
        await source.connect()
        quotes = await source.get_realtime_quote(code_list)
        return quotes
    finally:
        await source.disconnect()


@router.get("/batch")
async def get_batch_quotes(
    market: str = Query("all", description="市场: sh/sz/bj/all"),
    limit: int = Query(50, le=200, description="返回数量"),
) -> dict:
    """批量获取市场行情摘要"""
    # 获取主要指数
    indices = [
        "sh.000001",  # 上证指数
        "sh.399001",  # 深证成指
        "sh.399006",  # 创业板指
        "sh.000300",  # 沪深300
    ]
    
    source = DataSourceFactory.create("baostock")
    try:
        await source.connect()
        quotes = await source.get_realtime_quote(indices)
        
        return {
            "indices": quotes,
            "timestamp": quotes[0].update_time if quotes else None,
        }
    finally:
        await source.disconnect()
