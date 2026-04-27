"""Daily loss limit risk rule."""

from __future__ import annotations

from src.risk.base import BaseRiskRule
from src.risk.models import PortfolioState, RiskCheckResult


class DailyLossLimitRule(BaseRiskRule):
    """Daily loss limit. Params: max_daily_loss_pct (e.g., -0.03 for -3%)."""

    def check(self, state: PortfolioState) -> RiskCheckResult:
        limit = self.params.get("max_daily_loss_pct", -0.03)
        if state.total_equity <= 0:
            return RiskCheckResult(
                passed=True,
                rule_type="daily_loss",
                rule_name=self.name,
                message="",
                severity="error",
            )
        daily_return = state.daily_pnl / state.total_equity if state.total_equity > 0 else 0
        if daily_return <= limit:
            return RiskCheckResult(
                passed=False,
                rule_type="daily_loss",
                rule_name=self.name,
                message=f"当日收益 {daily_return * 100:.2f}% 低于限制 {limit * 100:.2f}%",
                severity="error",
                context={"daily_return": daily_return, "limit": limit},
            )
        return RiskCheckResult(
            passed=True,
            rule_type="daily_loss",
            rule_name=self.name,
            message="",
            severity="error",
        )
