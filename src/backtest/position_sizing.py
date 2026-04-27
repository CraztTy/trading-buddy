"""Position sizing algorithms for portfolio backtest.

Supports:
- equal: Equal weight across all positions
- fixed_amount: Fixed CNY amount per position
- volatility_target: Target annual volatility-based sizing
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

from src.common import get_logger
from src.data.models import KLine

logger = get_logger(__name__)


@dataclass
class SizingConfig:
    """Configuration for position sizing."""

    method: Literal["equal", "fixed_amount", "volatility_target"]
    params: dict


def _compute_20d_realized_vol(klines: list[KLine]) -> float:
    """Compute annualized realized volatility from 20-day daily returns.

    Returns annualized std dev of daily returns (sqrt(252) scaling).
    If insufficient data, returns a high default (1.0 = 100%).
    """
    if len(klines) < 5:
        return 1.0

    # Use last up to 20 days of close prices
    closes = np.array([float(k.close) for k in klines[-20:]], dtype=float)
    if len(closes) < 2:
        return 1.0

    # Daily returns
    rets = np.diff(closes) / closes[:-1]
    if len(rets) < 2:
        return 1.0

    # Annualized volatility
    vol = float(np.std(rets, ddof=1) * math.sqrt(252))
    return max(vol, 1e-6)  # avoid zero


def _get_latest_price(klines: list[KLine]) -> float:
    """Get the most recent close price."""
    if not klines:
        return 0.0
    return float(klines[-1].close)


def compute_position_sizes(
    codes: list[str],
    klines_dict: dict[str, list[KLine]],
    signals: dict[str, float],
    total_equity: float,
    config: SizingConfig,
) -> dict[str, int]:
    """Return code -> number of shares for each position.

    Args:
        codes: List of asset codes.
        klines_dict: Mapping from code to KLine list.
        signals: Mapping from code to signal value (0=flat, 1=full long).
        total_equity: Total portfolio equity to allocate.
        config: Sizing configuration.

    Returns:
        Mapping from code to number of shares (lot-sized to 100).
    """
    method = config.method
    params = config.params or {}

    # Filter to active codes (signal > 0) with data
    active_codes = [
        c for c in codes
        if c in klines_dict and klines_dict[c] and signals.get(c, 0.0) > 0
    ]

    if not active_codes:
        return {}

    if method == "equal":
        return _sizing_equal(active_codes, klines_dict, total_equity)

    if method == "fixed_amount":
        amount_per_position = float(params.get("amount_per_position", 100_000.0))
        return _sizing_fixed_amount(active_codes, klines_dict, amount_per_position)

    if method == "volatility_target":
        target_annual_vol = float(params.get("target_annual_volatility", 0.10))
        return _sizing_volatility_target(
            active_codes, klines_dict, total_equity, target_annual_vol
        )

    raise ValueError(f"Unsupported sizing method: {method!r}")


def _lot_size(qty: float) -> int:
    """Round quantity down to nearest 100-share lot."""
    return max(0, int(math.floor(qty / 100.0)) * 100)


def _sizing_equal(
    codes: list[str],
    klines_dict: dict[str, list[KLine]],
    total_equity: float,
) -> dict[str, int]:
    """Equal weight: total_equity / N / price for each position."""
    n = len(codes)
    if n == 0:
        return {}

    equity_per_position = total_equity / n
    result: dict[str, int] = {}
    for code in codes:
        price = _get_latest_price(klines_dict[code])
        if price <= 0:
            result[code] = 0
            continue
        qty = _lot_size(equity_per_position / price)
        result[code] = qty
    return result


def _sizing_fixed_amount(
    codes: list[str],
    klines_dict: dict[str, list[KLine]],
    amount_per_position: float,
) -> dict[str, int]:
    """Fixed amount per position: amount_per_position / price shares each."""
    result: dict[str, int] = {}
    for code in codes:
        price = _get_latest_price(klines_dict[code])
        if price <= 0:
            result[code] = 0
            continue
        qty = _lot_size(amount_per_position / price)
        result[code] = qty
    return result


def _sizing_volatility_target(
    codes: list[str],
    klines_dict: dict[str, list[KLine]],
    total_equity: float,
    target_annual_vol: float,
) -> dict[str, int]:
    """Target volatility-based sizing.

    1. Compute 20-day realized volatility for each code
    2. Position weight = target_vol / (code_vol * sqrt(252))
       (This gives the notional weight that would produce target volatility)
    3. Normalize so sum of weights = 1.0
    4. Cap individual weight at 0.5 to avoid extreme allocations
    """
    if not codes:
        return {}

    # Compute volatility for each code
    vols: dict[str, float] = {}
    for code in codes:
        klines = klines_dict[code]
        vols[code] = _compute_20d_realized_vol(klines)

    # Compute raw weights: target_vol / (code_vol)
    # Note: vols are already annualized, so weight = target / vol
    raw_weights: dict[str, float] = {}
    for code in codes:
        vol = vols[code]
        if vol > 1e-12:
            raw_weights[code] = target_annual_vol / vol
        else:
            raw_weights[code] = 0.0

    if not raw_weights or sum(raw_weights.values()) < 1e-12:
        # Fallback to equal weight
        return _sizing_equal(codes, klines_dict, total_equity)

    # Normalize to sum = 1.0
    total_raw = sum(raw_weights.values())
    weights = {c: w / total_raw for c, w in raw_weights.items()}

    # Cap individual weight at 0.5
    max_weight = 0.5
    capped = False
    for code in weights:
        if weights[code] > max_weight:
            weights[code] = max_weight
            capped = True

    if capped:
        # Renormalize after capping
        total_w = sum(weights.values())
        if total_w > 1e-12:
            weights = {c: w / total_w for c, w in weights.items()}

    # Convert weights to shares
    result: dict[str, int] = {}
    for code in codes:
        price = _get_latest_price(klines_dict[code])
        if price <= 0:
            result[code] = 0
            continue
        target_value = total_equity * weights[code]
        qty = _lot_size(target_value / price)
        result[code] = qty

    return result
