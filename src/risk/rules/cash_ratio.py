"""Cash ratio risk rule."""

from __future__ import annotations

from src.risk.base import BaseRiskRule
from src.risk.models import PortfolioState, RiskCheckResult


class CashRatioMinRule(BaseRiskRule):
    """Minimum cash ratio. Params: min_cash_pct (e.g., 0.10 for 10%)."""

    def check(self, state: PortfolioState) -> RiskCheckResult:
        limit = self.params.get("min_cash_pct", 0.10)
        if state.total_equity <= 0:
            return RiskCheckResult(
                passed=True,
                rule_type="cash_ratio",
                rule_name=self.name,
                message="",
                severity="error",
            )
        cash_ratio = state.cash / state.total_equity
        if cash_ratio < limit:
            return RiskCheckResult(
                passed=False,
                rule_type="cash_ratio",
                rule_name=self.name,
                message=f"现金比例 {cash_ratio * 100:.1f}% 低于最低要求 {limit * 100:.1f}%",
                severity="error",
                context={"cash_ratio": cash_ratio, "limit": limit},
            )
        return RiskCheckResult(
            passed=True,
            rule_type="cash_ratio",
            rule_name=self.name,
            message="",
            severity="error",
        )
