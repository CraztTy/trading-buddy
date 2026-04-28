"""实时风控监控消费者 — 基于行情变化的持仓风险持续检查。

盘中持续监控（事中）：
- 行情变化触发持仓风险重估
- 定期 VaR / CVaR 计算（每小时或每隔 N 个事件）
- 压力场景监控（大盘大跌、持仓个股暴跌）
- 实时风控状态缓存（供 API 查询）
- 集成风控规则引擎（支持数据库配置规则）

用法:
    consumer = RiskMonitorConsumer()
    await consumer.start()
"""

from __future__ import annotations

import asyncio
import time
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.common import get_logger
from src.data.storage.database import get_database
from src.data.storage.models import RiskRuleModel
from src.events.consumer import EventConsumer
from src.events.models import BaseEvent, EventType, RiskEvent
from src.events.publisher import EventPublisher
from src.risk.defaults import DEFAULT_RULE_CONFIGS, build_engine_from_configs
from src.risk.engine import RiskEngine
from src.risk.models import PortfolioState
from src.risk.var_calculator import calculate_var_historical

logger = get_logger("risk_monitor_consumer")

# 默认风控阈值
_DEFAULT_MAX_DRAWDOWN_PCT = 0.10
_DEFAULT_DAILY_LOSS_PCT = -7.0

# VaR 计算间隔（秒）
_VAR_CALC_INTERVAL = 300  # 5 分钟

# 压力场景阈值
_STRESS_INDEX_DROP_PCT = -0.03
_STRESS_SINGLE_DROP_PCT = -0.07

# 风控规则刷新间隔（秒）- 从数据库重新加载规则
_RULE_REFRESH_INTERVAL = 3600  # 1 小时


