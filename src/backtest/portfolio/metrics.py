"""Portfolio metrics computation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np

from src.common import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class PortfolioMetrics:
    """Portfolio-level computed metrics."""

    total_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    annualized_return_pct: float = 0.0
    annualized_volatility_pct: float = 0.0
    turnover_pct: float = 0.0  # average turnover per rebalance
    benchmark_beta: float = 0.0
    benchmark_alpha_ann_pct: float = 0.0

    def to_dict(self) -> dict:
        return {
            "total_return_pct": round(self.total_return_pct, 4),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "sharpe_ratio": round(self.sharpe_ratio, 4),
            "sortino_ratio": round(self.sortino_ratio, 4),
            "calmar_ratio": round(self.calmar_ratio, 4),
            "annualized_return_pct": round(self.annualized_return_pct, 4),
            "annualized_volatility_pct": round(self.annualized_volatility_pct, 4),
            "turnover_pct": round(self.turnover_pct, 4),
            "benchmark_beta": round(self.benchmark_beta, 4),
            "benchmark_alpha_ann_pct": round(self.benchmark_alpha_ann_pct, 4),
        }


def compute_portfolio_metrics(
    equity_curve: list[float],
    dates: list[date],
    trades: list[dict],
    benchmark_returns: list[float] | None = None,
) -> PortfolioMetrics:
    """Compute portfolio-level risk-adjusted metrics.

    Args:
        equity_curve: List of equity values (starting at 1.0).
        dates: Corresponding trade dates.
        trades: List of rebalance trades for turnover calculation.
        benchmark_returns: Optional daily benchmark returns aligned with equity_curve.

    Returns:
        PortfolioMetrics dataclass with all computed values.
    """
    if not equity_curve or len(equity_curve) < 2:
        return PortfolioMetrics()

    eq_arr = np.array(equity_curve, dtype=float)
    n = len(eq_arr)

    # Total return
    total_return_pct = float((eq_arr[-1] / eq_arr[0] - 1.0) * 100.0)

    # Daily returns from equity curve
    daily_ret = np.diff(eq_arr) / eq_arr[:-1]

    # Max drawdown
    peak = np.maximum.accumulate(eq_arr)
    dd_series = (eq_arr / peak) - 1.0
    max_drawdown_pct = float(dd_series.min() * 100.0)

    # Sharpe and volatility (annualized, 252 trading days)
    if len(daily_ret) > 1 and float(daily_ret.std()) > 1e-12:
        sharpe_ratio = float(np.sqrt(252.0) * daily_ret.mean() / daily_ret.std())
        annualized_volatility_pct = float(daily_ret.std() * np.sqrt(252.0) * 100.0)
    else:
        sharpe_ratio = 0.0
        annualized_volatility_pct = 0.0

    # Annualized return (compound)
    n_periods = max(1, len(daily_ret))
    tr_dec = total_return_pct / 100.0
    annualized_return_pct = float(
        ((1.0 + tr_dec) ** (252.0 / n_periods) - 1.0) * 100.0
    )

    # Sortino ratio (MAR = 0)
    mar = 0.0
    downside_sq = np.minimum(0.0, daily_ret - mar) ** 2
    downside_dev = float(np.sqrt(np.mean(downside_sq))) if len(daily_ret) > 0 else 0.0
    if len(daily_ret) > 1 and downside_dev > 1e-12:
        sortino_ratio = float(np.sqrt(252.0) * float(daily_ret.mean()) / downside_dev)
    else:
        sortino_ratio = 0.0

    # Calmar ratio
    dd_abs = abs(max_drawdown_pct) / 100.0
    if dd_abs > 1e-8:
        calmar_ratio = float((annualized_return_pct / 100.0) / dd_abs)
    else:
        calmar_ratio = 0.0

    # Turnover: average turnover per rebalance
    # Turnover = sum(|delta_weight|) / 2 for each rebalance, averaged
    turnover_pct = _compute_average_turnover(trades)

    # Benchmark beta / alpha
    benchmark_beta = 0.0
    benchmark_alpha_ann_pct = 0.0
    if benchmark_returns is not None and len(benchmark_returns) == len(daily_ret) and len(daily_ret) > 1:
        b_arr = np.array(benchmark_returns, dtype=float)
        vm = float(np.var(b_arr))
        if vm > 1e-18:
            cov_pb = float(np.cov(daily_ret, b_arr, bias=True)[0, 1])
            benchmark_beta = float(cov_pb / vm)
        alpha_daily = float(np.mean(daily_ret) - benchmark_beta * float(np.mean(b_arr)))
        benchmark_alpha_ann_pct = float(alpha_daily * 252.0 * 100.0)

    return PortfolioMetrics(
        total_return_pct=total_return_pct,
        max_drawdown_pct=max_drawdown_pct,
        sharpe_ratio=sharpe_ratio,
        sortino_ratio=sortino_ratio,
        calmar_ratio=calmar_ratio,
        annualized_return_pct=annualized_return_pct,
        annualized_volatility_pct=annualized_volatility_pct,
        turnover_pct=turnover_pct,
        benchmark_beta=benchmark_beta,
        benchmark_alpha_ann_pct=benchmark_alpha_ann_pct,
    )


def _compute_average_turnover(trades: list[dict]) -> float:
    """Compute average turnover per rebalance from trade records.

    Turnover for a single rebalance = sum(|weight_change|) / 2.
    Averaged across all rebalance events.
    """
    if not trades:
        return 0.0

    # Group trades by rebalance date
    from collections import defaultdict

    by_date: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        td = t.get("trade_date")
        if td is not None:
            by_date[str(td)].append(t)

    if not by_date:
        return 0.0

    turnovers: list[float] = []
    for _td_str, day_trades in by_date.items():
        # Sum of absolute weight changes for this rebalance
        total_delta = sum(abs(t.get("weight_change", 0.0)) for t in day_trades)
        # Turnover = half the sum (one side only)
        turnovers.append(total_delta / 2.0)

    return float(np.mean(turnovers)) * 100.0  # as percentage
