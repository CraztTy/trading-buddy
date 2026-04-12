"""
通用回测 MVP — 可插拔执行器（单标的 + 批量扫描内核）。

- `GET /api/backtest/ma-cross`、`POST /api/backtest/run`（`ma_cross`）→ `execute_ma_cross_single`
- `GET /api/backtest/ma-cross/scan`、`POST /api/backtest/run`（`ma_cross_scan`）→ `execute_ma_cross_scan`（`ma_cross_scan_items` 在 runner 内）
"""

from .ma_cross_executor import (
    ENGINE_VERSION,
    STRATEGY_ID_MA_CROSS,
    execute_ma_cross_single,
)
from .ma_cross_scan_executor import (
    STRATEGY_ID_MA_CROSS_SCAN,
    build_ma_cross_scan_assumptions,
    execute_ma_cross_scan,
    ma_cross_scan_items,
    parse_scan_codes,
)

__all__ = [
    "ENGINE_VERSION",
    "STRATEGY_ID_MA_CROSS",
    "STRATEGY_ID_MA_CROSS_SCAN",
    "build_ma_cross_scan_assumptions",
    "execute_ma_cross_single",
    "execute_ma_cross_scan",
    "ma_cross_scan_items",
    "parse_scan_codes",
]
