"""Risk management rule engine for Trading Buddy."""

from __future__ import annotations

from src.risk.engine import RiskEngine
from src.risk.models import RiskCheckResult


def register_rule(engine: RiskEngine, rule: "BaseRiskRule") -> None:
    """Helper to register a rule on an engine."""
    engine.register(rule)


__all__ = [
    "register_rule",
    "RiskCheckResult",
    "RiskEngine",
]
