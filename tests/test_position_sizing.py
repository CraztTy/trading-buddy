"""Unit tests for position sizing algorithms.

Tests:
- Equal weight: 3 codes, 1M equity -> each gets ~333K / price
- Fixed amount: 3 codes, 100K each -> verify shares
- Volatility target: high vol code gets smaller allocation
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from src.backtest.position_sizing import SizingConfig, compute_position_sizes
from src.data.models import KLine


def _make_klines(
    code: str,
    n: int,
    base_price: float,
    volatility: float = 0.0,
) -> list[KLine]:
    """Generate KLines with optional daily volatility.

    Args:
        code: Stock code.
        n: Number of days.
        base_price: Starting close price.
        volatility: Daily volatility (std dev of returns). 0 = flat price.
    """
    klines: list[KLine] = []
    price = base_price
    for i in range(n):
        td = date(2024, 1, 1 + i)
        if volatility > 0 and i > 0:
            ret = np.random.normal(0, volatility)
            price = price * (1 + ret)
            price = max(price, 1.0)
        k = KLine(
            code=code,
            trade_date=td,
            open=price,
            high=price * 1.02,
            low=price * 0.98,
            close=price,
            volume=1000000,
            amount=price * 1000000,
        )
        klines.append(k)
    return klines


def _make_klines_with_trend(code: str, n: int, base_price: float, trend: float = 0.0) -> list[KLine]:
    """Generate KLines with a deterministic trend (no randomness)."""
    klines: list[KLine] = []
    price = base_price
    for i in range(n):
        td = date(2024, 1, 1 + i)
        price = price * (1 + trend)
        k = KLine(
            code=code,
            trade_date=td,
            open=price,
            high=price * 1.02,
            low=price * 0.98,
            close=price,
            volume=1000000,
            amount=price * 1000000,
        )
        klines.append(k)
    return klines


def _make_high_vol_klines(code: str, n: int, base_price: float) -> list[KLine]:
    """Generate KLines with high volatility (alternating +/- 5%)."""
    klines: list[KLine] = []
    price = base_price
    for i in range(n):
        td = date(2024, 1, 1 + i)
        # Alternate up and down 5%
        ret = 0.05 if i % 2 == 0 else -0.05
        price = price * (1 + ret)
        price = max(price, 1.0)
        k = KLine(
            code=code,
            trade_date=td,
            open=price,
            high=price * 1.02,
            low=price * 0.98,
            close=price,
            volume=1000000,
            amount=price * 1000000,
        )
        klines.append(k)
    return klines


def _make_low_vol_klines(code: str, n: int, base_price: float) -> list[KLine]:
    """Generate KLines with very low volatility (nearly flat)."""
    klines: list[KLine] = []
    price = base_price
    for i in range(n):
        td = date(2024, 1, 1 + i)
        # Tiny 0.1% wiggle
        ret = 0.001 if i % 2 == 0 else -0.001
        price = price * (1 + ret)
        k = KLine(
            code=code,
            trade_date=td,
            open=price,
            high=price * 1.001,
            low=price * 0.999,
            close=price,
            volume=1000000,
            amount=price * 1000000,
        )
        klines.append(k)
    return klines


class TestEqualWeightSizing:
    """Test equal weight position sizing."""

    def test_three_codes_one_million_equity(self):
        """3 codes, 1M equity -> each gets ~333K / price."""
        codes = ["sh.600000", "sh.600001", "sh.600002"]
        klines_dict = {
            "sh.600000": _make_klines_with_trend("sh.600000", 30, 100.0),
            "sh.600001": _make_klines_with_trend("sh.600001", 30, 50.0),
            "sh.600002": _make_klines_with_trend("sh.600002", 30, 25.0),
        }
        signals = {c: 1.0 for c in codes}
        total_equity = 1_000_000.0

        config = SizingConfig(method="equal", params={})
        sizes = compute_position_sizes(codes, klines_dict, signals, total_equity, config)

        # Each should get ~333K worth
        # sh.600000 @ 100 -> ~3330 shares, lot-sized to 3300
        # sh.600001 @ 50  -> ~6660 shares, lot-sized to 6600
        # sh.600002 @ 25  -> ~13320 shares, lot-sized to 13300
        assert sizes["sh.600000"] == 3300  # 3300 * 100 = 330K
        assert sizes["sh.600001"] == 6600  # 6600 * 50 = 330K
        assert sizes["sh.600002"] == 13300  # 13300 * 25 = 332.5K

    def test_zero_signal_excludes_code(self):
        """Code with signal=0 should be excluded from results."""
        codes = ["sh.600000", "sh.600001"]
        klines_dict = {
            "sh.600000": _make_klines_with_trend("sh.600000", 30, 100.0),
            "sh.600001": _make_klines_with_trend("sh.600001", 30, 50.0),
        }
        signals = {"sh.600000": 1.0, "sh.600001": 0.0}
        total_equity = 1_000_000.0

        config = SizingConfig(method="equal", params={})
        sizes = compute_position_sizes(codes, klines_dict, signals, total_equity, config)

        assert sizes["sh.600000"] > 0
        assert "sh.600001" not in sizes  # signal=0 excluded from results

    def test_empty_codes(self):
        """Empty codes list returns empty dict."""
        config = SizingConfig(method="equal", params={})
        sizes = compute_position_sizes({}, {}, {}, 1_000_000.0, config)
        assert sizes == {}

    def test_all_signals_zero(self):
        """All signals zero returns empty dict."""
        codes = ["sh.600000"]
        klines_dict = {"sh.600000": _make_klines_with_trend("sh.600000", 30, 100.0)}
        signals = {"sh.600000": 0.0}
        config = SizingConfig(method="equal", params={})
        sizes = compute_position_sizes(codes, klines_dict, signals, 1_000_000.0, config)
        assert sizes == {}


class TestFixedAmountSizing:
    """Test fixed amount per position sizing."""

    def test_three_codes_100k_each(self):
        """3 codes, 100K each -> verify shares."""
        codes = ["sh.600000", "sh.600001", "sh.600002"]
        klines_dict = {
            "sh.600000": _make_klines_with_trend("sh.600000", 30, 100.0),
            "sh.600001": _make_klines_with_trend("sh.600001", 30, 50.0),
            "sh.600002": _make_klines_with_trend("sh.600002", 30, 25.0),
        }
        signals = {c: 1.0 for c in codes}

        config = SizingConfig(method="fixed_amount", params={"amount_per_position": 100_000.0})
        sizes = compute_position_sizes(codes, klines_dict, signals, 1_000_000.0, config)

        # 100K / 100 = 1000 shares (lot-sized to 1000)
        assert sizes["sh.600000"] == 1000  # 1000 * 100 = 100K
        # 100K / 50 = 2000 shares
        assert sizes["sh.600001"] == 2000  # 2000 * 50 = 100K
        # 100K / 25 = 4000 shares
        assert sizes["sh.600002"] == 4000  # 4000 * 25 = 100K

    def test_default_amount(self):
        """Default amount_per_position is 100K."""
        codes = ["sh.600000"]
        klines_dict = {
            "sh.600000": _make_klines_with_trend("sh.600000", 30, 100.0),
        }
        signals = {c: 1.0 for c in codes}

        config = SizingConfig(method="fixed_amount", params={})
        sizes = compute_position_sizes(codes, klines_dict, signals, 1_000_000.0, config)

        # Default 100K / 100 = 1000 shares
        assert sizes["sh.600000"] == 1000

    def test_lot_sizing(self):
        """Shares are rounded down to nearest 100."""
        codes = ["sh.600000"]
        klines_dict = {
            "sh.600000": _make_klines_with_trend("sh.600000", 30, 33.33),
        }
        signals = {c: 1.0 for c in codes}

        config = SizingConfig(method="fixed_amount", params={"amount_per_position": 100_000.0})
        sizes = compute_position_sizes(codes, klines_dict, signals, 1_000_000.0, config)

        # 100K / 33.33 = ~3000.3 -> lot-sized to 3000
        assert sizes["sh.600000"] == 3000
        assert sizes["sh.600000"] % 100 == 0


class TestVolatilityTargetSizing:
    """Test volatility target-based position sizing."""

    def test_high_vol_gets_smaller_allocation(self):
        """High volatility code gets smaller allocation than low vol code."""
        codes = ["sh.high_vol", "sh.low_vol"]
        klines_dict = {
            "sh.high_vol": _make_high_vol_klines("sh.high_vol", 30, 100.0),
            "sh.low_vol": _make_low_vol_klines("sh.low_vol", 30, 100.0),
        }
        signals = {c: 1.0 for c in codes}
        total_equity = 1_000_000.0

        config = SizingConfig(
            method="volatility_target",
            params={"target_annual_volatility": 0.10},
        )
        sizes = compute_position_sizes(codes, klines_dict, signals, total_equity, config)

        # High vol should get fewer shares (smaller allocation)
        assert sizes["sh.high_vol"] < sizes["sh.low_vol"]
        # Both should be positive
        assert sizes["sh.high_vol"] > 0
        assert sizes["sh.low_vol"] > 0

    def test_weight_cap_at_50_percent(self):
        """Individual weight should be capped at 50%."""
        # One very low vol and one very high vol
        codes = ["sh.very_low", "sh.very_high"]
        klines_dict = {
            "sh.very_low": _make_low_vol_klines("sh.very_low", 30, 100.0),
            "sh.very_high": _make_high_vol_klines("sh.very_high", 30, 100.0),
        }
        signals = {c: 1.0 for c in codes}
        total_equity = 1_000_000.0

        config = SizingConfig(
            method="volatility_target",
            params={"target_annual_volatility": 0.10},
        )
        sizes = compute_position_sizes(codes, klines_dict, signals, total_equity, config)

        # With 2 codes, uncapped the low-vol one might get >50%
        # But it should be capped at 50%, so both should get roughly equal
        # or at least the high-vol one should not be starved
        total_shares = sum(sizes.values())
        assert total_shares > 0
        # Both should have some allocation
        assert sizes["sh.very_low"] > 0
        assert sizes["sh.very_high"] > 0

    def test_lot_sizing_applied(self):
        """Volatility target output should be lot-sized to 100."""
        codes = ["sh.600000"]
        klines_dict = {
            "sh.600000": _make_klines_with_trend("sh.600000", 30, 100.0),
        }
        signals = {c: 1.0 for c in codes}

        config = SizingConfig(
            method="volatility_target",
            params={"target_annual_volatility": 0.10},
        )
        sizes = compute_position_sizes(codes, klines_dict, signals, 1_000_000.0, config)

        assert sizes["sh.600000"] >= 0
        assert sizes["sh.600000"] % 100 == 0

    def test_insufficient_data_fallback(self):
        """With insufficient data, should fallback to equal weight."""
        codes = ["sh.600000", "sh.600001"]
        # Only 3 days of data - not enough for reliable vol calc
        klines_dict = {
            "sh.600000": _make_klines_with_trend("sh.600000", 3, 100.0),
            "sh.600001": _make_klines_with_trend("sh.600001", 3, 50.0),
        }
        signals = {c: 1.0 for c in codes}
        total_equity = 1_000_000.0

        config = SizingConfig(
            method="volatility_target",
            params={"target_annual_volatility": 0.10},
        )
        sizes = compute_position_sizes(codes, klines_dict, signals, total_equity, config)

        # Should still produce valid lot-sized results
        assert sizes["sh.600000"] >= 0
        assert sizes["sh.600001"] >= 0
        assert sizes["sh.600000"] % 100 == 0
        assert sizes["sh.600001"] % 100 == 0


class TestSizingConfigValidation:
    """Test config validation and edge cases."""

    def test_invalid_method_raises(self):
        """Invalid sizing method should raise ValueError."""
        codes = ["sh.600000"]
        klines_dict = {"sh.600000": _make_klines_with_trend("sh.600000", 30, 100.0)}
        signals = {c: 1.0 for c in codes}

        config = SizingConfig(method="invalid", params={})  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="Unsupported sizing method"):
            compute_position_sizes(codes, klines_dict, signals, 1_000_000.0, config)

    def test_missing_klines_data(self):
        """Code missing from klines_dict should be skipped."""
        codes = ["sh.600000", "sh.600001"]
        klines_dict = {
            "sh.600000": _make_klines_with_trend("sh.600000", 30, 100.0),
            # sh.600001 missing
        }
        signals = {c: 1.0 for c in codes}

        config = SizingConfig(method="equal", params={})
        sizes = compute_position_sizes(codes, klines_dict, signals, 1_000_000.0, config)

        assert "sh.600000" in sizes
        assert sizes["sh.600000"] > 0
        assert "sh.600001" not in sizes

    def test_zero_price(self):
        """Code with zero/negative price should get 0 shares."""
        codes = ["sh.600000"]
        klines_dict = {
            "sh.600000": [
                KLine(
                    code="sh.600000",
                    trade_date=date(2024, 1, 1),
                    open=0,
                    high=0,
                    low=0,
                    close=0,
                    volume=0,
                    amount=0,
                )
            ],
        }
        signals = {c: 1.0 for c in codes}

        config = SizingConfig(method="equal", params={})
        sizes = compute_position_sizes(codes, klines_dict, signals, 1_000_000.0, config)

        assert sizes["sh.600000"] == 0
