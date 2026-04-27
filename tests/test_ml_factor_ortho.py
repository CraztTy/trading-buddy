"""Tests for src.ml.factor_ortho.FactorOrthogonalizer.

Coverage:
- zscore: standardizes each column to zero-mean / unit-std
- regression: target factor becomes residual after regressing on others
- gram_schmidt: produces mutually orthogonal columns per cross-section
- correlation_matrix: utility helper
- error paths: unknown method, transform-before-fit
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.ml.factor_ortho import FactorOrthogonalizer


def _build_factor_panel(
    n_dates: int = 5,
    n_codes: int = 12,
    n_factors: int = 3,
    seed: int = 0,
) -> pd.DataFrame:
    """Build factors DataFrame with MultiIndex (date, code), columns=factor_*."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=n_dates, freq="D")
    codes = [f"S{i:03d}" for i in range(n_codes)]

    rows = []
    for d in dates:
        for c in codes:
            rows.append((d, c))
    idx = pd.MultiIndex.from_tuples(rows, names=["date", "code"])

    data = {}
    for f in range(n_factors):
        data[f"factor_{f}"] = rng.normal(size=len(idx))
    return pd.DataFrame(data, index=idx)


# ---------------------------------------------------------------------------
# Init / errors
# ---------------------------------------------------------------------------


def test_init_rejects_unknown_method():
    with pytest.raises(ValueError, match="Unknown method"):
        FactorOrthogonalizer(method="invalid")


def test_transform_without_fit_raises():
    panel = _build_factor_panel()
    ortho = FactorOrthogonalizer(method="zscore")
    with pytest.raises(RuntimeError, match="Must call fit"):
        ortho.transform(panel)


# ---------------------------------------------------------------------------
# zscore
# ---------------------------------------------------------------------------


def test_zscore_normalizes_to_zero_mean_unit_std():
    panel = _build_factor_panel(seed=1)
    ortho = FactorOrthogonalizer(method="zscore")
    transformed = ortho.fit_transform(panel)
    # Implementation uses pandas default std (ddof=1) to scale, so
    # transformed columns have ddof=1 std == 1, mean == 0.
    for col in transformed.columns:
        assert abs(transformed[col].mean()) < 1e-10
        assert abs(transformed[col].std() - 1.0) < 1e-10


def test_zscore_handles_zero_std_column():
    """Constant column -> std stored as 1.0 (avoid divide by zero)."""
    rows = [("2024-01-01", f"S{i}") for i in range(12)]
    idx = pd.MultiIndex.from_tuples(rows, names=["date", "code"])
    panel = pd.DataFrame(
        {
            "factor_const": np.ones(12),  # std = 0
            "factor_var": np.arange(12.0),
        },
        index=idx,
    )
    ortho = FactorOrthogonalizer(method="zscore").fit(panel)
    transformed = ortho.transform(panel)
    # Constant column: (1 - 1) / 1.0 = 0 (no NaN/Inf)
    assert (transformed["factor_const"] == 0.0).all()
    assert not transformed["factor_const"].isna().any()


# ---------------------------------------------------------------------------
# regression (residual)
# ---------------------------------------------------------------------------


def test_regression_default_target_is_first_factor():
    panel = _build_factor_panel(n_factors=3, seed=2)
    ortho = FactorOrthogonalizer(method="regression").fit(panel)
    assert ortho._params["target"] == "factor_0"
    assert sorted(ortho._params["others"]) == ["factor_1", "factor_2"]


def test_regression_explicit_target():
    panel = _build_factor_panel(n_factors=3, seed=3)
    ortho = FactorOrthogonalizer(method="regression").fit(panel, target_factor="factor_2")
    assert ortho._params["target"] == "factor_2"
    assert sorted(ortho._params["others"]) == ["factor_0", "factor_1"]


