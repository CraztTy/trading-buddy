"""
买入持有（全样本做多）：日收益 = 标的收盘到收盘；首根无收益；双边一次费率近似。

响应体与 ``MaCrossBacktestResponse`` 对齐（``fast_period``/``slow_period`` 占位 1/2，见 ``note``）。
"""

from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from src.backtest.ma_cross import (
    MaCrossBacktestResult,
    benchmark_close_on_primary_dates,
    _equity_weighted_win_rate_pct,
    _long_hold_segments_start_and_return_pct,
)
from src.data.models import KLine


def run_buy_hold_backtest(
    klines: list[KLine],
    *,
    commission_rate: float = 0.0,
    slippage_rate: float = 0.0,
    include_equity_curve: bool = True,
    benchmark_klines: list[KLine] | None = None,
) -> tuple[MaCrossBacktestResult, list[dict[str, Any]]]:
    """
    从 KLine 列表跑买入持有；与 ``run_ma_cross_backtest`` 相同返回形状，便于 ``POST /api/backtest/run``。
    """
    if not klines:
        raise ValueError("klines 为空")
    if len(klines) < 2:
        raise ValueError("K 线不足：买入持有至少需要 2 根日 K")
    if commission_rate < 0 or commission_rate > 0.05:
        raise ValueError("commission_rate 须在 [0, 0.05] 内")
    if slippage_rate < 0 or slippage_rate > 0.05:
        raise ValueError("slippage_rate 须在 [0, 0.05] 内")
    if commission_rate + slippage_rate > 0.08:
        raise ValueError("commission_rate 与 slippage_rate 之和勿超过 0.08")

    code = klines[0].code
    df = pd.DataFrame(
        {
            "trade_date": [k.trade_date for k in klines],
            "close": [float(k.close) for k in klines],
        }
    )
    d = df.sort_values("trade_date").reset_index(drop=True)
    bench_c: str | None = None
    bench_close_aligned: pd.Series | None = None
    if benchmark_klines is not None:
        bench_close_aligned = benchmark_close_on_primary_dates(d, benchmark_klines)
        bench_c = str(benchmark_klines[0].code).strip().lower()

    close = d["close"].astype(float)
    daily_ret = close.pct_change().fillna(0.0)
    # 首根无持仓收益；自第二根起满仓日收益（与「收盘入场」直觉一致）
    hold = pd.Series([0.0] + [1.0] * (len(d) - 1), index=d.index, dtype=float)
    flip_cost = float(commission_rate) + float(slippage_rate)
    strat_ret = hold * daily_ret
    strat_ret = strat_ret.fillna(0.0)

    equity_gross = (1.0 + strat_ret).cumprod()
    fee_tail = max(0.0, 1.0 - 2.0 * flip_cost)
    equity = equity_gross * fee_tail

    total_return_pct = float((equity.iloc[-1] - 1.0) * 100.0)
    buy_hold_return_pct = float((close.iloc[-1] / close.iloc[0] - 1.0) * 100.0)
    excess_return_pct = float(total_return_pct - buy_hold_return_pct)

    peak = equity.cummax()
    dd_pct = float(((equity / peak) - 1.0).min() * 100.0)

    active = strat_ret.iloc[1:]
    if len(active) > 1 and float(active.std()) > 1e-12:
        sharpe = float(np.sqrt(252.0) * active.mean() / active.std())
        annualized_volatility_pct = float(active.std() * np.sqrt(252.0) * 100.0)
    else:
        sharpe = 0.0
        annualized_volatility_pct = 0.0

    n_periods = max(1, len(d) - 1)
    tr_dec = total_return_pct / 100.0
    annualized_return_pct = float(((1.0 + tr_dec) ** (252.0 / n_periods) - 1.0) * 100.0)
    bh_dec = buy_hold_return_pct / 100.0
    buy_hold_annualized_return_pct = float(((1.0 + bh_dec) ** (252.0 / n_periods) - 1.0) * 100.0)

    mar = 0.0
    downside_sq = np.minimum(0.0, (active - mar).to_numpy(dtype=float)) ** 2
    downside_dev = float(np.sqrt(np.mean(downside_sq))) if len(active) > 0 else 0.0
    if len(active) > 1 and downside_dev > 1e-12:
        sortino_ratio = float(np.sqrt(252.0) * float(active.mean()) / downside_dev)
    else:
        sortino_ratio = 0.0

    dd_abs = abs(dd_pct) / 100.0
    if dd_abs > 1e-8:
        calmar_ratio = float((annualized_return_pct / 100.0) / dd_abs)
    else:
        calmar_ratio = 0.0

    if bench_close_aligned is not None:
        mkt_line = bench_close_aligned.astype(float).pct_change().fillna(0.0)
    else:
        mkt_line = daily_ret
    mkt_active = mkt_line.iloc[1:].astype(float)
    if len(mkt_active) == len(active) and len(active) > 1:
        m = mkt_active.to_numpy(dtype=float)
        s_arr = active.to_numpy(dtype=float)
        vm = float(np.var(m))
        if vm > 1e-18:
            cov_sm = float(np.cov(s_arr, m, bias=True)[0, 1])
            underlying_beta = float(cov_sm / vm)
        else:
            underlying_beta = 0.0
        alpha_daily = float(np.mean(s_arr) - underlying_beta * float(np.mean(m)))
        underlying_alpha_ann_pct = float(alpha_daily * 252.0 * 100.0)
    else:
        underlying_beta = 0.0
        underlying_alpha_ann_pct = 0.0

    seg_list = _long_hold_segments_start_and_return_pct(hold, strat_ret)
    long_trades_count = len(seg_list)
    if long_trades_count > 0:
        seg_returns_pct = [rp for _, rp in seg_list]
        win_rate_pct = _equity_weighted_win_rate_pct(seg_list, equity)
        avg_holding_return_pct = float(np.mean(seg_returns_pct))
    else:
        win_rate_pct = 0.0
        avg_holding_return_pct = 0.0

    signal_changes = 0

    td = d["trade_date"]
    first_d = pd.Timestamp(td.iloc[0]).date()
    last_d = pd.Timestamp(td.iloc[-1]).date()

    res = MaCrossBacktestResult(
        code=code,
        fast_period=1,
        slow_period=2,
        bars_used=len(d),
        first_trade_date=first_d,
        last_trade_date=last_d,
        total_return_pct=total_return_pct,
        buy_hold_return_pct=buy_hold_return_pct,
        excess_return_pct=excess_return_pct,
        max_drawdown_pct=dd_pct,
        sharpe_ratio=sharpe,
        signal_changes=signal_changes,
        annualized_return_pct=annualized_return_pct,
        buy_hold_annualized_return_pct=buy_hold_annualized_return_pct,
        annualized_volatility_pct=annualized_volatility_pct,
        sortino_ratio=sortino_ratio,
        calmar_ratio=calmar_ratio,
        long_trades_count=long_trades_count,
        win_rate_pct=win_rate_pct,
        avg_holding_return_pct=avg_holding_return_pct,
        underlying_beta=underlying_beta,
        underlying_alpha_ann_pct=underlying_alpha_ann_pct,
        benchmark_code=bench_c,
        commission_rate=float(commission_rate),
        slippage_rate=float(slippage_rate),
    )

    if not include_equity_curve:
        return res, []

    dates = d["trade_date"].tolist()
    eqv = equity.to_numpy()
    n = len(eqv)
    max_pts = 120
    if n <= max_pts:
        idx = list(range(n))
    else:
        idx = sorted(set([0] + [int(round(i)) for i in np.linspace(0, n - 1, max_pts)]))
    curve = [
        {
            "trade_date": dates[i].isoformat() if hasattr(dates[i], "isoformat") else str(dates[i]),
            "equity": round(float(eqv[i]), 6),
        }
        for i in idx
    ]
    return res, curve
