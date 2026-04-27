"""
涨停回调策略批量扫描执行器。
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.backtest.limit_up_pullback import run_limit_up_pullback_backtest
from src.backtest.runner.ma_cross_scan_executor import (
    _fetch_klines_one,
    normalize_sort_by,
    sort_scan_rows_inplace,
)
from src.common import get_settings
from src.data.models import KLine, StockType
from src.data.storage import KlineRepository, StockRepository, get_database

STRATEGY_ID_LIMIT_UP_PULLBACK_SCAN = "limit_up_pullback_scan"


async def _fetch_stock_info_map(
    session: AsyncSession, codes: list[str]
) -> dict[str, Any]:
    """批量拉取股票完整信息，返回 code -> stock_info 映射。"""
    repo = StockRepository(session)
    out: dict[str, Any] = {}
    for c in codes:
        info = await repo.get_by_code(c)
        if info:
            out[c] = info
    return out


async def limit_up_pullback_scan_items(
    codes: list[str],
    stock_info_map: dict[str, Any],
    *,
    pullback_days: int,
    entry_type: str,
    volume_shrink_ratio: float,
    limit: int,
    start_date: date | None,
    end_date: date | None,
    commission_rate: float,
    slippage_rate: float,
    sort_by: str = "total_return",
    max_concurrent: int = 8,
    benchmark_klines: list[KLine] | None = None,
    adjust_flag: str = "3",
    max_hold_days: int = 0,
    time_stop_days: int = 0,
    time_stop_pct: float = 0.0,
    market_index_klines: list[KLine] | None = None,
    require_market_bull: bool = False,
    market_strict: bool = False,
) -> list[dict[str, Any]]:
    """
    并发拉取各标的日 K，再逐只运行涨停回调回测并排序。
    """
    _ = normalize_sort_by(sort_by)
    settings = get_settings()
    if settings.database.mode == "sqlite":
        db = get_database()
        async with db.session() as session:
            repo = KlineRepository(session)
            pairs: list[tuple[str, list[KLine]]] = []
            for c in codes:
                klines = await repo.get_daily(
                    code=c,
                    start_date=start_date,
                    end_date=end_date,
                    limit=limit,
                    adjust_flag=adjust_flag,
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
                        adjust_flag=adjust_flag,
                    )
                    for c in codes
                ]
            )
        )

    rows: list[dict[str, Any]] = []
    for c, klines in pairs:
        if len(klines) < 30:
            rows.append(
                {
                    "code": c,
                    "error": f"K 线不足（{len(klines)}<30）",
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
            info = stock_info_map.get(c)
            stock_type = info.stock_type if info else StockType.COMMON
            res, _, _ = run_limit_up_pullback_backtest(
                klines,
                stock_type=stock_type,
                pullback_days=pullback_days,
                entry_type=entry_type,
                volume_shrink_ratio=volume_shrink_ratio,
                commission_rate=commission_rate,
                slippage_rate=slippage_rate,
                include_equity_curve=False,
                benchmark_klines=benchmark_klines,
                stock_info=info,
                max_hold_days=max_hold_days,
                time_stop_days=time_stop_days,
                time_stop_pct=time_stop_pct,
                market_index_klines=market_index_klines,
                require_market_bull=require_market_bull,
                market_strict=market_strict,
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


async def execute_limit_up_pullback_scan(
    session: AsyncSession,
    *,
    codes: list[str],
    limit: int,
    start_date: date | None,
    end_date: date | None,
    commission_rate: float,
    slippage_rate: float,
    sort_by: str,
    max_concurrent: int,
    benchmark_code: str | None,
    adjust_flag: str = "3",
    pullback_days: int = 10,
    entry_type: str = "neutral",
    volume_shrink_ratio: float = 0.5,
    max_hold_days: int = 0,
    time_stop_days: int = 0,
    time_stop_pct: float = 0.0,
    market_index_code: str | None = None,
    require_market_bull: bool = False,
    market_strict: bool = False,
) -> tuple[list[dict[str, Any]], str, str]:
    """
    含基准 K 拉取、sort_by 校验与 stock_type 批量查询；失败抛出 ValueError（供 HTTP 400）。

    Returns:
        (items, sort_by_normalized, benchmark_normalized_or_empty)
    """
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
            adjust_flag=adjust_flag,
        )
        if not bench_klines:
            raise ValueError(f"基准 {bench_norm} 无可用日 K")

    # 可选：拉取大盘K线（第1层过滤）
    market_index_klines = None
    if require_market_bull and market_index_code:
        repo = KlineRepository(session)
        market_index_klines = await repo.get_daily(
            code=market_index_code.strip(),
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            adjust_flag=adjust_flag,
        )

    stock_info_map = await _fetch_stock_info_map(session, codes)

    items = await limit_up_pullback_scan_items(
        codes,
        stock_info_map,
        pullback_days=pullback_days,
        entry_type=entry_type,
        volume_shrink_ratio=volume_shrink_ratio,
        limit=limit,
        start_date=start_date,
        end_date=end_date,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        sort_by=sort_norm,
        max_concurrent=max_concurrent,
        benchmark_klines=bench_klines,
        adjust_flag=adjust_flag,
        max_hold_days=max_hold_days,
        time_stop_days=time_stop_days,
        time_stop_pct=time_stop_pct,
        market_index_klines=market_index_klines,
        require_market_bull=require_market_bull,
        market_strict=market_strict,
    )
    return items, sort_norm, bench_norm
