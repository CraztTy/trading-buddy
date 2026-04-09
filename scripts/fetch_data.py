#!/usr/bin/env python3
"""
Trading Buddy - 数据拉取脚本
使用 mock 数据源拉取模拟数据
"""

import sys
import asyncio
from pathlib import Path
from datetime import date, timedelta

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(project_root))

from src.common import get_logger
from src.data.storage import get_database, StockRepository, KlineRepository
from src.data.sources import DataSourceFactory


logger = get_logger("fetcher")


async def fetch_stock_list():
    """拉取股票列表"""
    logger.info("Fetching mock stock list...")
    
    source = DataSourceFactory.create("mock")
    db = get_database()
    
    try:
        await source.connect()
        stocks = await source.get_stock_list()
        
        logger.info(f"Got {len(stocks)} stocks from mock source")
        
        async with db.session() as session:
            repo = StockRepository(session)
            count = await repo.bulk_upsert(stocks)
            logger.info(f"Successfully saved {count} stocks")
        
    finally:
        await source.disconnect()
        await db.close()


async def fetch_daily_klines(codes: list[str] | None = None, days: int = 30):
    """拉取日K线数据"""
    logger.info(f"Fetching mock daily klines for {len(codes) if codes else 'all'} stocks...")
    
    source = DataSourceFactory.create("mock")
    db = get_database()
    
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    
    try:
        await source.connect()
        
        async with db.session() as session:
            repo = StockRepository(session)
            kline_repo = KlineRepository(session)
            
            if not codes:
                codes = await repo.get_all_codes(is_trading=True)
            
            if not codes:
                logger.warning("No stock codes found. Please fetch stock list first.")
                return
            
            logger.info(f"Fetching klines for {len(codes)} stocks from {start_date} to {end_date}")
            
            total = 0
            for i, code in enumerate(codes):
                try:
                    klines = await source.get_daily_kline(code, start_date, end_date)
                    if klines:
                        await kline_repo.bulk_insert(klines)
                        total += len(klines)
                        logger.info(f"[{i+1}/{len(codes)}] {code}: {len(klines)} klines")
                except Exception as e:
                    logger.warning(f"Failed to fetch klines for {code}: {e}")
            
            logger.info(f"Successfully fetched {total} klines")
        
    finally:
        await source.disconnect()
        await db.close()


async def fetch_index_data():
    """拉取主要指数数据"""
    logger.info("Fetching mock index data...")
    
    source = DataSourceFactory.create("mock")
    db = get_database()
    
    indices = [
        ("sh.000001", "上证指数"),
        ("sh.399001", "深证成指"),
        ("sh.399006", "创业板指"),
        ("sh.000300", "沪深300"),
    ]
    
    end_date = date.today()
    start_date = end_date - timedelta(days=60)
    
    try:
        await source.connect()
        
        async with db.session() as session:
            repo = KlineRepository(session)
            
            for code, name in indices:
                try:
                    klines = await source.get_index_data(code, start_date, end_date)
                    if klines:
                        await repo.bulk_insert(klines)
                        logger.info(f"Fetched {len(klines)} klines for {name}")
                except Exception as e:
                    logger.warning(f"Failed to fetch {name}: {e}")
        
        logger.info("Index data fetch completed")
        
    finally:
        await source.disconnect()
        await db.close()


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Trading Buddy Data Fetcher (Mock)")
    parser.add_argument("--mode", choices=["all", "stocks", "klines", "indices"],
                        default="all", help="Fetch mode")
    parser.add_argument("--codes", nargs="+", help="Specific stock codes")
    parser.add_argument("--days", type=int, default=30, help="Days of kline data")
    
    args = parser.parse_args()
    
    if args.mode == "all" or args.mode == "stocks":
        await fetch_stock_list()
    
    if args.mode == "all" or args.mode == "klines":
        await fetch_daily_klines(args.codes, args.days)
    
    if args.mode == "all" or args.mode == "indices":
        await fetch_index_data()
    
    logger.info("Data fetch completed!")


if __name__ == "__main__":
    asyncio.run(main())
