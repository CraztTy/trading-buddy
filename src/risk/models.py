"""Risk data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass
class PortfolioState:
    """Current portfolio state for risk checking."""

    cash: float
    total_equity: float
    positions: list[dict] = field(default_factory=list)
    trade_date: date | None = None
    daily_pnl: float = 0.0
    peak_equity: float = 0.0


@dataclass
class RiskCheckResult:
    """Result of a single risk rule check."""

    passed: bool
    rule_type: str
    rule_name: str
    message: str
    severity: str  # "error" | "warning"
    context: dict[str, Any] | None = None
