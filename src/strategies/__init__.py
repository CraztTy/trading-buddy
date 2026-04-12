"""策略目录与统一信号入口（V2 切片：可扩展多策略）。"""

from .catalog import list_strategy_catalog
from .signal_ma_cross import compute_ma_cross_signal

__all__ = ["compute_ma_cross_signal", "list_strategy_catalog"]
