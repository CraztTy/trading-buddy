"""
涨停回调策略回测引擎。

规则：遍历日K，识别涨停日 → 在 pullback_days 窗口内
寻找回调买点（须通过完整五层选股过滤）→ 建仓后执行：
- 选股级止损（激进型=涨停日最低价 / 中性型=涨停日开盘价 / 保守型=前日收盘价）
- 兜底硬止损 8%
- 移动止盈：+10% 止损上移至成本；+15% 上移至 +5%；+20% 上移至 +15%
- 目标位：+10% 卖出 1/3，+15% 再卖出 1/3（剩余 1/3 继续按移动止盈）
- 趋势破坏：收盘价跌破 20 日线清仓
- 持仓上限：max_hold_days 个交易日（0 表示不限制）
- 时间止损：建仓后 time_stop_days 个交易日若浮盈低于 time_stop_pct 即清仓

为与现有 ``MaCrossBacktestResponse`` 兼容，结果字段结构复用 ``MaCrossBacktestResult``
（fast_period/slow_period/signal_changes 为占位 0）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
from src.data.models import KLine, StockInfo, StockType
from src.strategies.limit_up_pullback_scan import FilterResult, LimitUpPullbackScanParams, check_filters_at_idx
from src.strategies.limit_up_utils import is_limit_up
from src.strategies.market_env import evaluate_market_condition


VALID_ENTRY_TYPES: frozenset[str] = frozenset({"aggressive", "neutral", "conservative"})


@dataclass
class _TradeRecord:
    """单笔交易内部记录。"""

    entry_idx: int
    entry_date: date
    entry_price: float
    entry_position: float
    exit_idx: int = -1
    exit_date: date | None = None
    exit_price: float = 0.0
    exit_position: float = 0.0
    exit_reason: str = ""
    max_price: float = 0.0

    def to_dict(self, strat_ret: np.ndarray) -> dict[str, Any]:
        """转为 API 友好的字典。"""
        hold_days = self.exit_idx - self.entry_idx if self.exit_idx > 0 else 0
        # 段内收益（复利，已含费用与仓位变化）
        if self.exit_idx > self.entry_idx:
            seg = strat_ret[self.entry_idx : self.exit_idx + 1]
            pnl = float(np.prod(1.0 + seg) - 1.0) * 100.0
        else:
            pnl = 0.0
        max_ret = (self.max_price / self.entry_price - 1.0) * 100.0 if self.entry_price > 0 else 0.0
        return {
            "entry_date": self.entry_date.isoformat() if self.entry_date else None,
            "entry_price": round(self.entry_price, 4),
            "entry_position": round(self.entry_position, 4),
            "exit_date": self.exit_date.isoformat() if self.exit_date else None,
            "exit_price": round(self.exit_price, 4),
            "exit_position": round(self.exit_position, 4),
            "hold_days": hold_days,
            "pnl_pct": round(pnl, 4),
            "exit_reason": self.exit_reason,
            "max_price": round(self.max_price, 4),
            "max_return_pct": round(max_ret, 4),
        }


def _entry_type_to_buy_types(entry_type: str) -> tuple[str, ...]:
    """将 entry_type 映射为 buy_point_types。"""
    return (entry_type,)


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
    stock_info: StockInfo | None = None,
    max_hold_days: int = 0,
    time_stop_days: int = 0,
    time_stop_pct: float = 0.0,
    ma_strict: bool = False,
    use_full_filters: bool = True,
    market_index_klines: list[KLine] | None = None,
    require_market_bull: bool = False,
    market_strict: bool = False,
) -> tuple[MaCrossBacktestResult, list[dict[str, Any]], list[dict[str, Any]]]:
    """
    对单只标的跑涨停回调策略回测。

    Args:
        klines: 日K线列表
        stock_type: 股票类型（用于涨停阈值）
        pullback_days: 涨停后观察回调的窗口天数
        entry_type: 买点类型（aggressive/neutral/conservative）
        volume_shrink_ratio: 缩量比例上限（回调量 <= 涨停量 * ratio）
        commission_rate: 单边手续费率
        slippage_rate: 滑点率
        include_equity_curve: 是否包含权益曲线
        benchmark_klines: 基准K线（用于计算 β/α）
        stock_info: 股票信息（用于市值/ST过滤，为 None 时跳过）
        max_hold_days: 最大持仓天数（0=不限制）
        time_stop_days: 时间止损天数（建仓后 N 个交易日检查；0=不启用）
        time_stop_pct: 时间止损盈利阈值（建仓后 time_stop_days 天若浮盈 < 该值则清仓；0=不盈利即止损）
        ma_strict: 均线是否严格多头排列
        use_full_filters: 是否使用完整选股五层过滤（True=与选股引擎完全一致）
        market_index_klines: 大盘指数日K线（如上证指数），传入后启用第1层大盘环境过滤
        require_market_bull: 是否要求大盘多头（close>MA20>MA60）才允许建仓
        market_strict: 大盘严格模式（额外要求MA20斜率向上）

    Returns:
        (MaCrossBacktestResult 对象, equity_curve 列表, trades 交易明细列表)
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
    if max_hold_days < 0 or max_hold_days > 120:
        raise ValueError("max_hold_days 须在 [0, 120] 内")
    if time_stop_days < 0 or time_stop_days > 120:
        raise ValueError("time_stop_days 须在 [0, 120] 内")
    if time_stop_pct < -0.5 or time_stop_pct > 0.5:
        raise ValueError("time_stop_pct 须在 [-50%, 50%] 内")

    klines_sorted = sorted(klines, key=lambda k: k.trade_date)
    code = klines_sorted[0].code

    df = pd.DataFrame(
        {
            "trade_date": [k.trade_date for k in klines_sorted],
            "open": [float(k.open) for k in klines_sorted],
            "high": [float(k.high) for k in klines_sorted],
            "low": [float(k.low) for k in klines_sorted],
            "close": [float(k.close) for k in klines_sorted],
            "pre_close": [float(k.pre_close) if k.pre_close is not None else np.nan for k in klines_sorted],
            "volume": [int(k.volume) for k in klines_sorted],
        }
    )
    d = df.sort_values("trade_date").reset_index(drop=True)
    n = len(d)
    if n < 30:
        raise ValueError("K 线不足：涨停回调策略至少需要 30 根日 K")

    dates = d["trade_date"].tolist()
    close = d["close"].astype(float)
    volume = d["volume"].astype(float)
    daily_ret = close.pct_change().fillna(0.0)

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
    entry_day = -1
    entry_filter: FilterResult | None = None

    # 交易明细记录
    trades: list[_TradeRecord] = []
    current_trade: _TradeRecord | None = None

    # 构建选股参数（用于完整过滤时）
    if use_full_filters:
        scan_params = LimitUpPullbackScanParams(
            as_of_date=date(2000, 1, 1),  # 占位，实际由 current_idx 决定
            limit_up_lookback_min=5,
            limit_up_lookback_max=pullback_days,
            adjustment_volume_ratio_max=volume_shrink_ratio,
            buy_point_types=_entry_type_to_buy_types(entry_type),
            ma_strict=ma_strict,
        )

    # 预构建大盘K线日期映射（用于第1层过滤）
    market_date_map: dict[date, int] = {}
    if require_market_bull and market_index_klines:
        mkt_sorted = sorted(market_index_klines, key=lambda k: k.trade_date)
        for idx, k in enumerate(mkt_sorted):
            market_date_map[k.trade_date] = idx

    for i in range(1, n):
        if position[i - 1] > 0:
            # 更新建仓后最高价
            max_price = max(max_price, close[i])
            if current_trade is not None:
                current_trade.max_price = max(current_trade.max_price, close[i])

            # 更新移动止盈线
            if max_price >= cost_price * 1.20:
                trailing_stop = cost_price * 1.15
            elif max_price >= cost_price * 1.15:
                trailing_stop = cost_price * 1.05
            elif max_price >= cost_price * 1.10:
                trailing_stop = cost_price * 1.00

            sell = False
            sell_reason = ""

            # 趋势破坏：跌破 20 日线
            if pd.notna(ma20[i]) and close[i] < ma20[i]:
                sell = True
                sell_reason = "跌破20日线"

            # 选股级止损（若可用）
            if not sell and entry_filter is not None:
                hard_stop = entry_filter.stop_loss_price
                if close[i] <= hard_stop:
                    sell = True
                    sell_reason = f"选股止损({entry_filter.buy_point_type})"

            # 兜底硬止损 8%
            if not sell and close[i] <= cost_price * 0.92:
                sell = True
                sell_reason = "硬止损8%"

            # 移动止盈
            if not sell and trailing_stop > cost_price and close[i] <= trailing_stop:
                sell = True
                sell_reason = "移动止盈"

            # 最大持仓天数
            if not sell and max_hold_days > 0 and (i - entry_day) >= max_hold_days:
                sell = True
                sell_reason = f"持仓超{max_hold_days}天"

            # 时间止损：建仓后 N 天若浮盈未达到阈值即清仓
            if not sell and time_stop_days > 0 and (i - entry_day) >= time_stop_days:
                current_return = (close[i] / cost_price - 1.0) * 100.0
                if current_return < time_stop_pct * 100.0:
                    sell = True
                    sell_reason = f"时间止损({time_stop_days}天收益{current_return:.1f}%<{time_stop_pct*100:.0f}%)"

            if sell:
                position[i] = 0.0
                entry_filter = None
                if current_trade is not None:
                    current_trade.exit_idx = i
                    current_trade.exit_date = dates[i]
                    current_trade.exit_price = float(close[i])
                    current_trade.exit_position = 0.0
                    current_trade.exit_reason = sell_reason
                    trades.append(current_trade)
                    current_trade = None
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
            # 第1层：大盘环境过滤
            if require_market_bull and market_date_map:
                current_date = dates[i]
                mkt_idx = market_date_map.get(current_date)
                if mkt_idx is not None:
                    mkt_result = evaluate_market_condition(
                        market_index_klines,
                        strict=market_strict,
                        current_idx=mkt_idx,
                    )
                    if not mkt_result.passed:
                        continue
                else:
                    # 大盘当日无数据，保守跳过
                    continue

            buy_triggered = False
            if use_full_filters:
                filter_result = check_filters_at_idx(d, stock_info, stock_type, scan_params, current_idx=i)
                if filter_result.passed:
                    buy_triggered = True
            else:
                limit_up_mask = np.array([is_limit_up(k, stock_type) for k in klines_sorted])
                is_yiziban = np.array(
                    [k.open == k.close == k.high == k.low for k in klines_sorted]
                )
                valid_limit_up = limit_up_mask & ~is_yiziban

                lu_idx = None
                start_j = max(0, i - pullback_days)
                for j in range(i - 1, start_j - 1, -1):
                    if not valid_limit_up[j]:
                        continue
                    prev_start = max(0, j - 20)
                    if valid_limit_up[prev_start:j].any():
                        continue
                    lu_idx = j
                    break

                if lu_idx is not None:
                    open_p = float(d.at[lu_idx, "open"])
                    close_p = float(d.at[lu_idx, "close"])
                    if entry_type == "aggressive":
                        entry_price = close_p
                    elif entry_type == "conservative":
                        entry_price = open_p
                    else:
                        entry_price = (open_p + close_p) / 2.0

                    price_dev = abs(close[i] - entry_price) / entry_price if entry_price > 0 else float("inf")
                    if price_dev <= 0.02:
                        vol_ok = volume[lu_idx] > 0 and volume[i] <= volume[lu_idx] * volume_shrink_ratio
                        ma_ok = (
                            pd.notna(ma5[i])
                            and pd.notna(ma10[i])
                            and pd.notna(ma20[i])
                            and close[i] > ma10[i]
                            and ma5[i] > ma10[i] > ma20[i]
                        )
                        if vol_ok and ma_ok:
                            buy_triggered = True

            if buy_triggered:
                position[i] = 1.0
                cost_price = float(close[i])
                max_price = cost_price
                trailing_stop = cost_price * 0.92
                target_10_done = False
                target_15_done = False
                entry_day = i
                if use_full_filters:
                    entry_filter = filter_result
                current_trade = _TradeRecord(
                    entry_idx=i,
                    entry_date=dates[i],
                    entry_price=float(close[i]),
                    entry_position=1.0,
                    max_price=float(close[i]),
                )

    # 回测结束时若有未平仓交易，按最后一日收盘价结算
    if current_trade is not None:
        current_trade.exit_idx = n - 1
        current_trade.exit_date = dates[n - 1]
        current_trade.exit_price = float(close.iloc[-1])
        current_trade.exit_position = float(position[n - 1])
        current_trade.exit_reason = "回测结束"
        trades.append(current_trade)

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

    trade_dicts = [t.to_dict(strat_ret) for t in trades]

    if not include_equity_curve:
        return res, [], trade_dicts

    dates_out = d["trade_date"].tolist()
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
                dates_out[i].isoformat()
                if hasattr(dates_out[i], "isoformat")
                else str(dates_out[i])
            ),
            "equity": round(float(eqv[i]), 6),
        }
        for i in idx
    ]
    return res, curve, trade_dicts


