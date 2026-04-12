"""因子原语单元测（路线图阶段 B）。"""

from __future__ import annotations

import pytest

from src.factors import (
    aroon,
    atr_wilder,
    donchian,
    vwap_cumulative,
    vwap_rolling,
    bollinger_bands,
    cci,
    dmi_adx_wilder,
    diff_n,
    ema,
    obv,
    kdj_k_d_j,
    mfi,
    macd_dif_dea_hist,
    pct_change_1,
    pct_change_n,
    roc,
    trix,
    true_range,
    rolling_max,
    rolling_mean,
    rolling_min,
    rolling_std,
    rolling_sum,
    rolling_zscore,
    rsi_wilder,
    williams_r,
)


def test_rolling_mean_window3():
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert rolling_mean(xs, 3) == [None, None, 2.0, 3.0, 4.0]


def test_rolling_sum_window3():
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert rolling_sum(xs, 3) == [None, None, 6.0, 9.0, 12.0]


def test_rolling_sum_empty():
    assert rolling_sum([], 3) == []


def test_rolling_sum_bad_window():
    with pytest.raises(ValueError):
        rolling_sum([1.0], 0)


def test_rolling_mean_empty():
    assert rolling_mean([], 3) == []


def test_rolling_mean_window1():
    assert rolling_mean([10.0, 20.0], 1) == [10.0, 20.0]


def test_pct_change_1():
    c = [100.0, 110.0, 99.0]
    assert pct_change_1(c)[0] is None
    assert pytest.approx(pct_change_1(c)[1]) == 10.0
    assert pytest.approx(pct_change_1(c)[2]) == (99 / 110 - 1) * 100


def test_pct_change_n():
    c = [100.0, 100.0, 100.0, 121.0]
    out = pct_change_n(c, 3)
    assert out[0] is out[1] is out[2] is None
    assert pytest.approx(out[3]) == 21.0


def test_roc_matches_pct_change_n():
    c = [10.0, 11.0, 12.0, 13.0]
    assert roc(c, 2) == pct_change_n(c, 2)


def test_roc_bad_period():
    with pytest.raises(ValueError):
        roc([1.0, 2.0], 0)


def test_trix_span1_matches_pct_change_1():
    c = [100.0, 102.0, 101.0, 103.0]
    assert trix(c, 1) == pct_change_1(c)


def test_trix_first_bar_none():
    assert trix([10.0, 11.0], 3)[0] is None


def test_trix_span_lt_1_raises():
    with pytest.raises(ValueError):
        trix([1.0], 0)


def test_true_range_two_bars():
    hi = [10.0, 12.0]
    lo = [9.0, 11.0]
    cl = [9.5, 11.5]
    assert true_range(hi, lo, cl) == [1.0, 2.5]


def test_dmi_adx_wilder_period_lt_2_raises():
    with pytest.raises(ValueError):
        dmi_adx_wilder([1.0], [1.0], [1.0], period=1)


def test_dmi_adx_wilder_length_mismatch_raises():
    with pytest.raises(ValueError):
        dmi_adx_wilder([1.0, 2.0], [1.0], [1.0, 2.0], period=2)


def test_dmi_adx_wilder_uptrend_plus_di_eventually_higher():
    n = 40
    hi = [100.0 + float(i) * 0.5 for i in range(n)]
    lo = [99.0 + float(i) * 0.5 for i in range(n)]
    cl = [99.5 + float(i) * 0.5 for i in range(n)]
    period = 5
    pdi, mdi, adx = dmi_adx_wilder(hi, lo, cl, period=period)
    assert pdi[0] is None
    first_adx = 2 * period - 2
    assert adx[first_adx] is not None
    j = n - 1
    assert pdi[j] is not None and mdi[j] is not None
    assert float(pdi[j]) > float(mdi[j])


def test_aroon_period_lt_2_raises():
    with pytest.raises(ValueError):
        aroon([1.0, 2.0], [1.0, 2.0], period=1)


def test_aroon_length_mismatch_raises():
    with pytest.raises(ValueError):
        aroon([1.0, 2.0], [1.0], period=2)


def test_aroon_period3_known_window():
    hi = [1.0, 5.0, 3.0, 4.0, 2.0]
    lo = [1.0, 2.0, 2.0, 1.0, 1.0]
    up, down, osc = aroon(hi, lo, 3)
    assert up[0] is up[1] is None
    assert down[0] is down[1] is None
    assert osc[0] is osc[1] is None
    assert up[2] == pytest.approx(200.0 / 3.0)
    assert down[2] == pytest.approx(100.0 / 3.0)
    assert osc[2] == pytest.approx(100.0 / 3.0)
    assert up[3] == pytest.approx(100.0 / 3.0)
    assert down[3] == pytest.approx(100.0)
    assert osc[3] == pytest.approx(-200.0 / 3.0)
    assert up[4] == pytest.approx(200.0 / 3.0)
    assert down[4] == pytest.approx(100.0)
    assert osc[4] == pytest.approx(-100.0 / 3.0)


