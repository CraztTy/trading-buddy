"""Portfolio weight computation schemes."""

from __future__ import annotations

from datetime import date

from src.common import get_logger
from src.data.models import KLine

logger = get_logger(__name__)


class EqualWeightScheme:
    """Equal weight: 1/N for each code."""

    name = "equal"


class ValueWeightScheme:
    """Value (market-cap) weight placeholder."""

    name = "value"


VALID_SCHEMES = frozenset({EqualWeightScheme.name, ValueWeightScheme.name})


def compute_weights(
    codes: list[str],
    scheme: str,
    klines_dict: dict[str, list[KLine]],
    trade_date: date,
) -> dict[str, float]:
    """Compute target portfolio weights for the given codes.

    Args:
        codes: List of asset codes.
        scheme: Weight scheme name - "equal" or "value".
        klines_dict: Mapping from code to KLine list.
        trade_date: The trade date for which weights are computed.

    Returns:
        Mapping from code to weight (sum to 1.0).

    Raises:
        ValueError: If scheme is unsupported or no valid codes.
    """
    scheme_norm = scheme.strip().lower()
    if scheme_norm not in VALID_SCHEMES:
        raise ValueError(
            f"weights_scheme must be one of {sorted(VALID_SCHEMES)}, got {scheme!r}"
        )

    if not codes:
        raise ValueError("codes list is empty")

    # Filter to codes that have klines data
    valid_codes = [c for c in codes if c in klines_dict and klines_dict[c]]
    if not valid_codes:
        raise ValueError("no valid klines data for any code")

    n = len(valid_codes)
    if scheme_norm == "equal":
        weight = 1.0 / n
        return {c: weight for c in valid_codes}

    # scheme_norm == "value"
    # Placeholder: market-cap weighted using close * volume as proxy
    market_caps: dict[str, float] = {}
    for c in valid_codes:
        klines = klines_dict[c]
        # Find the latest kline on or before trade_date
        latest = None
        for k in reversed(klines):
            if k.trade_date <= trade_date:
                latest = k
                break
        if latest is None:
            continue
        # Use close * volume as a proxy for market cap
        proxy = float(latest.close) * float(latest.volume)
        market_caps[c] = proxy

    if not market_caps:
        logger.warning("No market cap proxies available; falling back to equal weight")
        weight = 1.0 / n
        return {c: weight for c in valid_codes}

    total = sum(market_caps.values())
    if total < 1e-12:
        weight = 1.0 / len(market_caps)
        return {c: weight for c in market_caps}

    return {c: v / total for c, v in market_caps.items()}
