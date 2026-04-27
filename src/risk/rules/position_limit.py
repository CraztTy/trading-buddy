"""Position limit risk rule."""

from __future__ import annotations

from src.risk.base import BaseRiskRule
from src.risk.models import PortfolioState, RiskCheckResult


class SinglePositionLimitRule(BaseRiskRule):
    """Single position weight limit. Params: max_weight_pct (e.g., 0.30 for 30%)."""

    def check(self, state: PortfolioState) -> RiskCheckResult:
        limit = self.params.get("max_weight_pct", 0.30)
        for pos in state.positions:
            weight = pos.get("weight", 0)
            if weight > limit:
                return RiskCheckResult(
                    passed=False,
                    rule_type="position_limit",
                    rule_name=self.name,
                    message=f"{pos['code']} 仓位 {weight * 100:.1f}% 超过上限 {limit * 100:.1f}%",
                    severity="error",
                    context={"code": pos["code"], "weight": weight, "limit": limit},
                )
        return RiskCheckResult(
            passed=True,
            rule_type="position_limit",
            rule_name=self.name,
            message="",
            severity="error",
        )
