"""
多标的双均线扫描（日线），供 API 与 CLI 复用。
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.backtest import run_ma_cross_backtest
from src.data.storage import KlineRepository


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


async def ma_cross_scan_items(
    session: AsyncSession,
    codes: list[str],
    *,
    fast: int,
    slow: int,
    limit: int,
    start_date: date | None,
    end_date: date | None,
    commission_rate: float,
    slippage_rate: float,
) -> list[dict[str, Any]]:
    """返回已排序的 dict 列表，键与 MaCrossScanRow 一致。"""
    repo = KlineRepository(session)
    rows: list[dict[str, Any]] = []

    for c in codes:
        klines = await repo.get_daily(
            code=c,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
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

    def sort_key(r: dict[str, Any]) -> float:
        if r.get("error") or r.get("total_return_pct") is None:
            return float("-inf")
        return float(r["total_return_pct"])

    rows.sort(key=sort_key, reverse=True)
    return rows


def ma_cross_scan_csv_bytes(
    items: list[dict[str, Any]],
    *,
    fast: int,
    slow: int,
    limit: int,
    commission_rate: float,
    slippage_rate: float,
) -> bytes:
    """UTF-8 BOM + CSV，便于 Excel 打开。"""
    import csv
    import io

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            f"# fast={fast} slow={slow} limit={limit} "
            f"commission_rate={commission_rate} slippage_rate={slippage_rate}"
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
