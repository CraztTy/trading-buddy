"""Portfolio backtest engine unit tests."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.backtest.portfolio import (
    EqualWeightScheme,
    ValueWeightScheme,
    compute_portfolio_metrics,
    compute_weights,
    run_portfolio_backtest,
)
from src.backtest.portfolio.rebalance import is_rebalance_day
from src.data.models import KLine


def _date_series(n: int, start: date | None = None) -> list[date]:
    s = start or date(2020, 1, 2)
    return [s + timedelta(days=i) for i in range(n)]


def _kline(code: str, trade_date: date, close: float, volume: int = 1000) -> KLine:
    return KLine(
        code=code,
        trade_date=trade_date,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=volume,
        amount=close * volume,
    )


# ---------------------------------------------------------------------------
# Rebalance schedule tests
# ---------------------------------------------------------------------------


def test_is_rebalance_day_first_day():
    """First trading day is always a rebalance day."""
    d = date(2020, 1, 2)
    assert is_rebalance_day(d, None, "daily") is True
    assert is_rebalance_day(d, None, "weekly") is True
    assert is_rebalance_day(d, None, "monthly") is True


def test_is_rebalance_day_daily():
    """Daily rebalances every day."""
    d1 = date(2020, 1, 2)
    d2 = date(2020, 1, 3)
    assert is_rebalance_day(d1, None, "daily") is True
    assert is_rebalance_day(d2, d1, "daily") is True


def test_is_rebalance_day_weekly():
    """Weekly rebalances on ISO week change."""
    # Jan 2 2020 is Thursday (week 1)
    d1 = date(2020, 1, 2)
    d2 = date(2020, 1, 3)  # Same week
    d3 = date(2020, 1, 6)  # Monday, week 2
    assert is_rebalance_day(d2, d1, "weekly") is False
    assert is_rebalance_day(d3, d2, "weekly") is True


def test_is_rebalance_day_monthly():
    """Monthly rebalances on month change."""
    d1 = date(2020, 1, 30)
    d2 = date(2020, 1, 31)  # Same month
    d3 = date(2020, 2, 3)  # New month
    assert is_rebalance_day(d2, d1, "monthly") is False
    assert is_rebalance_day(d3, d2, "monthly") is True


def test_is_rebalance_day_invalid_freq():
    with pytest.raises(ValueError, match="rebalance_freq"):
        is_rebalance_day(date(2020, 1, 2), None, "yearly")


# ---------------------------------------------------------------------------
# Weight scheme tests
# ---------------------------------------------------------------------------


def test_compute_weights_equal():
    """Equal weight gives 1/N to each code."""
    codes = ["a", "b", "c"]
    dates = _date_series(5)
    klines = {
        "a": [_kline("a", d, 100.0) for d in dates],
        "b": [_kline("b", d, 200.0) for d in dates],
        "c": [_kline("c", d, 300.0) for d in dates],
    }
    weights = compute_weights(codes, "equal", klines, dates[-1])
    assert len(weights) == 3
    for w in weights.values():
        assert abs(w - 1.0 / 3) < 1e-9
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_compute_weights_value_placeholder():
    """Value weight uses close * volume as proxy."""
    codes = ["a", "b"]
    dates = _date_series(5)
    klines = {
        "a": [_kline("a", d, 100.0, volume=1000) for d in dates],
        "b": [_kline("b", d, 200.0, volume=2000) for d in dates],
    }
    weights = compute_weights(codes, "value", klines, dates[-1])
    assert len(weights) == 2
    # a: 100*1000 = 100k, b: 200*2000 = 400k
    # a weight = 100k / 500k = 0.2, b weight = 0.8
    assert abs(weights["a"] - 0.2) < 1e-6
    assert abs(weights["b"] - 0.8) < 1e-6
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_compute_weights_empty_codes_raises():
    with pytest.raises(ValueError, match="empty"):
        compute_weights([], "equal", {}, date(2020, 1, 2))


def test_compute_weights_invalid_scheme_raises():
    with pytest.raises(ValueError, match="weights_scheme"):
        compute_weights(["a"], "invalid", {}, date(2020, 1, 2))


# ---------------------------------------------------------------------------
# Portfolio metrics tests
# ---------------------------------------------------------------------------


def test_compute_portfolio_metrics_basic():
    """Basic metrics for a simple upward equity curve."""
    # 10 days, equity goes from 1.0 to 1.1 (10% return)
    equity = [1.0 + i * 0.01 for i in range(10)]
    dates = _date_series(10)
    metrics = compute_portfolio_metrics(equity, dates, [])
    assert metrics.total_return_pct == pytest.approx(9.0, rel=1e-3)
    assert metrics.max_drawdown_pct == 0.0  # No drawdown in monotonic up
    assert metrics.sharpe_ratio > 0
    assert metrics.annualized_return_pct > 0


def test_compute_portfolio_metrics_with_drawdown():
    """Metrics with a drawdown."""
    equity = [1.0, 1.1, 1.05, 0.95, 1.0, 1.2]
    dates = _date_series(6)
    metrics = compute_portfolio_metrics(equity, dates, [])
    assert metrics.total_return_pct == pytest.approx(20.0, abs=1e-9)
    # Max drawdown: peak at 1.1, trough at 0.95
    expected_dd = (0.95 / 1.1 - 1.0) * 100.0
    assert abs(metrics.max_drawdown_pct - expected_dd) < 1e-6
    assert metrics.calmar_ratio > 0


def test_compute_portfolio_metrics_empty():
    """Empty equity curve returns zero metrics."""
    metrics = compute_portfolio_metrics([], [], [])
    assert metrics.total_return_pct == 0.0
    assert metrics.sharpe_ratio == 0.0


def test_compute_portfolio_metrics_turnover():
    """Turnover computed from trades."""
    trades = [
        {"trade_date": "2020-01-02", "weight_change": 0.5},
        {"trade_date": "2020-01-02", "weight_change": 0.3},
        {"trade_date": "2020-02-03", "weight_change": 0.2},
    ]
    equity = [1.0, 1.0, 1.0]
    dates = [date(2020, 1, 2), date(2020, 1, 3), date(2020, 2, 3)]
    metrics = compute_portfolio_metrics(equity, dates, trades)
    # Day 1: (0.5 + 0.3) / 2 = 0.4
    # Day 2: 0.2 / 2 = 0.1
    # Average: (0.4 + 0.1) / 2 = 0.25 = 25%
    assert abs(metrics.turnover_pct - 25.0) < 1e-6


# ---------------------------------------------------------------------------
# Core engine tests
# ---------------------------------------------------------------------------


def test_portfolio_equal_weight_two_codes():
    """Equal weight portfolio: 2 codes, both return 10%, portfolio should return ~10%."""
    n = 10
    dates = _date_series(n, start=date(2020, 1, 2))
    # Code A: 100 -> 110 (10% return)
    closes_a = [100.0 + i * 1.0 for i in range(n)]  # 100 to 109
    # Code B: 50 -> 55 (10% return)
    closes_b = [50.0 + i * 0.5 for i in range(n)]  # 50 to 54.5

    klines_dict = {
        "sh.a": [_kline("sh.a", d, c) for d, c in zip(dates, closes_a)],
        "sh.b": [_kline("sh.b", d, c) for d, c in zip(dates, closes_b)],
    }
    signals_dict = {
        "sh.a": [1.0] * n,
        "sh.b": [1.0] * n,
    }

    result = run_portfolio_backtest(
        klines_dict,
        signals_dict=signals_dict,
        weights_scheme="equal",
        rebalance_freq="monthly",
        initial_cash=1_000_000.0,
    )

    assert result.codes == ["sh.a", "sh.b"]
    assert result.bars_used == n
    # Both assets return ~9% over 10 days (100->109, 50->54.5)
    # Portfolio should have similar return
    assert result.total_return_pct > 0
    assert len(result.equity_curve) == n
    assert result.equity_curve[0]["equity"] == pytest.approx(1_000_000.0, rel=1e-9)
    # Final equity should be higher than initial
    assert result.equity_curve[-1]["equity"] > result.equity_curve[0]["equity"]


def test_portfolio_monthly_rebalance_resets_weights():
    """Monthly rebalance: weights reset on month boundary."""
    # Create data spanning two months
    dates = []
    d = date(2020, 1, 2)
    while d.month == 1:
        dates.append(d)
        d += timedelta(days=1)
    # Add a few February dates
    for i in range(5):
        dates.append(d + timedelta(days=i))

    n = len(dates)
    # Code A rises, Code B falls - weights should drift then reset
    closes_a = [100.0 + i * 2.0 for i in range(n)]
    closes_b = [100.0 - i * 1.0 for i in range(n)]

    klines_dict = {
        "sh.a": [_kline("sh.a", d, c) for d, c in zip(dates, closes_a)],
        "sh.b": [_kline("sh.b", d, c) for d, c in zip(dates, closes_b)],
    }
    signals_dict = {
        "sh.a": [1.0] * n,
        "sh.b": [1.0] * n,
    }

    result = run_portfolio_backtest(
        klines_dict,
        signals_dict=signals_dict,
        weights_scheme="equal",
        rebalance_freq="monthly",
        initial_cash=1_000_000.0,
    )

    assert result.bars_used == n
    # Should have trades (rebalance at start + month boundary)
    assert len(result.trades) > 0

    # Find first rebalance in February
    feb_trades = [t for t in result.trades if t["trade_date"].startswith("2020-02")]
    assert len(feb_trades) > 0


def test_portfolio_with_commission_reduces_cash():
    """Commission should reduce portfolio value."""
    n = 10
    dates = _date_series(n, start=date(2020, 1, 2))
    closes_a = [100.0] * n
    closes_b = [50.0] * n

    klines_dict = {
        "sh.a": [_kline("sh.a", d, c) for d, c in zip(dates, closes_a)],
        "sh.b": [_kline("sh.b", d, c) for d, c in zip(dates, closes_b)],
    }
    signals_dict = {
        "sh.a": [1.0] * n,
        "sh.b": [1.0] * n,
    }

    # With commission
    result_with_fee = run_portfolio_backtest(
        klines_dict,
        signals_dict=signals_dict,
        weights_scheme="equal",
        rebalance_freq="monthly",
        initial_cash=1_000_000.0,
        commission_rate=0.001,
        slippage_rate=0.0,
    )

    # Without commission
    result_no_fee = run_portfolio_backtest(
        klines_dict,
        signals_dict=signals_dict,
        weights_scheme="equal",
        rebalance_freq="monthly",
        initial_cash=1_000_000.0,
        commission_rate=0.0,
        slippage_rate=0.0,
    )

    # With fees, final equity should be lower (or equal if no trades)
    # Since prices are flat, the only difference is commission on rebalance
    assert result_with_fee.equity_curve[-1]["equity"] <= result_no_fee.equity_curve[-1]["equity"]
    # There should be fee records in trades
    assert all(t["fee"] > 0 for t in result_with_fee.trades)


def test_portfolio_empty_klines_raises():
    with pytest.raises(ValueError, match="klines_dict is empty"):
        run_portfolio_backtest({}, signals_dict={})


def test_portfolio_invalid_commission_raises():
    n = 5
    dates = _date_series(n)
    klines_dict = {
        "sh.a": [_kline("sh.a", d, 100.0) for d in dates],
    }
    signals_dict = {"sh.a": [1.0] * n}
    with pytest.raises(ValueError, match="commission_rate"):
        run_portfolio_backtest(
            klines_dict,
            signals_dict=signals_dict,
            commission_rate=0.1,
        )


def test_portfolio_invalid_slippage_raises():
    n = 5
    dates = _date_series(n)
    klines_dict = {
        "sh.a": [_kline("sh.a", d, 100.0) for d in dates],
    }
    signals_dict = {"sh.a": [1.0] * n}
    with pytest.raises(ValueError, match="slippage_rate"):
        run_portfolio_backtest(
            klines_dict,
            signals_dict=signals_dict,
            slippage_rate=0.1,
        )


def test_portfolio_flip_cost_cap_raises():
    n = 5
    dates = _date_series(n)
    klines_dict = {
        "sh.a": [_kline("sh.a", d, 100.0) for d in dates],
    }
    signals_dict = {"sh.a": [1.0] * n}
    with pytest.raises(ValueError, match="之和勿超过"):
        run_portfolio_backtest(
            klines_dict,
            signals_dict=signals_dict,
            commission_rate=0.05,
            slippage_rate=0.04,
        )


def test_portfolio_to_api_dict():
    """PortfolioBacktestResult.to_api_dict produces valid structure."""
    n = 5
    dates = _date_series(n, start=date(2020, 1, 2))
    klines_dict = {
        "sh.a": [_kline("sh.a", d, 100.0 + i) for i, d in enumerate(dates)],
    }
    signals_dict = {"sh.a": [1.0] * n}

    result = run_portfolio_backtest(
        klines_dict,
        signals_dict=signals_dict,
        weights_scheme="equal",
        rebalance_freq="daily",
    )

    api_dict = result.to_api_dict()
    assert "codes" in api_dict
    assert "equity_curve" in api_dict
    assert "total_return_pct" in api_dict
    assert "max_drawdown_pct" in api_dict
    assert "sharpe_ratio" in api_dict
    assert "note" in api_dict
    assert api_dict["codes"] == ["sh.a"]
    assert api_dict["weights_scheme"] == "equal"
    assert api_dict["rebalance_freq"] == "daily"


def test_portfolio_signal_zero_excludes_asset():
    """Signal of 0 should exclude an asset from the portfolio."""
    n = 5
    dates = _date_series(n, start=date(2020, 1, 2))
    klines_dict = {
        "sh.a": [_kline("sh.a", d, 100.0) for d in dates],
        "sh.b": [_kline("sh.b", d, 50.0) for d in dates],
    }
    # Signal 0 for sh.b means it should not be held
    signals_dict = {
        "sh.a": [1.0] * n,
        "sh.b": [0.0] * n,
    }

    result = run_portfolio_backtest(
        klines_dict,
        signals_dict=signals_dict,
        weights_scheme="equal",
        rebalance_freq="monthly",
    )

    # sh.b should have 0 weight in positions after rebalance
    pos_b = [p for p in result.positions_history if p["code"] == "sh.b"]
    # On first day (rebalance), weight should be 0 for sh.b
    first_day_b = [p for p in pos_b if p["trade_date"] == dates[0].isoformat()]
    assert len(first_day_b) > 0
    assert first_day_b[0]["weight"] == 0.0


def test_portfolio_three_assets_equal_weight():
    """3-asset equal weight portfolio with known returns."""
    n = 5
    dates = _date_series(n, start=date(2020, 1, 2))
    # All flat - no return, no drawdown
    klines_dict = {
        "sh.a": [_kline("sh.a", d, 100.0) for d in dates],
        "sh.b": [_kline("sh.b", d, 200.0) for d in dates],
        "sh.c": [_kline("sh.c", d, 300.0) for d in dates],
    }
    signals_dict = {c: [1.0] * n for c in klines_dict}

    result = run_portfolio_backtest(
        klines_dict,
        signals_dict=signals_dict,
        weights_scheme="equal",
        rebalance_freq="monthly",
    )

    assert len(result.codes) == 3
    # Equal weights: each gets 1/3
    # Check first rebalance day positions
    first_day = dates[0].isoformat()
    day_positions = [p for p in result.positions_history if p["trade_date"] == first_day]
    assert len(day_positions) == 3
    weights = [p["weight"] for p in day_positions]
    for w in weights:
        assert abs(w - 1.0 / 3) < 1e-4


def test_portfolio_insufficient_common_dates_raises():
    """If codes have no overlapping dates, should raise."""
    klines_dict = {
        "sh.a": [_kline("sh.a", date(2020, 1, 2), 100.0)],
        "sh.b": [_kline("sh.b", date(2020, 3, 2), 50.0)],
    }
    signals_dict = {
        "sh.a": [1.0],
        "sh.b": [1.0],
    }
    with pytest.raises(ValueError, match="Insufficient common"):
        run_portfolio_backtest(klines_dict, signals_dict=signals_dict)


def test_portfolio_with_benchmark():
    """Portfolio backtest with benchmark klines."""
    n = 10
    dates = _date_series(n, start=date(2020, 1, 2))
    closes_a = [100.0 + i * 1.0 for i in range(n)]
    closes_b = [50.0 + i * 0.5 for i in range(n)]

    klines_dict = {
        "sh.a": [_kline("sh.a", d, c) for d, c in zip(dates, closes_a)],
        "sh.b": [_kline("sh.b", d, c) for d, c in zip(dates, closes_b)],
    }
    signals_dict = {
        "sh.a": [1.0] * n,
        "sh.b": [1.0] * n,
    }
    # Flat benchmark
    bench_klines = [_kline("sh.bench", d, 100.0) for d in dates]

    result = run_portfolio_backtest(
        klines_dict,
        signals_dict=signals_dict,
        weights_scheme="equal",
        rebalance_freq="monthly",
        benchmark_klines=bench_klines,
    )

    # Beta should be near 0 for flat benchmark
    assert abs(result.benchmark_beta) < 1e-6


def test_portfolio_metrics_by_code():
    """Per-code contribution metrics are populated."""
    n = 5
    dates = _date_series(n, start=date(2020, 1, 2))
    klines_dict = {
        "sh.a": [_kline("sh.a", d, 100.0 + i * 2) for i, d in enumerate(dates)],
        "sh.b": [_kline("sh.b", d, 50.0 + i) for i, d in enumerate(dates)],
    }
    signals_dict = {
        "sh.a": [1.0] * n,
        "sh.b": [1.0] * n,
    }

    result = run_portfolio_backtest(
        klines_dict,
        signals_dict=signals_dict,
        weights_scheme="equal",
        rebalance_freq="monthly",
    )

    assert "sh.a" in result.metrics_by_code
    assert "sh.b" in result.metrics_by_code
    for code, metrics in result.metrics_by_code.items():
        assert "start_value" in metrics
        assert "end_value" in metrics
        assert "return_pct" in metrics
        assert "start_weight" in metrics
        assert "end_weight" in metrics
