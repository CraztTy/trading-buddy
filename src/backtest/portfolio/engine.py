"""Core portfolio backtest engine.

Supports multi-asset portfolios with configurable weight schemes and rebalance frequencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np

from src.common import get_logger
from src.data.models import KLine

from .metrics import PortfolioMetrics, compute_portfolio_metrics
from .rebalance import is_rebalance_day
from .weights import compute_weights
from ..position_sizing import SizingConfig, compute_position_sizes

logger = get_logger(__name__)


@dataclass(frozen=True)
class PortfolioBacktestResult:
    """Portfolio backtest result."""

    equity_curve: list[dict]  # [{trade_date, equity, cash, positions_value}]
    positions_history: list[dict]  # [{trade_date, code, weight, quantity, market_value}]
    trades: list[dict]  # rebalance trades
    total_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    annualized_return_pct: float
    annualized_volatility_pct: float
    turnover_pct: float  # average turnover per rebalance
    metrics_by_code: dict[str, dict]  # per-code contribution
    calmar_ratio: float = 0.0
    benchmark_beta: float = 0.0
    benchmark_alpha_ann_pct: float = 0.0
    codes: list[str] = field(default_factory=list)
    rebalance_freq: str = "monthly"
    weights_scheme: str = "equal"
    initial_cash: float = 1_000_000.0
    commission_rate: float = 0.0
    slippage_rate: float = 0.0
    bars_used: int = 0
    first_trade_date: date | None = None
    last_trade_date: date | None = None
    position_sizing_method: str = "equal"
    position_sizing_params: dict = field(default_factory=dict)

    def to_api_dict(self, equity_sample_max: int = 120) -> dict[str, Any]:
        """Serialize to API-compatible dict following existing result patterns."""
        note = (
            "Portfolio backtest: multi-asset with rebalancing. "
            f"weights_scheme={self.weights_scheme}, rebalance_freq={self.rebalance_freq}. "
            "Sharpe / Sortino 按 252 交易日年化；Sortino 的 MAR=0、下行偏差为 min(0,r) 的二阶矩均方根。 "
            "年化收益为区间复利换算：(1+总收益)^(252/区间交易日)-1。 "
            "Calmar=年化收益/|最大回撤|（回撤为负百分比时取绝对值）。 "
            "Turnover=每次再平衡的平均换手率（sum(|delta_weight|)/2）。"
        )
        if self.commission_rate > 0:
            note += f" 单边手续费={self.commission_rate:.6f}。"
        if self.slippage_rate > 0:
            note += f" 滑点={self.slippage_rate:.6f}。"

        # Sample equity curve if too many points
        curve = self.equity_curve
        if len(curve) > equity_sample_max:
            n = len(curve)
            idx = sorted(
                set([0] + [int(round(i)) for i in np.linspace(0, n - 1, equity_sample_max)])
            )
            curve = [curve[i] for i in idx]

        return {
            "codes": self.codes,
            "weights_scheme": self.weights_scheme,
            "rebalance_freq": self.rebalance_freq,
            "bars_used": self.bars_used,
            "initial_cash": round(self.initial_cash, 2),
            "commission_rate": round(self.commission_rate, 8),
            "slippage_rate": round(self.slippage_rate, 8),
            "first_trade_date": self.first_trade_date.isoformat() if self.first_trade_date else None,
            "last_trade_date": self.last_trade_date.isoformat() if self.last_trade_date else None,
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
            "metrics_by_code": {
                k: {kk: round(vv, 4) if isinstance(vv, float) else vv for kk, vv in v.items()}
                for k, v in self.metrics_by_code.items()
            },
            "equity_curve": curve,
            "positions_history": self.positions_history,
            "trades": self.trades,
            "note": note,
        }


def run_portfolio_backtest(
    klines_dict: dict[str, list[KLine]],
    *,
    signals_dict: dict[str, list[float]],  # code -> daily position (0 or 1 or continuous)
    weights_scheme: str = "equal",  # "equal" | "value"
    rebalance_freq: str = "monthly",  # "daily" | "weekly" | "monthly"
    initial_cash: float = 1_000_000.0,
    commission_rate: float = 0.0,
    slippage_rate: float = 0.0,
    trade_calendar: list[date] | None = None,
    benchmark_klines: list[KLine] | None = None,
    position_sizing_config: SizingConfig | None = None,
) -> PortfolioBacktestResult:
    """Run a portfolio-level backtest across multiple assets.

    Algorithm:
    1. Align all klines to common trade dates (intersection of dates across all codes).
    2. For each trade date:
       - Check if rebalance day (based on freq)
       - On rebalance: compute target weights, calculate target positions in shares,
         execute trades with commission+slippage
       - Update equity curve with daily price movements
    3. Compute portfolio-level metrics

    Args:
        klines_dict: Mapping from code to list of KLine objects.
        signals_dict: Mapping from code to daily position signal (0=flat, 1=full long,
            or continuous values for partial positions).
        weights_scheme: "equal" or "value" weighting.
        rebalance_freq: "daily", "weekly", or "monthly".
        initial_cash: Starting portfolio cash.
        commission_rate: Per-trade commission rate (e.g. 0.001 = 0.1%).
        slippage_rate: Per-trade slippage rate.
        trade_calendar: Optional explicit trade calendar. If None, derived from klines.
        benchmark_klines: Optional benchmark KLines for beta/alpha calculation.

        position_sizing_config: Optional position sizing config. If None,
            uses equal weight sizing (backward compatible).

    Returns:
        PortfolioBacktestResult with full history and metrics.

    Raises:
        ValueError: On invalid inputs.
    """
    # ---- Validation ----
    if not klines_dict:
        raise ValueError("klines_dict is empty")
    if not signals_dict:
        raise ValueError("signals_dict is empty")
    if commission_rate < 0 or commission_rate > 0.05:
        raise ValueError("commission_rate must be in [0, 0.05]")
    if slippage_rate < 0 or slippage_rate > 0.05:
        raise ValueError("slippage_rate must be in [0, 0.05]")
    if commission_rate + slippage_rate > 0.08:
        raise ValueError("commission_rate 与 slippage_rate 之和勿超过 0.08")
    if initial_cash <= 0:
        raise ValueError("initial_cash must be positive")

    codes = sorted(klines_dict.keys())

    # ---- Align dates ----
    # Build date -> {code: KLine} mapping using intersection of all codes' dates
    date_code_kline: dict[date, dict[str, KLine]] = {}
    for code in codes:
        klines = klines_dict[code]
        if not klines:
            raise ValueError(f"No klines for code {code}")
        for k in klines:
            td = k.trade_date
            if isinstance(td, str):
                td = date.fromisoformat(td)
            if td not in date_code_kline:
                date_code_kline[td] = {}
            date_code_kline[td][code] = k

    # Use trade_calendar if provided, else intersection of dates where ALL codes have data
    if trade_calendar:
        common_dates = sorted(
            d for d in trade_calendar
            if d in date_code_kline and len(date_code_kline[d]) == len(codes)
        )
    else:
        common_dates = sorted(
            d for d, ck in date_code_kline.items()
            if len(ck) == len(codes)
        )

    if len(common_dates) < 2:
        raise ValueError(
            f"Insufficient common trading dates: {len(common_dates)} (need >= 2)"
        )

    # Build aligned close prices and signals
    aligned_closes: dict[str, list[float]] = {c: [] for c in codes}
    aligned_signals: dict[str, list[float]] = {c: [] for c in codes}

    # Build date -> signal mapping for each code
    code_date_signal: dict[str, dict[date, float]] = {}
    for code in codes:
        sig_map: dict[date, float] = {}
        sig_list = signals_dict.get(code, [])
        klines = klines_dict[code]
        for s, kl in zip(sig_list, klines):
            kl_td = kl.trade_date
            if isinstance(kl_td, str):
                kl_td = date.fromisoformat(kl_td)
            sig_map[kl_td] = float(s)
        code_date_signal[code] = sig_map

    for td in common_dates:
        for code in codes:
            k = date_code_kline[td][code]
            aligned_closes[code].append(float(k.close))
            aligned_signals[code].append(code_date_signal[code].get(td, 1.0))

    n_dates = len(common_dates)

    # ---- Benchmark returns ----
    benchmark_returns: list[float] | None = None
    if benchmark_klines:
        bench_by_date: dict[date, float] = {}
        for k in benchmark_klines:
            td = k.trade_date
            if isinstance(td, str):
                td = date.fromisoformat(td)
            bench_by_date[td] = float(k.close)
        bench_rets = []
        prev_close = None
        for td in common_dates:
            close = bench_by_date.get(td)
            if close is not None and prev_close is not None and prev_close > 0:
                bench_rets.append((close - prev_close) / prev_close)
            else:
                bench_rets.append(0.0)
            if close is not None:
                prev_close = close
        benchmark_returns = bench_rets

    # ---- Simulation state ----
    cash = float(initial_cash)
    positions: dict[str, float] = {c: 0.0 for c in codes}  # quantity held
    equity_curve: list[dict] = []
    positions_history: list[dict] = []
    trades: list[dict] = []

    # Track per-code equity contribution
    code_contrib_start: dict[str, float] = {c: 0.0 for c in codes}
    code_contrib_end: dict[str, float] = {c: 0.0 for c in codes}

    prev_trade_date: date | None = None
    prev_weights: dict[str, float] = {c: 0.0 for c in codes}
    first_rebalance_done = False

    for i, td in enumerate(common_dates):
        # --- Compute current portfolio value at today's close ---
        current_prices = {c: aligned_closes[c][i] for c in codes}
        portfolio_value = cash + sum(
            positions[c] * current_prices[c] for c in codes
        )

        # --- Check rebalance ---
        do_rebalance = is_rebalance_day(td, prev_trade_date, rebalance_freq)

        if do_rebalance:
            # On first rebalance, optionally use position sizing config
            if not first_rebalance_done and position_sizing_config is not None:
                # Build signals dict for current date
                current_signals = {c: aligned_signals[c][i] for c in codes}
                sized_shares = compute_position_sizes(
                    codes,
                    klines_dict,
                    current_signals,
                    portfolio_value,
                    position_sizing_config,
                )
                # Set target quantities directly from sizing
                for code in codes:
                    target_qty = float(sized_shares.get(code, 0))
                    current_qty = positions[code]
                    delta_qty = target_qty - current_qty

                    if abs(delta_qty) > 1e-9:
                        trade_value = abs(delta_qty) * current_prices[code]
                        fee = trade_value * (commission_rate + slippage_rate)
                        cash -= fee

                        if delta_qty > 0:
                            cost = delta_qty * current_prices[code]
                            cash -= cost
                        else:
                            proceeds = abs(delta_qty) * current_prices[code]
                            cash += proceeds

                        positions[code] = target_qty
                        target_weight = (
                            target_qty * current_prices[code] / portfolio_value
                            if portfolio_value > 0 else 0.0
                        )
                        prev_weight = prev_weights.get(code, 0.0)
                        weight_change = target_weight - prev_weight

                        trades.append({
                            "trade_date": td.isoformat(),
                            "code": code,
                            "direction": "buy" if delta_qty > 0 else "sell",
                            "quantity": round(abs(delta_qty), 6),
                            "price": round(current_prices[code], 4),
                            "value": round(trade_value, 2),
                            "fee": round(fee, 2),
                            "prev_weight": round(prev_weight, 6),
                            "target_weight": round(target_weight, 6),
                            "weight_change": round(abs(weight_change), 6),
                        })
                        prev_weights[code] = target_weight

                first_rebalance_done = True
                # Recompute portfolio value after trades
                portfolio_value = cash + sum(
                    positions[c] * current_prices[c] for c in codes
                )
            else:
                # Standard weight-based rebalance (existing behavior)
                # Compute target weights
                target_weights = compute_weights(codes, weights_scheme, klines_dict, td)

                # Apply signal scaling to weights
                # If a code has signal=0, its weight becomes 0
                # If signal is continuous (e.g. 0.5), weight is scaled
                active_codes = []
                scaled_weights: dict[str, float] = {}
                for code in codes:
                    sig = aligned_signals[code][i]
                    if sig > 0 and code in target_weights:
                        scaled_weights[code] = target_weights[code] * sig
                        active_codes.append(code)

                # Renormalize weights to sum to 1.0
                total_w = sum(scaled_weights.values())
                if total_w > 1e-12:
                    scaled_weights = {c: w / total_w for c, w in scaled_weights.items()}

                # Execute trades to reach target weights
                for code in codes:
                    target_weight = scaled_weights.get(code, 0.0)
                    prev_weight = prev_weights.get(code, 0.0)
                    target_value = portfolio_value * target_weight
                    target_qty = target_value / current_prices[code] if current_prices[code] > 0 else 0.0
                    current_qty = positions[code]
                    delta_qty = target_qty - current_qty

                    if abs(delta_qty) > 1e-9:
                        trade_value = abs(delta_qty) * current_prices[code]
                        fee = trade_value * (commission_rate + slippage_rate)
                        cash -= fee

                        if delta_qty > 0:
                            # Buy
                            cost = delta_qty * current_prices[code]
                            cash -= cost
                        else:
                            # Sell
                            proceeds = abs(delta_qty) * current_prices[code]
                            cash += proceeds

                        positions[code] = target_qty
                        weight_change = target_weight - prev_weight

                        trades.append({
                            "trade_date": td.isoformat(),
                            "code": code,
                            "direction": "buy" if delta_qty > 0 else "sell",
                            "quantity": round(abs(delta_qty), 6),
                            "price": round(current_prices[code], 4),
                            "value": round(trade_value, 2),
                            "fee": round(fee, 2),
                            "prev_weight": round(prev_weight, 6),
                            "target_weight": round(target_weight, 6),
                            "weight_change": round(abs(weight_change), 6),
                        })

                prev_weights = {c: scaled_weights.get(c, 0.0) for c in codes}
                first_rebalance_done = True
                # Recompute portfolio value after trades
                portfolio_value = cash + sum(
                    positions[c] * current_prices[c] for c in codes
                )

        # --- Record equity curve ---
        equity_curve.append({
            "trade_date": td.isoformat(),
            "equity": round(portfolio_value, 2),
            "cash": round(cash, 2),
            "positions_value": round(portfolio_value - cash, 2),
        })

        # --- Record positions ---
        total_val = portfolio_value if portfolio_value > 0 else 1.0
        for code in codes:
            mv = positions[code] * aligned_closes[code][i]
            positions_history.append({
                "trade_date": td.isoformat(),
                "code": code,
                "weight": round(mv / total_val, 6) if total_val > 0 else 0.0,
                "quantity": round(positions[code], 6),
                "market_value": round(mv, 2),
            })

        # Track per-code contribution
        if i == 0:
            for code in codes:
                code_contrib_start[code] = positions[code] * aligned_closes[code][i]
        if i == n_dates - 1:
            for code in codes:
                code_contrib_end[code] = positions[code] * aligned_closes[code][i]

        prev_trade_date = td

    # ---- Compute metrics ----
    equity_values = [e["equity"] for e in equity_curve]
    # Normalize to start at 1.0 for metric computation
    if equity_values[0] > 0:
        normalized_equity = [v / equity_values[0] for v in equity_values]
    else:
        normalized_equity = equity_values

    metrics = compute_portfolio_metrics(
        normalized_equity,
        common_dates,
        trades,
        benchmark_returns,
    )

    # Per-code contribution metrics
    metrics_by_code: dict[str, dict] = {}
    total_start = sum(code_contrib_start.values())
    total_end = sum(code_contrib_end.values())
    for code in codes:
        start_val = code_contrib_start[code]
        end_val = code_contrib_end[code]
        if start_val > 1e-9:
            code_return_pct = (end_val / start_val - 1.0) * 100.0
        else:
            code_return_pct = 0.0
        start_weight = start_val / total_start if total_start > 0 else 0.0
        end_weight = end_val / total_end if total_end > 0 else 0.0
        metrics_by_code[code] = {
            "start_value": round(start_val, 2),
            "end_value": round(end_val, 2),
            "return_pct": round(code_return_pct, 4),
            "start_weight": round(start_weight, 6),
            "end_weight": round(end_weight, 6),
        }

    return PortfolioBacktestResult(
        equity_curve=equity_curve,
        positions_history=positions_history,
        trades=trades,
        total_return_pct=metrics.total_return_pct,
        max_drawdown_pct=metrics.max_drawdown_pct,
        sharpe_ratio=metrics.sharpe_ratio,
        sortino_ratio=metrics.sortino_ratio,
        annualized_return_pct=metrics.annualized_return_pct,
        annualized_volatility_pct=metrics.annualized_volatility_pct,
        turnover_pct=metrics.turnover_pct,
        metrics_by_code=metrics_by_code,
        calmar_ratio=metrics.calmar_ratio,
        benchmark_beta=metrics.benchmark_beta,
        benchmark_alpha_ann_pct=metrics.benchmark_alpha_ann_pct,
        codes=codes,
        rebalance_freq=rebalance_freq,
        weights_scheme=weights_scheme,
        initial_cash=initial_cash,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        bars_used=n_dates,
        first_trade_date=common_dates[0],
        last_trade_date=common_dates[-1],
        position_sizing_method=position_sizing_config.method if position_sizing_config else "equal",
        position_sizing_params=position_sizing_config.params if position_sizing_config else {},
    )
