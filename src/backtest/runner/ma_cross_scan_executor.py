"""
多标的双均线扫描：并行/顺序拉 K → 逐只 run_ma_cross_backtest → 排序。

原位于 `src/backtest/scan.py`，迁入 runner 与单标的 `execute_ma_cross_single` 并列。
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.backtest import run_ma_cross_backtest
from src.common import get_settings
from src.data.models import KLine
from src.data.storage import KlineRepository, get_database


STRATEGY_ID_MA_CROSS_SCAN = "ma_cross_scan"


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


def build_ma_cross_scan_assumptions(
    *,
    n_codes: int,
    sort_by: str,
    max_concurrent: int,
    bench: str | None,
    start_date: date | None,
    end_date: date | None,
) -> list[str]:
    out = [
        "双均线（日线收盘）批量扫描；与 GET /api/backtest/ma-cross/scan 口径一致。",
        f"共 {n_codes} 只标的（按 max_codes 截断后）。",
        f"结果按 {sort_by} 降序；失败行沉底。",
        f"拉取日 K 最大并发 max_concurrent={max_concurrent}。",
        "价格口径以入库 daily_kline 为准（参见 docs/DATA_AND_ADJUSTMENT.md）。",
    ]
    if bench:
        out.append(f"各标的 β/α 相对基准 {bench}（交易日对齐、仅前向填充）。")
    else:
        out.append("各标的 β/α 为对标的自身日收益的回归。")
    if start_date or end_date:
        out.append(
            f"日期约束：start_date={start_date or '∅'}，end_date={end_date or '∅'}（含端点）。"
        )
    return out


VALID_SORT_BY = frozenset(
    {
        "total_return",
        "excess_return",
        "sharpe",
        "buy_hold",
        "ann_return",
        "sortino",
        "calmar",
        "win_rate",
        "avg_holding",
        "underlying_beta",
        "underlying_alpha",
    }
)

_SORT_FIELD: dict[str, str] = {
    "total_return": "total_return_pct",
    "excess_return": "excess_return_pct",
    "sharpe": "sharpe_ratio",
    "buy_hold": "buy_hold_return_pct",
    "ann_return": "annualized_return_pct",
    "sortino": "sortino_ratio",
    "calmar": "calmar_ratio",
    "win_rate": "win_rate_pct",
    "avg_holding": "avg_holding_return_pct",
    "underlying_beta": "underlying_beta",
    "underlying_alpha": "underlying_alpha_ann_pct",
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
    benchmark_klines: list[KLine] | None = None,
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
                    "annualized_return_pct": None,
                    "buy_hold_annualized_return_pct": None,
                    "annualized_volatility_pct": None,
                    "sortino_ratio": None,
                    "calmar_ratio": None,
                    "long_trades_count": None,
                    "win_rate_pct": None,
                    "avg_holding_return_pct": None,
                    "underlying_beta": None,
                    "underlying_alpha_ann_pct": None,
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
                benchmark_klines=benchmark_klines,
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
                    "annualized_return_pct": None,
                    "buy_hold_annualized_return_pct": None,
                    "annualized_volatility_pct": None,
                    "sortino_ratio": None,
                    "calmar_ratio": None,
                    "long_trades_count": None,
                    "win_rate_pct": None,
                    "avg_holding_return_pct": None,
                    "underlying_beta": None,
                    "underlying_alpha_ann_pct": None,
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
                "annualized_return_pct": round(res.annualized_return_pct, 4),
                "buy_hold_annualized_return_pct": round(
                    res.buy_hold_annualized_return_pct, 4
                ),
                "annualized_volatility_pct": round(res.annualized_volatility_pct, 4),
                "sortino_ratio": round(res.sortino_ratio, 4),
                "calmar_ratio": round(res.calmar_ratio, 4),
                "long_trades_count": res.long_trades_count,
                "win_rate_pct": round(res.win_rate_pct, 4),
                "avg_holding_return_pct": round(res.avg_holding_return_pct, 4),
                "underlying_beta": round(res.underlying_beta, 4),
                "underlying_alpha_ann_pct": round(res.underlying_alpha_ann_pct, 4),
            }
        )

    sort_scan_rows_inplace(rows, sort_by)
    return rows


async def execute_ma_cross_scan(
    session: AsyncSession,
    *,
    codes: list[str],
    fast: int,
    slow: int,
    limit: int,
    start_date: date | None,
    end_date: date | None,
    commission_rate: float,
    slippage_rate: float,
    sort_by: str,
    max_concurrent: int,
    benchmark_code: str | None,
) -> tuple[list[dict[str, Any]], str, str]:
    """
    含基准 K 拉取与 sort_by 校验；失败抛出 ValueError（供 HTTP 400）。

    Returns:
        (items, sort_by_normalized, benchmark_normalized_or_empty)
    """
    if fast >= slow:
        raise ValueError("fast 必须小于 slow")
    if commission_rate + slippage_rate > 0.08:
        raise ValueError("commission_rate 与 slippage_rate 之和勿超过 0.08")
    if start_date and end_date and start_date > end_date:
        raise ValueError("start_date 不能晚于 end_date")
    sort_norm = normalize_sort_by(sort_by)

    bench_norm = (benchmark_code or "").strip().lower() or ""
    bench_klines = None
    if bench_norm:
        repo = KlineRepository(session)
        bench_klines = await repo.get_daily(
            code=bench_norm,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
        if not bench_klines:
            raise ValueError(f"基准 {bench_norm} 无可用日 K")

    items = await ma_cross_scan_items(
        codes,
        fast=fast,
        slow=slow,
        limit=limit,
        start_date=start_date,
        end_date=end_date,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        sort_by=sort_norm,
        max_concurrent=max_concurrent,
        benchmark_klines=bench_klines,
    )
    return items, sort_norm, bench_norm
