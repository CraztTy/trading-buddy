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


def benchmark_close_on_primary_dates(
    d: pd.DataFrame, bench_klines: list[KLine]
) -> pd.Series:
    """
    将基准收盘按标的 `d` 的 `trade_date` 对齐；缺省交易日仅前向填充（不 bfill，避免前视）。
    """
    if not bench_klines:
        raise ValueError("benchmark_klines 为空")
    by_date: dict[date, float] = {}
    for k in bench_klines:
        td = k.trade_date
        dd = td if isinstance(td, date) else pd.Timestamp(td).date()
        by_date[dd] = float(k.close)
    raw: list[float] = []
    for _, row in d.iterrows():
        td = row["trade_date"]
        dd = td if isinstance(td, date) else pd.Timestamp(td).date()
        raw.append(by_date.get(dd, np.nan))
    ser = pd.Series(raw, index=d.index, dtype=float).ffill()
    if ser.isna().any():
        raise ValueError(
            "基准 K 线在标的样本起始日前无有效收盘，无法对齐（请增大 limit 或调整区间）"
        )
    return ser


def _long_hold_segments_start_and_return_pct(
    hold: pd.Series, strat_ret: pd.Series
) -> list[tuple[int, float]]:
    """
    连续多头段：返回 (段首索引, 段总收益百分点)，与 total_return_pct 同口径。
    hold 为滞后一日的有效仓位，与 strat_ret 逐行对齐。
    """
    h = hold.to_numpy(dtype=float)
    r = strat_ret.to_numpy(dtype=float)
    n = len(h)
    if len(r) != n:
        raise ValueError("hold 与 strat_ret 长度须一致")
    out: list[tuple[int, float]] = []
    i = 0
    while i < n:
        if h[i] < 0.5:
            i += 1
            continue
        j = i
        while j + 1 < n and h[j + 1] >= 0.5:
            j += 1
        chunk = r[i : j + 1]
        out.append((i, float(np.prod(1.0 + chunk) - 1.0) * 100.0))
        i = j + 1
    return out


def _equity_weighted_win_rate_pct(
    segments: list[tuple[int, float]], equity: pd.Series
) -> float:
    """
    按「段首日前一日权益」加权：胜率% = 100 × Σ(w_k·𝟙{r_k>0}) / Σ w_k。
    段首日为 s 时 w_k = equity[s-1]（s=0 时用 1.0 表示期初净值）。
    """
    if not segments:
        return 0.0
    eq_arr = equity.to_numpy(dtype=float)
    weights: list[float] = []
    win_flags: list[float] = []
    for s, rp in segments:
        w = float(eq_arr[s - 1]) if s > 0 else 1.0
        weights.append(w)
        win_flags.append(1.0 if rp > 0.0 else 0.0)
    w_np = np.array(weights, dtype=float)
    wf_np = np.array(win_flags, dtype=float)
    sw = float(w_np.sum())
    if sw <= 1e-12:
        return 0.0
    return float(100.0 * float((w_np * wf_np).sum()) / sw)


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
            "Sharpe / Sortino 按 252 交易日年化；Sortino 的 MAR=0、下行偏差为 min(0,r) 的二阶矩均方根。"
            " 年化收益为区间复利换算：(1+总收益)^(252/区间交易日)−1。"
            " Calmar=年化收益÷|最大回撤|（回撤为负百分比时取绝对值）。"
            " 多头持仓段=有效仓位为多的最长连续区间；段内收益为日 strat_ret 复利。"
            " 段胜率按金额加权：权重为段首日前一日累计权益，盈利段贡献其权重。"
            " 平均持有收益为各段总收益（%）的简单平均。"
            " underlying_beta / underlying_alpha_ann_pct：日策略收益对「回归市场收益」的 OLS（rf=0），"
            " α 按 ×252 年化到百分点；未传 benchmark 时为对标的自身日收益，传 benchmark 时为对基准日收益。"
            " 信号基于收盘均线，收益为收盘到收盘且滞后一日。"
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


