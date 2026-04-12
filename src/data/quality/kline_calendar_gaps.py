"""
按「抽样若干 code + 有序 trade_date」估算相邻 K 线之间的缺口：

- **公历**：相邻日期的间隔天数减 1（与是否周末无关的粗代理）。
- **交易日**（可选）：当 `trade_calendar` 表在指定 `exchange` 下有数据时，统计相邻两根日 K
  的 ``trade_date`` **开区间**内属于**交易日**的个数（依赖 `scripts/fetch_trade_calendar.py` 等灌数）。
"""

from __future__ import annotations

from datetime import date
from itertools import groupby
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.data.storage.calendar_repository import TradeCalendarRepository
from src.data.storage.models import DailyKlineModel


def max_interior_gap_calendar_days(dates: list[date]) -> int | None:
    """相邻 trade_date 公历间隔天数减 1（同日或连续自然日 → 0）；单根 K 返回 None。"""
    if len(dates) < 2:
        return None
    m = 0
    for i in range(1, len(dates)):
        delta = (dates[i] - dates[i - 1]).days
        interior = max(0, delta - 1)
        if interior > m:
            m = interior
    return m


def max_missing_trading_sessions_between_klines(
    dates: list[date],
    trading_days: set[date],
) -> int | None:
    """相邻日 K 开区间 (d_prev, d_next) 内、落在 ``trading_days`` 集合中的交易日个数之最大；单根 K 返回 None。"""
    if len(dates) < 2:
        return None
    m = 0
    for i in range(1, len(dates)):
        d0, d1 = dates[i - 1], dates[i]
        c = sum(1 for td in trading_days if d0 < td < d1)
        if c > m:
            m = c
    return m


def normalize_gap_exchange(raw: str | None) -> str | None:
    """将 CLI/API 传入的 exchange 规范化；空 / none / off → 不启用交易日缺口分支。"""
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if s in ("", "none", "off"):
        return None
    return s


