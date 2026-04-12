"""
Trading Buddy - SQLAlchemy ORM 模型
"""

from datetime import datetime, date
from sqlalchemy import (
    String,
    Integer,
    Float,
    Date,
    DateTime,
    Text,
    JSON,
    Boolean,
    Numeric,
    BigInteger,
    ForeignKey,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class StockInfoModel(Base):
    """股票信息表"""
    __tablename__ = "stock_info"

    code: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(50), nullable=True)
    market: Mapped[str] = mapped_column(String(8), default="sh")
    is_trading: Mapped[bool] = mapped_column(Boolean, default=True)
    market_cap: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    float_cap: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    list_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    out_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    stock_type: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class TradingCalendarModel(Base):
    """交易日历：自然日一行，是否交易日（与 Baostock `query_trade_dates` 等数据源对齐）。"""

    __tablename__ = "trade_calendar"
    __table_args__ = (
        UniqueConstraint("exchange", "calendar_date", name="uq_trade_calendar_exchange_date"),
        Index("ix_trade_calendar_exchange_date", "exchange", "calendar_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exchange: Mapped[str] = mapped_column(String(16), nullable=False)
    calendar_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_trading_day: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class DailyKlineModel(Base):
    """日线K线表"""
    __tablename__ = "daily_kline"
    __table_args__ = (
        UniqueConstraint("code", "trade_date", name="uq_daily_kline_code_date"),
        # 涨跌榜：WHERE trade_date=? ORDER BY change_pct LIMIT N（避免全分区排序）
        Index("ix_daily_kline_trade_date_pct", "trade_date", "change_pct"),
        # 成交额榜：WHERE trade_date=? ORDER BY amount DESC LIMIT N
        Index("ix_daily_kline_trade_date_amount", "trade_date", "amount"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    # 指数日 K 成交量为全市场合计，易超过 32 位 INT
    volume: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    turnover_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class MinuteKlineModel(Base):
    """分钟K线表"""
    __tablename__ = "minute_kline"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    trade_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    period: Mapped[str] = mapped_column(String(10), nullable=False)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class SectorInfoModel(Base):
    """板块信息表"""
    __tablename__ = "sector_info"
    
    code: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    sector_type: Mapped[str] = mapped_column(String(20), nullable=False)
    stock_count: Mapped[int] = mapped_column(Integer, default=0)
    leading_stocks: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class IndexDataModel(Base):
    """指数数据表"""
    __tablename__ = "index_data"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    change: Mapped[float | None] = mapped_column(Float, nullable=True)
    pct_change: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class PaperAccountModel(Base):
    """纸交易资金账户（单默认账户 MVP）"""

    __tablename__ = "paper_account"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    label: Mapped[str] = mapped_column(String(32), nullable=False, default="default", unique=True)
    cash: Mapped[float] = mapped_column(Float, nullable=False, default=1_000_000.0)
    initial_cash: Mapped[float] = mapped_column(Float, nullable=False, default=1_000_000.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class PaperPositionModel(Base):
    """纸交易持仓"""

    __tablename__ = "paper_position"
    __table_args__ = (
        UniqueConstraint("account_id", "code", name="uq_paper_position_account_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("paper_account.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_price: Mapped[float] = mapped_column(Float, nullable=False)


class PaperOrderModel(Base):
    """纸交易成交记录（按日 K 最近一根收盘价撮合）"""

    __tablename__ = "paper_order"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("paper_account.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(16), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    fill_price: Mapped[float] = mapped_column(Float, nullable=False)
    fill_amount: Mapped[float] = mapped_column(Float, nullable=False)
    trade_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class PaperLotModel(Base):
    """纸交易可卖持仓批（FIFO；买入日记 buy_trade_date，卖出须 buy_trade_date < 定价日 K 线日 T+1）"""

    __tablename__ = "paper_lot"
    __table_args__ = (Index("ix_paper_lot_account_code_date", "account_id", "code", "buy_trade_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("paper_account.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    buy_trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    buy_price: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class WatchlistModel(Base):
    """自选股分组（MVP：单默认分组）"""

    __tablename__ = "watchlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    label: Mapped[str] = mapped_column(String(32), nullable=False, default="default", unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class WatchlistItemModel(Base):
    """自选股条目"""

    __tablename__ = "watchlist_item"
    __table_args__ = (UniqueConstraint("watchlist_id", "code", name="uq_watchlist_item_list_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    watchlist_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("watchlist.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class BacktestRunModel(Base):
    """回测 / 批量扫描结果存档（JSON 可查）"""

    __tablename__ = "backtest_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    request_params: Mapped[dict] = mapped_column(JSON, nullable=False)
    response_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)


class SyncLogModel(Base):
    """数据同步日志表"""
    __tablename__ = "sync_log"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    data_type: Mapped[str] = mapped_column(String(50), nullable=False)
    last_update: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="success")
    records_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
