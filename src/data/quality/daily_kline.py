"""
daily_kline 表质量摘要：重复 (code, trade_date)、总行数、全局日期范围、
与 stock_info 不一致的孤立行、仅一条日 K 的代码数等。

用于路线图「阶段 A：关键表数据质量检查」；ORM 模型上已有 UniqueConstraint，
若线上库为历史无约束版本，本报告仍可检出重复行。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.data.storage.models import DailyKlineModel, StockInfoModel


async def daily_kline_quality_report(session: AsyncSession) -> dict[str, Any]:
    total = await session.scalar(select(func.count()).select_from(DailyKlineModel))
    total = int(total or 0)

    dup_stmt = (
        select(DailyKlineModel.code, DailyKlineModel.trade_date, func.count().label("n"))
        .group_by(DailyKlineModel.code, DailyKlineModel.trade_date)
        .having(func.count() > 1)
        .order_by(func.count().desc())
        .limit(100)
    )
    dup_rows = (await session.execute(dup_stmt)).all()
    duplicate_groups = len(dup_rows)
    duplicate_examples: list[dict[str, Any]] = [
        {"code": r[0], "trade_date": str(r[1]), "count": int(r[2])} for r in dup_rows[:20]
    ]

    bounds = await session.execute(
        select(
            func.min(DailyKlineModel.trade_date),
            func.max(DailyKlineModel.trade_date),
        ).select_from(DailyKlineModel)
    )
    b = bounds.one()
    min_d, max_d = b[0], b[1]

    distinct_codes = await session.scalar(
        select(func.count(func.distinct(DailyKlineModel.code))).select_from(DailyKlineModel)
    )
    distinct_codes = int(distinct_codes or 0)

    single_bar_subq = (
        select(DailyKlineModel.code)
        .group_by(DailyKlineModel.code)
        .having(func.count() == 1)
        .subquery()
    )
    codes_with_single_bar = await session.scalar(
        select(func.count()).select_from(single_bar_subq)
    )
    codes_with_single_bar = int(codes_with_single_bar or 0)

    stock_exists = exists(
        select(1).select_from(StockInfoModel).where(StockInfoModel.code == DailyKlineModel.code)
    )
    orphan_kline_rows = await session.scalar(
        select(func.count()).select_from(DailyKlineModel).where(~stock_exists)
    )
    orphan_kline_rows = int(orphan_kline_rows or 0)

    rows_on_max_trade_date: int | None = None
    if max_d is not None:
        rows_on_max_trade_date = int(
            await session.scalar(
                select(func.count()).where(DailyKlineModel.trade_date == max_d)
            )
            or 0
        )

    stock_info_row_count = int(
        await session.scalar(select(func.count()).select_from(StockInfoModel)) or 0
    )
    kline_exists_for_stock = exists(
        select(1)
        .select_from(DailyKlineModel)
        .where(DailyKlineModel.code == StockInfoModel.code)
    )
    stock_info_codes_without_kline = int(
        await session.scalar(
            select(func.count()).select_from(StockInfoModel).where(~kline_exists_for_stock)
        )
        or 0
    )

    invalid_ohlc_rows = int(
        await session.scalar(
            select(func.count())
            .select_from(DailyKlineModel)
            .where(
                or_(
                    DailyKlineModel.high < DailyKlineModel.low,
                    DailyKlineModel.high < DailyKlineModel.open,
                    DailyKlineModel.high < DailyKlineModel.close,
                    DailyKlineModel.low > DailyKlineModel.open,
                    DailyKlineModel.low > DailyKlineModel.close,
                    DailyKlineModel.open <= 0,
                    DailyKlineModel.close <= 0,
                )
            )
        )
        or 0
    )

    negative_volume_rows = int(
        await session.scalar(
            select(func.count())
            .select_from(DailyKlineModel)
            .where(
                and_(
                    DailyKlineModel.volume.is_not(None),
                    DailyKlineModel.volume < 0,
                )
            )
        )
        or 0
    )

    return {
        "table": "daily_kline",
        "row_count": total,
        "distinct_codes": distinct_codes,
        "trade_date_min": str(min_d) if min_d is not None else None,
        "trade_date_max": str(max_d) if max_d is not None else None,
        "rows_on_max_trade_date": rows_on_max_trade_date,
        "codes_with_single_bar": codes_with_single_bar,
        "orphan_kline_rows": orphan_kline_rows,
        "duplicate_code_date_groups": duplicate_groups,
        "duplicate_examples": duplicate_examples,
        "stock_info_row_count": stock_info_row_count,
        "stock_info_codes_without_kline": stock_info_codes_without_kline,
        "invalid_ohlc_rows": invalid_ohlc_rows,
        "negative_volume_rows": negative_volume_rows,
        "note": (
            "duplicate_code_date_groups>0：违反 (code, trade_date) 唯一性；"
            "invalid_ohlc_rows>0：high/low 与 OHLC 常识不一致或价格≤0（脏数据）；"
            "negative_volume_rows>0：volume 非空且为负；"
            "orphan_kline_rows>0：日 K 的 code 在 stock_info 中不存在（拉数顺序或退市清理问题）；"
            "codes_with_single_bar：仅一条日 K 的标的数（可能是灌数不完整）；"
            "stock_info_codes_without_kline：stock_info 中尚无任何日 K 的标的数（灌数缺口）。"
        ),
    }
