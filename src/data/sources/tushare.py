"""
Trading Buddy - Tushare 数据源适配器
使用 Tushare API 获取 A 股数据
"""

import tushare as ts
from datetime import date, datetime
from typing import AsyncIterator

from .base import BaseDataSource, DataSourceFactory
from ..models import StockInfo, KLine, RealtimeQuote, SectorData


class TushareSource(BaseDataSource):
    """Tushare 数据源"""
    
    def __init__(self, token: str):
        self._token = token
        self._pro: ts.pro.API = None
        
    @property
    def name(self) -> str:
        return "tushare"
    
    async def connect(self) -> None:
        """初始化 Tushare 连接"""
        ts.set_token(self._token)
        self._pro = ts.pro_api()
    
    async def disconnect(self) -> None:
        """断开连接（Tushare 无需断开）"""
        pass
    
    async def get_stock_list(self) -> list[StockInfo]:
        """获取股票列表"""
        try:
            df = self._pro.stock_basic(
                exchange='',
                list_status='L',
                fields='ts_code,symbol,name,area,industry,market,list_date'
            )
            
            stocks = []
            for _, row in df.iterrows():
                stocks.append(StockInfo(
                    code=row['symbol'],  # 使用原始代码
                    name=row['name'],
                    market=row['market'],
                    industry=row['industry'],
                    list_date=datetime.strptime(str(row['list_date']), '%Y%m%d').date() if row['list_date'] else None,
                ))
            return stocks
        except Exception as e:
            print(f"获取股票列表失败: {e}")
            return []
    
    async def get_stock_info(self, code: str) -> StockInfo | None:
        """获取单个股票信息"""
        try:
            # 转换代码格式
            ts_code = self._format_code(code)
            df = self._pro.stock_basic(ts_code=ts_code, fields='ts_code,symbol,name,area,industry,market,list_date')
            
            if df is not None and len(df) > 0:
                row = df.iloc[0]
                return StockInfo(
                    code=row['symbol'],
                    name=row['name'],
                    market=row['market'],
                    industry=row['industry'],
                    list_date=datetime.strptime(str(row['list_date']), '%Y%m%d').date() if row['list_date'] else None,
                )
        except Exception as e:
            print(f"获取股票信息失败 {code}: {e}")
        return None
    
    async def get_daily_kline(
        self,
        code: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[KLine]:
        """获取日K线数据"""
        try:
            ts_code = self._format_code(code)
            
            # 格式化日期
            start = start_date.strftime('%Y%m%d') if start_date else '20200101'
            end = end_date.strftime('%Y%m%d') if end_date else datetime.now().strftime('%Y%m%d')
            
            df = self._pro.daily(
                ts_code=ts_code,
                start_date=start,
                end_date=end
            )

            klines = []
            for _, row in df.iterrows():
                klines.append(KLine(
                    code=code,
                    trade_date=row['trade_date'],
                    open=float(row['open']),
                    high=float(row['high']),
                    low=float(row['low']),
                    close=float(row['close']),
                    volume=float(row['vol']),
                    adjust_flag="3",
                ))
            return klines
        except Exception as e:
            print(f"获取K线失败 {code}: {e}")
            return []
    
    async def get_realtime_quote(self, codes: list[str]) -> list[RealtimeQuote]:
        """获取实时行情"""
        try:
            # 转换代码格式
            ts_codes = [self._format_code(c) for c in codes]
            df = ts.realtime_quote(ts_code=','.join(ts_codes))
            
            quotes = []
            for _, row in df.iterrows():
                quotes.append(RealtimeQuote(
                    code=row.get('code', ''),
                    current=float(row.get('price', 0)),
                    open=float(row.get('open', 0)),
                    high=float(row.get('high', 0)),
                    low=float(row.get('low', 0)),
                    volume=float(row.get('volume', 0)),
                    amount=float(row.get('amount', 0)),
                    change=float(row.get('price', 0)) - float(row.get('pre_close', 0)) if row.get('price') and row.get('pre_close') else 0,
                ))
            return quotes
        except Exception as e:
            print(f"获取实时行情失败: {e}")
            return []
    
    async def get_index_data(
        self,
        code: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[KLine]:
        """获取指数数据"""
        try:
            # 转换代码格式
            ts_code = self._format_code(code)
            
            start = start_date.strftime('%Y%m%d') if start_date else '20200101'
            end = end_date.strftime('%Y%m%d') if end_date else datetime.now().strftime('%Y%m%d')
            
            df = self._pro.index_daily(
                ts_code=ts_code,
                start_date=start,
                end_date=end
            )

            klines = []
            for _, row in df.iterrows():
                klines.append(KLine(
                    code=code,
                    trade_date=row['trade_date'],
                    open=float(row['open']),
                    high=float(row['high']),
                    low=float(row['low']),
                    close=float(row['close']),
                    volume=float(row['vol']),
                    adjust_flag="3",
                ))
            return klines
        except Exception as e:
            print(f"获取指数数据失败 {code}: {e}")
            return []
    
    def _format_code(self, code: str) -> str:
        """转换代码格式: sh.600519 -> 600519.SH"""
        if '.' in code:
            exchange, num = code.split('.')
            exchange = exchange.upper()
            if exchange == 'SH':
                return f"{num}.SH"
            elif exchange == 'SZ':
                return f"{num}.SZ"
        # 如果是纯数字，添加默认后缀
        if code.isdigit():
            if code.startswith('6'):
                return f"{code}.SH"
            else:
                return f"{code}.SZ"
        return code


# 注册到工厂
DataSourceFactory.register('tushare', TushareSource)
