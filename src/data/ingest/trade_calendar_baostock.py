"""Baostock `query_trade_dates` → `trade_calendar`（供 `fetch_trade_calendar` / `fetch_data` 复用）。"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta

from src.common import get_logger
from src.data.storage import TradeCalendarRepository, get_database

logger = get_logger("trade_calendar_baostock")


def fetch_baostock_trade_dates_chunk(start: date, end: date) -> list[tuple[date, bool]]:
    """同步调用 Baostock，返回 [(calendar_date, is_trading_day), ...]。"""
    import baostock as bs

    rs_login = bs.login()
    if rs_login.error_code != "0":
        raise ConnectionError(f"baostock 登录失败: {rs_login.error_msg}")
    out: list[tuple[date, bool]] = []
    try:
        rs = bs.query_trade_dates(
            start_date=start.strftime("%Y-%m-%d"),
            end_date=end.strftime("%Y-%m-%d"),
        )
        if rs.error_code != "0":
            raise RuntimeError(f"query_trade_dates 失败: {rs.error_msg}")
        while rs.next():
            row = rs.get_row_data()
            cal = datetime.strptime(row[0], "%Y-%m-%d").date()
            is_td = len(row) > 1 and str(row[1]).strip() == "1"
            out.append((cal, is_td))
    finally:
        bs.logout()
    return out


async def ingest_trade_calendar_from_baostock(
    *,
    start: date,
    end: date,
    exchange: str = "cn",
    chunk_days: int = 400,
) -> int:
    """
    按自然日分块拉取并 upsert；幂等。

    Returns:
        累计写入行数（各 chunk 之和，非去重后的表行数）。
    """
    if start > end:
        raise ValueError("start 不能晚于 end")

    ex = exchange.strip().lower()
    db = get_database()
    total = 0
    cur = start
    delta = timedelta(days=max(1, chunk_days))
    while cur <= end:
        chunk_end = min(cur + delta - timedelta(days=1), end)
        logger.info(f"交易日历 {ex}: {cur} ~ {chunk_end}")
        rows = await asyncio.to_thread(fetch_baostock_trade_dates_chunk, cur, chunk_end)
        async with db.session() as session:
            repo = TradeCalendarRepository(session)
            n = await repo.bulk_upsert_days(ex, rows)
            total += n
        cur = chunk_end + timedelta(days=1)
    logger.info(f"交易日历完成 exchange={ex} 累计 upsert 约 {total} 行")
    return total