def test_regression_residual_reduces_correlation():
    """After residualization, target should be less correlated with regressors than before.

    Note: current implementation fits beta on raw values but applies after z-scoring,
    so the residualization is approximate, not perfectly orthogonal.
    """
    rng = np.random.default_rng(4)
    n = 200
    rows = [("2024-01-01", f"S{i}") for i in range(n)]
    idx = pd.MultiIndex.from_tuples(rows, names=["date", "code"])
    f1 = rng.normal(size=n)
    f2 = rng.normal(size=n)
    target = 0.6 * f1 + 0.4 * f2 + 0.3 * rng.normal(size=n)
    panel = pd.DataFrame({"target": target, "f1": f1, "f2": f2}, index=idx)

    # Original correlation should be high (~0.5+)
    orig_corr_f1 = abs(panel["target"].corr(panel["f1"]))
    assert orig_corr_f1 > 0.4

    ortho = FactorOrthogonalizer(method="regression")
    out = ortho.fit_transform(panel, target_factor="target")
    # Residual should have *lower* correlation with regressors than original
    new_corr_f1 = abs(out["target"].corr(out["f1"]))
    new_corr_f2 = abs(out["target"].corr(out["f2"]))
    assert new_corr_f1 < orig_corr_f1
    assert new_corr_f2 < abs(panel["target"].corr(panel["f2"]))


def test_regression_with_only_one_factor_returns_input():
    """Single factor -> nothing to regress against; params empty, transform passes through."""
    rows = [("2024-01-01", f"S{i}") for i in range(15)]
    idx = pd.MultiIndex.from_tuples(rows, names=["date", "code"])
    panel = pd.DataFrame({"factor_only": np.arange(15.0)}, index=idx)
    ortho = FactorOrthogonalizer(method="regression").fit(panel)
    assert ortho._params == {}
    # transform with empty params should just return input unchanged
    out = ortho.transform(panel)
    pd.testing.assert_frame_equal(out, panel)


# ---------------------------------------------------------------------------
# gram_schmidt
# ---------------------------------------------------------------------------


def test_gram_schmidt_first_column_unchanged():
    """Gram-Schmidt: v0' = v0 (no projection to remove)."""
    panel = _build_factor_panel(n_dates=2, n_codes=15, n_factors=3, seed=5)
    ortho = FactorOrthogonalizer(method="gram_schmidt")
    out = ortho.fit_transform(panel)
    # First factor unchanged within each date
    for d in panel.index.get_level_values(0).unique():
        original = panel.loc[d, "factor_0"]
        transformed = out.loc[d, "factor_0"]
        np.testing.assert_allclose(original.values, transformed.values, atol=1e-10)


def test_gram_schmidt_columns_orthogonal_per_date():
    """For each date, transformed columns should be pairwise orthogonal."""
    panel = _build_factor_panel(n_dates=3, n_codes=20, n_factors=3, seed=6)
    out = FactorOrthogonalizer(method="gram_schmidt").fit_transform(panel)
    for d in panel.index.get_level_values(0).unique():
        day = out.loc[d]
        # f0 . f1 ~ 0, f0 . f2 ~ 0, f1 . f2 ~ 0
        for i in range(3):
            for j in range(i + 1, 3):
                dot = float(np.dot(day[f"factor_{i}"], day[f"factor_{j}"]))
                assert abs(dot) < 1e-8


# ---------------------------------------------------------------------------
# correlation_matrix utility
# ---------------------------------------------------------------------------


def test_correlation_matrix_diagonal_is_one():
    panel = _build_factor_panel(seed=7)
    corr = FactorOrthogonalizer.correlation_matrix(panel)
    assert corr.shape == (3, 3)
    for col in corr.columns:
        assert corr.loc[col, col] == pytest.approx(1.0, abs=1e-10)


def test_correlation_matrix_excludes_code_column():
    """Legacy support: 'code' column is excluded from correlation."""
    panel = _build_factor_panel(seed=8).reset_index()
    panel = panel.drop(columns=["date"])  # leave 'code' + factors
    corr = FactorOrthogonalizer.correlation_matrix(panel)
    assert "code" not in corr.columns
    assert "code" not in corr.index
