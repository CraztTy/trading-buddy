"""双均线回测纯逻辑（不连库）。"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from src.backtest.ma_cross import (
    _equity_weighted_win_rate_pct,
    _long_hold_segments_start_and_return_pct,
    benchmark_close_on_primary_dates,
    ma_cross_result_from_df,
    run_ma_cross_backtest,
)
from src.data.models import KLine


def _date_series(n: int, start: date | None = None) -> list[date]:
    s = start or date(2020, 1, 2)
    return [s + timedelta(days=i) for i in range(n)]


def test_ma_cross_uptrend_positive_return():
    n = 80
    # 单调上涨：慢均线低于价，金叉后多头应吃到大部分涨幅
    closes = [100.0 + i * 0.5 for i in range(n)]
    df = pd.DataFrame(
        {"trade_date": _date_series(n), "close": closes},
    )
    res, equity, _ = ma_cross_result_from_df(df, code="sh.000001", fast=3, slow=10)
    assert res.bars_used == n
    assert res.buy_hold_return_pct > 10
    assert res.total_return_pct > 5
    assert abs(res.excess_return_pct - (res.total_return_pct - res.buy_hold_return_pct)) < 1e-6
    assert equity.iloc[-1] > 1.0
    assert res.signal_changes >= 0
    assert res.annualized_volatility_pct > 0
    assert res.annualized_return_pct > 0
    assert res.buy_hold_annualized_return_pct > 0
    assert isinstance(res.sortino_ratio, float)
    assert isinstance(res.calmar_ratio, float)
    assert res.long_trades_count >= 1
    assert 0.0 <= res.win_rate_pct <= 100.0
    assert isinstance(res.underlying_beta, float)
    assert isinstance(res.underlying_alpha_ann_pct, float)


def test_long_hold_segments_start_and_return_pct_two_segments():
    hold = pd.Series([0.0, 1.0, 1.0, 0.0, 1.0])
    r = pd.Series([0.0, 0.1, -0.05, 0.0, 0.2])
    segs = _long_hold_segments_start_and_return_pct(hold, r)
    assert len(segs) == 2
    exp0 = float(((1.1 * 0.95) - 1.0) * 100.0)
    assert segs[0][0] == 1
    assert abs(segs[0][1] - exp0) < 1e-6
    assert segs[1][0] == 4
    assert abs(segs[1][1] - 20.0) < 1e-6


def test_equity_weighted_win_rate_pct_not_equal_simple_count():
    equity = pd.Series([1.0, 1.1, 0.99, 0.99, 1.188])
    segs = [(1, -1.0), (4, 20.0)]
    wr = _equity_weighted_win_rate_pct(segs, equity)
    exp = 100.0 * 0.99 / (1.0 + 0.99)
    assert abs(wr - exp) < 1e-6
    assert abs(wr - 50.0) > 0.1


def test_flat_market_zero_underlying_beta():
    n = 50
    closes = [100.0] * n
    df = pd.DataFrame({"trade_date": _date_series(n), "close": closes})
    res, _, _ = ma_cross_result_from_df(df, code="x", fast=2, slow=10)
    assert res.underlying_beta == 0.0


def test_ma_cross_fast_ge_slow_raises():
    df = pd.DataFrame(
        {"trade_date": _date_series(30), "close": list(range(30))},
    )
    with pytest.raises(ValueError, match="fast"):
        ma_cross_result_from_df(df, code="x", fast=10, slow=10)


def test_ma_cross_insufficient_bars_raises():
    df = pd.DataFrame(
        {"trade_date": _date_series(10), "close": list(range(10))},
    )
    with pytest.raises(ValueError, match="K 线数量不足"):
        ma_cross_result_from_df(df, code="x", fast=2, slow=20)


def test_commission_reduces_return_vs_zero():
    n = 120
    flat = [100.0] * 35
    ramp = list(100.0 + (i / 84.0) * 55.0 for i in range(85))
    closes = flat + ramp
    df = pd.DataFrame({"trade_date": _date_series(n), "close": closes})
    r0, _, _ = ma_cross_result_from_df(df, code="x", fast=3, slow=12, commission_rate=0.0)
    r1, _, _ = ma_cross_result_from_df(
        df, code="x", fast=3, slow=12, commission_rate=0.001
    )
    assert r0.signal_changes > 0
    assert r1.total_return_pct < r0.total_return_pct
    assert r0.long_trades_count >= 1
    assert 0.0 <= r0.win_rate_pct <= 100.0


def test_commission_rate_out_of_range_raises():
    df = pd.DataFrame(
        {"trade_date": _date_series(40), "close": list(range(40, 80))},
    )
    with pytest.raises(ValueError, match="commission_rate"):
        ma_cross_result_from_df(df, code="x", fast=2, slow=10, commission_rate=0.1)


def test_slippage_rate_out_of_range_raises():
    df = pd.DataFrame(
        {"trade_date": _date_series(40), "close": list(range(40, 80))},
    )
    with pytest.raises(ValueError, match="slippage_rate"):
        ma_cross_result_from_df(df, code="x", fast=2, slow=10, slippage_rate=0.06)


def test_flip_cost_sum_cap_raises():
    df = pd.DataFrame(
        {"trade_date": _date_series(40), "close": list(range(40, 80))},
    )
    with pytest.raises(ValueError, match="之和"):
        ma_cross_result_from_df(
            df, code="x", fast=2, slow=10, commission_rate=0.05, slippage_rate=0.04
        )


def test_slippage_reduces_return_like_commission():
    n = 120
    flat = [100.0] * 35
    ramp = list(100.0 + (i / 84.0) * 55.0 for i in range(85))
    closes = flat + ramp
    df = pd.DataFrame({"trade_date": _date_series(n), "close": closes})
    r0, _, _ = ma_cross_result_from_df(df, code="x", fast=3, slow=12, slippage_rate=0.0)
    r1, _, _ = ma_cross_result_from_df(df, code="x", fast=3, slow=12, slippage_rate=0.001)
    assert r0.signal_changes > 0
    assert r1.total_return_pct < r0.total_return_pct


def _kline(code: str, trade_date: date, close: float) -> KLine:
    return KLine(
        code=code,
        trade_date=trade_date,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=0,
        amount=0.0,
    )


def test_benchmark_close_on_primary_dates_ffill():
    d0 = date(2020, 1, 2)
    dates = [d0 + timedelta(days=i) for i in range(4)]
    d = pd.DataFrame({"trade_date": dates, "close": [10.0] * 4})
    bench = [
        _kline("sh.b", dates[0], 100.0),
        _kline("sh.b", dates[2], 104.0),
    ]
    ser = benchmark_close_on_primary_dates(d, bench)
    assert ser.tolist() == [100.0, 100.0, 104.0, 104.0]


def test_benchmark_close_on_primary_dates_raises_without_prior_bench_bar():
    dates = [date(2020, 1, 2), date(2020, 1, 3)]
    d = pd.DataFrame({"trade_date": dates, "close": [10.0, 10.0]})
    bench = [_kline("sh.b", date(2020, 1, 4), 100.0)]
    with pytest.raises(ValueError, match="标的样本起始日前"):
        benchmark_close_on_primary_dates(d, bench)


def test_ma_cross_benchmark_flat_index_beta_zero():
    n = 80
    closes = [100.0 + i * 0.5 for i in range(n)]
    ds = _date_series(n)
    df = pd.DataFrame({"trade_date": ds, "close": closes})
    bench_k = [_kline("sh.bench", ds[i], 50.0) for i in range(n)]
    r_self, _, _ = ma_cross_result_from_df(df, code="sh.x", fast=3, slow=10)
    r_b, _, _ = ma_cross_result_from_df(
        df, code="sh.x", fast=3, slow=10, benchmark_klines=bench_k
    )
    assert r_b.benchmark_code == "sh.bench"
    assert r_b.underlying_beta == 0.0
    assert abs(r_self.underlying_beta) > 1e-6


def test_run_ma_cross_skip_equity_curve():
    klines = [
        KLine(
            code="sh.x",
            trade_date=_date_series(50)[i],
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0 + i * 0.1,
            volume=1,
            amount=1.0,
        )
        for i in range(50)
    ]
    res, curve = run_ma_cross_backtest(
        klines, fast=2, slow=10, include_equity_curve=False
    )
    assert res.bars_used == 50
    assert curve == []
