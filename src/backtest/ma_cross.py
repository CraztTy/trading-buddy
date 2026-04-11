"""
双均线（日线收盘）最小回测。

规则：用收盘计算快慢均线；第 t 日收盘后的多空信号在 t+1 日收盘到收盘的收益上生效
（即 signal 滞后一日乘日收益，避免当根 K 线「看到收盘再交易」的前视偏差）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from src.data.models import KLine


@dataclass(frozen=True)
class MaCrossBacktestResult:
    code: str
    fast_period: int
    slow_period: int
    bars_used: int
    first_trade_date: date | None
    last_trade_date: date | None
    total_return_pct: float
    buy_hold_return_pct: float
    excess_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    signal_changes: int
    commission_rate: float = 0.0
    slippage_rate: float = 0.0

    def to_api_dict(self, equity_sample_max: int = 120) -> dict[str, Any]:
        note = (
            "Sharpe 按 252 交易日年化；信号基于收盘均线，收益为收盘到收盘且滞后一日。"
        )
        if self.commission_rate > 0:
            note += (
                f" 单边手续费按调仓日扣减（费率={self.commission_rate:.6f}，每次翻转仓位扣一次）。"
            )
        if self.slippage_rate > 0:
            note += (
                f" 滑点按调仓日扣减（费率={self.slippage_rate:.6f}，与手续费同口径）。"
            )
        d: dict[str, Any] = {
            "code": self.code,
            "fast_period": self.fast_period,
            "slow_period": self.slow_period,
            "bars_used": self.bars_used,
            "commission_rate": round(self.commission_rate, 8),
            "slippage_rate": round(self.slippage_rate, 8),
            "first_trade_date": self.first_trade_date.isoformat()
            if self.first_trade_date
            else None,
            "last_trade_date": self.last_trade_date.isoformat()
            if self.last_trade_date
            else None,
            "total_return_pct": round(self.total_return_pct, 4),
            "buy_hold_return_pct": round(self.buy_hold_return_pct, 4),
            "excess_return_pct": round(self.excess_return_pct, 4),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "sharpe_ratio": round(self.sharpe_ratio, 4),
            "signal_changes": self.signal_changes,
            "note": note,
        }
        return d


def ma_cross_result_from_df(
    df: pd.DataFrame,
    *,
    code: str,
    fast: int,
    slow: int,
    commission_rate: float = 0.0,
    slippage_rate: float = 0.0,
) -> tuple[MaCrossBacktestResult, pd.Series, pd.Series]:
    """
    df 须含列 trade_date, close；按时间升序。
    返回 (结果, equity 序列, strategy_daily_ret 序列) 供采样或测试。
    """
    if fast < 1 or slow < 2:
        raise ValueError("fast 须 >=1，slow 须 >=2")
    if fast >= slow:
        raise ValueError("fast 须小于 slow")
    if df.empty or len(df) < slow + 1:
        raise ValueError(f"K 线数量不足（需要至少 {slow + 1} 根）")
    if commission_rate < 0 or commission_rate > 0.05:
        raise ValueError("commission_rate 须在 [0, 0.05] 内")
    if slippage_rate < 0 or slippage_rate > 0.05:
        raise ValueError("slippage_rate 须在 [0, 0.05] 内")
    if commission_rate + slippage_rate > 0.08:
        raise ValueError("commission_rate 与 slippage_rate 之和勿超过 0.08")

    d = df.sort_values("trade_date").reset_index(drop=True)
    close = d["close"].astype(float)
    ma_f = close.rolling(fast, min_periods=fast).mean()
    ma_s = close.rolling(slow, min_periods=slow).mean()
    valid = ma_f.notna() & ma_s.notna()
    pos_signal = np.where(valid & (ma_f > ma_s), 1.0, 0.0)
    pos = pd.Series(pos_signal, index=d.index)

    daily_ret = close.pct_change().fillna(0.0)
    hold = pos.shift(1).fillna(0.0)
    flipped = (hold.diff().abs() > 1e-12).fillna(False)
    flip_cost = float(commission_rate) + float(slippage_rate)
    strat_ret = hold * daily_ret - flipped.astype(float) * flip_cost
    strat_ret = strat_ret.fillna(0.0)

    equity = (1.0 + strat_ret).cumprod()

    total_return_pct = float((equity.iloc[-1] - 1.0) * 100.0)
    buy_hold_return_pct = float((close.iloc[-1] / close.iloc[0] - 1.0) * 100.0)
    excess_return_pct = float(total_return_pct - buy_hold_return_pct)

    peak = equity.cummax()
    dd_pct = float(((equity / peak) - 1.0).min() * 100.0)

    active = strat_ret.iloc[1:]
    if len(active) > 1 and float(active.std()) > 1e-12:
        sharpe = float(np.sqrt(252.0) * active.mean() / active.std())
    else:
        sharpe = 0.0

    ps = pos.to_numpy()
    changes = int(np.sum(ps[1:] != ps[:-1])) if len(ps) > 1 else 0

    td = d["trade_date"]
    first_raw = td.iloc[slow - 1]
    last_raw = td.iloc[-1]
    first_d = pd.Timestamp(first_raw).date()
    last_d = pd.Timestamp(last_raw).date()

    res = MaCrossBacktestResult(
        code=code,
        fast_period=fast,
        slow_period=slow,
        bars_used=len(d),
        first_trade_date=first_d,
        last_trade_date=last_d,
        total_return_pct=total_return_pct,
        buy_hold_return_pct=buy_hold_return_pct,
        excess_return_pct=excess_return_pct,
        max_drawdown_pct=dd_pct,
        sharpe_ratio=sharpe,
        signal_changes=changes,
        commission_rate=float(commission_rate),
        slippage_rate=float(slippage_rate),
    )
    return res, equity, strat_ret


def run_ma_cross_backtest(
    klines: list[KLine],
    *,
    fast: int = 5,
    slow: int = 20,
    commission_rate: float = 0.0,
    slippage_rate: float = 0.0,
    include_equity_curve: bool = True,
) -> tuple[MaCrossBacktestResult, list[dict[str, Any]]]:
    """从 KLine 列表运行双均线回测；可跳过权益曲线采样以加速批量扫描。"""
    if not klines:
        raise ValueError("klines 为空")
    code = klines[0].code
    df = pd.DataFrame(
        {
            "trade_date": [k.trade_date for k in klines],
            "close": [float(k.close) for k in klines],
        }
    )
    res, equity, _ = ma_cross_result_from_df(
        df,
        code=code,
        fast=fast,
        slow=slow,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
    )

    if not include_equity_curve:
        return res, []

    dates = df["trade_date"].tolist()
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
