"""Sector exposure risk rule."""

from __future__ import annotations

from src.risk.base import BaseRiskRule
from src.risk.models import PortfolioState, RiskCheckResult


class SectorExposureLimitRule(BaseRiskRule):
    """Sector exposure limit. Params: max_sector_weight_pct (e.g., 0.40)."""

    def check(self, state: PortfolioState) -> RiskCheckResult:
        limit = self.params.get("max_sector_weight_pct", 0.40)
        sector_weights: dict[str, float] = {}
        for pos in state.positions:
            sector = pos.get("sector", "unknown")
            sector_weights[sector] = sector_weights.get(sector, 0) + pos.get("weight", 0)
        for sector, weight in sector_weights.items():
            if weight > limit:
                return RiskCheckResult(
                    passed=False,
                    rule_type="sector_exposure",
                    rule_name=self.name,
                    message=f"行业 {sector} 暴露 {weight * 100:.1f}% 超过上限 {limit * 100:.1f}%",
                    severity="error",
                    context={"sector": sector, "weight": weight, "limit": limit},
                )
        return RiskCheckResult(
            passed=True,
            rule_type="sector_exposure",
            rule_name=self.name,
            message="",
            severity="error",
        )
