"""
均值回归策略（Mean Reversion）

基于 Bollinger Bands 布林带的均值回归策略。
当价格跌破下轨时买入，当价格突破上轨时卖出。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from src.data.models import KLine


@dataclass(frozen=True)
class MeanReversionBacktestResult:
    """均值回归策略回测结果"""
    code: str
    bb_period: int
    bb_std: float
    bars_used: int
    first_trade_date: date | None
    last_trade_date: date | None
    total_return_pct: float
    buy_hold_return_pct: float
    excess_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    signal_changes: int
    annualized_return_pct: float
    buy_hold_annualized_return_pct: float
    annualized_volatility_pct: float
    sortino_ratio: float
    calmar_ratio: float
    long_trades_count: int
    win_rate_pct: float
    avg_holding_return_pct: float
    underlying_beta: float
    underlying_alpha_ann_pct: float
    benchmark_code: str | None = None
    commission_rate: float = 0.0
    slippage_rate: float = 0.0

    def to_api_dict(self, equity_sample_max: int = 120) -> dict[str, Any]:
        note = (
            "均值回归策略：基于布林带指标。"
            " 当收盘价跌破下轨时开多仓，当收盘价突破上轨时平仓。"
            " Sharpe / Sortino 按 252 交易日年化。"
            " Calmar=年化收益÷|最大回撤|。"
        )
        if self.commission_rate > 0:
            note += (
                f" 单边手续费按调仓日扣减（费率={self.commission_rate:.6f}）。"
            )
        if self.slippage_rate > 0:
            note += (
                f" 滑点按调仓日扣减（费率={self.slippage_rate:.6f}）。"
            )
        d: dict[str, Any] = {
            "code": self.code,
            "bb_period": self.bb_period,
            "bb_std": round(self.bb_std, 2),
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
            "annualized_return_pct": round(self.annualized_return_pct, 4),
            "buy_hold_annualized_return_pct": round(
                self.buy_hold_annualized_return_pct, 4
            ),
            "annualized_volatility_pct": round(self.annualized_volatility_pct, 4),
            "sortino_ratio": round(self.sortino_ratio, 4),
            "calmar_ratio": round(self.calmar_ratio, 4),
            "long_trades_count": self.long_trades_count,
            "win_rate_pct": round(self.win_rate_pct, 4),
            "avg_holding_return_pct": round(self.avg_holding_return_pct, 4),
            "underlying_beta": round(self.underlying_beta, 4),
            "underlying_alpha_ann_pct": round(self.underlying_alpha_ann_pct, 4),
            "benchmark_code": self.benchmark_code,
            "note": note,
        }
        return d


def calculate_bollinger_bands(df: pd.DataFrame, period: int, std_dev: float) -> tuple[pd.Series, pd.Series, pd.Series]:
    """计算布林带指标"""
    middle_band = df['close'].rolling(window=period).mean()
    std = df['close'].rolling(window=period).std()
    upper_band = middle_band + std * std_dev
    lower_band = middle_band - std * std_dev
    return upper_band, middle_band, lower_band


def mean_reversion_backtest(
    df: pd.DataFrame,
    *,
    code: str,
    bb_period: int = 20,
    bb_std: float = 2.0,
    commission_rate: float = 0.0,
    slippage_rate: float = 0.0,
    benchmark_klines: list[KLine] | None = None,
) -> tuple[MeanReversionBacktestResult, pd.Series, pd.Series]:
    """
    均值回归策略回测。
    
    策略规则：
    1. 计算布林带（中轨=MA，上轨=MA+σ×N，下轨=MA-σ×N）
    2. 当收盘价跌破下轨时，开多仓（预计价格回归均值）
    3. 当收盘价突破上轨或回到中轨之上时，平仓
    
    df 须含列 trade_date, close；按时间升序。
    """
    if bb_period < 10:
        raise ValueError("bb_period 须 >= 10")
    if bb_std <= 0:
        raise ValueError("bb_std 须 > 0")
    
    d = df.copy().reset_index(drop=True)
    n = len(d)
    if n < bb_period:
        raise ValueError(f"数据量不足（需要至少 {bb_period} 根K线）")
    
    # 计算布林带
    d['upper_band'], d['middle_band'], d['lower_band'] = calculate_bollinger_bands(d, bb_period, bb_std)
    
    # 计算日收益率
    d['ret'] = d['close'].pct_change()
    d['ret'].iloc[0] = 0.0
    
    # 生成信号：1=持有多仓，0=空仓
    d['signal'] = 0
    in_position = False
    
    for i in range(bb_period, n):
        if not in_position:
            # 跌破下轨开仓
            if d['close'].iloc[i] < d['lower_band'].iloc[i]:
                d['signal'].iloc[i] = 1
                in_position = True
        else:
            # 突破上轨或回到中轨之上平仓
            if d['close'].iloc[i] > d['upper_band'].iloc[i] or d['close'].iloc[i] > d['middle_band'].iloc[i]:
                d['signal'].iloc[i] = 0
                in_position = False
            else:
                d['signal'].iloc[i] = 1
    
    # 滞后一日执行，避免前视偏差
    d['hold'] = d['signal'].shift(1).fillna(0)
    d['hold'].iloc[0] = 0.0
    
    # 计算策略收益（滞后一日）
    d['strat_ret'] = d['hold'] * d['ret']
    
    # 计算手续费和滑点（仅在仓位翻转时扣减）
    d['position_change'] = d['hold'].diff().abs()
    cost_rate = commission_rate + slippage_rate
    d['cost'] = d['position_change'] * cost_rate
    d['strat_ret_after_cost'] = d['strat_ret'] - d['cost']
    
    # 计算权益曲线
    d['equity'] = (1.0 + d['strat_ret_after_cost']).cumprod()
    d['buy_hold_equity'] = (1.0 + d['ret']).cumprod()
    
    # 计算统计指标
    total_return = float(d['equity'].iloc[-1] - 1.0) * 100.0
    buy_hold_return = float(d['buy_hold_equity'].iloc[-1] - 1.0) * 100.0
    excess_return = total_return - buy_hold_return
    
    # 最大回撤
    running_max = d['equity'].cummax()
    drawdown = (d['equity'] - running_max) / running_max
    max_drawdown = float(drawdown.min()) * 100.0
    
    # 年化指标
    daily_returns = d['strat_ret_after_cost'].dropna()
    n_days = len(daily_returns)
    if n_days > 0:
        annualized_return = (1.0 + total_return / 100.0) ** (252.0 / n_days) - 1.0
        annualized_return_pct = annualized_return * 100.0
        
        buy_hold_annualized_return = (1.0 + buy_hold_return / 100.0) ** (252.0 / n_days) - 1.0
        buy_hold_annualized_return_pct = buy_hold_annualized_return * 100.0
        
        volatility = daily_returns.std() * np.sqrt(252)
        annualized_volatility_pct = volatility * 100.0
        
        # Sharpe Ratio (rf=0)
        sharpe_ratio = annualized_return / volatility if volatility > 1e-12 else 0.0
        
        # Sortino Ratio
        downside_returns = daily_returns[daily_returns < 0]
        if len(downside_returns) > 0:
            downside_deviation = downside_returns.std() * np.sqrt(252)
            sortino_ratio = annualized_return / downside_deviation if downside_deviation > 1e-12 else 0.0
        else:
            sortino_ratio = 0.0
        
        # Calmar Ratio
        calmar_ratio = -annualized_return / (max_drawdown / 100.0) if abs(max_drawdown) > 1e-12 else 0.0
    else:
        annualized_return_pct = 0.0
        buy_hold_annualized_return_pct = 0.0
        annualized_volatility_pct = 0.0
        sharpe_ratio = 0.0
        sortino_ratio = 0.0
        calmar_ratio = 0.0
    
    # 信号变化次数
    signal_changes = int(d['position_change'].sum())
    
    # 多头持仓段统计
    hold_arr = d['hold'].to_numpy()
    segments = []
    i = 0
    while i < n:
        if hold_arr[i] < 0.5:
            i += 1
            continue
        j = i
        while j + 1 < n and hold_arr[j + 1] >= 0.5:
            j += 1
        segment_ret = float((1.0 + d['strat_ret_after_cost'].iloc[i:j+1]).prod() - 1.0) * 100.0
        segments.append((i, segment_ret))
        i = j + 1
    
    long_trades_count = len(segments)
    if segments:
        win_rate_pct = 100.0 * sum(1 for _, ret in segments if ret > 0) / len(segments)
        avg_holding_return_pct = sum(ret for _, ret in segments) / len(segments)
    else:
        win_rate_pct = 0.0
        avg_holding_return_pct = 0.0
    
    # Beta 和 Alpha（对自身收益回归）
    if benchmark_klines:
        from src.backtest.ma_cross import benchmark_close_on_primary_dates
        bench_ser = benchmark_close_on_primary_dates(d, benchmark_klines)
        bench_ret = bench_ser.pct_change().fillna(0)
        y = d['strat_ret_after_cost']
        x = bench_ret
    else:
        y = d['strat_ret_after_cost']
        x = d['ret']
    
    valid_mask = ~y.isna() & ~x.isna()
    y_valid = y[valid_mask]
    x_valid = x[valid_mask]
    
    if len(y_valid) >= 2:
        cov_matrix = np.cov(x_valid, y_valid)
        if cov_matrix[0, 0] > 1e-12:
            beta = cov_matrix[0, 1] / cov_matrix[0, 0]
        else:
            beta = 0.0
        alpha = float(y_valid.mean() - beta * x_valid.mean()) * 252 * 100.0
    else:
        beta = 0.0
        alpha = 0.0
    
    first_date = d['trade_date'].iloc[0]
    last_date = d['trade_date'].iloc[-1]
    
    result = MeanReversionBacktestResult(
        code=code,
        bb_period=bb_period,
        bb_std=bb_std,
        bars_used=n,
        first_trade_date=first_date if isinstance(first_date, date) else pd.Timestamp(first_date).date(),
        last_trade_date=last_date if isinstance(last_date, date) else pd.Timestamp(last_date).date(),
        total_return_pct=total_return,
        buy_hold_return_pct=buy_hold_return,
        excess_return_pct=excess_return,
        max_drawdown_pct=max_drawdown,
        sharpe_ratio=sharpe_ratio,
        signal_changes=signal_changes,
        annualized_return_pct=annualized_return_pct,
        buy_hold_annualized_return_pct=buy_hold_annualized_return_pct,
        annualized_volatility_pct=annualized_volatility_pct,
        sortino_ratio=sortino_ratio,
        calmar_ratio=calmar_ratio,
        long_trades_count=long_trades_count,
        win_rate_pct=win_rate_pct,
        avg_holding_return_pct=avg_holding_return_pct,
        underlying_beta=beta,
        underlying_alpha_ann_pct=alpha,
        benchmark_code=benchmark_klines[0].code if benchmark_klines else None,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
    )
    
    return result, d['equity'], d['strat_ret_after_cost']
