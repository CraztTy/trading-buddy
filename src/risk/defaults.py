"""默认风控规则配置与引擎工厂。"""

from __future__ import annotations

from typing import Any

from src.risk.engine import RiskEngine
from src.risk.rules import RULE_REGISTRY

# 默认规则配置（内存中；未来可扩展为从数据库加载）
DEFAULT_RULE_CONFIGS: list[dict[str, Any]] = [
    {
        "rule_type": "max_drawdown",
        "name": "最大回撤限制",
        "params": {"max_drawdown_pct": -0.15},
        "enabled": True,
    },
    {
        "rule_type": "position_limit",
        "name": "单票仓位上限",
        "params": {"max_weight_pct": 0.30},
        "enabled": True,
    },
    {
        "rule_type": "sector_exposure",
        "name": "行业暴露上限",
        "params": {"max_sector_weight_pct": 0.40},
        "enabled": True,
    },
    {
        "rule_type": "daily_loss",
        "name": "单日亏损限制",
        "params": {"max_daily_loss_pct": -0.03},
        "enabled": True,
    },
    {
        "rule_type": "cash_ratio",
        "name": "最低现金比例",
        "params": {"min_cash_pct": 0.10},
        "enabled": True,
    },
    {
        "rule_type": "var_limit",
        "name": "VaR 限额",
        "params": {"max_var_pct": 0.02, "confidence": 0.95},
        "enabled": False,  # 默认关闭，需先计算 VaR 历史数据
    },
    {
        "rule_type": "stress_test",
        "name": "压力测试触发",
        "params": {"index_drop_pct": -0.03, "single_drop_pct": -0.07},
        "enabled": True,
    },
]


def create_default_engine() -> RiskEngine:
    """使用默认规则配置创建风控引擎。"""
    return build_engine_from_configs(DEFAULT_RULE_CONFIGS)


def build_engine_from_configs(configs: list[dict[str, Any]]) -> RiskEngine:
    """从规则配置列表构建风控引擎。"""
    engine = RiskEngine()
    for cfg in configs:
        if not cfg.get("enabled", True):
            continue
        rule_cls = RULE_REGISTRY.get(cfg["rule_type"])
        if rule_cls is None:
            continue
        rule = rule_cls(
            name=cfg.get("name", cfg["rule_type"]),
            params=cfg.get("params", {}),
            enabled=cfg.get("enabled", True),
        )
        engine.register(rule)
    return engine
