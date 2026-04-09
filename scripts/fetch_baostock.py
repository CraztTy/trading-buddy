#!/usr/bin/env python3
"""
Trading Buddy - baostock 数据拉取脚本
拉取 A 股所有股票数据到 MySQL
"""

import sys
import asyncio
import time
from pathlib import Path
from datetime import date, timedelta, datetime
import baostock as bs

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(project_root))

from src.common import get_logger
from src.data.storage import get_database, StockRepository, KlineRepository
from src.data.sources import DataSourceFactory
from src.data.models import StockInfo


logger = get_logger("baostock_fetcher")


class ProgressTracker:
    """进度追踪器"""
    def __init__(self, total: int):
        self.total = total
        self.current = 0
        self.success = 0
        self.failed = 0
        self.start_time = time.time()
    
    def update(self, success: bool = True):
        self.current += 1
        if success:
            self.success += 1
        else:
            self.failed += 1
    
    def show(self):
        elapsed = time.time() - self.start_time
        rate = self.current / elapsed if elapsed > 0 else 0
        remaining = (self.total - self.current) / rate if rate > 0 else 0
        
        bar_length = 30
        filled = int(bar_length * self.current / self.total) if self.total > 0 else 0
        bar = '=' * filled + '-' * (bar_length - filled)
        
        print(f"\r[{bar}] {self.current}/{self.total} ({self.current*100//self.total}%) | "
              f"成功: {self.success} | 失败: {self.failed} | "
              f"速度: {rate:.1f}/s | 剩余: {remaining/60:.1f}min", end='', flush=True)


async def get_last_trading_day() -> str:
    """获取上一个交易日"""
    import baostock as bs
    bs.login()
    
    today = date.today()
    # 尝试最近5天
    for i in range(1, 6):
        check_date = (today - timedelta(days=i)).strftime('%Y-%m-%d')
        rs = bs.query_trade_dates(start_date=check_date, end_date=check_date)
        while rs.next():
            row = rs.get_row_data()
            if row[1] == '1':  # is_trading_day
                bs.logout()
                return check_date
    
    bs.logout()
    return (today - timedelta(days=1)).strftime('%Y-%m-%d')


async def fetch_stock_list(trading_day: str | None = None):
    """拉取股票列表"""
    print("\n" + "="*60)
    print("[步骤 1] 拉取 A 股股票列表")
    print("="*60)
    
    source = DataSourceFactory.create("baostock")
    db = get_database()
    
    try:
        await source.connect()
        
        # 使用 baostock 的批量查询方法，一次性获取所有股票
        stocks = await source.get_stock_list()
        
        print(f"查询到 {len(stocks)} 只股票")
        
        if not stocks:
            logger.warning("No stocks fetched from baostock")
            return []
        
        async with db.session() as session:
            repo = StockRepository(session)
            count = await repo.bulk_upsert(stocks)
            print(f"[OK] 成功保存 {count} 只股票到数据库")
        
        return [s.code for s in stocks]
        
    finally:
        await source.disconnect()
        await db.close()


async def fetch_daily_klines(codes: list[str], days: int = 365):
    """拉取日K线数据"""
    print("\n" + "="*60)
    print(f"[步骤 2] 拉取日K线数据 (最近 {days} 天)")
    print("="*60)
    
    source = DataSourceFactory.create("baostock")
    db = get_database()
    
    # 使用上一个交易日作为结束日期
    last_trading_day = await get_last_trading_day()
    end_date = datetime.strptime(last_trading_day, '%Y-%m-%d').date()
    start_date = end_date - timedelta(days=days)
    print(f"交易日范围: {start_date} ~ {end_date}")
    
    tracker = ProgressTracker(len(codes))
    
    try:
        # 顺序执行，避免并发问题
        for i, code in enumerate(codes):
            try:
                # baostock 有频率限制，每秒最多 10 次请求
                await asyncio.sleep(0.15)
                klines = await source.get_daily_kline(code, start_date, end_date)
                
                if klines:
                    async with db.session() as session:
                        kline_repo = KlineRepository(session)
                        await kline_repo.bulk_insert(klines)
                
                tracker.update(success=len(klines) > 0)
            except Exception as e:
                logger.warning(f"Failed to fetch klines for {code}: {e}")
                tracker.update(success=False)
            
            tracker.show()
        
        print(f"\n[OK] K线数据拉取完成!")
        print(f"   成功: {tracker.success} 只股票")
        print(f"   失败: {tracker.failed} 只股票")
        
    finally:
        await db.close()


async def fetch_index_data():
    """拉取主要指数数据"""
    print("\n" + "="*60)
    print("[步骤 3] 拉取主要指数数据")
    print("="*60)
    
    source = DataSourceFactory.create("baostock")
    db = get_database()
    
    indices = [
        ("sh.000001", "上证指数"),
        ("sh.399001", "深证成指"),
        ("sh.399006", "创业板指"),
        ("sh.000300", "沪深300"),
        ("sh.000016", "上证50"),
        ("sh.000905", "中证500"),
        ("sh.000852", "中证1000"),
    ]
    
    # 使用上一个交易日作为结束日期
    last_trading_day = await get_last_trading_day()
    end_date = datetime.strptime(last_trading_day, '%Y-%m-%d').date()
    start_date = end_date - timedelta(days=730)  # 2年数据
    
    try:
        await source.connect()
        
        async with db.session() as session:
            kline_repo = KlineRepository(session)
            
            for code, name in indices:
                try:
                    klines = await source.get_index_data(code, start_date, end_date)
                    if klines:
                        await kline_repo.bulk_insert(klines)
                        print(f"  [OK] {name}: {len(klines)} 条K线")
                except Exception as e:
                    print(f"  [FAIL] {name}: {e}")
        
        print("\n[OK] 指数数据拉取完成!")
        
    finally:
        await source.disconnect()
        await db.close()


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Trading Buddy - baostock 数据拉取")
    parser.add_argument("--mode", choices=["all", "stocks", "klines", "indices"], 
                        default="all", help="拉取模式")
    parser.add_argument("--days", type=int, default=365, help="K线天数")
    parser.add_argument("--limit", type=int, default=0, help="限制股票数量(用于测试)")
    
    args = parser.parse_args()
    
    print("\n" + "="*60)
    print("Trading Buddy - A股数据拉取")
    print("="*60)
    print(f"数据源: baostock (免费，无需注册)")
    print(f"数据库: MySQL trading")
    print(f"开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    start_time = time.time()
    
    if args.mode == "all" or args.mode == "stocks":
        codes = await fetch_stock_list()
        
        if args.limit > 0:
            codes = codes[:args.limit]
            print(f"\n[!] 测试模式: 仅处理前 {args.limit} 只股票")
    
    if args.mode == "all" or args.mode == "klines":
        if args.mode == "klines":
            # klines 模式需要先获取股票列表
            codes = await fetch_stock_list()
            if args.limit > 0:
                codes = codes[:args.limit]
        await fetch_daily_klines(codes, args.days)
    
    if args.mode == "all" or args.mode == "indices":
        await fetch_index_data()
    
    elapsed = time.time() - start_time
    print("\n" + "="*60)
    print(f"[DONE] 全部完成! 总耗时: {elapsed/60:.1f} 分钟")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
