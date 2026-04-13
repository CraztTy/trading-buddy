"""CLI 脚本共用的 ISO 日期解析（``YYYY-MM-DD``，含端点语义由调用方决定）。

使用方：**``scripts/run_backtest.py``**、**``scripts/scan_backtest.py``**、
**``scripts/trend_v0_archive_baseline.py``**、**``scripts/trend_v0_backtest_compare.py``**（解析 + 起止顺序）。
"""

from __future__ import annotations

from datetime import date


def parse_cli_iso_date(label: str, raw: str | None) -> date | None:
    """
    解析命令行可选日期。空或仅空白返回 ``None``；否则须为 ``date.fromisoformat`` 可解析格式。

    :param label: 用于错误信息，如 ``\"--start-date\"``。
    :raises ValueError: 非空但非法日期字符串。
    """
    s = (raw or "").strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError as e:
        raise ValueError(f"{label} 须为 YYYY-MM-DD，当前 {raw!r}") from e


def check_cli_date_order(start: date | None, end: date | None) -> str | None:
    """
    若起止日期均有值且 ``start > end``，返回固定错误句（供各脚本套自己的前缀）；否则 ``None``。
    """
    if start is not None and end is not None and start > end:
        return "--start-date 不能晚于 --end-date"
    return None
