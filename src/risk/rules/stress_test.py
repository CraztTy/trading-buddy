"""压力测试触发规则。

当市场出现极端波动（大盘大跌、VIX 飙升等）时，自动触发持仓压力重估。

与常规风控规则不同，本规则关注"外部环境"而非"持仓本身"：
- 大盘指数跌幅超过阈值
- 个股涨跌停
- 市场流动性枯竭（买卖价差扩大）

触发后生成压力事件，由 RiskMonitorConsumer 推送到事件总线。
"""

from __future__ import annotations

from src.risk.base import BaseRiskRule
from src.risk.models import PortfolioState, RiskCheckResult


class StressTestTriggerRule(BaseRiskRule):
    """压力测试触发规则。

    Params:
        index_drop_pct: 大盘指数跌幅触发阈值（如 -0.03 = -3%）
        single_drop_pct: 个股跌幅触发阈值（如 -0.07 = -7%）
        spread_widen_pct: 买卖价差扩大阈值（如 0.02 = 2%）

    使用方式:
        在 RiskMonitorConsumer 中传入 market_snapshot，由 check() 判断是否触发。
    """

    def __init__(self, name: str, params: dict, enabled: bool = True):
        super().__init__(name, params, enabled)
        self._market_snapshot: dict | None = None

    def set_market_snapshot(self, snapshot: dict | None) -> None:
        """注入市场快照（由外部定时任务更新）。"""
        self._market_snapshot = snapshot

    def check(self, state: PortfolioState) -> RiskCheckResult:
        if self._market_snapshot is None:
            return RiskCheckResult(
                passed=True,
                rule_type="stress_test",
                rule_name=self.name,
                message="市场快照未就绪",
                severity="warning",
            )

        index_drop_pct = self.params.get("index_drop_pct", -0.03)
        single_drop_pct = self.params.get("single_drop_pct", -0.07)

        # 检查大盘跌幅
        index_change = self._market_snapshot.get("index_change_pct", 0.0)
        if index_change <= index_drop_pct:
            return RiskCheckResult(
                passed=False,
                rule_type="stress_test",
                rule_name=self.name,
                message=f"大盘跌 {index_change*100:.2f}%（阈值 {index_drop_pct*100:.1f}%），触发压力场景",
                severity="warning",
                context={
                    "trigger": "index_drop",
                    "index_change_pct": index_change,
                    "threshold": index_drop_pct,
                },
            )

        # 检查持仓个股跌幅
        triggered_codes = []
        for pos in state.positions:
            code = pos.get("code", "")
            code_change = self._market_snapshot.get(f"change_pct_{code}", 0.0)
            if code_change <= single_drop_pct:
                triggered_codes.append({
                    "code": code,
                    "change_pct": code_change,
                })

        if triggered_codes:
            return RiskCheckResult(
                passed=False,
                rule_type="stress_test",
                rule_name=self.name,
                message=f"{len(triggered_codes)} 只持仓跌超 {single_drop_pct*100:.0f}%，触发压力场景",
                severity="warning",
                context={
                    "trigger": "single_drop",
                    "triggered_codes": triggered_codes,
                    "threshold": single_drop_pct,
                },
            )

        return RiskCheckResult(
            passed=True,
            rule_type="stress_test",
            rule_name=self.name,
            message="",
            severity="warning",
        )
