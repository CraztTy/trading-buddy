"""VaR / CVaR 计算 — 历史模拟法。

基于持仓标的的历史日收益率，按市值权重加权计算组合收益率分布。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np

from src.common import get_logger

logger = get_logger("var_calculator")


@dataclass
class VarResult:
    """VaR / CVaR 计算结果。"""

    var_95: float  # 95% 置信度 VaR（负数表示损失）
    var_99: float  # 99% 置信度 VaR
    cvar_95: float  # 95% 置信度 CVaR（条件风险价值）
    cvar_99: float  # 99% 置信度 CVaR
    lookback_days: int  # 使用的历史天数
    data_quality: dict  # 各标的的数据覆盖情况


def _compute_returns(closes: list[float]) -> list[float]:
    """从收盘价序列计算日收益率。"""
    returns = []
    for i in range(1, len(closes)):
        if closes[i - 1] != 0:
            returns.append((closes[i] - closes[i - 1]) / closes[i - 1])
        else:
            returns.append(0.0)
    return returns


def calculate_var_historical(
    positions: list[dict],
    klines_map: dict[str, list],
    lookback_days: int = 252,
    total_equity: float | None = None,
) -> VarResult:
    """历史模拟法计算组合 VaR / CVaR。

    :param positions: 持仓列表，每项含 code, market_value
    :param klines_map: 标的代码 -> KLine 对象列表（按日期升序）
    :param lookback_days: 回看天数（默认 252 个交易日 ≈ 1 年）
    :param total_equity: 总权益（用于计算权重；不传则自动求和）
    :return: VarResult
    """
    if not positions:
        return VarResult(
            var_95=0.0,
            var_99=0.0,
            cvar_95=0.0,
            cvar_99=0.0,
            lookback_days=0,
            data_quality={},
        )

    total = total_equity or sum(p.get("market_value", 0) for p in positions)
    if total <= 0:
        return VarResult(
            var_95=0.0,
            var_99=0.0,
            cvar_95=0.0,
            cvar_99=0.0,
            lookback_days=0,
            data_quality={},
        )

    # 收集各标的的收益率序列和权重
    returns_matrix: list[list[float]] = []
    weights: list[float] = []
    data_quality: dict[str, dict] = {}

    for pos in positions:
        code = pos.get("code", "")
        mv = pos.get("market_value", 0)
        weight = mv / total
        klines = klines_map.get(code, [])

        if len(klines) < 2:
            data_quality[code] = {
                "bars": len(klines),
                "status": "insufficient_data",
            }
            continue

        closes = [float(k.close) for k in klines]
        returns = _compute_returns(closes)

        data_quality[code] = {
            "bars": len(klines),
            "returns_count": len(returns),
            "status": "ok",
        }

        returns_matrix.append(returns)
        weights.append(weight)

    if not returns_matrix:
        return VarResult(
            var_95=0.0,
            var_99=0.0,
            cvar_95=0.0,
            cvar_99=0.0,
            lookback_days=lookback_days,
            data_quality=data_quality,
        )

    # 对齐收益率序列长度（取最短）
    min_len = min(len(r) for r in returns_matrix)
    aligned = [r[-min_len:] for r in returns_matrix]

    # 计算组合日收益率（加权平均）
    portfolio_returns = []
    for day_idx in range(min_len):
        day_return = sum(
            aligned[i][day_idx] * weights[i]
            for i in range(len(aligned))
        )
        portfolio_returns.append(day_return)

    # 排序后计算分位数
    sorted_returns = sorted(portfolio_returns)
    n = len(sorted_returns)

    def percentile(pct: float) -> float:
        idx = int(n * (1 - pct))
        idx = max(0, min(idx, n - 1))
        return sorted_returns[idx]

    def cvar(pct: float) -> float:
        """CVaR：低于 VaR 阈值的平均收益率。"""
        threshold = percentile(pct)
        tail = [r for r in sorted_returns if r <= threshold]
        return sum(tail) / len(tail) if tail else threshold

    var_95 = percentile(0.95)
    var_99 = percentile(0.99)
    cvar_95 = cvar(0.95)
    cvar_99 = cvar(0.99)

    return VarResult(
        var_95=round(var_95, 6),
        var_99=round(var_99, 6),
        cvar_95=round(cvar_95, 6),
        cvar_99=round(cvar_99, 6),
        lookback_days=min_len,
        data_quality=data_quality,
    )
