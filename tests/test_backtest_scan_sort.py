"""扫描排序与 sort_by 校验。"""

import pytest

from src.backtest.scan import normalize_sort_by, sort_scan_rows_inplace


def test_normalize_sort_by_invalid():
    with pytest.raises(ValueError, match="sort_by"):
        normalize_sort_by("alpha")


def test_sort_by_excess_puts_higher_first():
    items = [
        {
            "code": "a",
            "error": None,
            "total_return_pct": 10.0,
            "excess_return_pct": 1.0,
            "buy_hold_return_pct": 9.0,
            "sharpe_ratio": 0.5,
        },
        {
            "code": "b",
            "error": None,
            "total_return_pct": 5.0,
            "excess_return_pct": 4.0,
            "buy_hold_return_pct": 1.0,
            "sharpe_ratio": 0.2,
        },
    ]
    sort_scan_rows_inplace(items, "excess_return")
    assert items[0]["code"] == "b"
    assert items[1]["code"] == "a"


def test_sort_by_ann_return():
    items = [
        {
            "code": "a",
            "error": None,
            "annualized_return_pct": 1.0,
            "total_return_pct": 0.0,
            "excess_return_pct": 0,
            "sharpe_ratio": 0,
            "sortino_ratio": 0,
            "calmar_ratio": 0,
        },
        {
            "code": "b",
            "error": None,
            "annualized_return_pct": 5.0,
            "total_return_pct": 0.0,
            "excess_return_pct": 0,
            "sharpe_ratio": 0,
            "sortino_ratio": 0,
            "calmar_ratio": 0,
        },
    ]
    sort_scan_rows_inplace(items, "ann_return")
    assert items[0]["code"] == "b"


def test_sort_by_avg_holding():
    items = [
        {
            "code": "a",
            "error": None,
            "avg_holding_return_pct": 0.5,
            "total_return_pct": 0.0,
            "excess_return_pct": 0,
            "sharpe_ratio": 0,
        },
        {
            "code": "b",
            "error": None,
            "avg_holding_return_pct": 2.0,
            "total_return_pct": 0.0,
            "excess_return_pct": 0,
            "sharpe_ratio": 0,
        },
    ]
    sort_scan_rows_inplace(items, "avg_holding")
    assert items[0]["code"] == "b"


def test_error_rows_sink():
    items = [
        {"code": "ok", "error": None, "total_return_pct": 1.0, "excess_return_pct": 0, "sharpe_ratio": 0},
        {"code": "bad", "error": "no data", "total_return_pct": None, "excess_return_pct": None, "sharpe_ratio": None},
    ]
    sort_scan_rows_inplace(items, "total_return")
    assert items[0]["code"] == "ok"
    assert items[1]["code"] == "bad"
