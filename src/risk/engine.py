"""Main risk engine."""

from __future__ import annotations

from src.risk.base import BaseRiskRule
from src.risk.models import PortfolioState, RiskCheckResult


class RiskEngine:
    """Pluggable risk engine that checks portfolio states against registered rules."""

    def __init__(self):
        self._rules: list[BaseRiskRule] = []

    def register(self, rule: BaseRiskRule) -> None:
        """Register a risk rule."""
        self._rules.append(rule)

    def check(self, state: PortfolioState) -> list[RiskCheckResult]:
        """Run all registered rules against portfolio state."""
        results: list[RiskCheckResult] = []
        for rule in self._rules:
            if rule.enabled:
                result = rule.check(state)
                results.append(result)
        return results

    def check_all_passed(self, state: PortfolioState) -> tuple[bool, list[str]]:
        """Return (all_passed, list of error messages)."""
        results = self.check(state)
        errors = [
            r.message for r in results if not r.passed and r.severity == "error"
        ]
        return len(errors) == 0, errors
