"""
Trading Buddy - baostock 数据源适配器
免费、无需注册、支持A股历史数据
文档: http://baostock.com/baostock/index.php
"""

import baostock as bs
from datetime import date, datetime, timedelta

from src.common import get_logger
from ..models import (
    StockInfo, KLine, RealtimeQuote, SectorData,
    Market, StockType
)
from .base import BaseDataSource, DataSourceFactory


logger = get_logger("baostock")


class BaostockSource(BaseDataSource):
    """baostock 数据源"""
    
    def __init__(self):
        self._connected = False
    
    @property
    def name(self) -> str:
        return "baostock"
    
    async def connect(self) -> None:
        """连接 baostock"""
        if self._connected:
            return
        
        logger.info("Connecting to baostock...")
        rs = bs.login()
        if rs.error_code != '0':
            raise ConnectionError(f"Baostock login failed: {rs.error_msg}")
        
        self._connected = True
        logger.info("Connected to baostock successfully")
    
    async def disconnect(self) -> None:
        """断开连接"""
        if self._connected:
            bs.logout()
            self._connected = False
            logger.info("Disconnected from baostock")
    
    def _parse_stock_type(self, code: str, stock_type_str: str | None) -> StockType:
        """解析股票类型"""
        if stock_type_str:
            stock_type_str = stock_type_str.lower()
            if 'st' in stock_type_str:
                return StockType.ST
            elif stock_type_str == '科创':
                return StockType.STAR
            elif stock_type_str == '创业':
                return StockType.GROWTH
        
        # 根据代码判断
        if code.startswith('sh.688'):
            return StockType.STAR  # 科创板
        elif code.startswith('sz.300'):
            return StockType.GROWTH  # 创业板
        elif code.startswith('bj.'):
            return StockType.BEIJING  # 北交所
        else:
            return StockType.COMMON
    
    def _parse_market(self, code: str) -> Market:
        """解析市场"""
        if code.startswith('sh.'):
            return Market.SH
        elif code.startswith('sz.'):
            return Market.SZ
        elif code.startswith('bj.'):
            return Market.BJ
        elif code.startswith('hk.'):
            return Market.HK
        else:
            return Market.SZ  # 默认深圳
    
    async def get_stock_list(self) -> list[StockInfo]:
        """获取所有A股股票列表（不含指数）"""
        await self.connect()
        logger.info("Fetching stock list from baostock...")
        
        # 找到最近交易日
        trading_day = date.today()
        for i in range(1, 10):
            check_date = trading_day - timedelta(days=i)
            rs_dates = bs.query_trade_dates(
                start_date=check_date.strftime('%Y-%m-%d'),
                end_date=check_date.strftime('%Y-%m-%d')
            )
            while rs_dates.next():
                row = rs_dates.get_row_data()
                if row[1] == '1':  # is_trading_day
                    trading_day = check_date
                    break
            else:
                continue
            break
        
        logger.info(f"Using trading day: {trading_day}")
        
        stocks = []
        rs = bs.query_all_stock(day=trading_day.strftime('%Y-%m-%d'))
        
        while rs.error_code == '0' and rs.next():
            row = rs.get_row_data()
            code = row[0]
            trade_status = row[1]  # 1=交易中, 0=停牌
            name = row[2]  # code_name
            
            # 跳过非A股股票
            # 北交所
            if code.startswith('bj.'):
                continue
            
            # B股: sh.900xxx, sz.200xxx
            if code.startswith('sh.900') or code.startswith('sz.200'):
                continue
            
            # 指数: sh.000xxx, sh.399xxx, sz.399xxx
            if code.startswith('sh.000') or code.startswith('sh.399') or code.startswith('sz.399'):
                continue
            
            # 基金/ETF: sh.5xxxxx, sz.1xxxxx
            if code.startswith('sh.5') or code.startswith('sz.1'):
                continue
            
            # 只保留真正的A股股票代码格式
            # 上交所: 600xxx, 601xxx, 603xxx, 605xxx, 688xxx
            # 深交所: 000xxx, 001xxx, 002xxx, 003xxx, 300xxx
            if code.startswith('sh.'):
                suffix = code[3:]
                if not (suffix.startswith('6') or suffix.startswith('688') or suffix.startswith('689')):
                    continue
            elif code.startswith('sz.'):
                suffix = code[3:]
                if not (suffix.startswith('000') or suffix.startswith('001') or 
                        suffix.startswith('002') or suffix.startswith('003') or suffix.startswith('300')):
                    continue
            else:
                continue
            
            stocks.append(StockInfo(
                code=code,
                name=name,
                stock_type=self._parse_stock_type(code, None),  # 简化版列表不需要精确类型
                market=self._parse_market(code),
                is_trading=(trade_status == "1"),
            ))
        
        logger.info(f"Fetched {len(stocks)} stocks")
        return stocks
    
    async def get_stock_info(self, code: str) -> StockInfo | None:
        """获取单个股票详细信息"""
        await self.connect()
        logger.info(f"Fetching stock info: {code}")
        
        rs = bs.query_stock_basic(code=code)
        
        if rs.error_code != '0':
            logger.error(f"Query failed: {rs.error_msg}")
            return None
        
        while rs.next():
            row = rs.get_row_data()
            return StockInfo(
                code=row[0],
                name=row[1],
                ipo_date=datetime.strptime(row[2], '%Y-%m-%d').date() if row[2] else None,
                out_date=datetime.strptime(row[3], '%Y-%m-%d').date() if row[3] and row[3] != '' else None,
                stock_type=self._parse_stock_type(row[0], row[4]),
                market=self._parse_market(row[0]),
                industry=row[5] if len(row) > 5 else None,
            )
        
        return None
    
    async def get_daily_kline(
        self,
        code: str,
        start_date: date | None = None,
        end_date: date | None = None,
        adjustflag: str = "3",
    ) -> list[KLine]:
        """获取日K线数据；每只股票独立登录+登出，设置套接字超时避免连接僵死。"""
        import socket as _socket

        if end_date is None:
            end_date = date.today()
        if start_date is None:
            start_date = date(end_date.year - 3, end_date.month, end_date.day)

        logger.info(f"Fetching daily kline: {code} from {start_date} to {end_date} (adjustflag={adjustflag})")

        # 单只股票查询总超时（秒）；过长会拖慢整体进度，过短可能触发正常慢查询
        QUERY_TIMEOUT = 45
        _socket.setdefaulttimeout(QUERY_TIMEOUT)

        klines: list[KLine] = []
        try:
            bs.login()
            rs = bs.query_history_k_data_plus(
                code,
                "date,open,high,low,close,preclose,volume,amount,pctChg",
                start_date=start_date.strftime('%Y-%m-%d'),
                end_date=end_date.strftime('%Y-%m-%d'),
                frequency="d",
                adjustflag=adjustflag,
            )

            if rs.error_code == '0':
                while rs.next():
                    row = rs.get_row_data()
                    try:
                        # 字段顺序: date,open,high,low,close,preclose,volume,amount,pctChg
                        pct = float(row[8]) if len(row) > 8 and row[8] not in (None, "") else None
                        pre_close = float(row[5]) if len(row) > 5 and row[5] not in (None, "") else None
                        kline = KLine(
                            code=code,
                            trade_date=datetime.strptime(row[0], '%Y-%m-%d').date(),
                            open=float(row[1]),
                            high=float(row[2]),
                            low=float(row[3]),
                            close=float(row[4]),
                            pre_close=pre_close,
                            volume=int(float(row[6])) if row[6] else 0,
                            amount=float(row[7]) if row[7] else 0.0,
                            turnover_rate=None,
                            pct_change=pct,
                            adjust_flag=adjustflag,
                        )
                        klines.append(kline)
                    except (ValueError, IndexError) as e:
                        logger.warning(f"Parse error for {code} on {row[0]}: {e}")
            else:
                logger.warning(f"Query failed for {code}: {rs.error_msg}")
        except Exception as e:
            logger.warning(f"Exception for {code}: {e}")
        finally:
            bs.logout()
            _socket.setdefaulttimeout(None)

        logger.info(f"Fetched {len(klines)} klines for {code}")
        return klines
    
    async def get_realtime_quote(self, codes: list[str]) -> list[RealtimeQuote]:
        """获取实时行情"""
        await self.connect()
        
        if not codes:
            return []
        
        code_str = ','.join(codes)
        rs = bs.query_realtime_data(code_str)
        
        quotes = []
        if rs.error_code == '0':
            while rs.next():
                row = rs.get_row_data()
                try:
                    quote = RealtimeQuote(
                        code=row[0],
                        name=row[1],
                        open=float(row[2]) if row[2] else 0,
                        close=float(row[3]) if row[3] else 0,
                        price=float(row[4]) if row[4] else 0,
                        high=float(row[5]) if row[5] else 0,
                        low=float(row[6]) if row[6] else 0,
                        volume=int(row[7]) if row[7] else 0,
                        amount=float(row[8]) if row[8] else 0,
                        bid1_price=float(row[9]) if row[9] else 0,
                        bid1_volume=int(row[10]) if row[10] else 0,
                        ask1_price=float(row[11]) if row[11] else 0,
                        ask1_volume=int(row[12]) if row[12] else 0,
                        update_time=datetime.strptime(row[13], '%Y-%m-%d %H:%M:%S') if row[13] else datetime.now(),
                    )
                    if quote.close > 0:
                        quote.change = round(quote.price - quote.close, 2)
                        quote.pct_change = round((quote.price - quote.close) / quote.close * 100, 2)
                    quotes.append(quote)
                except (ValueError, IndexError) as e:
                    logger.warning(f"Parse realtime quote error: {e}")
        
        return quotes
    
    async def get_index_data(
        self,
        code: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[KLine]:
        """获取指数数据（深证/创业板等须保留 sz. 前缀）"""
        if not (
            code.startswith("sh.")
            or code.startswith("sz.")
            or code.startswith("bj.")
        ):
            code = f"sh.{code}"
        return await self.get_daily_kline(code, start_date, end_date)
    
    async def get_sector_list(self) -> list[SectorData]:
        """获取板块列表"""
        await self.connect()
        logger.info("Fetching sector list...")
        
        sectors = []
        rs = bs.query_stock_industry()
        
        if rs.error_code == '0':
            while rs.next():
                row = rs.get_row_data()
                sectors.append(SectorData(
                    code=row[0],
                    name=row[1],
                    sector_type="industry",
                    stock_count=int(row[2]) if row[2] else 0,
                    leading_stocks=[],
                ))
        
        logger.info(f"Fetched {len(sectors)} sectors")
        return sectors


# 注册到工厂
DataSourceFactory.register("baostock", BaostockSource)
