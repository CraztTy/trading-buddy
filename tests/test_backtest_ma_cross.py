"""双均线回测纯逻辑（不连库）。"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from src.backtest.ma_cross import ma_cross_result_from_df


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
    assert equity.iloc[-1] > 1.0
    assert res.signal_changes >= 0


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
    with pytest.raises(ValueError, match="数量不足"):
        ma_cross_result_from_df(df, code="x", fast=2, slow=20)
