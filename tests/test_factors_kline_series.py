"""KLine → float 列薄封装与 primitives 衔接。"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.data.models import KLine
from src.factors import kline_float_series, kline_true_range, rolling_max, rolling_min


def _bar(d: date, o: float, h: float, l: float, c: float) -> KLine:
    return KLine(
        code="sh.t",
        trade_date=d,
        open=o,
        high=h,
        low=l,
        close=c,
        volume=1000,
        amount=c * 1000,
        turnover_rate=None,
        adjust_flag="3",
    )


def test_kline_float_series_high_and_rolling_max():
    base = date(2025, 1, 1)
    rows = [
        _bar(base, 10, 12, 9, 11),
        _bar(base + timedelta(days=1), 11, 13, 10, 12),
        _bar(base + timedelta(days=2), 12, 15, 11, 14),
    ]
    highs = kline_float_series(rows, "high")
    assert highs == [12.0, 13.0, 15.0]
    mx = rolling_max(highs, 2)
    assert mx[0] is None
    assert mx[1] == 13.0
    assert mx[2] == 15.0


def test_kline_float_series_low_rolling_min():
    base = date(2025, 2, 1)
    rows = [
        _bar(base, 5, 6, 4, 5),
        _bar(base + timedelta(days=1), 5, 7, 3, 6),
        _bar(base + timedelta(days=2), 6, 8, 5, 7),
    ]
    lows = kline_float_series(rows, "low")
    mn = rolling_min(lows, 2)
    assert mn[0] is None
    assert mn[1] == 3.0
    assert mn[2] == 3.0


def test_kline_true_range_first_bar_and_gap():
    base = date(2025, 3, 1)
    rows = [
        _bar(base, 10, 12, 9, 11),
        _bar(base + timedelta(days=1), 11, 14, 12, 13),
    ]
    tr = kline_true_range(rows)
    assert tr[0] == 3.0
    assert tr[1] == max(14 - 12, abs(14 - 11), abs(12 - 11))


def test_kline_float_series_bad_column():
    with pytest.raises(ValueError, match="column"):
        kline_float_series([], "typo")  # type: ignore[arg-type]
