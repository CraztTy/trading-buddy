"""最小回测模块（日线、向量化）。"""

from .ma_cross import ma_cross_result_from_df, run_ma_cross_backtest

__all__ = ["ma_cross_result_from_df", "run_ma_cross_backtest"]
