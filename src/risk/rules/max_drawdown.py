"""Max drawdown risk rule."""

from __future__ import annotations

from src.risk.base import BaseRiskRule
from src.risk.models import PortfolioState, RiskCheckResult


class MaxDrawdownRule(BaseRiskRule):
    """Max drawdown limit. Params: max_drawdown_pct (e.g., -0.15 for -15%)."""

    def check(self, state: PortfolioState) -> RiskCheckResult:
        if state.total_equity <= 0 or state.peak_equity <= 0:
            return RiskCheckResult(
                passed=True,
                rule_type="max_drawdown",
                rule_name=self.name,
                message="",
                severity="error",
            )
        dd = (state.total_equity - state.peak_equity) / state.peak_equity
        limit = self.params.get("max_drawdown_pct", -0.15)
        if dd <= limit:
            return RiskCheckResult(
                passed=False,
                rule_type="max_drawdown",
                rule_name=self.name,
                message=f"当前回撤 {dd * 100:.2f}% 超过限制 {limit * 100:.2f}%",
                severity="error",
                context={"current_drawdown": dd, "limit": limit},
            )
        return RiskCheckResult(
            passed=True,
            rule_type="max_drawdown",
            rule_name=self.name,
            message="",
            severity="error",
        )