# ---------------------------------------------------------------------------
# 参数网格优化扫描
# ---------------------------------------------------------------------------

@dataclass
class LimitUpPullbackParamGrid:
    """涨停回调策略参数网格。"""

    entry_types: list[str] = field(default_factory=lambda: ["neutral"])
    pullback_days_list: list[int] | None = None
    volume_shrink_ratios: list[float] = field(default_factory=lambda: [0.5])
    max_hold_days_list: list[int] = field(default_factory=lambda: [0])
    time_stop_days_list: list[int] = field(default_factory=lambda: [0])
    time_stop_pcts: list[float] = field(default_factory=lambda: [0.0])
    ma_strict_values: list[bool] = field(default_factory=lambda: [False])
    max_combinations: int = 200

    def __post_init__(self) -> None:
        if self.pullback_days_list is None:
            self.pullback_days_list = list(range(5, 16))
        self.entry_types = [e for e in self.entry_types if e in VALID_ENTRY_TYPES]
        if not self.entry_types:
            self.entry_types = ["neutral"]

    def combinations(self) -> list[dict[str, Any]]:
        """生成所有参数组合，限制总数不超过 max_combinations。"""
        import itertools

        raw = list(
            itertools.product(
                self.entry_types,
                self.pullback_days_list,
                self.volume_shrink_ratios,
                self.max_hold_days_list,
                self.time_stop_days_list,
                self.time_stop_pcts,
                self.ma_strict_values,
            )
        )
        if len(raw) > self.max_combinations:
            step = max(1, len(raw) // self.max_combinations)
            raw = raw[::step][: self.max_combinations]

        out: list[dict[str, Any]] = []
        for et, pd, vsr, mhd, tsd, tsp, ms in raw:
            out.append(
                {
                    "entry_type": et,
                    "pullback_days": pd,
                    "volume_shrink_ratio": vsr,
                    "max_hold_days": mhd,
                    "time_stop_days": tsd,
                    "time_stop_pct": tsp,
                    "ma_strict": ms,
                }
            )
        return out


GRID_SORT_KEYS: frozenset[str] = frozenset(
    {
        "total_return",
        "excess_return",
        "sharpe",
        "sortino",
        "calmar",
        "win_rate",
        "max_drawdown",
        "trades_count",
    }
)


def run_limit_up_pullback_param_grid(
    klines: list[KLine],
    *,
    stock_type: StockType,
    grid: LimitUpPullbackParamGrid,
    commission_rate: float = 0.0,
    slippage_rate: float = 0.0,
    benchmark_klines: list[KLine] | None = None,
    stock_info: StockInfo | None = None,
    sort_by: str = "sharpe",
    top_n: int = 10,
) -> list[dict[str, Any]]:
    """
    对单只标的跑涨停回调策略参数网格扫描。

    Args:
        klines: 日K线列表
        stock_type: 股票类型
        grid: 参数网格
        commission_rate: 单边手续费率
        slippage_rate: 滑点率
        benchmark_klines: 基准K线
        stock_info: 股票信息
        sort_by: 排序指标（total_return/sharpe/sortino/calmar/win_rate/max_drawdown/trades_count）
        top_n: 返回前N个最优组合

    Returns:
        排序后的参数组合结果列表
    """
    sort_by = sort_by.lower().strip()
    if sort_by not in GRID_SORT_KEYS:
        sort_by = "sharpe"

    combos = grid.combinations()
    rows: list[dict[str, Any]] = []

    for combo in combos:
        try:
            res, _curve, trades = run_limit_up_pullback_backtest(
                klines,
                stock_type=stock_type,
                commission_rate=commission_rate,
                slippage_rate=slippage_rate,
                benchmark_klines=benchmark_klines,
                stock_info=stock_info,
                include_equity_curve=False,
                **combo,
            )
        except ValueError:
            continue

        row = {
            "params": combo,
            "total_return_pct": round(res.total_return_pct, 4),
            "excess_return_pct": round(res.excess_return_pct, 4),
            "max_drawdown_pct": round(res.max_drawdown_pct, 4),
            "sharpe_ratio": round(res.sharpe_ratio, 4),
            "sortino_ratio": round(res.sortino_ratio, 4),
            "calmar_ratio": round(res.calmar_ratio, 4),
            "long_trades_count": res.long_trades_count,
            "win_rate_pct": round(res.win_rate_pct, 4),
            "avg_holding_return_pct": round(res.avg_holding_return_pct, 4),
            "annualized_return_pct": round(res.annualized_return_pct, 4),
            "annualized_volatility_pct": round(res.annualized_volatility_pct, 4),
            "trades": trades,
        }
        rows.append(row)

    # 排序
    reverse = sort_by != "max_drawdown"
    sort_key_map = {
        "total_return": lambda r: r["total_return_pct"],
        "excess_return": lambda r: r["excess_return_pct"],
        "sharpe": lambda r: r["sharpe_ratio"],
        "sortino": lambda r: r["sortino_ratio"],
        "calmar": lambda r: r["calmar_ratio"],
        "win_rate": lambda r: r["win_rate_pct"],
        "max_drawdown": lambda r: r["max_drawdown_pct"],
        "trades_count": lambda r: r["long_trades_count"],
    }
    rows.sort(key=sort_key_map[sort_by], reverse=reverse)
    return rows[:top_n]
