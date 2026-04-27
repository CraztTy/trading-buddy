"""VaR 限额风控规则。

基于历史模拟法计算组合 VaR，当 VaR 超过总权益的设定比例时触发告警。

注意：本规则依赖外部传入的 var_result（由 RiskMonitorConsumer 定期计算后注入），
避免在 check() 中同步查询 K 线数据（可能导致阻塞）。
"""

from __future__ import annotations

from src.risk.base import BaseRiskRule
from src.risk.models import PortfolioState, RiskCheckResult


class VaRLimitRule(BaseRiskRule):
    """VaR 限额规则。

    Params:
        max_var_pct: VaR 占组合总权益的最大比例（如 0.02 = 2%）
        confidence: 置信度（0.95 或 0.99）

    使用方式:
        在 RiskMonitorConsumer 中定期计算 VaR，通过 set_var_result() 注入。
    """

    def __init__(self, name: str, params: dict, enabled: bool = True):
        super().__init__(name, params, enabled)
        self._var_result: dict | None = None

    def set_var_result(self, var_result: dict | None) -> None:
        """注入 VaR 计算结果（由外部定时任务更新）。"""
        self._var_result = var_result

    def check(self, state: PortfolioState) -> RiskCheckResult:
        max_var_pct = self.params.get("max_var_pct", 0.02)
        confidence = self.params.get("confidence", 0.95)

        var_key = f"var_{int(confidence * 100)}"
        cvar_key = f"cvar_{int(confidence * 100)}"

        if self._var_result is None:
            return RiskCheckResult(
                passed=True,
                rule_type="var_limit",
                rule_name=self.name,
                message="VaR 尚未计算",
                severity="warning",
            )

        var_value = self._var_result.get(var_key, 0.0)
        # var_value 是负数（损失），取绝对值
        var_abs = abs(var_value)

        if state.total_equity <= 0:
            return RiskCheckResult(
                passed=True,
                rule_type="var_limit",
                rule_name=self.name,
                message="",
                severity="error",
            )

        var_pct = var_abs  # var_value 已经是收益率
        limit_pct = max_var_pct

        if var_pct >= limit_pct:
            cvar_value = abs(self._var_result.get(cvar_key, 0.0))
            return RiskCheckResult(
                passed=False,
                rule_type="var_limit",
                rule_name=self.name,
                message=f"VaR({int(confidence*100)}%) {var_pct*100:.2f}% 超过限额 {limit_pct*100:.2f}%",
                severity="error",
                context={
                    "var_pct": var_pct,
                    "limit_pct": limit_pct,
                    "cvar_pct": cvar_value,
                    "confidence": confidence,
                },
            )

        return RiskCheckResult(
            passed=True,
            rule_type="var_limit",
            rule_name=self.name,
            message="",
            severity="error",
        )
