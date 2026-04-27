"""ClickHouse 表结构定义。

设计原则：
- 使用 MergeTree 引擎族（适合时序数据）
- 按 trade_date 分区，code 排序
- 压缩率高，聚合查询快

表：
- daily_kline: 日K线（ReplacingMergeTree，支持更新）
- minute_kline: 分钟K线
- tick_data: Tick 数据（未来扩展）
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 日K线表
# ---------------------------------------------------------------------------

DAILY_KLINE_TABLE = """
CREATE TABLE IF NOT EXISTS daily_kline (
    code String,
    trade_date Date,
    adjust_flag String DEFAULT '3',
    open Float64,
    high Float64,
    low Float64,
    close Float64,
    pre_close Float64,
    volume Int64,
    amount Float64,
    change_pct Float64,
    turnover_rate Float64,
    created_at DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(created_at)
PARTITION BY toYYYYMM(trade_date)
ORDER BY (code, trade_date, adjust_flag)
SETTINGS index_granularity = 8192
"""

# ---------------------------------------------------------------------------
# 分钟K线表
# ---------------------------------------------------------------------------

MINUTE_KLINE_TABLE = """
CREATE TABLE IF NOT EXISTS minute_kline (
    code String,
    trade_date Date,
    trade_time DateTime,
    period String DEFAULT '1m',
    open Float64,
    high Float64,
    low Float64,
    close Float64,
    volume Int64,
    amount Float64,
    created_at DateTime DEFAULT now()
)
ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(trade_date)
ORDER BY (code, trade_time, period)
SETTINGS index_granularity = 8192
"""

# ---------------------------------------------------------------------------
# Tick 数据表
# ---------------------------------------------------------------------------

TICK_DATA_TABLE = """
CREATE TABLE IF NOT EXISTS tick_data (
    code String,
    trade_date Date,
    trade_time DateTime64(3),
    price Float64,
    volume Int64,
    amount Float64,
    bid1_price Float64,
    bid1_volume Int64,
    ask1_price Float64,
    ask1_volume Int64,
    created_at DateTime DEFAULT now()
)
ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(trade_date)
ORDER BY (code, trade_time)
SETTINGS index_granularity = 8192
"""

# 所有表
ALL_TABLES = {
    "daily_kline": DAILY_KLINE_TABLE,
    "minute_kline": MINUTE_KLINE_TABLE,
    "tick_data": TICK_DATA_TABLE,
}


def get_create_table_sql(table_name: str) -> str:
    """获取建表 SQL。"""
    return ALL_TABLES.get(table_name, "")
