"""Base risk rule class."""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.risk.models import PortfolioState, RiskCheckResult


class BaseRiskRule(ABC):
    """Abstract base class for risk rules."""

    def __init__(self, name: str, params: dict, enabled: bool = True):
        self.name = name
        self.params = params
        self.enabled = enabled
        self.rule_type = self.__class__.__name__.replace("Rule", "").lower()

    @abstractmethod
    def check(self, state: PortfolioState) -> RiskCheckResult:
        """Check the portfolio state against this rule."""
        pass