class RiskMonitorConsumer(EventConsumer):
    """实时风控监控消费者。

    订阅 market_data_change 事件，检查持仓风险。
    集成风控规则引擎，支持从数据库动态加载规则配置。
    """

    def __init__(self):
        super().__init__(
            name="risk_monitor",
            event_types=["market_data_change"],
            batch_size=50,
            poll_interval=1.0,
        )
        self._publisher = EventPublisher()

        # 持仓缓存: code -> {"avg_cost": float, "quantity": int, "max_price": float, "sector": str}
        self._positions: dict[str, dict[str, Any]] = {}

        # 实时风控状态（供 API 查询）
        self._risk_state: dict[str, Any] = {
            "last_update": None,
            "drawdowns": {},
            "daily_changes": {},
            "var_result": None,
            "stress_active": False,
            "alerts": [],
            "engine_enabled": True,
            "last_rule_refresh": None,
        }

        # 市场快照: code -> {"price": float, "change_pct": float, "pre_close": float}
        self._market_snapshot: dict[str, dict[str, Any]] = {}

        # VaR 计算上次时间
        self._last_var_calc = 0.0

        # 规则刷新上次时间
        self._last_rule_refresh = 0.0

        # 风控引擎（延迟初始化）
        self._engine: RiskEngine | None = None

        # 最大告警保留数量
        self._max_alerts = 100

    # ------------------------------------------------------------------
    # 事件处理
    # ------------------------------------------------------------------

    async def handle(self, event: BaseEvent) -> None:
        """处理行情变化事件，检查风险。"""
        if event.event_type.value != "market_data_change":
            return

        payload = event.payload
        code = payload.get("code", "").strip().lower()
        price = float(payload.get("price", 0))
        change_pct = float(payload.get("change_pct", 0))
        pre_close = float(payload.get("pre_close", 0))

        if not code or price <= 0:
            return

        # 更新市场快照
        self._market_snapshot[code] = {
            "price": price,
            "change_pct": change_pct,
            "pre_close": pre_close,
            "timestamp": time.time(),
        }

        # 定期刷新风控规则
        await self._refresh_rules_if_needed()

        # 检查持仓风险
        position = self._positions.get(code)
        if position is not None:
            await self._check_drawdown(code, price, position)
            await self._check_daily_loss(code, price, position, change_pct)

            # 使用风控引擎进行全面检查
            await self._check_with_engine(code, price, position)

        # 检查压力场景（大盘/个股暴跌）
        await self._check_stress_scenario(code, change_pct)

        # 定期 VaR 计算
        now = time.time()
        if now - self._last_var_calc >= _VAR_CALC_INTERVAL:
            await self._calculate_var()
            self._last_var_calc = now

        # 更新风控状态时间戳
        self._risk_state["last_update"] = time.time()

    # ------------------------------------------------------------------
    # 规则刷新
    # ------------------------------------------------------------------

    async def _refresh_rules_if_needed(self) -> None:
        """定期从数据库刷新风控规则配置。"""
        now = time.time()
        if now - self._last_rule_refresh >= _RULE_REFRESH_INTERVAL:
            await self._load_rules_from_db()
            self._last_rule_refresh = now
            self._risk_state["last_rule_refresh"] = now
            logger.info("risk rules refreshed from database")

    async def _load_rules_from_db(self) -> None:
        """从数据库加载风控规则配置。"""
        try:
            db = get_database()
            async with db.session() as session:
                stmt = select(RiskRuleModel).where(RiskRuleModel.user_id.is_(None))
                result = await session.execute(stmt)
                rules = result.scalars().all()

                if rules:
                    configs = [
                        {
                            "rule_type": r.rule_type,
                            "name": r.name,
                            "params": r.params,
                            "enabled": r.enabled,
                        }
                        for r in rules
                    ]
                    self._engine = build_engine_from_configs(configs)
                else:
                    # 无数据库规则，使用默认配置
                    self._engine = build_engine_from_configs(DEFAULT_RULE_CONFIGS)

                self._risk_state["engine_enabled"] = True
        except Exception as e:
            logger.error("failed to load rules from db: %s", e)
            # 数据库不可用时，使用内存中的默认规则
            if self._engine is None:
                self._engine = build_engine_from_configs(DEFAULT_RULE_CONFIGS)

    # ------------------------------------------------------------------
    # 风控引擎检查
    # ------------------------------------------------------------------

    async def _check_with_engine(self, code: str, price: float, position: dict[str, Any]) -> None:
        """使用风控引擎进行全面风险检查。"""
        if self._engine is None:
            return

        try:
            # 构建组合状态（当前只包含触发事件的标的）
            total_equity = position.get("quantity", 0) * price
            positions = [
                {
                    "code": code,
                    "quantity": position.get("quantity", 0),
                    "avg_price": position.get("avg_cost", 0),
                    "market_value": total_equity,
                    "weight": 1.0,  # 单个标的权重为 100%
                    "sector": position.get("sector", "unknown"),
                }
            ]

            state = PortfolioState(
                cash=0.0,
                total_equity=total_equity,
                positions=positions,
                trade_date=date.today(),
                daily_pnl=(price - position.get("avg_cost", 0)) * position.get("quantity", 0),
                peak_equity=position.get("max_price", 0) * position.get("quantity", 0),
            )

            results = self._engine.check(state)
            for result in results:
                if not result.passed:
                    severity = "violation" if result.severity == "error" else "warning"
                    await self._publish_risk_event(
                        rule_name=result.rule_name,
                        rule_type=result.rule_type,
                        detail=result.message,
                        context=result.context or {},
                        severity=severity,
                    )
                    logger.warning("engine rule violated: %s - %s", result.rule_name, result.message)

        except Exception as e:
            logger.error("engine check failed: %s", e)

    # ------------------------------------------------------------------
    # 持仓管理
    # ------------------------------------------------------------------

    def update_position(
        self,
        code: str,
        quantity: int,
        avg_cost: float,
        sector: str | None = None,
    ) -> None:
        """更新持仓信息（由交易模块调用）。"""
        code = code.strip().lower()
        existing = self._positions.get(code)
        current_max_price = avg_cost if existing is None else max(
            existing.get("max_price", avg_cost), avg_cost
        )
        self._positions[code] = {
            "quantity": quantity,
            "avg_cost": avg_cost,
            "max_price": current_max_price,
            "sector": sector or existing.get("sector") if existing else "unknown",
        }

    def remove_position(self, code: str) -> None:
        """移除持仓。"""
        code = code.strip().lower()
        self._positions.pop(code, None)
        # 同时清理相关的风险状态
        self._risk_state["drawdowns"].pop(code, None)
        self._risk_state["daily_changes"].pop(code, None)

    def clear_all_positions(self) -> None:
        """清空所有持仓（日终结算时调用）。"""
        self._positions.clear()
        self._risk_state["drawdowns"].clear()
        self._risk_state["daily_changes"].clear()

    def get_risk_state(self) -> dict[str, Any]:
        """获取当前实时风控状态（供 API 查询）。"""
        return {
            **self._risk_state,
            "positions_count": len(self._positions),
            "monitored_codes": list(self._positions.keys()),
            "snapshot_count": len(self._market_snapshot),
        }

    # ------------------------------------------------------------------
    # 风险检查
    # ------------------------------------------------------------------

    async def _check_drawdown(
        self,
        code: str,
        price: float,
        position: dict[str, Any],
    ) -> None:
        """检查回撤风险。"""
        avg_cost = position["avg_cost"]
        max_price = max(position.get("max_price", avg_cost), price)
        position["max_price"] = max_price

        if max_price <= 0 or avg_cost <= 0:
            return

        drawdown_pct = (max_price - price) / max_price

        # 更新状态
        self._risk_state["drawdowns"][code] = {
            "drawdown_pct": round(drawdown_pct, 4),
            "max_price": max_price,
            "current_price": price,
            "avg_cost": avg_cost,
            "timestamp": time.time(),
        }

        if drawdown_pct >= _DEFAULT_MAX_DRAWDOWN_PCT:
            await self._publish_risk_event(
                rule_name="max_drawdown",
                rule_type="position",
                detail=f"{code} 从高点回撤 {drawdown_pct*100:.2f}%（阈值 {_DEFAULT_MAX_DRAWDOWN_PCT*100:.0f}%）",
                context={
                    "code": code,
                    "price": price,
                    "max_price": max_price,
                    "avg_cost": avg_cost,
                    "drawdown_pct": drawdown_pct,
                },
                severity="warning",
            )
            logger.warning("risk warning: %s drawdown %.2f%%", code, drawdown_pct * 100)

    async def _check_daily_loss(
        self,
        code: str,
        price: float,
        position: dict[str, Any],
        change_pct: float,
    ) -> None:
        """检查当日跌幅。"""
        self._risk_state["daily_changes"][code] = {
            "change_pct": round(change_pct, 2),
            "price": price,
            "timestamp": time.time(),
        }

        if change_pct <= _DEFAULT_DAILY_LOSS_PCT:
            await self._publish_risk_event(
                rule_name="daily_loss",
                rule_type="position",
                detail=f"{code} 当日跌幅 {change_pct:.2f}%",
                context={
                    "code": code,
                    "price": price,
                    "change_pct": change_pct,
                },
                severity="warning",
            )
            logger.warning("risk warning: %s daily loss %.2f%%", code, change_pct)

    # ------------------------------------------------------------------
    # 压力场景
    # ------------------------------------------------------------------

    async def _check_stress_scenario(
        self,
        code: str,
        change_pct: float,
    ) -> None:
        """检查压力场景触发条件。"""
        # 大盘指数监控（sh.000001 上证指数）
        if code == "sh.000001" and change_pct <= _STRESS_INDEX_DROP_PCT:
            self._risk_state["stress_active"] = True
            alert = {
                "type": "stress_index_drop",
                "code": code,
                "change_pct": change_pct,
                "threshold": _STRESS_INDEX_DROP_PCT,
                "timestamp": time.time(),
                "datetime": datetime.now().isoformat(),
            }
            self._risk_state["alerts"].append(alert)
            await self._publish_risk_event(
                rule_name="stress_test",
                rule_type="market",
                detail=f"上证指数跌 {change_pct*100:.2f}%，触发压力场景",
                context={
                    "index_code": code,
                    "change_pct": change_pct,
                    "threshold": _STRESS_INDEX_DROP_PCT,
                },
                severity="violation",
            )
            logger.warning("STRESS TRIGGERED: index %s drop %.2f%%", code, change_pct)

        # 持仓个股暴跌监控
        elif code in self._positions and change_pct <= _STRESS_SINGLE_DROP_PCT:
            self._risk_state["stress_active"] = True
            alert = {
                "type": "stress_single_drop",
                "code": code,
                "change_pct": change_pct,
                "threshold": _STRESS_SINGLE_DROP_PCT,
                "timestamp": time.time(),
                "datetime": datetime.now().isoformat(),
            }
            self._risk_state["alerts"].append(alert)
            await self._publish_risk_event(
                rule_name="stress_test",
                rule_type="position",
                detail=f"{code} 跌 {change_pct*100:.2f}%，触发压力场景",
                context={
                    "code": code,
                    "change_pct": change_pct,
                    "threshold": _STRESS_SINGLE_DROP_PCT,
                },
                severity="violation",
            )
            logger.warning("STRESS TRIGGERED: %s drop %.2f%%", code, change_pct)

        # 只保留最近 N 条告警
        self._risk_state["alerts"] = self._risk_state["alerts"][-self._max_alerts :]

    # ------------------------------------------------------------------
    # VaR 计算
    # ------------------------------------------------------------------

    async def _calculate_var(self) -> None:
        """定期计算组合 VaR / CVaR。"""
        if not self._positions:
            return

        try:
            # 构建持仓数据
            positions = [
                {
                    "code": code,
                    "market_value": pos["quantity"] * self._market_snapshot.get(code, {}).get(
                        "price", pos["avg_cost"]
                    ),
                }
                for code, pos in self._positions.items()
            ]

            total_equity = sum(p["market_value"] for p in positions)
            if total_equity <= 0:
                return

            # 获取历史 K 线（这里简化处理，实际应从 KlineRepository 获取）
            # 由于消费者没有 session，这里暂时使用简化计算
            var_result = self._simplified_var(positions, total_equity)

            self._risk_state["var_result"] = {
                "var_95": var_result.get("var_95", 0),
                "var_99": var_result.get("var_99", 0),
                "cvar_95": var_result.get("cvar_95", 0),
                "cvar_99": var_result.get("cvar_99", 0),
                "timestamp": time.time(),
                "total_equity": total_equity,
                "position_count": len(positions),
            }

            # 检查 VaR 限额（2% 默认）
            var_95_pct = abs(var_result.get("var_95", 0))
            if var_95_pct >= 0.02:
                await self._publish_risk_event(
                    rule_name="var_limit",
                    rule_type="portfolio",
                    detail=f"组合 VaR(95%) {var_95_pct*100:.2f}% 超过限额 2%",
                    context={
                        "var_95_pct": var_95_pct,
                        "limit_pct": 0.02,
                        "total_equity": total_equity,
                    },
                    severity="warning",
                )
                logger.warning("risk warning: VaR %.2f%% exceeds limit", var_95_pct * 100)

        except Exception as e:
            logger.error("VaR calculation error: %s", e)

    def _simplified_var(self, positions: list[dict], total_equity: float) -> dict[str, Any]:
        """简化 VaR 计算（基于持仓当日涨跌幅）。

        当无法获取完整历史数据时使用简化版：
        用当日各持仓涨跌幅模拟组合日收益分布。
        """
        portfolio_returns = []
        weights = []

        for pos in positions:
            code = pos["code"]
            weight = pos["market_value"] / total_equity
            snapshot = self._market_snapshot.get(code, {})
            change_pct = snapshot.get("change_pct", 0) / 100  # 转为小数

            weights.append(weight)
            portfolio_returns.append(change_pct)

        # 简化：只有一天数据，无法做历史模拟
        # 返回基于当日波动的估计
        if not portfolio_returns:
            return {"var_95": 0, "var_99": 0, "cvar_95": 0, "cvar_99": 0}

        # 组合当日收益
        portfolio_return = sum(r * w for r, w in zip(portfolio_returns, weights))

        # 用当日波动率 * sqrt(1) 估计日 VaR（正态分布假设）
        import math

        # 简化：假设波动率为当日绝对变化的 2 倍
        volatility = abs(portfolio_return) * 2 if portfolio_return != 0 else 0.01

        var_95 = -1.645 * volatility
        var_99 = -2.326 * volatility
        cvar_95 = -2.0 * volatility  # 近似
        cvar_99 = -2.665 * volatility  # 近似

        return {
            "var_95": round(var_95, 6),
            "var_99": round(var_99, 6),
            "cvar_95": round(cvar_95, 6),
            "cvar_99": round(cvar_99, 6),
        }

    # ------------------------------------------------------------------
    # 风险事件发布
    # ------------------------------------------------------------------

    async def _publish_risk_event(
        self,
        rule_name: str,
        rule_type: str,
        detail: str,
        context: dict[str, Any],
        severity: str = "warning",
    ) -> None:
        """统一发布风险事件。"""
        if severity == "violation":
            await self._publisher.risk_violation(
                rule_name=rule_name,
                rule_type=rule_type,
                detail=detail,
                context=context,
            )
        elif severity == "blocked":
            await self._publisher.risk_blocked(
                rule_name=rule_name,
                rule_type=rule_type,
                detail=detail,
                context=context,
            )
        else:
            await self._publisher.risk_warning(
                rule_name=rule_name,
                rule_type=rule_type,
                detail=detail,
                context=context,
            )

    # ------------------------------------------------------------------
    # 生命周期扩展
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """启动消费者前先加载规则。"""
        await self._load_rules_from_db()
        await super().start()

    async def stop(self) -> None:
        """停止消费者。"""
        await super().stop()
        logger.info("risk monitor consumer stopped")
