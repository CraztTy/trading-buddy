"""
stock_info 表质量摘要：行数、名称为空的行数、上市状态中缺 list_date 等。

与 daily_kline 报告配合用于路线图「阶段 A：关键表数据质量检查」。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.data.storage.models import StockInfoModel


async def stock_info_quality_report(session: AsyncSession) -> dict[str, Any]:
    total = int(await session.scalar(select(func.count()).select_from(StockInfoModel)) or 0)

    empty_name_rows = int(
        await session.scalar(
            select(func.count())
            .select_from(StockInfoModel)
            .where(
                or_(
                    StockInfoModel.name.is_(None),
                    func.trim(StockInfoModel.name) == "",
                )
            )
        )
        or 0
    )

    trading_no_list_date = int(
        await session.scalar(
            select(func.count())
            .select_from(StockInfoModel)
            .where(
                StockInfoModel.is_trading.is_(True),
                StockInfoModel.list_date.is_(None),
            )
        )
        or 0
    )

    return {
        "table": "stock_info",
        "row_count": total,
        "empty_name_rows": empty_name_rows,
        "is_trading_rows_missing_list_date": trading_no_list_date,
        "note": (
            "empty_name_rows>0：code 存在但 name 为空，展示层会回退为 code；"
            "is_trading_rows_missing_list_date：仍交易中但缺 list_date，多为数据源缺口，非硬错误。"
        ),
    }
