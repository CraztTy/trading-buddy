"""
涨停回调策略回测引擎。

规则：遍历日K，识别涨停日（排除一字板、距上次>20日）→ 在 pullback_days 窗口内
寻找回调买点（±2%、缩量、均线多头）→ 建仓后执行：
- 8% 硬止损
- 移动止盈：+10% 止损上移至成本；+15% 上移至 +5%；+20% 上移至 +15%
- 目标位：+10% 卖出 1/3，+15% 再卖出 1/3（剩余 1/3 继续按移动止盈）
- 趋势破坏：收盘价跌破 20 日线清仓

为与现有 ``MaCrossBacktestResponse`` 兼容，结果字段结构复用 ``MaCrossBacktestResult``
（fast_period/slow_period/signal_changes 为占位 0）。
"""

from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from src.backtest.ma_cross import (
    MaCrossBacktestResult,
    _equity_weighted_win_rate_pct,
    _long_hold_segments_start_and_return_pct,
    benchmark_close_on_primary_dates,
)
from src.data.models import KLine, StockType
from src.strategies.limit_up_utils import is_limit_up


VALID_ENTRY_TYPES: frozenset[str] = frozenset({"aggressive", "neutral", "conservative"})


def _find_entry_limit_up(
    i: int,
    valid_limit_up: np.ndarray,
    pullback_days: int,
) -> int | None:
    """从 i-1 往回找，找到落在 [i-pullback_days, i-1] 范围内的孤立涨停日索引。"""
    start = max(0, i - pullback_days)
    for j in range(i - 1, start - 1, -1):
        if not valid_limit_up[j]:
            continue
        # 距上一次涨停须 > 20 个交易日
        prev_start = max(0, j - 20)
        if valid_limit_up[prev_start:j].any():
            continue
        return j
    return None


def _calc_entry_price(df: pd.DataFrame, lu_idx: int, entry_type: str) -> float:
    open_p = float(df.at[lu_idx, "open"])
    close_p = float(df.at[lu_idx, "close"])
    if entry_type == "aggressive":
        return close_p
    if entry_type == "conservative":
        return open_p
    # neutral
    return (open_p + close_p) / 2.0


