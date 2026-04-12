"""
双均线信号：从会话拉 K 线并调用核心 `ma_cross_last_signal`。
供 `/api/backtest/ma-cross/signal` 与 `/api/strategies/signal` 共用。
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from src.backtest import ma_cross_last_signal
from src.data.storage import KlineRepository


async def compute_ma_cross_signal(
    session: AsyncSession,
    *,
    code: str,
    fast: int,
    slow: int,
    start_date: date | None,
    end_date: date | None,
    limit: int,
) -> dict:
    """
    返回可映射到 MaCrossSignalResponse 的 dict。
    校验失败抛出 ValueError（与路由层转为 HTTP 400）。
    """
    if fast >= slow:
        raise ValueError("fast 必须小于 slow")
    if start_date and end_date and start_date > end_date:
        raise ValueError("start_date 不能晚于 end_date")
    if limit < slow:
        raise ValueError("limit 不能小于 slow")

    repo = KlineRepository(session)
    klines = await repo.get_daily(
        code=code.strip(),
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
    if len(klines) < slow:
        raise ValueError(
            f"K 线不足：需要至少 slow={slow} 根，当前 {len(klines)}",
        )
    return ma_cross_last_signal(klines, fast=fast, slow=slow)