def ma_cross_result_from_df(
    df: pd.DataFrame,
    *,
    code: str,
    fast: int,
    slow: int,
    commission_rate: float = 0.0,
    slippage_rate: float = 0.0,
    benchmark_klines: list[KLine] | None = None,
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
    bench_c: str | None = None
    bench_close_aligned: pd.Series | None = None
    if benchmark_klines is not None:
        bench_close_aligned = benchmark_close_on_primary_dates(d, benchmark_klines)
        bench_c = str(benchmark_klines[0].code).strip().lower()

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
        annualized_volatility_pct = float(active.std() * np.sqrt(252.0) * 100.0)
    else:
        sharpe = 0.0
        annualized_volatility_pct = 0.0

    n_periods = max(1, len(d) - 1)
    tr_dec = total_return_pct / 100.0
    annualized_return_pct = float(
        ((1.0 + tr_dec) ** (252.0 / n_periods) - 1.0) * 100.0
    )
    bh_dec = buy_hold_return_pct / 100.0
    buy_hold_annualized_return_pct = float(
        ((1.0 + bh_dec) ** (252.0 / n_periods) - 1.0) * 100.0
    )

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
    return res, equity, strat_ret


def run_ma_cross_backtest(
    klines: list[KLine],
    *,
    fast: int = 5,
    slow: int = 20,
    commission_rate: float = 0.0,
    slippage_rate: float = 0.0,
    include_equity_curve: bool = True,
    benchmark_klines: list[KLine] | None = None,
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
        benchmark_klines=benchmark_klines,
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


def ma_cross_last_signal(
    klines: list[KLine],
    *,
    fast: int,
    slow: int,
) -> dict[str, Any]:
    """
    最近一根「快慢均线均已就绪」的 K 上的多空状态（与 `ma_cross_result_from_df` 中 pos 同口径：收盘后比较 MA）。

    返回字段供 API 使用；不含手续费与滑点（仅状态展示）。
    """
    if not klines:
        raise ValueError("klines 为空")
    if fast < 1 or slow < 2:
        raise ValueError("fast 须 >=1，slow 须 >=2")
    if fast >= slow:
        raise ValueError("fast 须小于 slow")
    raw_code = str(klines[0].code or "").strip()
    code_norm = raw_code.lower()
    df = pd.DataFrame(
        {
            "trade_date": [k.trade_date for k in klines],
            "close": [float(k.close) for k in klines],
        }
    )
    d = df.sort_values("trade_date").reset_index(drop=True)
    if len(d) < slow:
        raise ValueError(f"K 线不足：需要至少 slow={slow} 根，当前 {len(d)}")
    close = d["close"].astype(float)
    ma_f = close.rolling(fast, min_periods=fast).mean()
    ma_s = close.rolling(slow, min_periods=slow).mean()
    valid = ma_f.notna() & ma_s.notna()
    if not valid.any():
        raise ValueError("无有效均线")
    last_i = int(valid[valid].index[-1])
    td_raw = d.at[last_i, "trade_date"]
    as_of = td_raw.isoformat() if hasattr(td_raw, "isoformat") else str(td_raw)
    c_last = float(close.iloc[last_i])
    mf = float(ma_f.iloc[last_i])
    ms = float(ma_s.iloc[last_i])
    position = "long" if mf > ms else "flat"
    note = (
        "与 ma-cross 回测同一均线口径：收盘后比较 MA_fast 与 MA_slow；"
        "position 为截至 as_of_date 收盘的多空状态（回测中下一根 K 起按滞后一日 hold 生效）。"
    )
    return {
        "code": code_norm,
        "fast_period": fast,
        "slow_period": slow,
        "bars_used": len(d),
        "as_of_date": as_of,
        "position": position,
        "close": round(c_last, 4),
        "ma_fast": round(mf, 4),
        "ma_slow": round(ms, 4),
        "note": note,
    }
