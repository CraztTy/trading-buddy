"""
从 ``KLine`` 时间序列抽取 float 列或 True Range，供 ``primitives`` 使用。

``klines`` 须按 **trade_date 升序**（旧 → 新），与仓储 ``get_daily`` 正序一致。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from src.data.models import KLine

KlineFloatColumn = Literal["open", "high", "low", "close", "volume", "amount"]

_COLUMNS: frozenset[str] = frozenset({"open", "high", "low", "close", "volume", "amount"})


def kline_float_series(klines: Sequence[KLine], column: KlineFloatColumn) -> list[float]:
    """
    抽取单列浮点序列（``volume`` 以 float 形式给出，便于与其它原语统一签名）。
    """
    col = str(column)
    if col not in _COLUMNS:
        raise ValueError(
            f"column 须为 {', '.join(sorted(_COLUMNS))} 之一，当前为 {column!r}"
        )
    return [float(getattr(row, col)) for row in klines]


def kline_true_range(klines: Sequence[KLine]) -> list[float]:
    """
    日 K **True Range**（与 ``KLine`` 行对齐、**时间升序**）。

    首根：``high - low``；其后：``max(high-low, |high-prev_close|, |low-prev_close|)``。
    """
    if not klines:
        return []
    m = len(klines)
    out: list[float] = [0.0] * m
    out[0] = float(klines[0].high) - float(klines[0].low)
    for i in range(1, m):
        h = float(klines[i].high)
        l = float(klines[i].low)
        pc = float(klines[i - 1].close)
        hl = h - l
        out[i] = max(hl, abs(h - pc), abs(l - pc))
    return out
