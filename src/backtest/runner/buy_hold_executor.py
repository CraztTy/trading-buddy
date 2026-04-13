"""
买入持有单标的：拉 K → run_buy_hold_backtest → 与 ma_cross 同形 API 载荷。
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.backtest.buy_hold import run_buy_hold_backtest
from src.data.storage import KlineRepository

STRATEGY_ID_BUY_HOLD = "buy_hold"


def _build_assumptions(
    *,
    n_bars: int,
    bench: str | None,
    start_date: date | None,
    end_date: date | None,
) -> list[str]:
    out = [
        "买入持有：自第二根 K 起按收盘到收盘计入策略日收益；首根无收益。",
        "双边一次费率近似：净值序列末尾乘以 (1 − 2×(commission_rate+slippage_rate))。",
        f"样本内共 {n_bars} 根日 K（含区间与 limit 约束后）。",
        "价格口径以入库 daily_kline 为准（参见 docs/DATA_AND_ADJUSTMENT.md）。",
        "fast_period=1、slow_period=2 为占位字段，与双均线无关；详见响应 note。",
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


async def execute_buy_hold_single(
    session: AsyncSession,
    *,
    code: str,
    limit: int,
    start_date: date | None,
    end_date: date | None,
    commission_rate: float,
    slippage_rate: float,
    benchmark_code: str | None,
) -> tuple[dict[str, Any], list[str]]:
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
    if len(klines) < 2:
        raise ValueError(f"K 线不足：买入持有至少需要 2 根，当前 {len(klines)}")

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

    result, curve = run_buy_hold_backtest(
        klines,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        include_equity_curve=True,
        benchmark_klines=bench_klines,
    )
    body = result.to_api_dict()
    body["equity_curve"] = curve
    body["note"] = (
        "strategy=buy_hold：全样本买入持有；fast_period/slow_period 为占位（1/2），非均线周期。"
        " Sharpe/Sortino/年化收益/Calmar/β/α 与 equity 口径同 ma_cross 的 MaCrossBacktestResponse.note 说明。"
    )
    assumptions = _build_assumptions(
        n_bars=len(klines),
        bench=bench_norm,
        start_date=start_date,
        end_date=end_date,
    )
    return body, assumptions


# 供测试断言与 ma_cross 区分版本线时引用（与 ma_cross 共用 ENGINE_VERSION）
__all__ = ["STRATEGY_ID_BUY_HOLD", "execute_buy_hold_single"]
