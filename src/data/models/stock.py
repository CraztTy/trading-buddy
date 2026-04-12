"""
Trading Buddy - 数据模型
定义股票、K线、板块等数据模型
"""

from datetime import datetime, date
from decimal import Decimal
from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class Market(str, Enum):
    """市场类型"""
    SH = "sh"  # 上海
    SZ = "sz"  # 深圳
    BJ = "bj"  # 北京
    HK = "hk"  # 港股（未来扩展）
    US = "us"  # 美股（未来扩展）


class StockType(str, Enum):
    """股票类型"""
    COMMON = "common"  # 普通股票
    ST = "st"  # ST股票
    STAR = "star"  # 科创板
    GROWTH = "growth"  # 创业板
    BEIJING = "beijing"  # 北交所


class StockInfo(BaseModel):
    """股票基本信息"""

    model_config = ConfigDict(from_attributes=True)

    code: str = Field(..., description="股票代码，如 000001.SZ")
    name: str = Field(..., description="股票名称")
    ipo_date: Optional[date] = Field(None, description="上市日期")
    out_date: Optional[date] = Field(None, description="退市日期")
    stock_type: StockType = Field(StockType.COMMON, description="股票类型")
    market: Market = Field(..., description="交易市场")
    industry: Optional[str] = Field(None, description="所属行业")
    sector_code: Optional[str] = Field(None, description="板块代码（概念/行业）")
    is_trading: bool = Field(True, description="是否交易中（未停牌）")


class KLine(BaseModel):
    """K线数据"""

    model_config = ConfigDict(from_attributes=True)

    code: str = Field(..., description="股票代码")
    trade_date: date = Field(..., description="交易日期")
    open: float = Field(..., description="开盘价")
    high: float = Field(..., description="最高价")
    low: float = Field(..., description="最低价")
    close: float = Field(..., description="收盘价")
    volume: int = Field(..., description="成交量")
    amount: float = Field(..., description="成交额")
    turnover_rate: Optional[float] = Field(None, description="换手率")
    adjust_flag: str = Field("3", description="复权类型: 1=后复权 2=前复权 3=不复权")
    
    # 预计算字段（可选）
    change: Optional[float] = Field(None, description="涨跌额")
    pct_change: Optional[float] = Field(None, description="涨跌幅")
    ma5: Optional[float] = Field(None, description="5日均线")
    ma10: Optional[float] = Field(None, description="10日均线")
    ma20: Optional[float] = Field(None, description="20日均线")


class RealtimeQuote(BaseModel):
    """实时行情"""

    model_config = ConfigDict(from_attributes=True)

    code: str = Field(..., description="股票代码")
    name: str = Field(..., description="股票名称")
    open: float = Field(..., description="今日开盘价")
    close: float = Field(..., description="昨日收盘价")
    price: float = Field(..., description="当前价格")
    high: float = Field(..., description="今日最高价")
    low: float = Field(..., description="今日最低价")
    volume: int = Field(..., description="成交量")
    amount: float = Field(..., description="成交额")
    bid1_price: float = Field(..., description="买一价")
    bid1_volume: int = Field(..., description="买一量")
    ask1_price: float = Field(..., description="卖一价")
    ask1_volume: int = Field(..., description="卖一量")
    update_time: datetime = Field(..., description="更新时间")
    
    # 计算字段
    change: Optional[float] = Field(None, description="涨跌额")
    pct_change: Optional[float] = Field(None, description="涨跌幅")


class SectorData(BaseModel):
    """板块数据"""

    model_config = ConfigDict(from_attributes=True)

    code: str = Field(..., description="板块代码")
    name: str = Field(..., description="板块名称")
    sector_type: str = Field(..., description="板块类型: industry=行业, concept=概念")
    stock_count: int = Field(0, description="成分股数量")
    leading_stocks: list[str] = Field(default_factory=list, description="龙头股代码列表")
