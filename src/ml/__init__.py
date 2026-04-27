"""ML / 因子挖掘管道 — 超参优化、因子分析、自动特征生成。

用法:
    from src.ml import FactorAnalyzer, HyperOptRunner
    analyzer = FactorAnalyzer()
    ic = analyzer.information_coefficient(factor_values, forward_returns)

    runner = HyperOptRunner(strategy_fn)
    best_params = runner.optimize(n_trials=100)
"""

from __future__ import annotations

from src.ml.factor_analysis import FactorAnalyzer
from src.ml.factor_ortho import FactorOrthogonalizer
from src.ml.feature_engine import AutoFeatureEngine
from src.ml.hyperopt import HyperOptRunner

__all__ = [
    "AutoFeatureEngine",
    "FactorAnalyzer",
    "FactorOrthogonalizer",
    "HyperOptRunner",
]
