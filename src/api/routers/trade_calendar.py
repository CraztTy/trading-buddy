"""交易日历库表状态（供运维 / 看板探测是否已灌数）。"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.common import get_settings
from src.data.storage import TradeCalendarRepository, get_session


router = APIRouter()

_EXCHANGE_LABEL_FALLBACK: dict[str, str] = {
    "cn": "cn · A 股",
    "hk": "hk",
    "us": "us",
}


class TradeCalendarExchangeItem(BaseModel):
    value: str = Field(description="trade_calendar.exchange")
    label: str = Field(description="展示用短标签")


class TradeCalendarOptionsResponse(BaseModel):
    """与 ``TRADE_CALENDAR_EXCHANGE_OPTIONS`` 等环境变量对齐，供前端下拉。"""

    exchanges: list[TradeCalendarExchangeItem]
    default_exchange: str


class TradeCalendarStatus(BaseModel):
    """`trade_calendar` 在指定 exchange 下的覆盖概况。"""

    exchange: str = Field(description="分区键，默认 cn")
    row_count: int = Field(description="该 exchange 下行数")
    date_min: date | None = Field(
        default=None, description="最小 calendar_date，无数据时为 null"
    )
    date_max: date | None = Field(
        default=None, description="最大 calendar_date，无数据时为 null"
    )


@router.get("/trade-calendar/options", response_model=TradeCalendarOptionsResponse)
async def get_trade_calendar_options() -> TradeCalendarOptionsResponse:
    tc = get_settings().trade_calendar
    vals = tc.exchange_option_values()
    default_ex = tc.resolved_default_exchange()
    items = [
        TradeCalendarExchangeItem(
            value=v,
            label=_EXCHANGE_LABEL_FALLBACK.get(v, v),
        )
        for v in vals
    ]
    return TradeCalendarOptionsResponse(exchanges=items, default_exchange=default_ex)


@router.get("/trade-calendar/status", response_model=TradeCalendarStatus)
async def get_trade_calendar_status(
    exchange: str = Query("cn", min_length=1, max_length=32),
    session: AsyncSession = Depends(get_session),
) -> TradeCalendarStatus:
    ex = exchange.strip().lower()
    repo = TradeCalendarRepository(session)
    n = await repo.row_count(ex)
    lo, hi = await repo.min_max_dates(ex)
    return TradeCalendarStatus(exchange=ex, row_count=n, date_min=lo, date_max=hi)
