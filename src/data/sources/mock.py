"""
Trading Buddy - 模拟数据源
用于测试和开发阶段，提供模拟股票数据
"""

import random
from datetime import date, datetime, timedelta
from typing import AsyncIterator

from .base import BaseDataSource, DataSourceFactory
from ..models import StockInfo, KLine, RealtimeQuote, SectorData


class MockDataSource(BaseDataSource):
    """模拟数据源 - 用于测试"""
    
    # 预定义热门股票
    STOCKS = [
        {"code": "sh.600519", "name": "贵州茅台", "market": "sh", "industry": "白酒"},
        {"code": "sh.601318", "name": "中国平安", "market": "sh", "industry": "保险"},
        {"code": "sh.600036", "name": "招商银行", "market": "sh", "industry": "银行"},
        {"code": "sh.000858", "name": "五粮液", "market": "sz", "industry": "白酒"},
        {"code": "sh.600276", "name": "恒瑞医药", "market": "sh", "industry": "医药"},
        {"code": "sz.000333", "name": "美的集团", "market": "sz", "industry": "家电"},
        {"code": "sz.002594", "name": "比亚迪", "market": "sz", "industry": "汽车"},
        {"code": "sh.601888", "name": "中国中免", "market": "sh", "industry": "旅游零售"},
        {"code": "sz.300750", "name": "宁德时代", "market": "sz", "industry": "锂电池"},
        {"code": "sz.002475", "name": "立讯精密", "market": "sz", "industry": "消费电子"},
        {"code": "sh.600030", "name": "中信证券", "market": "sh", "industry": "证券"},
        {"code": "sh.601012", "name": "隆基绿能", "market": "sh", "industry": "光伏"},
    ]
    
    # 预定义股票价格（模拟）
    BASE_PRICES = {
        "sh.600519": 1680.0,
        "sh.601318": 42.5,
        "sh.600036": 35.2,
        "sh.000858": 145.0,
        "sh.600276": 48.8,
        "sz.000333": 62.5,
        "sz.002594": 268.0,
        "sh.601888": 72.3,
        "sz.300750": 198.5,
        "sz.002475": 32.8,
        "sh.600030": 22.5,
        "sh.601012": 28.6,
    }
    
    @property
    def name(self) -> str:
        return "mock"
    
    async def connect(self) -> None:
        """连接（无需操作）"""
        pass
    
    async def disconnect(self) -> None:
        """断开连接"""
        pass
    
    async def get_stock_list(self) -> list[StockInfo]:
        """获取股票列表"""
        stocks = []
        for s in self.STOCKS:
            stocks.append(StockInfo(
                code=s["code"],
                name=s["name"],
                market=s["market"],
                industry=s["industry"],
                ipo_date=date(2010, 1, 1),
            ))
        return stocks
    
    async def get_stock_info(self, code: str) -> StockInfo | None:
        """获取单个股票信息"""
        for s in self.STOCKS:
            if s["code"] == code:
                return StockInfo(
                    code=s["code"],
                    name=s["name"],
                    market=s["market"],
                    industry=s["industry"],
                    list_date=date(2010, 1, 1),
                )
        return None
    
    async def get_daily_kline(
        self,
        code: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[KLine]:
        """生成模拟K线数据"""
        end = end_date or date.today()
        start = start_date or (end - timedelta(days=365))
        
        if code not in self.BASE_PRICES:
            return []
        
        base_price = self.BASE_PRICES[code]
        klines = []
        
        current_date = start
        current_price = base_price * random.uniform(0.85, 1.15)
        
        while current_date <= end:
            # 跳过周末
            if current_date.weekday() >= 5:
                current_date += timedelta(days=1)
                continue
            
            # 随机波动
            change = random.uniform(-0.05, 0.05)
            current_price *= (1 + change)
            
            day_range = current_price * random.uniform(0.01, 0.03)
            open_price = current_price * random.uniform(0.98, 1.02)
            high_price = max(open_price, current_price) + random.uniform(0, day_range)
            low_price = min(open_price, current_price) - random.uniform(0, day_range)
            
            volume = random.uniform(500000, 5000000)
            
            amount = volume * current_price
            klines.append(KLine(
                code=code,
                trade_date=current_date,
                open=round(open_price, 2),
                high=round(high_price, 2),
                low=round(low_price, 2),
                close=round(current_price, 2),
                volume=int(volume),
                amount=round(amount, 2),
            ))
            
            current_date += timedelta(days=1)
        
        return klines
    
    async def get_realtime_quote(self, codes: list[str]) -> list[RealtimeQuote]:
        """生成模拟实时行情"""
        quotes = []
        for code in codes:
            if code not in self.BASE_PRICES:
                continue
                
            base = self.BASE_PRICES[code]
            price = base * random.uniform(0.98, 1.02)
            pre_close = base * random.uniform(0.95, 1.05)
            
            quotes.append(RealtimeQuote(
                code=code,
                name=code,  # 简化
                open=round(pre_close * random.uniform(0.99, 1.01), 2),
                close=round(pre_close, 2),
                price=round(price, 2),
                high=round(price * random.uniform(1.0, 1.03), 2),
                low=round(price * random.uniform(0.97, 1.0), 2),
                volume=int(random.uniform(1000000, 5000000)),
                amount=round(random.uniform(50000000, 200000000), 2),
                bid1_price=round(price * 0.999, 2),
                bid1_volume=int(random.uniform(100, 1000)),
                ask1_price=round(price * 1.001, 2),
                ask1_volume=int(random.uniform(100, 1000)),
                update_time=datetime.now(),
                change=round(price - pre_close, 2),
                pct_change=round((price - pre_close) / pre_close * 100, 2),
            ))
        
        return quotes
    
    async def get_index_data(
        self,
        code: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[KLine]:
        """生成模拟指数数据"""
        # 模拟指数代码
        index_prices = {
            "sh.000001": 3200.0,
            "sh.399001": 10000.0,
            "sh.399006": 2000.0,
            "sh.000300": 3800.0,
        }
        
        base_price = index_prices.get(code, 3000.0)
        
        end = end_date or date.today()
        start = start_date or (end - timedelta(days=365))
        
        klines = []
        current_date = start
        current_price = base_price
        
        while current_date <= end:
            if current_date.weekday() >= 5:
                current_date += timedelta(days=1)
                continue
            
            change = random.uniform(-0.02, 0.02)
            current_price *= (1 + change)
            
            vol = random.uniform(200000000, 400000000)
            amount = vol * current_price
            klines.append(KLine(
                code=code,
                trade_date=current_date,
                open=round(current_price * 0.999, 2),
                high=round(current_price * 1.005, 2),
                low=round(current_price * 0.995, 2),
                close=round(current_price, 2),
                volume=int(vol),
                amount=round(amount, 2),
            ))
            
            current_date += timedelta(days=1)
        
        return klines


# 注册到工厂
DataSourceFactory.register('mock', MockDataSource)