def test_donchian_window_lt_1_raises():
    with pytest.raises(ValueError):
        donchian([1.0], [1.0], window=0)


def test_donchian_length_mismatch_raises():
    with pytest.raises(ValueError):
        donchian([1.0, 2.0], [1.0], window=2)


def test_vwap_cumulative_two_bars():
    hi = [10.0, 11.0]
    lo = [9.0, 10.0]
    cl = [10.0, 10.5]
    vol = [1000.0, 2000.0]
    out = vwap_cumulative(hi, lo, cl, vol)
    tp0 = (10 + 9 + 10) / 3.0
    assert out[0] == pytest.approx(tp0)
    tp1 = (11 + 10 + 10.5) / 3.0
    assert out[1] == pytest.approx((tp0 * 1000 + tp1 * 2000) / 3000.0)


def test_vwap_rolling_window2():
    hi = [1.0, 2.0, 3.0]
    lo = [0.5, 1.5, 2.5]
    cl = [1.2, 2.2, 3.2]
    vol = [10.0, 10.0, 10.0]
    out = vwap_rolling(hi, lo, cl, vol, 2)
    assert out[0] is None
    tp0 = (1.0 + 0.5 + 1.2) / 3.0
    tp1 = (2.0 + 1.5 + 2.2) / 3.0
    assert out[1] == pytest.approx((tp0 * 10 + tp1 * 10) / 20.0)


def test_vwap_negative_volume_raises():
    with pytest.raises(ValueError):
        vwap_cumulative([1.0], [1.0], [1.0], [-1.0])


def test_vwap_rolling_window_lt_1_raises():
    with pytest.raises(ValueError):
        vwap_rolling([1.0], [1.0], [1.0], [1.0], 0)


def test_donchian_window2_matches_rolling_max_min_mid():
    hi = [1.0, 3.0, 2.0, 4.0]
    lo = [0.5, 1.0, 1.5, 2.0]
    up, dn, mid = donchian(hi, lo, 2)
    assert up == [None, 3.0, 3.0, 4.0]
    assert dn == [None, 0.5, 1.0, 1.5]
    assert mid[0] is None
    assert mid[1] == pytest.approx(1.75)
    assert mid[2] == pytest.approx(2.0)
    assert mid[3] == pytest.approx(2.75)


def test_diff_n_lag3():
    xs = [10.0, 20.0, 30.0, 50.0]
    out = diff_n(xs, 3)
    assert out[0] is out[1] is out[2] is None
    assert out[3] == 40.0


def test_diff_n_order1():
    assert diff_n([1.0, 4.0, 9.0], 1) == [None, 3.0, 5.0]


def test_diff_n_bad_n():
    with pytest.raises(ValueError):
        diff_n([1.0, 2.0], 0)


def test_ema_constant_series():
    xs = [5.0, 5.0, 5.0, 5.0]
    assert ema(xs, 3) == [5.0, 5.0, 5.0, 5.0]


def test_ema_span2_first_three():
    alpha = 2.0 / 3.0
    xs = [1.0, 2.0, 3.0, 4.0]
    out = ema(xs, 2)
    assert out[0] == 1.0
    assert pytest.approx(out[1]) == alpha * 2.0 + (1.0 - alpha) * 1.0
    assert pytest.approx(out[2]) == alpha * 3.0 + (1.0 - alpha) * out[1]


def test_ema_empty():
    assert ema([], 5) == []


def test_ema_bad_span():
    with pytest.raises(ValueError):
        ema([1.0], 0)


def test_rolling_zscore_constant_window_std_zero():
    xs = [5.0, 5.0, 5.0, 5.0]
    out = rolling_zscore(xs, 3)
    assert out[0] is out[1] is None
    assert out[2] is None
    assert out[3] is None


def test_rolling_zscore_window3_peak():
    xs = [1.0, 2.0, 3.0, 4.0]
    out = rolling_zscore(xs, 3)
    assert out[0] is out[1] is None
    std2 = (2.0 / 3.0) ** 0.5
    assert pytest.approx(out[2]) == (3.0 - 2.0) / std2
    assert pytest.approx(out[3]) == (4.0 - 3.0) / std2


