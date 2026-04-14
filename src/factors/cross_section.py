"""
截面日一行价量 + N 期收益（``pct_change_n``），供 CLI 导出与 HTTP 只读接口共用。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Sequence

from src.data.models import KLine


@dataclass(frozen=True, slots=True)
class CrossSectionRowData:
    code: str
    close: float
    volume: int
    amount: float
    turnover_rate: float | None
    pct_change: float | None
    ret_pct: float | None
    meta_bars: int


def cross_section_factor_set_id(*, period: int, version: str = "v1") -> str:
    """与 **docs/FACTOR_SNAPSHOT_AND_PERSISTENCE.md** 中 ``factor_set_id`` 占位一致：``ret_close_{N}d_v1``。"""
    if period < 1:
        raise ValueError("period 须 >= 1")
    v = (version or "v1").strip() or "v1"
    return f"ret_close_{period}d_{v}"


def compute_cross_section_row(
    klines: list[KLine],
    as_of: date,
    period: int,
) -> CrossSectionRowData | None:
    """最后一根须为 ``as_of``，且 ``period>=1``；用 ``pct_change_n(close, period)`` 取末点收益 %。"""
    from src.factors.primitives import pct_change_n

    if period < 1 or not klines or klines[-1].trade_date != as_of:
        return None
    last_bar = klines[-1]
    closes: Sequence[float] = [float(k.close) for k in klines]
    rets = pct_change_n(closes, period)
    return CrossSectionRowData(
        code=last_bar.code,
        close=float(last_bar.close),
        volume=int(last_bar.volume),
        amount=float(last_bar.amount),
        turnover_rate=last_bar.turnover_rate,
        pct_change=last_bar.pct_change,
        ret_pct=rets[-1],
        meta_bars=len(klines),
    )