def run_limit_up_pullback_backtest(
    klines: list[KLine],
    *,
    stock_type: StockType,
    pullback_days: int = 10,
    entry_type: str = "neutral",
    volume_shrink_ratio: float = 0.5,
    commission_rate: float = 0.0,
    slippage_rate: float = 0.0,
    include_equity_curve: bool = True,
    benchmark_klines: list[KLine] | None = None,
) -> tuple[MaCrossBacktestResult, list[dict[str, Any]]]:
    """
    对单只标的跑涨停回调策略回测。

    Returns:
        (MaCrossBacktestResult 对象, equity_curve 列表)
    """
    if not klines:
        raise ValueError("klines 为空")
    if pullback_days < 1 or pullback_days > 60:
        raise ValueError("pullback_days 须在 [1, 60] 内")
    if entry_type not in VALID_ENTRY_TYPES:
        raise ValueError("entry_type 须为 aggressive / neutral / conservative 之一")
    if commission_rate < 0 or commission_rate > 0.05:
        raise ValueError("commission_rate 须在 [0, 0.05] 内")
    if slippage_rate < 0 or slippage_rate > 0.05:
        raise ValueError("slippage_rate 须在 [0, 0.05] 内")
    if commission_rate + slippage_rate > 0.08:
        raise ValueError("commission_rate 与 slippage_rate 之和勿超过 0.08")

    klines_sorted = sorted(klines, key=lambda k: k.trade_date)
    code = klines_sorted[0].code

    df = pd.DataFrame(
        {
            "trade_date": [k.trade_date for k in klines_sorted],
            "open": [float(k.open) for k in klines_sorted],
            "high": [float(k.high) for k in klines_sorted],
            "low": [float(k.low) for k in klines_sorted],
            "close": [float(k.close) for k in klines_sorted],
            "volume": [int(k.volume) for k in klines_sorted],
        }
    )
    d = df.sort_values("trade_date").reset_index(drop=True)
    n = len(d)
    if n < 30:
        raise ValueError("K 线不足：涨停回调策略至少需要 30 根日 K")

    close = d["close"].astype(float)
    volume = d["volume"].astype(float)
    daily_ret = close.pct_change().fillna(0.0)

    # 涨停检测（按排序后 klines）
    limit_up_mask = np.array([is_limit_up(k, stock_type) for k in klines_sorted])
    is_yiziban = np.array(
        [k.open == k.close == k.high == k.low for k in klines_sorted]
    )
    valid_limit_up = limit_up_mask & ~is_yiziban

    # 均线
    ma5 = close.rolling(5, min_periods=5).mean()
    ma10 = close.rolling(10, min_periods=10).mean()
    ma20 = close.rolling(20, min_periods=20).mean()

    position = np.zeros(n, dtype=float)
    flip_cost = float(commission_rate) + float(slippage_rate)

    cost_price = 0.0
    max_price = 0.0
    trailing_stop = 0.0
    target_10_done = False
    target_15_done = False

    for i in range(1, n):
        if position[i - 1] > 0:
            # 更新建仓后最高价
            max_price = max(max_price, close[i])

            # 更新移动止盈线
            if max_price >= cost_price * 1.20:
                trailing_stop = cost_price * 1.15
            elif max_price >= cost_price * 1.15:
                trailing_stop = cost_price * 1.05
            elif max_price >= cost_price * 1.10:
                trailing_stop = cost_price * 1.00

            sell = False
            # 趋势破坏：跌破 20 日线
            if pd.notna(ma20[i]) and close[i] < ma20[i]:
                sell = True
            # 硬止损 8%
            elif close[i] <= cost_price * 0.92:
                sell = True
            # 移动止盈（止损线已上移过成本价）
            elif trailing_stop > cost_price and close[i] <= trailing_stop:
                sell = True

            if sell:
                position[i] = 0.0
            else:
                new_pos = position[i - 1]
                if not target_15_done and close[i] >= cost_price * 1.15:
                    new_pos = 1.0 / 3.0
                    target_15_done = True
                    target_10_done = True
                elif not target_10_done and close[i] >= cost_price * 1.10:
                    new_pos = 2.0 / 3.0
                    target_10_done = True
                position[i] = new_pos
        else:
            # 寻找买点
            lu_idx = _find_entry_limit_up(i, valid_limit_up, pullback_days)
            if lu_idx is not None:
                entry_price = _calc_entry_price(d, lu_idx, entry_type)
                price_dev = (
                    abs(close[i] - entry_price) / entry_price
                    if entry_price > 0
                    else float("inf")
                )
                if price_dev <= 0.02:
                    vol_ok = (
                        volume[lu_idx] > 0
                        and volume[i] <= volume[lu_idx] * volume_shrink_ratio
                    )
                    ma_ok = (
                        pd.notna(ma5[i])
                        and pd.notna(ma10[i])
                        and pd.notna(ma20[i])
                        and close[i] > ma10[i]
                        and ma5[i] > ma10[i] > ma20[i]
                    )
                    if vol_ok and ma_ok:
                        position[i] = 1.0
                        cost_price = float(close[i])
                        max_price = cost_price
                        trailing_stop = cost_price * 0.92
                        target_10_done = False
                        target_15_done = False

    # 策略日收益：前一日仓位享受当日价格收益，调仓部分扣费用
    strat_ret = np.zeros(n, dtype=float)
    for i in range(1, n):
        trade_size = abs(position[i] - position[i - 1])
        strat_ret[i] = position[i - 1] * daily_ret[i] - trade_size * flip_cost

    equity = pd.Series((1.0 + strat_ret).cumprod(), index=d.index)

    total_return_pct = float((equity.iloc[-1] - 1.0) * 100.0)
    buy_hold_return_pct = float((close.iloc[-1] / close.iloc[0] - 1.0) * 100.0)
    excess_return_pct = float(total_return_pct - buy_hold_return_pct)

    peak = equity.cummax()
    dd_pct = float(((equity / peak) - 1.0).min() * 100.0)

    active = strat_ret[1:]
    if len(active) > 1 and float(np.std(active)) > 1e-12:
        sharpe = float(np.sqrt(252.0) * np.mean(active) / np.std(active))
        annualized_volatility_pct = float(np.std(active) * np.sqrt(252.0) * 100.0)
    else:
        sharpe = 0.0
        annualized_volatility_pct = 0.0

    n_periods = max(1, n - 1)
    tr_dec = total_return_pct / 100.0
    annualized_return_pct = float(
        ((1.0 + tr_dec) ** (252.0 / n_periods) - 1.0) * 100.0
    )
    bh_dec = buy_hold_return_pct / 100.0
    buy_hold_annualized_return_pct = float(
        ((1.0 + bh_dec) ** (252.0 / n_periods) - 1.0) * 100.0
    )

    mar = 0.0
    downside_sq = np.minimum(0.0, (active - mar)) ** 2
    downside_dev = float(np.sqrt(np.mean(downside_sq))) if len(active) > 0 else 0.0
    if len(active) > 1 and downside_dev > 1e-12:
        sortino_ratio = float(np.sqrt(252.0) * float(np.mean(active)) / downside_dev)
    else:
        sortino_ratio = 0.0

    dd_abs = abs(dd_pct) / 100.0
    if dd_abs > 1e-8:
        calmar_ratio = float((annualized_return_pct / 100.0) / dd_abs)
    else:
        calmar_ratio = 0.0

    # 基准对齐与 β/α
    bench_c: str | None = None
    if benchmark_klines is not None:
        bench_close_aligned = benchmark_close_on_primary_dates(d, benchmark_klines)
        bench_c = str(benchmark_klines[0].code).strip().lower()
        mkt_line = bench_close_aligned.astype(float).pct_change().fillna(0.0)
    else:
        mkt_line = daily_ret

    mkt_active = mkt_line.iloc[1:].astype(float)
    if len(mkt_active) == len(active) and len(active) > 1:
        m = mkt_active.to_numpy(dtype=float)
        s_arr = active
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

    # 持仓段统计
    hold = pd.Series(np.roll(position, 1), index=d.index)
    hold.iloc[0] = 0.0
    strat_ret_series = pd.Series(strat_ret, index=d.index)
    seg_list = _long_hold_segments_start_and_return_pct(hold, strat_ret_series)
    long_trades_count = len(seg_list)
    if long_trades_count > 0:
        seg_returns_pct = [rp for _, rp in seg_list]
        win_rate_pct = _equity_weighted_win_rate_pct(seg_list, equity)
        avg_holding_return_pct = float(np.mean(seg_returns_pct))
    else:
        win_rate_pct = 0.0
        avg_holding_return_pct = 0.0

    td = d["trade_date"]
    first_d = pd.Timestamp(td.iloc[0]).date()
    last_d = pd.Timestamp(td.iloc[-1]).date()

    res = MaCrossBacktestResult(
        code=code,
        fast_period=0,
        slow_period=0,
        bars_used=len(d),
        first_trade_date=first_d,
        last_trade_date=last_d,
        total_return_pct=total_return_pct,
        buy_hold_return_pct=buy_hold_return_pct,
        excess_return_pct=excess_return_pct,
        max_drawdown_pct=dd_pct,
        sharpe_ratio=sharpe,
        signal_changes=0,
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
    max_pts = 120
    if n <= max_pts:
        idx = list(range(n))
    else:
        idx = sorted(
            set([0] + [int(round(i)) for i in np.linspace(0, n - 1, max_pts)])
        )
    curve = [
        {
            "trade_date": (
                dates[i].isoformat()
                if hasattr(dates[i], "isoformat")
                else str(dates[i])
            ),
            "equity": round(float(eqv[i]), 6),
        }
        for i in idx
    ]
    return res, curve
