"""Tests for src.ml.feature_engine.AutoFeatureEngine."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.ml.feature_engine import AutoFeatureEngine, generate_features


def _build_ohlcv(n: int = 100, seed: int = 0) -> pd.DataFrame:
    """Synthetic price/volume series with positive prices."""
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, size=n))
    close = np.maximum(close, 1.0)  # keep positive for log returns
    high = close * (1 + rng.uniform(0, 0.02, size=n))
    low = close * (1 - rng.uniform(0, 0.02, size=n))
    open_ = (high + low) / 2
    volume = rng.integers(1000, 10000, size=n).astype(float)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume}
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_rejects_non_dataframe_input():
    engine = AutoFeatureEngine()
    with pytest.raises(TypeError, match="pandas DataFrame"):
        engine.fit_transform([1, 2, 3])


def test_rejects_missing_base_columns():
    df = pd.DataFrame({"open": [1.0, 2.0]})
    engine = AutoFeatureEngine(base_columns=("close",))
    with pytest.raises(ValueError, match="missing required base_columns"):
        engine.fit(df)


@pytest.mark.parametrize("attr,bad_value", [
    ("rolling_windows", (1,)),
    ("lags", (0,)),
    ("diff_periods", (-1,)),
    ("log_return_periods", (0,)),
])
def test_rejects_invalid_window_params(attr, bad_value):
    df = _build_ohlcv()
    kwargs = {attr: bad_value}
    engine = AutoFeatureEngine(**kwargs)
    with pytest.raises(ValueError):
        engine.fit(df)


def test_rejects_unknown_rolling_stat():
    df = _build_ohlcv()
    engine = AutoFeatureEngine(include_rolling_stats=("variance",))
    with pytest.raises(ValueError, match="Unknown rolling stat"):
        engine.fit(df)


# ---------------------------------------------------------------------------
# Feature generation
# ---------------------------------------------------------------------------


def test_default_config_generates_expected_columns():
    df = _build_ohlcv()
    engine = AutoFeatureEngine()  # defaults: close-only, 3 windows, 4 stats
    out = engine.fit_transform(df)

    # Original columns retained
    for col in ("open", "high", "low", "close", "volume"):
        assert col in out.columns

    # Default config: close x [mean,std,max,min] x [5,10,20] = 12 rolling
    # + 3 zscore + 2 lags + 2 diffs + 3 log_returns = 22 features
    new_cols = [c for c in out.columns if c not in df.columns]
    assert len(new_cols) == 22
    assert all(c.startswith("close_") for c in new_cols)


def test_multiple_base_columns():
    df = _build_ohlcv()
    engine = AutoFeatureEngine(base_columns=("close", "volume"))
    out = engine.fit_transform(df)
    new_cols = [c for c in out.columns if c not in df.columns]
    close_features = [c for c in new_cols if c.startswith("close_")]
    volume_features = [c for c in new_cols if c.startswith("volume_")]
    assert len(close_features) == 22
    assert len(volume_features) == 22


def test_rolling_mean_correctness():
    df = pd.DataFrame({"close": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]})
    engine = AutoFeatureEngine(
        rolling_windows=(3,),
        include_rolling_stats=("mean",),
        lags=(1,),
        diff_periods=(1,),
        log_return_periods=(1,),
        include_zscore=False,
    )
    out = engine.fit_transform(df)
    # close_rolling_mean_3 starts at index 2: mean of [1,2,3]=2, [2,3,4]=3, ...
    expected = [None, None, 2.0, 3.0, 4.0, 5.0, 6.0]
    for i, exp in enumerate(expected):
        if exp is None:
            assert pd.isna(out["close_rolling_mean_3"].iloc[i])
        else:
            assert out["close_rolling_mean_3"].iloc[i] == pytest.approx(exp)


def test_lag_correctness():
    df = pd.DataFrame({"close": [1.0, 2.0, 3.0, 4.0, 5.0]})
    engine = AutoFeatureEngine(
        rolling_windows=(2,),
        lags=(1, 2),
        diff_periods=(1,),
        log_return_periods=(1,),
        include_zscore=False,
        include_rolling_stats=("mean",),
    )
    out = engine.fit_transform(df)
    # lag_1: shifted by 1 -> [NaN, 1, 2, 3, 4]
    assert pd.isna(out["close_lag_1"].iloc[0])
    assert out["close_lag_1"].iloc[1] == pytest.approx(1.0)
    assert out["close_lag_1"].iloc[4] == pytest.approx(4.0)
    # lag_2: [NaN, NaN, 1, 2, 3]
    assert pd.isna(out["close_lag_2"].iloc[1])
    assert out["close_lag_2"].iloc[2] == pytest.approx(1.0)


def test_diff_correctness():
    df = pd.DataFrame({"close": [1.0, 2.0, 4.0, 7.0, 11.0]})
    engine = AutoFeatureEngine(
        rolling_windows=(2,),
        lags=(1,),
        diff_periods=(1,),
        log_return_periods=(1,),
        include_zscore=False,
        include_rolling_stats=("mean",),
    )
    out = engine.fit_transform(df)
    # diff_1: [NaN, 1, 2, 3, 4]
    expected = [None, 1.0, 2.0, 3.0, 4.0]
    for i, exp in enumerate(expected):
        if exp is None:
            assert pd.isna(out["close_diff_1"].iloc[i])
        else:
            assert out["close_diff_1"].iloc[i] == pytest.approx(exp)


def test_log_return_correctness():
    df = pd.DataFrame({"close": [1.0, np.e, np.e ** 2]})  # log diffs = 1.0, 1.0
    engine = AutoFeatureEngine(
        rolling_windows=(2,),
        lags=(1,),
        diff_periods=(1,),
        log_return_periods=(1,),
        include_zscore=False,
        include_rolling_stats=("mean",),
    )
    out = engine.fit_transform(df)
    assert pd.isna(out["close_log_return_1"].iloc[0])
    assert out["close_log_return_1"].iloc[1] == pytest.approx(1.0, abs=1e-10)
    assert out["close_log_return_1"].iloc[2] == pytest.approx(1.0, abs=1e-10)


def test_zscore_correctness():
    """Z-score: at each rolling window, value should be (x - mean) / std."""
    df = pd.DataFrame({"close": np.arange(1.0, 11.0)})  # 1..10
    engine = AutoFeatureEngine(
        rolling_windows=(5,),
        lags=(1,),
        diff_periods=(1,),
        log_return_periods=(1,),
        include_zscore=True,
        include_rolling_stats=("mean",),
    )
    out = engine.fit_transform(df)
    # At index 4: window [1,2,3,4,5], mean=3, std=sqrt(2), z = (5-3)/sqrt(2) ~ 1.414
    expected = (5.0 - 3.0) / np.sqrt(2.0)
    assert out["close_zscore_5"].iloc[4] == pytest.approx(expected, abs=1e-6)


def test_zscore_handles_constant_window():
    """Constant window -> std=0, zscore should be NaN (not inf)."""
    df = pd.DataFrame({"close": [5.0] * 10})
    engine = AutoFeatureEngine(
        rolling_windows=(3,),
        lags=(1,),
        diff_periods=(1,),
        log_return_periods=(1,),
        include_zscore=True,
        include_rolling_stats=("mean",),
    )
    out = engine.fit_transform(df)
    # std=0 -> zscore should be NaN
    for i in range(2, 10):
        val = out["close_zscore_3"].iloc[i]
        assert pd.isna(val) or val == 0.0


def test_drop_na_removes_warmup_rows():
    df = _build_ohlcv(n=50)
    engine = AutoFeatureEngine(rolling_windows=(20,), drop_na=True)
    out = engine.fit_transform(df)
    # Largest window is 20, so first 19 rows dropped at minimum
    assert len(out) < len(df)
    # No NaN in remaining rows
    assert not out.isna().any().any()


# ---------------------------------------------------------------------------
# fit / transform / fit_transform contract
# ---------------------------------------------------------------------------


def test_feature_names_requires_fit():
    engine = AutoFeatureEngine()
    with pytest.raises(RuntimeError, match="fit"):
        _ = engine.feature_names


def test_feature_names_after_fit():
    df = _build_ohlcv()
    engine = AutoFeatureEngine().fit(df)
    names = engine.feature_names
    assert len(names) == 22
    assert all(n.startswith("close_") for n in names)


def test_transform_without_fit_works():
    """transform() does not strictly require fit() (sklearn-loose contract)."""
    df = _build_ohlcv()
    engine = AutoFeatureEngine()
    # Direct transform should still produce features
    out = engine.transform(df)
    assert "close_rolling_mean_5" in out.columns


def test_fit_transform_equals_fit_then_transform():
    df = _build_ohlcv()
    e1 = AutoFeatureEngine()
    out1 = e1.fit_transform(df)
    e2 = AutoFeatureEngine()
    e2.fit(df)
    out2 = e2.transform(df)
    pd.testing.assert_frame_equal(out1, out2)


def test_generate_features_helper():
    df = _build_ohlcv()
    out = generate_features(df, base_columns=("close",), rolling_windows=(5,))
    assert "close_rolling_mean_5" in out.columns
