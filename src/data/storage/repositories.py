"""
Trading Buddy - 数据仓库
封装数据库操作，提供简洁的增删改查接口
"""

from datetime import date, datetime
from typing import Sequence

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.common import get_logger
from ..models import StockInfo, KLine, Market, StockType
from .models import StockInfoModel, DailyKlineModel, SectorInfoModel


logger = get_logger("repository")


class StockRepository:
    """股票数据仓库"""
    
    def __init__(self, session: AsyncSession):
        self._session = session
    
    async def bulk_upsert(self, stocks: list[StockInfo]) -> int:
        """批量插入或更新股票"""
        count = 0
        for stock in stocks:
            model = StockInfoModel(
                code=stock.code,
                name=stock.name,
                industry=stock.industry,
                sector=stock.sector_code,
                list_date=stock.ipo_date,
                stock_type=1,  # 1=普通股票
                status=1,      # 1=正常
            )
            self._session.add(model)
            count += 1

        await self._session.flush()
        # 注意：不调用 commit()，由 db.session() 上下文管理器负责 commit
        logger.info(f"Bulk upserted {count} stocks")
        return count
    
    async def get_by_code(self, code: str) -> StockInfo | None:
        """根据代码查询股票"""
        stmt = select(StockInfoModel).where(StockInfoModel.code == code)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        
        if model:
            return StockInfo(
                code=model.code,
                name=model.name,
                ipo_date=model.ipo_date,
                out_date=model.out_date,
                stock_type=StockType(model.stock_type),
                market=Market(model.market),
                industry=model.industry,
                sector_code=model.sector_code,
            )
        return None
    
    async def get_all_codes(self, market: str | None = None, is_trading: bool = True) -> list[str]:
        """获取所有股票代码"""
        stmt = select(StockInfoModel.code)
        if market:
            stmt = stmt.where(StockInfoModel.market == market)
        if is_trading is not None:
            stmt = stmt.where(StockInfoModel.is_trading == is_trading)
        
        result = await self._session.execute(stmt)
        return [row[0] for row in result.all()]
    
    async def get_by_industry(self, industry: str) -> list[StockInfo]:
        """根据行业查询股票"""
        stmt = select(StockInfoModel).where(StockInfoModel.industry == industry)
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        
        return [
            StockInfo(
                code=m.code,
                name=m.name,
                ipo_date=m.ipo_date,
                out_date=m.out_date,
                stock_type=StockType(m.stock_type),
                market=Market(m.market),
                industry=m.industry,
                sector_code=m.sector_code,
            )
            for m in models
        ]


class KlineRepository:
    """K线数据仓库"""
    
    def __init__(self, session: AsyncSession):
        self._session = session
    
    async def bulk_insert(self, klines: list[KLine]) -> int:
        """批量插入K线数据"""
        count = 0
        for kline in klines:
            model = DailyKlineModel(
                code=kline.code,
                trade_date=kline.trade_date,
                open=kline.open,
                high=kline.high,
                low=kline.low,
                close=kline.close,
                volume=kline.volume,
                amount=kline.amount,
                turnover_rate=kline.turnover_rate,
                change_pct=kline.pct_change,
            )
            self._session.add(model)
            count += 1

        await self._session.flush()
        # 注意：不调用 commit()，由 db.session() 上下文管理器负责 commit
        logger.info(f"Bulk inserted {count} klines")
        return count
    
    async def get_daily(
        self,
        code: str,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 100,
    ) -> list[KLine]:
        """查询日K线数据"""
        stmt = select(DailyKlineModel).where(DailyKlineModel.code == code)
        
        if start_date:
            stmt = stmt.where(DailyKlineModel.trade_date >= start_date)
        if end_date:
            stmt = stmt.where(DailyKlineModel.trade_date <= end_date)
        
        stmt = stmt.order_by(DailyKlineModel.trade_date.desc()).limit(limit)
        
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        
        return [
            KLine(
                code=m.code,
                trade_date=m.trade_date,
                open=float(m.open),
                high=float(m.high),
                low=float(m.low),
                close=float(m.close),
                volume=m.volume or 0,
                amount=float(m.amount) if m.amount else 0.0,
                turnover_rate=float(m.turnover_rate) if m.turnover_rate else None,
                pct_change=float(m.change_pct) if m.change_pct else None,
            )
            for m in reversed(models)  # 正序返回
        ]
    
    async def get_latest_date(self, code: str) -> date | None:
        """获取最新K线日期"""
        stmt = select(func.max(DailyKlineModel.trade_date)).where(
            DailyKlineModel.code == code
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_top_gainers(self, trade_date: date, limit: int = 10) -> list[KLine]:
        """获取涨幅最大的股票"""
        stmt = (
            select(DailyKlineModel)
            .where(DailyKlineModel.trade_date == trade_date)
            .order_by(DailyKlineModel.change_pct.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        
        return [
            KLine(
                code=m.code,
                trade_date=m.trade_date,
                open=float(m.open),
                high=float(m.high),
                low=float(m.low),
                close=float(m.close),
                volume=m.volume or 0,
                amount=float(m.amount) if m.amount else 0.0,
                pct_change=float(m.change_pct) if m.change_pct else None,
            )
            for m in models
        ]

    async def get_top_losers(self, trade_date: date, limit: int = 10) -> list[KLine]:
        """获取跌幅最大的股票"""
        stmt = (
            select(DailyKlineModel)
            .where(DailyKlineModel.trade_date == trade_date)
            .order_by(DailyKlineModel.change_pct.asc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()

        return [
            KLine(
                code=m.code,
                trade_date=m.trade_date,
                open=float(m.open),
                high=float(m.high),
                low=float(m.low),
                close=float(m.close),
                volume=m.volume or 0,
                amount=float(m.amount) if m.amount else 0.0,
                pct_change=float(m.change_pct) if m.change_pct else None,
            )
            for m in models
        ]
