#!/usr/bin/env python3
"""
Trading Buddy - 定时任务调度器
每天收盘后自动拉取最新数据
"""

import sys
import asyncio
from pathlib import Path
from datetime import date, timedelta

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.common import setup_logger
from src.data.storage import get_database, StockRepository, KlineRepository
from src.data.sources import DataSourceFactory


logger = setup_logger()


async def update_daily_data():
    """每日收盘后更新数据"""
    logger.info("Starting daily data update...")
    
    db = get_database()
    source = DataSourceFactory.create("baostock")
    
    today = date.today()
    start_date = today - timedelta(days=5)  # 获取最近5天数据（包含可能的补数据）
    
    try:
        await source.connect()
        
        async with db.session() as session:
            stock_repo = StockRepository(session)
            kline_repo = KlineRepository(session)
            
            # 获取所有股票代码
            codes = await stock_repo.get_all_codes(is_trading=True)
            logger.info(f"Updating {len(codes)} stocks...")
            
            updated = 0
            for code in codes:
                try:
                    klines = await source.get_daily_kline(code, start_date, today)
                    if klines:
                        await kline_repo.bulk_insert(klines)
                        updated += 1
                except Exception as e:
                    logger.warning(f"Failed to update {code}: {e}")
            
            logger.info(f"Daily update completed: {updated}/{len(codes)} stocks updated")
        
    finally:
        await source.disconnect()
        await db.close()


async def update_realtime():
    """盘中间隔更新实时数据到Redis"""
    logger.info("Updating realtime data...")
    
    # 预留接口，后续实现
    # 1. 从 baostock 获取实时行情
    # 2. 存入 Redis 缓存
    # 3. 标记数据更新时间
    pass


async def scheduler_loop():
    """调度循环"""
    import schedule
    import time
    
    # 每天 16:00 执行日线更新（A股收盘后）
    schedule.every().day.at("16:00").do(lambda: asyncio.run(update_daily_data()))
    
    # 每 5 分钟更新实时数据（交易时间内）
    # schedule.every(5).minutes.do(lambda: asyncio.run(update_realtime()))
    
    logger.info("Scheduler started. Waiting for scheduled tasks...")
    
    while True:
        schedule.run_pending()
        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(scheduler_loop())