async def calendar_gap_sample_report(
    session: AsyncSession,
    *,
    sample_size: int,
    seed_offset: int = 0,
    top_k: int = 10,
    gap_exchange: str | None = "cn",
) -> dict[str, Any]:
    ex = normalize_gap_exchange(gap_exchange)

    if sample_size <= 0:
        return {
            "enabled": False,
            "sample_size_requested": sample_size,
            "gap_exchange": ex,
            "trading_calendar_row_count": 0,
            "note": "sample_size<=0 时跳过抽样缺口统计。",
        }

    distinct_total = int(
        await session.scalar(
            select(func.count(func.distinct(DailyKlineModel.code))).select_from(DailyKlineModel)
        )
        or 0
    )

    codes_stmt = (
        select(DailyKlineModel.code)
        .distinct()
        .order_by(DailyKlineModel.code)
        .offset(max(0, seed_offset))
        .limit(sample_size)
    )
    codes = list((await session.execute(codes_stmt)).scalars().all())
    codes_sampled = len(codes)

    cal_repo = TradeCalendarRepository(session)
    cal_rows = await cal_repo.row_count(ex) if ex else 0
    cal_min, cal_max = (None, None)
    if ex and cal_rows > 0:
        cal_min, cal_max = await cal_repo.min_max_dates(ex)

    if not codes:
        return {
            "enabled": True,
            "sample_size_requested": sample_size,
            "seed_offset": seed_offset,
            "gap_exchange": ex,
            "trading_calendar_row_count": cal_rows,
            "trading_calendar_date_min": str(cal_min) if cal_min else None,
            "trading_calendar_date_max": str(cal_max) if cal_max else None,
            "distinct_codes_in_table": distinct_total,
            "codes_sampled": 0,
            "codes_with_at_least_two_bars": 0,
            "max_interior_gap_calendar_days_in_sample": None,
            "max_missing_trading_sessions_in_sample": None,
            "worst_code_in_sample": None,
            "worst_code_trading_gap_in_sample": None,
            "top_by_max_gap": [],
            "top_by_missing_trading_sessions": [],
            "note": "无日 K 或 offset 超出 distinct code 范围。",
        }

    rows_stmt = (
        select(DailyKlineModel.code, DailyKlineModel.trade_date)
        .where(DailyKlineModel.code.in_(codes))
        .order_by(DailyKlineModel.code, DailyKlineModel.trade_date)
    )
    rows = (await session.execute(rows_stmt)).all()

    per_code: list[dict[str, Any]] = []
    for code, group_iter in groupby(rows, key=lambda r: r[0]):
        dates = [r[1] for r in group_iter]
        gap_cal = max_interior_gap_calendar_days(dates)
        gap_td: int | None = None
        if ex and cal_rows > 0 and len(dates) >= 2:
            d_lo, d_hi = min(dates), max(dates)
            tset = await cal_repo.trading_days_set(ex, d_lo, d_hi)
            gap_td = max_missing_trading_sessions_between_klines(dates, tset)
        per_code.append(
            {
                "code": code,
                "bar_count": len(dates),
                "max_interior_gap_calendar_days": gap_cal,
                "max_missing_trading_sessions_between_klines": gap_td,
            }
        )

    with_gap_cal = [p for p in per_code if p["max_interior_gap_calendar_days"] is not None]
    codes_with_at_least_two = len(with_gap_cal)

    worst_cal: dict[str, Any] | None = None
    if with_gap_cal:
        worst_cal = max(with_gap_cal, key=lambda x: int(x["max_interior_gap_calendar_days"] or 0))

    top_cal = sorted(
        with_gap_cal,
        key=lambda x: int(x["max_interior_gap_calendar_days"] or 0),
        reverse=True,
    )[: max(1, top_k)]

    sample_max_cal = int(worst_cal["max_interior_gap_calendar_days"]) if worst_cal else None

    with_td = [
        p
        for p in per_code
        if p.get("max_missing_trading_sessions_between_klines") is not None
    ]
    worst_td: dict[str, Any] | None = None
    if with_td:
        worst_td = max(with_td, key=lambda x: int(x["max_missing_trading_sessions_between_klines"] or 0))
    top_td = sorted(
        with_td,
        key=lambda x: int(x["max_missing_trading_sessions_between_klines"] or 0),
        reverse=True,
    )[: max(1, top_k)]
    sample_max_td = int(worst_td["max_missing_trading_sessions_between_klines"]) if worst_td else None

    note_parts = [
        "公历缺口：相邻 trade_date 公历间隔天数减 1（未区分是否交易日）。",
    ]
    if ex and cal_rows > 0:
        note_parts.append(
            f"交易日缺口：使用 trade_calendar.exchange={ex!r}，统计相邻日 K 开区间内 is_trading_day 的条数；"
            "停牌、未灌数仍会表现为缺失。"
        )
    elif ex:
        note_parts.append(
            f"已指定 gap_exchange={ex!r} 但 trade_calendar 无行数，未计算交易日缺口；可运行 scripts/fetch_trade_calendar.py。"
        )

    return {
        "enabled": True,
        "sample_size_requested": sample_size,
        "seed_offset": seed_offset,
        "gap_exchange": ex,
        "trading_calendar_row_count": cal_rows,
        "trading_calendar_date_min": str(cal_min) if cal_min else None,
        "trading_calendar_date_max": str(cal_max) if cal_max else None,
        "distinct_codes_in_table": distinct_total,
        "codes_sampled": codes_sampled,
        "codes_with_at_least_two_bars": codes_with_at_least_two,
        "max_interior_gap_calendar_days_in_sample": sample_max_cal,
        "max_missing_trading_sessions_in_sample": sample_max_td,
        "worst_code_in_sample": worst_cal["code"] if worst_cal else None,
        "worst_code_trading_gap_in_sample": worst_td["code"] if worst_td else None,
        "top_by_max_gap": top_cal,
        "top_by_missing_trading_sessions": top_td,
        "note": " ".join(note_parts),
    }
