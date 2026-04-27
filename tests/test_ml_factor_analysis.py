"""Tests for src.ml.factor_analysis.FactorAnalyzer.

Coverage:
- IC: spearman / pearson, monotonic factor -> high |IC|, random factor -> ~0 IC
- IC summary: mean / std / IR / positive_pct / significant_pct
- Quantile returns: monotonic factor -> long-short > 0
- Quantile summary: monotonicity score
- Turnover: stable factor -> low turnover, shuffled -> high turnover
- analyze_factor: integration smoke test
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.ml.factor_analysis import FactorAnalyzer


def _build_panel(
    n_dates: int = 30,
    n_codes: int = 30,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Construct synthetic factor + forward return panel.

    Forward return is correlated with factor (rho ~ 0.5) so IC should be positive.
    Panel format: index=date, columns=code.
    """
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=n_dates, freq="D")
    codes = [f"S{i:03d}" for i in range(n_codes)]

    factor = pd.DataFrame(
        rng.normal(size=(n_dates, n_codes)),
        index=dates,
        columns=codes,
    )
    noise = pd.DataFrame(
        rng.normal(size=(n_dates, n_codes)) * 0.5,
        index=dates,
        columns=codes,
    )
    forward = factor + noise  # rho between factor and forward ~ 1/sqrt(1+0.25) ~= 0.89
    return factor, forward


# ---------------------------------------------------------------------------
# IC
# ---------------------------------------------------------------------------


def test_information_coefficient_positive_for_correlated_factor():
    factor, forward = _build_panel(n_dates=20, n_codes=40)
    ic = FactorAnalyzer.information_coefficient(factor, forward, method="spearman")
    assert len(ic) == 20
    assert ic.mean() > 0.5  # strong positive correlation


def test_information_coefficient_near_zero_for_random_factor():
    rng = np.random.default_rng(0)
    dates = pd.date_range("2024-01-01", periods=15, freq="D")
    codes = [f"S{i}" for i in range(30)]
    factor = pd.DataFrame(rng.normal(size=(15, 30)), index=dates, columns=codes)
    forward = pd.DataFrame(rng.normal(size=(15, 30)), index=dates, columns=codes)
    ic = FactorAnalyzer.information_coefficient(factor, forward)
    assert abs(ic.mean()) < 0.2  # random -> small mean IC


def test_information_coefficient_pearson_method():
    factor, forward = _build_panel(n_dates=10, n_codes=30)
    ic_p = FactorAnalyzer.information_coefficient(factor, forward, method="pearson")
    ic_s = FactorAnalyzer.information_coefficient(factor, forward, method="spearman")
    assert len(ic_p) == 10
    assert len(ic_s) == 10
    # Both should agree on sign for strongly correlated panel
    assert ic_p.mean() > 0
    assert ic_s.mean() > 0


def test_information_coefficient_skips_dates_with_few_samples():
    """Days with fewer than 10 valid samples should be skipped."""
    dates = pd.date_range("2024-01-01", periods=3, freq="D")
    codes = [f"S{i}" for i in range(8)]
    factor = pd.DataFrame(np.arange(24.0).reshape(3, 8), index=dates, columns=codes)
    forward = pd.DataFrame(np.arange(24.0).reshape(3, 8), index=dates, columns=codes)
    ic = FactorAnalyzer.information_coefficient(factor, forward)
    # Each day has only 8 samples (< 10) -> all skipped
    assert len(ic) == 0


# ---------------------------------------------------------------------------
# IC summary
# ---------------------------------------------------------------------------


def test_ic_summary_basic_stats():
    series = pd.Series([0.05, 0.03, -0.01, 0.04, 0.02])
    stats = FactorAnalyzer.ic_summary(series)
    assert stats["count"] == 5
    assert stats["ic_mean"] == pytest.approx(0.026, abs=1e-3)
    assert stats["ic_std"] > 0
    # ic_ir is computed from rounded outputs of ic_mean/ic_std; allow 0.01 tolerance
    assert stats["ic_ir"] == pytest.approx(stats["ic_mean"] / stats["ic_std"], abs=0.01)
    assert stats["ic_positive_pct"] == pytest.approx(0.8, abs=1e-3)
    # series = [0.05, 0.03, -0.01, 0.04, 0.02]; |IC| > 0.02 strictly: 0.05/0.03/0.04 -> 3/5 = 0.6
    assert stats["ic_significant_pct"] == pytest.approx(0.6, abs=1e-3)


