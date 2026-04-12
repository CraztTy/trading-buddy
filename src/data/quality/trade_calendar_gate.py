"""
交易日历门控（B+D）：在启用「按 exchange 的交易日缺口」时，要求 trade_calendar 非空且覆盖足够新。

供 `check_daily_kline_quality.py` 与单测复用；不访问数据库，仅读报告 dict。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any


def evaluate_trade_calendar_gate(
    report_k: dict[str, Any],
    report_g: dict[str, Any],
    *,
    grace_days: int,
    today: date | None = None,
) -> tuple[bool, list[str]]:
    """
    B：仅当 ``calendar_gap_sample.enabled`` 且 ``gap_exchange`` 非空（非 none/off）时检查。
    D：``trading_calendar_row_count==0`` 或 ``date_max`` 早于参考日减 grace 则失败。

    参考日：``min(daily_kline.trade_date_max, 今天)``；无日 K 时参考日为今天。
    """
    if not report_g.get("enabled") or report_g.get("gap_exchange") is None:
        return True, []

    ex = report_g.get("gap_exchange")
    rc = int(report_g.get("trading_calendar_row_count") or 0)
    if rc == 0:
        return False, [
            f"已启用交易日缺口（gap_exchange={ex!r}）但 trade_calendar 无行数；"
            "请运行 scripts/fetch_trade_calendar.py 或 scripts/fetch_data.py --mode calendar。"
        ]

    raw_max = report_g.get("trading_calendar_date_max")
    if not raw_max:
        return False, [
            "trade_calendar 有行数但 trading_calendar_date_max 为空，无法校验覆盖。"
        ]

    cal_max = date.fromisoformat(str(raw_max)[:10])

    raw_k = report_k.get("trade_date_max")
    kmax: date | None
    if raw_k:
        kmax = date.fromisoformat(str(raw_k)[:10])
    else:
        kmax = None

    now = today if today is not None else date.today()
    ref = min(kmax, now) if kmax is not None else now
    grace = max(0, int(grace_days))
    need_min = ref - timedelta(days=grace)

    if cal_max < need_min:
        return False, [
            f"trade_calendar.date_max={cal_max} 早于要求下界 {need_min} "
            f"（参考日 {ref} = min(日K trade_date_max, 今天)，grace={grace} 自然日）。"
        ]

    return True, []
