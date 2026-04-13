"""``src/factors/cross_section.compute_cross_section_row`` 纯函数契约。"""

from __future__ import annotations

from datetime import date

import pytest

from src.data.models import KLine
from src.factors.cross_section import compute_cross_section_row
from src.factors.primitives import pct_change_n


def _bar(code: str, d: date, close: float) -> KLine:
    return KLine(
        code=code,
        trade_date=d,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=100,
        amount=close * 100,
        turnover_rate=None,
        pct_change=None,
    )


def test_compute_cross_section_row_empty_or_bad_period() -> None:
    as_of = date(2024, 1, 5)
    assert compute_cross_section_row([], as_of, 1) is None
    assert compute_cross_section_row([_bar("sh.x", as_of, 1.0)], as_of, 0) is None


def test_compute_cross_section_row_last_bar_must_match_as_of() -> None:
    as_of = date(2024, 1, 5)
    rows = [_bar("sh.x", date(2024, 1, 4), 1.0), _bar("sh.x", date(2024, 1, 5), 2.0)]
    assert compute_cross_section_row(rows, date(2024, 1, 6), 1) is None


def test_compute_cross_section_row_matches_pct_change_n_tail() -> None:
    as_of = date(2024, 6, 11)
    period = 2
    klines = [
        _bar("sh.z", date(2024, 6, 9), 8.0),
        _bar("sh.z", date(2024, 6, 10), 9.0),
        _bar("sh.z", as_of, 10.0),
    ]
    hit = compute_cross_section_row(klines, as_of, period)
    assert hit is not None
    assert hit.code == "sh.z"
    assert hit.close == pytest.approx(10.0)
    assert hit.meta_bars == 3
    closes = [float(k.close) for k in klines]
    assert hit.ret_pct == pct_change_n(closes, period)[-1]
    assert hit.ret_pct == pytest.approx((10.0 / 8.0 - 1.0) * 100.0)