def test_ic_summary_empty_series():
    stats = FactorAnalyzer.ic_summary(pd.Series([], dtype=float))
    assert stats == {
        "ic_mean": 0.0,
        "ic_std": 0.0,
        "ic_ir": 0.0,
        "ic_positive_pct": 0.0,
        "ic_significant_pct": 0.0,
        "count": 0,
    }


def test_ic_summary_zero_std_returns_zero_ir():
    """All identical IC values -> std=0, IR should be 0 (not inf)."""
    stats = FactorAnalyzer.ic_summary(pd.Series([0.05, 0.05, 0.05]))
    assert stats["ic_std"] == 0.0
    assert stats["ic_ir"] == 0.0


# ---------------------------------------------------------------------------
# Quantile returns
# ---------------------------------------------------------------------------


def test_quantile_returns_strong_factor_long_short_positive():
    factor, forward = _build_panel(n_dates=30, n_codes=50)
    q_df = FactorAnalyzer.quantile_returns(factor, forward, n_quantiles=5)
    summary = FactorAnalyzer.quantile_summary(q_df)
    assert summary["long_short_return"] > 0  # high factor -> high return
    assert summary["monotonicity"] > 0.5  # roughly monotonic


def test_quantile_returns_skips_when_too_few_samples():
    """n_quantiles * 2 = 10; with 8 codes, all dates skipped."""
    dates = pd.date_range("2024-01-01", periods=5, freq="D")
    codes = [f"S{i}" for i in range(8)]
    factor = pd.DataFrame(np.random.rand(5, 8), index=dates, columns=codes)
    forward = pd.DataFrame(np.random.rand(5, 8), index=dates, columns=codes)
    q_df = FactorAnalyzer.quantile_returns(factor, forward, n_quantiles=5)
    assert q_df.empty


def test_quantile_summary_empty():
    summary = FactorAnalyzer.quantile_summary(pd.DataFrame())
    assert summary["long_short_return"] == 0.0
    assert summary["monotonicity"] == 0.0
    assert summary["quantile_means"] == {}


# ---------------------------------------------------------------------------
# Turnover
# ---------------------------------------------------------------------------


def test_factor_turnover_stable_factor_low_turnover():
    """Constant ranking across days -> turnover = 0."""
    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    codes = [f"S{i}" for i in range(20)]
    # Every day same factor values -> top/bottom set unchanged
    factor = pd.DataFrame(
        np.tile(np.arange(20.0), (10, 1)),
        index=dates,
        columns=codes,
    )
    turnover = FactorAnalyzer.factor_turnover(factor, n_quantiles=5)
    assert len(turnover) == 9  # n - 1 (first day no prev)
    assert turnover.mean() == 0.0


def test_factor_turnover_shuffled_factor_high_turnover():
    """Shuffled ranks each day -> turnover > 0."""
    rng = np.random.default_rng(7)
    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    codes = [f"S{i}" for i in range(30)]
    factor = pd.DataFrame(
        rng.normal(size=(10, 30)),
        index=dates,
        columns=codes,
    )
    turnover = FactorAnalyzer.factor_turnover(factor, n_quantiles=5)
    assert turnover.mean() > 0.3  # random factor has high turnover


# ---------------------------------------------------------------------------
# analyze_factor (integration)
# ---------------------------------------------------------------------------


def test_analyze_factor_full_report():
    factor, forward = _build_panel(n_dates=20, n_codes=40)
    analyzer = FactorAnalyzer()
    report = analyzer.analyze_factor(factor, forward, n_quantiles=5)

    assert "ic" in report
    assert "quantile" in report
    assert "turnover_mean" in report
    assert "assessment" in report

    assert report["ic"]["count"] == 20
    assert report["ic"]["ic_mean"] > 0
    assert report["quantile"]["long_short_return"] > 0
    assert isinstance(report["assessment"], str)
    # Strong synthetic correlation should grade well
    assert ("优秀" in report["assessment"]) or ("良好" in report["assessment"])
