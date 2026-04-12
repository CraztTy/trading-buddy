"""
双均线单标的：拉 K → run_ma_cross_backtest → API 载荷 + 假设说明。
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.backtest import run_ma_cross_backtest
from src.data.storage import KlineRepository


ENGINE_VERSION = "0.1"
STRATEGY_ID_MA_CROSS = "ma_cross"


def _build_assumptions(
    *,
    n_bars: int,
    bench: str | None,
    start_date: date | None,
    end_date: date | None,
) -> list[str]:
    out = [
        "双均线（日线收盘）；多空信号滞后一日计入收益，与 GET /api/backtest/ma-cross 口径一致。",
        f"样本内共 {n_bars} 根日 K（含区间与 limit 约束后）。",
        "价格口径以入库 daily_kline 为准（参见 docs/DATA_AND_ADJUSTMENT.md）。",
    ]
    if bench:
        out.append(f"β/α 相对基准 {bench} 的日收益序列（标的交易日对齐、仅前向填充）。")
    else:
        out.append("β/α 为对标的自身日收益的回归。")
    if start_date or end_date:
        out.append(
            f"日期约束：start_date={start_date or '∅'}，end_date={end_date or '∅'}（含端点）。"
        )
    return out


async def execute_ma_cross_single(
    session: AsyncSession,
    *,
    code: str,
    fast: int,
    slow: int,
    limit: int,
    start_date: date | None,
    end_date: date | None,
    commission_rate: float,
    slippage_rate: float,
    benchmark_code: str | None,
) -> tuple[dict[str, Any], list[str]]:
    """
    校验与数据拉取均在此完成；失败抛出 ValueError（消息供 HTTP 400）。

    Returns:
        (api_payload, assumptions)：api_payload 可直接用于构造 MaCrossBacktestResponse（含 equity_curve）。
    """
    if fast >= slow:
        raise ValueError("fast 必须小于 slow")
    if commission_rate + slippage_rate > 0.08:
        raise ValueError("commission_rate 与 slippage_rate 之和勿超过 0.08")
    if start_date and end_date and start_date > end_date:
        raise ValueError("start_date 不能晚于 end_date")

    repo = KlineRepository(session)
    c = code.strip()
    klines = await repo.get_daily(
        code=c,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
    if len(klines) < slow + 1:
        raise ValueError(
            f"K 线不足：需要至少 slow+1={slow + 1} 根，当前 {len(klines)}",
        )

    bench_norm = (benchmark_code or "").strip().lower() or None
    bench_klines = None
    if bench_norm:
        bench_klines = await repo.get_daily(
            code=bench_norm,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
        if not bench_klines:
            raise ValueError(f"基准 {bench_norm} 无可用日 K")

    result, curve = run_ma_cross_backtest(
        klines,
        fast=fast,
        slow=slow,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        include_equity_curve=True,
        benchmark_klines=bench_klines,
    )
    body = result.to_api_dict()
    body["equity_curve"] = curve
    assumptions = _build_assumptions(
        n_bars=len(klines),
        bench=bench_norm,
        start_date=start_date,
        end_date=end_date,
    )
    return body, assumptions
