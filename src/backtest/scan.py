"""
多标的双均线扫描 — CSV 与 codes 解析；核心扫描逻辑见 `src/backtest/runner/ma_cross_scan_executor.py`。
"""

from __future__ import annotations

import csv
import io
from datetime import date
from typing import Any

# CLI / 测试兼容：从 runner 再导出
from src.backtest.runner.ma_cross_scan_executor import (
    ma_cross_scan_items,
    normalize_sort_by,
    parse_scan_codes,
    sort_scan_rows_inplace,
)

__all__ = [
    "ma_cross_scan_items",
    "ma_cross_scan_csv_bytes",
    "normalize_sort_by",
    "parse_scan_codes",
    "sort_scan_rows_inplace",
]


def ma_cross_scan_csv_bytes(
    items: list[dict[str, Any]],
    *,
    fast: int,
    slow: int,
    limit: int,
    commission_rate: float,
    slippage_rate: float,
    sort_by: str = "total_return",
    start_date: date | None = None,
    end_date: date | None = None,
    benchmark_code: str | None = None,
) -> bytes:
    """UTF-8 BOM + CSV，便于 Excel 打开。"""
    buf = io.StringIO()
    w = csv.writer(buf)
    range_bits = ""
    if start_date is not None:
        range_bits += f" start_date={start_date.isoformat()}"
    if end_date is not None:
        range_bits += f" end_date={end_date.isoformat()}"
    bench_bit = f" benchmark_code={benchmark_code}" if benchmark_code else ""
    w.writerow(
        [
            f"# fast={fast} slow={slow} limit={limit} "
            f"commission_rate={commission_rate} slippage_rate={slippage_rate} "
            f"sort_by={sort_by}{range_bits}{bench_bit}"
        ]
    )
    w.writerow(
        [
            "code",
            "error",
            "bars_used",
            "total_return_pct",
            "buy_hold_return_pct",
            "excess_return_pct",
            "max_drawdown_pct",
            "sharpe_ratio",
            "sortino_ratio",
            "calmar_ratio",
            "annualized_return_pct",
            "buy_hold_annualized_return_pct",
            "annualized_volatility_pct",
            "long_trades_count",
            "win_rate_pct",
            "avg_holding_return_pct",
            "underlying_beta",
            "underlying_alpha_ann_pct",
            "signal_changes",
        ]
    )
    for r in items:
        w.writerow(
            [
                r.get("code", ""),
                r.get("error") or "",
                r.get("bars_used") if r.get("bars_used") is not None else "",
                r.get("total_return_pct") if r.get("total_return_pct") is not None else "",
                r.get("buy_hold_return_pct")
                if r.get("buy_hold_return_pct") is not None
                else "",
                r.get("excess_return_pct")
                if r.get("excess_return_pct") is not None
                else "",
                r.get("max_drawdown_pct")
                if r.get("max_drawdown_pct") is not None
                else "",
                r.get("sharpe_ratio") if r.get("sharpe_ratio") is not None else "",
                r.get("sortino_ratio") if r.get("sortino_ratio") is not None else "",
                r.get("calmar_ratio") if r.get("calmar_ratio") is not None else "",
                r.get("annualized_return_pct")
                if r.get("annualized_return_pct") is not None
                else "",
                r.get("buy_hold_annualized_return_pct")
                if r.get("buy_hold_annualized_return_pct") is not None
                else "",
                r.get("annualized_volatility_pct")
                if r.get("annualized_volatility_pct") is not None
                else "",
                r.get("long_trades_count")
                if r.get("long_trades_count") is not None
                else "",
                r.get("win_rate_pct") if r.get("win_rate_pct") is not None else "",
                r.get("avg_holding_return_pct")
                if r.get("avg_holding_return_pct") is not None
                else "",
                r.get("underlying_beta") if r.get("underlying_beta") is not None else "",
                r.get("underlying_alpha_ann_pct")
                if r.get("underlying_alpha_ann_pct") is not None
                else "",
                r.get("signal_changes")
                if r.get("signal_changes") is not None
                else "",
            ]
        )
    text = buf.getvalue()
    return ("\ufeff" + text).encode("utf-8")
