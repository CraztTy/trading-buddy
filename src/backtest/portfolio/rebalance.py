"""Rebalance schedule utilities."""

from __future__ import annotations

from datetime import date


def is_rebalance_day(
    trade_date: date,
    prev_trade_date: date | None,
    freq: str,
) -> bool:
    """Determine if the given trade_date is a rebalance day.

    Args:
        trade_date: Current trading date.
        prev_trade_date: Previous trading date (None on first day).
        freq: Rebalance frequency - "daily", "weekly", or "monthly".

    Returns:
        True if rebalance should occur on trade_date.

    Raises:
        ValueError: If freq is not one of the supported values.
    """
    freq_norm = freq.strip().lower()
    if freq_norm not in ("daily", "weekly", "monthly"):
        raise ValueError(f"rebalance_freq must be 'daily', 'weekly', or 'monthly', got {freq!r}")

    if prev_trade_date is None:
        # First trading day is always a rebalance day
        return True

    if freq_norm == "daily":
        return True

    if freq_norm == "weekly":
        # Rebalance on the first trading day of each ISO week
        return trade_date.isocalendar().week != prev_trade_date.isocalendar().week

    # freq_norm == "monthly"
    # Rebalance on the first trading day of each month
    return trade_date.month != prev_trade_date.month