def test_rolling_zscore_bad_window():
    with pytest.raises(ValueError):
        rolling_zscore([1.0], 0)


def test_rsi_wilder_flat_closes():
    close = [100.0, 100.0, 100.0]
    out = rsi_wilder(close, 2)
    assert out[0] is out[1] is None
    assert out[2] == 50.0


def test_rsi_wilder_uptrend_period2():
    close = [10.0, 11.0, 12.0, 13.0]
    out = rsi_wilder(close, 2)
    assert out[0] is out[1] is None
    assert out[2] == 100.0
    assert out[3] == 100.0


def test_rsi_wilder_too_short_all_none():
    assert rsi_wilder([10.0, 11.0], 2) == [None, None]


def test_rsi_wilder_bad_period():
    with pytest.raises(ValueError):
        rsi_wilder([1.0, 2.0, 3.0], 0)


def test_atr_wilder_period2():
    tr = [2.0, 4.0, 6.0]
    out = atr_wilder(tr, 2)
    assert out[0] is None
    assert out[1] == 3.0
    assert out[2] == pytest.approx((3.0 * 1.0 + 6.0) / 2.0)


def test_atr_wilder_period1_is_tr():
    assert atr_wilder([5.0, 7.0], 1) == [5.0, 7.0]


def test_atr_wilder_too_short():
    assert atr_wilder([1.0], 3) == [None]


def test_atr_wilder_bad_period():
    with pytest.raises(ValueError):
        atr_wilder([1.0, 2.0], 0)


def test_rolling_std_window3():
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    out = rolling_std(xs, 3)
    assert out[0] is out[1] is None
    # [1,2,3]: mean 2, var = ((1-2)^2+0+(3-2)^2)/3 = 2/3
    assert pytest.approx(out[2]) == (2.0 / 3.0) ** 0.5
    assert pytest.approx(out[3]) == (2.0 / 3.0) ** 0.5
    assert pytest.approx(out[4]) == (2.0 / 3.0) ** 0.5


def test_rolling_std_constant_is_zero():
    xs = [5.0, 5.0, 5.0, 5.0]
    out = rolling_std(xs, 2)
    assert out[0] is None
    assert out[1] == 0.0
    assert out[2] == 0.0
    assert out[3] == 0.0


def test_rolling_std_empty():
    assert rolling_std([], 3) == []


def test_rolling_std_window1():
    assert rolling_std([3.0, 4.0], 1) == [0.0, 0.0]


def test_rolling_std_bad_window():
    with pytest.raises(ValueError):
        rolling_std([1.0], 0)


def test_rolling_mean_bad_window():
    with pytest.raises(ValueError):
        rolling_mean([1.0], 0)


def test_pct_change_n_bad_n():
    with pytest.raises(ValueError):
        pct_change_n([1.0, 2.0], 0)


def test_rolling_max_window3():
    xs = [3.0, 1.0, 4.0, 2.0, 5.0]
    assert rolling_max(xs, 3) == [None, None, 4.0, 4.0, 5.0]


def test_rolling_min_window3():
    xs = [3.0, 1.0, 4.0, 0.5, 2.0]
    assert rolling_min(xs, 3) == [None, None, 1.0, 0.5, 0.5]


def test_rolling_max_min_window1():
    assert rolling_max([7.0, 2.0], 1) == [7.0, 2.0]
    assert rolling_min([7.0, 2.0], 1) == [7.0, 2.0]


def test_rolling_max_empty():
    assert rolling_max([], 2) == []


def test_rolling_max_bad_window():
    with pytest.raises(ValueError):
        rolling_max([1.0], 0)


def test_bollinger_bands_window3_k2():
    xs = [10.0, 11.0, 12.0, 13.0]
    mid, upper, lower = bollinger_bands(xs, 3, 2.0)
    assert mid[0] is mid[1] is None
    assert mid[2] == 11.0
    std2 = (2.0 / 3.0) ** 0.5
    assert upper[2] == pytest.approx(11.0 + 2.0 * std2)
    assert lower[2] == pytest.approx(11.0 - 2.0 * std2)


def test_bollinger_bands_flat_series_std_zero():
    xs = [5.0, 5.0, 5.0, 5.0]
    mid, upper, lower = bollinger_bands(xs, 2, 2.0)
    assert mid[1] == 5.0
    assert upper[1] == 5.0
    assert lower[1] == 5.0


def test_bollinger_bands_bad_k():
    with pytest.raises(ValueError):
        bollinger_bands([1.0, 2.0], 2, 0.0)


