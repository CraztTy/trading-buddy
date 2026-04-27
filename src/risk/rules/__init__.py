"""Risk rules package."""

from __future__ import annotations

from src.risk.rules.cash_ratio import CashRatioMinRule
from src.risk.rules.daily_loss import DailyLossLimitRule
from src.risk.rules.max_drawdown import MaxDrawdownRule
from src.risk.rules.position_limit import SinglePositionLimitRule
from src.risk.rules.sector_exposure import SectorExposureLimitRule
from src.risk.rules.stress_test import StressTestTriggerRule
from src.risk.rules.var_limit import VaRLimitRule

RULE_REGISTRY: dict[str, type] = {
    "max_drawdown": MaxDrawdownRule,
    "position_limit": SinglePositionLimitRule,
    "sector_exposure": SectorExposureLimitRule,
    "daily_loss": DailyLossLimitRule,
    "cash_ratio": CashRatioMinRule,
    "var_limit": VaRLimitRule,
    "stress_test": StressTestTriggerRule,
}

__all__ = [
    "CashRatioMinRule",
    "DailyLossLimitRule",
    "MaxDrawdownRule",
    "RULE_REGISTRY",
    "SectorExposureLimitRule",
    "SinglePositionLimitRule",
    "StressTestTriggerRule",
    "VaRLimitRule",
]
