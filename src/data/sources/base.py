"""
Trading Buddy - 数据源基类
定义数据源接口规范，方便后续扩展付费数据源
"""

from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import AsyncIterator

from ..models import StockInfo, KLine, RealtimeQuote, SectorData


class BaseDataSource(ABC):
    """数据源基类"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """数据源名称"""
        pass
    
    @abstractmethod
    async def connect(self) -> None:
        """连接数据源"""
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """断开连接"""
        pass
    
    @abstractmethod
    async def get_stock_list(self) -> list[StockInfo]:
        """获取股票列表"""
        pass
    
    @abstractmethod
    async def get_stock_info(self, code: str) -> StockInfo | None:
        """获取单个股票信息"""
        pass
    
    @abstractmethod
    async def get_daily_kline(
        self,
        code: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[KLine]:
        """获取日K线数据"""
        pass
    
    @abstractmethod
    async def get_realtime_quote(self, codes: list[str]) -> list[RealtimeQuote]:
        """获取实时行情"""
        pass
    
    @abstractmethod
    async def get_index_data(
        self,
        code: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[KLine]:
        """获取指数数据"""
        pass


class DataSourceFactory:
    """数据源工厂"""
    
    _sources: dict[str, type[BaseDataSource]] = {}
    
    @classmethod
    def register(cls, name: str, source_class: type[BaseDataSource]) -> None:
        """注册数据源"""
        cls._sources[name] = source_class
    
    @classmethod
    def create(cls, name: str, **kwargs) -> BaseDataSource:
        """创建数据源实例"""
        if name not in cls._sources:
            raise ValueError(f"Unknown data source: {name}. Available: {list(cls._sources.keys())}")
        return cls._sources[name](**kwargs)

    @classmethod
    def create_from_settings(cls, override: str | None = None) -> BaseDataSource:
        """按全局配置创建数据源（tushare 需配置 TUSHARE_TOKEN）"""
        from src.common import get_settings

        s = get_settings().data_source
        name = (override or s.provider).strip().lower()
        if name not in cls._sources:
            raise ValueError(
                f"Unknown data source: {name}. Available: {list(cls._sources.keys())}"
            )
        if name == "tushare":
            token = s.tushare_token
            if not token:
                raise ValueError(
                    "数据源为 tushare 但未设置环境变量 TUSHARE_TOKEN（或配置中的 tushare_token）"
                )
            return cls.create("tushare", token=token)
        return cls.create(name)

    @classmethod
    def available_sources(cls) -> list[str]:
        """获取可用数据源列表"""
        return list(cls._sources.keys())