def test_macd_constant_close_all_zero_hist():
    c = [100.0] * 8
    dif, dea, hist = macd_dif_dea_hist(c, 2, 4, 3)
    assert len(dif) == len(dea) == len(hist) == 8
    for i in range(8):
        assert dif[i] == pytest.approx(0.0, abs=1e-9)
        assert dea[i] == pytest.approx(0.0, abs=1e-9)
        assert hist[i] == pytest.approx(0.0, abs=1e-9)


def test_macd_fast_ge_slow_raises():
    with pytest.raises(ValueError):
        macd_dif_dea_hist([1.0, 2.0, 3.0], 3, 3, 2)


def test_kdj_flat_range_rsv_50():
    hi = [10.0, 10.0, 10.0]
    lo = [10.0, 10.0, 10.0]
    cl = [10.0, 10.0, 10.0]
    k, d, j = kdj_k_d_j(hi, lo, cl, n=2, m1=3, m2=3)
    assert k[0] is d[0] is j[0] is None
    assert k[1] == d[1] == j[1] == pytest.approx(50.0)
    assert k[2] == d[2] == j[2] == pytest.approx(50.0)


def test_kdj_n2_known_rsv_then_smooth():
    hi = [5.0, 10.0]
    lo = [5.0, 5.0]
    cl = [5.0, 10.0]
    k, d, j = kdj_k_d_j(hi, lo, cl, n=2, m1=3, m2=3)
    assert k[0] is None
    assert k[1] == d[1] == j[1] == pytest.approx(100.0)


def test_kdj_n_lt_2_raises():
    with pytest.raises(ValueError):
        kdj_k_d_j([1.0], [1.0], [1.0], n=1)


def test_kdj_length_mismatch_raises():
    with pytest.raises(ValueError):
        kdj_k_d_j([1.0, 2.0], [1.0], [1.0, 2.0], n=2)


def test_cci_period3_known_bar():
    hi = [10.0, 10.0, 12.0]
    lo = [10.0, 10.0, 10.0]
    cl = [10.0, 11.0, 11.0]
    out = cci(hi, lo, cl, period=3)
    assert out[0] is out[1] is None
    assert out[2] == pytest.approx(100.0, rel=1e-5)


def test_cci_flat_tp_window_returns_none():
    hi = [5.0, 5.0, 5.0]
    lo = [5.0, 5.0, 5.0]
    cl = [5.0, 5.0, 5.0]
    out = cci(hi, lo, cl, period=3)
    assert out[2] is None


def test_cci_period_lt_2_raises():
    with pytest.raises(ValueError):
        cci([1.0], [1.0], [1.0], period=1)


def test_obv_rising_falling_flat():
    c = [10.0, 11.0, 10.0, 10.0]
    v = [100, 200, 300, 400]
    o = obv(c, v)
    assert o == [100.0, 300.0, 0.0, 0.0]


def test_obv_empty():
    assert obv([], []) == []


def test_obv_volume_mismatch_raises():
    with pytest.raises(ValueError):
        obv([1.0, 2.0], [100])


def test_williams_r_period2_known():
    hi = [10.0, 12.0]
    lo = [10.0, 10.0]
    cl = [10.0, 11.0]
    out = williams_r(hi, lo, cl, period=2)
    assert out[0] is None
    assert out[1] == pytest.approx(-50.0)


def test_williams_r_flat_window_none():
    hi = [5.0, 5.0]
    lo = [5.0, 5.0]
    cl = [5.0, 5.0]
    out = williams_r(hi, lo, cl, period=2)
    assert out[1] is None


def test_williams_r_period_lt_2_raises():
    with pytest.raises(ValueError):
        williams_r([1.0], [1.0], [1.0], period=1)


def test_mfi_period2_all_tp_up_mfi_100():
    hi = [10.0, 11.0, 12.0]
    lo = [10.0, 11.0, 12.0]
    cl = [10.0, 11.0, 12.0]
    vol = [100, 100, 100]
    out = mfi(hi, lo, cl, vol, period=2)
    assert out[0] is out[1] is None
    assert out[2] == pytest.approx(100.0)


def test_mfi_flat_tp_window_none():
    hi = [5.0, 5.0, 5.0]
    lo = [5.0, 5.0, 5.0]
    cl = [5.0, 5.0, 5.0]
    vol = [100, 100, 100]
    out = mfi(hi, lo, cl, vol, period=2)
    assert out[2] is None


def test_mfi_period_lt_2_raises():
    with pytest.raises(ValueError):
        mfi([1.0], [1.0], [1.0], [1], period=1)


def test_mfi_volume_length_mismatch_raises():
    with pytest.raises(ValueError):
        mfi([1.0, 2.0], [1.0, 2.0], [1.0, 2.0], [100], period=2)
