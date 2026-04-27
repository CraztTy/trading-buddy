"""Walk-forward 分析框架 — 防止过拟合的滚动验证方法。

将历史数据分为多个窗口（训练期 + 测试期），
在训练期优化参数，在测试期验证性能，滑动前进。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Callable

from src.common import get_logger

logger = get_logger("walk_forward")


@dataclass
class WalkForwardWindow:
    """单个 walk-forward 窗口。"""

    train_start: date
    train_end: date
    test_start: date
    test_end: date
    fold: int


@dataclass
class WalkForwardResult:
    """Walk-forward 分析结果。"""

    windows: list[WalkForwardWindow] = field(default_factory=list)
    train_results: list[dict[str, Any]] = field(default_factory=list)
    test_results: list[dict[str, Any]] = field(default_factory=list)
    aggregated: dict[str, Any] = field(default_factory=dict)


def generate_windows(
    start_date: date,
    end_date: date,
    train_days: int = 252,
    test_days: int = 63,
    step_days: int = 63,
) -> list[WalkForwardWindow]:
    """生成 walk-forward 窗口序列。

    :param start_date: 数据起始日
    :param end_date: 数据结束日
    :param train_days: 训练期长度（交易日）
    :param test_days: 测试期长度（交易日）
    :param step_days: 滑动步长（交易日）
    :return: 窗口列表
    """
    windows: list[WalkForwardWindow] = []
    current = start_date
    fold = 0

    # 粗略转换：假设每年 252 个交易日，每月 21 个交易日
    train_delta = timedelta(days=int(train_days * 365.25 / 252))
    test_delta = timedelta(days=int(test_days * 365.25 / 252))
    step_delta = timedelta(days=int(step_days * 365.25 / 252))

    while True:
        train_start = current
        train_end = train_start + train_delta
        test_start = train_end + timedelta(days=1)
        test_end = test_start + test_delta

        if test_end > end_date:
            break

        windows.append(WalkForwardWindow(
            train_start=train_start,
            train_end=train_end,
            test_start=test_start,
            test_end=test_end,
            fold=fold,
        ))

        current = current + step_delta
        fold += 1

        if train_end >= end_date:
            break

    return windows


def aggregate_results(test_results: list[dict[str, Any]]) -> dict[str, Any]:
    """聚合所有测试期的结果。"""
    if not test_results:
        return {}

    # 提取可聚合的数值字段
    returns = [r.get("total_return", 0) for r in test_results]
    sharpes = [r.get("sharpe_ratio", 0) for r in test_results if r.get("sharpe_ratio") is not None]
    max_dd = [r.get("max_drawdown", 0) for r in test_results if r.get("max_drawdown") is not None]

    def _mean(vals: list[float]) -> float:
        return sum(vals) / len(vals) if vals else 0.0

    return {
        "folds": len(test_results),
        "avg_total_return": round(_mean(returns), 4),
        "avg_sharpe_ratio": round(_mean(sharpes), 4) if sharpes else None,
        "avg_max_drawdown": round(_mean(max_dd), 4) if max_dd else None,
        "win_rate": round(sum(1 for r in returns if r > 0) / len(returns), 4) if returns else 0,
        "best_fold_return": round(max(returns), 4) if returns else 0,
        "worst_fold_return": round(min(returns), 4) if returns else 0,
    }
