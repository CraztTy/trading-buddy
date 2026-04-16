"""涨停检测工具单元测试。"""

from __future__ import annotations

from datetime import date

from src.data.models import KLine, StockType
from src.strategies.limit_up_utils import get_limit_up_pct, is_limit_up


def _kline(close: float, pre_close: float | None = None, pct_change: float | None = None) -> KLine:
    return KLine(
        code="sh.test",
        trade_date=date(2025, 1, 1),
        open=pre_close or close - 0.1,
        high=close + 0.1,
        low=close - 0.1,
        close=close,
        pre_close=pre_close,
        volume=1000,
        amount=close * 1000,
        pct_change=pct_change,
    )


def test_get_limit_up_pct() -> None:
    assert get_limit_up_pct(StockType.COMMON) == 10.0
    assert get_limit_up_pct(StockType.STAR) == 20.0
    assert get_limit_up_pct(StockType.GROWTH) == 20.0
    assert get_limit_up_pct(StockType.BEIJING) == 30.0
    assert get_limit_up_pct(StockType.ST) == 5.0


def test_is_limit_up_by_pre_close() -> None:
    # 主板涨停：10.0 -> 11.0 (+10%)
    k = _kline(close=11.0, pre_close=10.0)
    assert is_limit_up(k, StockType.COMMON) is True

    # 未涨停：10.0 -> 10.9 (+9%)
    k = _kline(close=10.9, pre_close=10.0)
    assert is_limit_up(k, StockType.COMMON) is False

    # ST 涨停：10.0 -> 10.5 (+5%)
    k = _kline(close=10.5, pre_close=10.0)
    assert is_limit_up(k, StockType.ST) is True

    # 创业板涨停：10.0 -> 12.0 (+20%)
    k = _kline(close=12.0, pre_close=10.0)
    assert is_limit_up(k, StockType.GROWTH) is True


def test_is_limit_up_by_pct_change_fallback() -> None:
    # pre_close 缺失时回退到 pct_change
    k = _kline(close=11.0, pre_close=None, pct_change=10.0)
    assert is_limit_up(k, StockType.COMMON) is True

    k = _kline(close=10.9, pre_close=None, pct_change=9.0)
    assert is_limit_up(k, StockType.COMMON) is False
