"""
涨停回调策略单标的执行器：拉 K → stock_info → run_limit_up_pullback_backtest → API 载荷。
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.backtest.limit_up_pullback import run_limit_up_pullback_backtest
from src.data.models import StockType
from src.data.storage import KlineRepository, StockRepository

ENGINE_VERSION = "0.1"
STRATEGY_ID_LIMIT_UP_PULLBACK = "limit_up_pullback"


def _build_assumptions(
    *,
    n_bars: int,
    stock_type: StockType,
    entry_type: str,
    pullback_days: int,
    volume_shrink_ratio: float,
    bench: str | None,
    start_date: date | None,
    end_date: date | None,
    adjust_flag: str,
) -> list[str]:
    adj_label = {"1": "后复权", "2": "前复权", "3": "不复权"}.get(adjust_flag, adjust_flag)
    out = [
        (
            f"涨停回调策略（entry_type={entry_type}, pullback_days={pullback_days}）；"
            "涨停检测后观察回调窗口，按买点/缩量/均线条件触发建仓；"
            "8%硬止损、移动止盈、目标位分批卖出、跌破20日线清仓。"
        ),
        f"标的类型={stock_type.value}，涨停阈值及买点口径据此确定。",
        f"样本内共 {n_bars} 根日 K。",
        f"缩量条件：回调日成交量 <= 涨停日量能的 {volume_shrink_ratio*100:.0f}%。",
        f"价格口径：adjust_flag={adjust_flag}（{adj_label}）（参见 docs/DATA_AND_ADJUSTMENT.md）。",
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


async def execute_limit_up_pullback_single(
    session: AsyncSession,
    *,
    code: str,
    limit: int,
    start_date: date | None,
    end_date: date | None,
    commission_rate: float,
    slippage_rate: float,
    benchmark_code: str | None,
    adjust_flag: str = "3",
    pullback_days: int = 10,
    entry_type: str = "neutral",
    volume_shrink_ratio: float = 0.5,
) -> tuple[dict[str, Any], list[str]]:
    """
    单标的涨停回调回测执行器；失败抛出 ValueError（供 HTTP 400）。
    """
    if commission_rate + slippage_rate > 0.08:
        raise ValueError("commission_rate 与 slippage_rate 之和勿超过 0.08")
    if start_date and end_date and start_date > end_date:
        raise ValueError("start_date 不能晚于 end_date")

    c = code.strip()
    repo = KlineRepository(session)
    klines = await repo.get_daily(
        code=c,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        adjust_flag=adjust_flag,
    )
    if len(klines) < 30:
        raise ValueError(
            f"K 线不足：涨停回调策略至少需要 30 根，当前 {len(klines)}"
        )

    stock_repo = StockRepository(session)
    stock_info = await stock_repo.get_by_code(c)
    stock_type = stock_info.stock_type if stock_info else StockType.COMMON

    bench_norm = (benchmark_code or "").strip().lower() or None
    bench_klines = None
    if bench_norm:
        bench_klines = await repo.get_daily(
            code=bench_norm,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            adjust_flag=adjust_flag,
        )
        if not bench_klines:
            raise ValueError(f"基准 {bench_norm} 无可用日 K")

    result, curve = run_limit_up_pullback_backtest(
        klines,
        stock_type=stock_type,
        pullback_days=pullback_days,
        entry_type=entry_type,
        volume_shrink_ratio=volume_shrink_ratio,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        include_equity_curve=True,
        benchmark_klines=bench_klines,
    )
    body = result.to_api_dict()
    body["equity_curve"] = curve
    body["note"] = (
        f"涨停回调策略（entry_type={entry_type}, pullback_days={pullback_days}）；"
        "涨停后观察回调，按买点±2%、缩量、均线条件触发建仓；"
        "8%硬止损、移动止盈（+10%保本/+15%移+5%/+20%移+15%）、"
        "+10%与+15%各卖1/3、跌破20日线清仓。"
        " fast_period=0/slow_period=0/signal_changes=0 为与双均线响应兼容的占位字段。"
    )
    if commission_rate > 0:
        body["note"] += f" 单边手续费={commission_rate:.6f}。"
    if slippage_rate > 0:
        body["note"] += f" 滑点={slippage_rate:.6f}。"

    assumptions = _build_assumptions(
        n_bars=len(klines),
        stock_type=stock_type,
        entry_type=entry_type,
        pullback_days=pullback_days,
        volume_shrink_ratio=volume_shrink_ratio,
        bench=bench_norm,
        start_date=start_date,
        end_date=end_date,
        adjust_flag=adjust_flag,
    )
    return body, assumptions
