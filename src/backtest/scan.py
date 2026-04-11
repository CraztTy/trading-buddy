"""
多标的双均线扫描（日线），供 API 与 CLI 复用。
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

from src.common import get_settings
from src.backtest import run_ma_cross_backtest
from src.data.models import KLine
from src.data.storage import KlineRepository, get_database


VALID_SORT_BY = frozenset({"total_return", "excess_return", "sharpe", "buy_hold"})

_SORT_FIELD: dict[str, str] = {
    "total_return": "total_return_pct",
    "excess_return": "excess_return_pct",
    "sharpe": "sharpe_ratio",
    "buy_hold": "buy_hold_return_pct",
}


def normalize_sort_by(sort_by: str) -> str:
    s = (sort_by or "total_return").strip().lower()
    if s not in VALID_SORT_BY:
        raise ValueError(
            f"sort_by 须为 {', '.join(sorted(VALID_SORT_BY))} 之一，当前为 {sort_by!r}"
        )
    return s


def sort_scan_rows_inplace(items: list[dict[str, Any]], sort_by: str) -> None:
    """按指标降序；失败行（含 error）沉底。"""
    field = _SORT_FIELD[normalize_sort_by(sort_by)]

    def key(r: dict[str, Any]) -> float:
        if r.get("error"):
            return float("-inf")
        v = r.get(field)
        if v is None:
            return float("-inf")
        return float(v)

    items.sort(key=key, reverse=True)


def parse_scan_codes(raw: str, cap: int) -> list[str]:
    parts = raw.replace("\n", ",").replace(";", ",").split(",")
    out: list[str] = []
    for p in parts:
        c = p.strip().lower()
        if c and c not in out:
            out.append(c)
        if len(out) >= cap:
            break
    return out


async def _fetch_klines_one(
    code: str,
    *,
    start_date: date | None,
    end_date: date | None,
    limit: int,
    semaphore: asyncio.Semaphore,
) -> tuple[str, list[KLine]]:
    async with semaphore:
        db = get_database()
        async with db.session() as session:
            repo = KlineRepository(session)
            klines = await repo.get_daily(
                code=code,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
            )
            return code, klines


async def ma_cross_scan_items(
    codes: list[str],
    *,
    fast: int,
    slow: int,
    limit: int,
    start_date: date | None,
    end_date: date | None,
    commission_rate: float,
    slippage_rate: float,
    sort_by: str = "total_return",
    max_concurrent: int = 8,
) -> list[dict[str, Any]]:
    """
    并行拉取各标的日 K（每标的独立会话，受 max_concurrent 限制），再逐只回测并排序。
    """
    _ = normalize_sort_by(sort_by)
    settings = get_settings()
    if settings.database.mode == "sqlite":
        db = get_database()
        async with db.session() as session:
            repo = KlineRepository(session)
            pairs = []
            for c in codes:
                klines = await repo.get_daily(
                    code=c,
                    start_date=start_date,
                    end_date=end_date,
                    limit=limit,
                )
                pairs.append((c, klines))
    else:
        sem = asyncio.Semaphore(max(1, min(max_concurrent, 20)))
        pairs = list(
            await asyncio.gather(
                *[
                    _fetch_klines_one(
                        c,
                        start_date=start_date,
                        end_date=end_date,
                        limit=limit,
                        semaphore=sem,
                    )
                    for c in codes
                ]
            )
        )

    rows: list[dict[str, Any]] = []
    for c, klines in pairs:
        if len(klines) < slow + 1:
            rows.append(
                {
                    "code": c,
                    "error": f"K 线不足（{len(klines)}<{slow + 1}）",
                    "bars_used": None,
                    "total_return_pct": None,
                    "buy_hold_return_pct": None,
                    "excess_return_pct": None,
                    "max_drawdown_pct": None,
                    "sharpe_ratio": None,
                    "signal_changes": None,
                }
            )
            continue
        try:
            res, _ = run_ma_cross_backtest(
                klines,
                fast=fast,
                slow=slow,
                commission_rate=commission_rate,
                slippage_rate=slippage_rate,
                include_equity_curve=False,
            )
        except ValueError as e:
            rows.append(
                {
                    "code": c,
                    "error": str(e),
                    "bars_used": None,
                    "total_return_pct": None,
                    "buy_hold_return_pct": None,
                    "excess_return_pct": None,
                    "max_drawdown_pct": None,
                    "sharpe_ratio": None,
                    "signal_changes": None,
                }
            )
            continue

        rows.append(
            {
                "code": res.code,
                "error": None,
                "bars_used": res.bars_used,
                "total_return_pct": round(res.total_return_pct, 4),
                "buy_hold_return_pct": round(res.buy_hold_return_pct, 4),
                "excess_return_pct": round(res.excess_return_pct, 4),
                "max_drawdown_pct": round(res.max_drawdown_pct, 4),
                "sharpe_ratio": round(res.sharpe_ratio, 4),
                "signal_changes": res.signal_changes,
            }
        )

    sort_scan_rows_inplace(rows, sort_by)
    return rows


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
) -> bytes:
    """UTF-8 BOM + CSV，便于 Excel 打开。"""
    import csv
    import io

    buf = io.StringIO()
    w = csv.writer(buf)
    range_bits = ""
    if start_date is not None:
        range_bits += f" start_date={start_date.isoformat()}"
    if end_date is not None:
        range_bits += f" end_date={end_date.isoformat()}"
    w.writerow(
        [
            f"# fast={fast} slow={slow} limit={limit} "
            f"commission_rate={commission_rate} slippage_rate={slippage_rate} "
            f"sort_by={sort_by}{range_bits}"
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
                r.get("signal_changes")
                if r.get("signal_changes") is not None
                else "",
            ]
        )
    text = buf.getvalue()
    return ("\ufeff" + text).encode("utf-8")
