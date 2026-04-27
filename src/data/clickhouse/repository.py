"""ClickHouse 数据仓库 — 高性能时序数据读写。

适用场景：
- 大量历史 K 线查询（比 SQLite/MySQL 快 10-100 倍）
- 分钟级/ tick 级数据存储
- 聚合分析（GROUP BY、窗口函数）

用法:
    from src.data.clickhouse.repository import ClickHouseRepository
    repo = ClickHouseRepository()
    klines = await repo.get_daily("sh.600000", limit=100)
    await repo.insert_daily(klines)
"""

from __future__ import annotations

from datetime import date
from typing import Any

from src.common import get_logger
from src.data.clickhouse.client import get_ch_client
from src.data.models import KLine

logger = get_logger("ch_repository")

# 单次插入最大行数
_MAX_INSERT_BATCH = 10000


class ClickHouseRepository:
    """ClickHouse 时序数据仓库。"""

    def __init__(self):
        self._client = get_ch_client()

    def _ensure_connected(self) -> None:
        if self._client is None:
            raise RuntimeError("ClickHouse 未启用或未连接")

    # ------------------------------------------------------------------
    # 日K线
    # ------------------------------------------------------------------

    def get_daily(
        self,
        code: str,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 100,
        adjust_flag: str = "3",
    ) -> list[KLine]:
        """查询日K线数据。

        Returns:
            KLine 列表（时间升序）
        """
        self._ensure_connected()

        code = code.strip().lower()
        conditions = [f"code = '{code}'", f"adjust_flag = '{adjust_flag}'"]
        if start_date:
            conditions.append(f"trade_date >= '{start_date.isoformat()}'")
        if end_date:
            conditions.append(f"trade_date <= '{end_date.isoformat()}'")

        where = " AND ".join(conditions)
        sql = f"""
            SELECT
                code,
                trade_date,
                open,
                high,
                low,
                close,
                pre_close,
                volume,
                amount,
                turnover_rate,
                change_pct,
                adjust_flag
            FROM daily_kline
            WHERE {where}
            ORDER BY trade_date ASC
            LIMIT {limit}
        """

        result = self._client.query(sql)
        rows = result.result_rows

        return [
            KLine(
                code=row[0],
                trade_date=row[1],
                open=float(row[2]),
                high=float(row[3]),
                low=float(row[4]),
                close=float(row[5]),
                pre_close=float(row[6]) if row[6] else None,
                volume=int(row[7]) if row[7] else 0,
                amount=float(row[8]) if row[8] else 0.0,
                turnover_rate=float(row[9]) if row[9] else None,
                pct_change=float(row[10]) if row[10] else None,
                adjust_flag=row[11] or "3",
            )
            for row in rows
        ]

    def insert_daily(self, klines: list[KLine]) -> int:
        """批量插入日K线数据。

        Returns:
            插入行数
        """
        self._ensure_connected()
        if not klines:
            return 0

        rows = [
            {
                "code": k.code.strip().lower(),
                "trade_date": k.trade_date.isoformat(),
                "adjust_flag": k.adjust_flag or "3",
                "open": k.open,
                "high": k.high,
                "low": k.low,
                "close": k.close,
                "pre_close": k.pre_close,
                "volume": k.volume or 0,
                "amount": k.amount or 0.0,
                "change_pct": k.pct_change,
                "turnover_rate": k.turnover_rate,
            }
            for k in klines
        ]

        self._client.insert("daily_kline", rows)
        logger.info("inserted %d daily klines into clickhouse", len(rows))
        return len(rows)

    # ------------------------------------------------------------------
    # 分钟K线
    # ------------------------------------------------------------------

    def get_minute(
        self,
        code: str,
        trade_date: date,
        period: str = "1m",
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """查询分钟K线数据。"""
        self._ensure_connected()

        code = code.strip().lower()
        sql = f"""
            SELECT
                trade_time,
                open,
                high,
                low,
                close,
                volume,
                amount
            FROM minute_kline
            WHERE code = '{code}'
              AND trade_date = '{trade_date.isoformat()}'
              AND period = '{period}'
            ORDER BY trade_time ASC
            LIMIT {limit}
        """

        result = self._client.query(sql)
        columns = [c[0] for c in result.column_names]

        return [
            dict(zip(columns, row))
            for row in result.result_rows
        ]

    def insert_minute(self, records: list[dict[str, Any]]) -> int:
        """批量插入分钟K线数据。"""
        self._ensure_connected()
        if not records:
            return 0

        self._client.insert("minute_kline", records)
        logger.info("inserted %d minute klines into clickhouse", len(records))
        return len(records)

    # ------------------------------------------------------------------
    # Tick 数据
    # ------------------------------------------------------------------

    def insert_tick(self, records: list[dict[str, Any]]) -> int:
        """批量插入 Tick 数据。"""
        self._ensure_connected()
        if not records:
            return 0

        self._client.insert("tick_data", records)
        logger.info("inserted %d ticks into clickhouse", len(records))
        return len(records)

    # ------------------------------------------------------------------
    # 聚合查询
    # ------------------------------------------------------------------

    def get_trade_date_range(self, code: str) -> tuple[date | None, date | None]:
        """获取某标的的数据日期范围。"""
        self._ensure_connected()
        code = code.strip().lower()

        sql = f"""
            SELECT min(trade_date), max(trade_date)
            FROM daily_kline
            WHERE code = '{code}'
        """
        result = self._client.query(sql)
        row = result.first_row
        if row and row[0]:
            return (row[0], row[1])
        return (None, None)

    def count_daily(self, code: str | None = None) -> int:
        """统计日K线记录数。"""
        self._ensure_connected()

        if code:
            sql = f"SELECT count() FROM daily_kline WHERE code = '{code.strip().lower()}'"
        else:
            sql = "SELECT count() FROM daily_kline"

        result = self._client.query(sql)
        return int(result.first_row[0]) if result.first_row else 0

    # ------------------------------------------------------------------
    # 表管理
    # ------------------------------------------------------------------

    def create_tables(self) -> None:
        """创建所有 ClickHouse 表。"""
        self._ensure_connected()
        from src.data.clickhouse.schema import ALL_TABLES

        for name, ddl in ALL_TABLES.items():
            try:
                self._client.command(ddl)
                logger.info("clickhouse table created: %s", name)
            except Exception as e:
                if "already exists" in str(e):
                    logger.debug("clickhouse table already exists: %s", name)
                else:
                    logger.error("clickhouse create table failed %s: %s", name, e)

    def optimize_table(self, table_name: str) -> None:
        """优化表（合并分区）。"""
        self._ensure_connected()
        self._client.command(f"OPTIMIZE TABLE {table_name} FINAL")

    def drop_table(self, table_name: str) -> None:
        """删除表（危险操作）。"""
        self._ensure_connected()
        self._client.command(f"DROP TABLE IF EXISTS {table_name}")
        logger.warning("clickhouse table dropped: %s", table_name)
