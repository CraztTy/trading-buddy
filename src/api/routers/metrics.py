"""Prometheus 风格 /metrics 端点 — 暴露关键系统与业务指标。"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import func, select, text

from src.common import get_settings
from src.common.kill_switch import is_killed
from src.common.redis_client import get_redis_client
from src.data.storage import get_database
from src.data.storage.models import (
    AuditLogModel,
    BacktestRunModel,
    DailyKlineModel,
    PaperOrderModel,
    RiskRuleModel,
    StockInfoModel,
)

router = APIRouter()

# 进程启动时间戳（由 lifespan 设置）
_PROCESS_START_TIME: float | None = None


def set_process_start_time(t: float) -> None:
    global _PROCESS_START_TIME
    _PROCESS_START_TIME = t


def _fmt(name: str, value: float | int, labels: dict[str, str] | None = None) -> str:
    if labels:
        label_str = ",".join(f'{k}="{v}"' for k, v in labels.items())
        return f'{name}{{{label_str}}} {value}'
    return f'{name} {value}'


def _metric_block(name: str, help_text: str, mtype: str, lines: list[str]) -> str:
    return f'# HELP {name} {help_text}\n# TYPE {name} {mtype}\n' + "\n".join(lines) + "\n"


@router.get('/metrics')
async def metrics(request: Request):
    """Prometheus 风格指标端点。"""
    now = time.time()
    settings = get_settings()
    db = get_database()
    parts: list[str] = []

    # 1. 进程指标
    uptime = 0.0
    if _PROCESS_START_TIME is not None:
        uptime = now - _PROCESS_START_TIME
    parts.append(_metric_block(
        "tradingbuddy_uptime_seconds",
        "Process uptime in seconds",
        "gauge",
        [_fmt("tradingbuddy_uptime_seconds", round(uptime, 3))]
    ))

    # 2. 数据库指标
    async with db.session() as session:
        # stock_info 数量
        result = await session.execute(select(func.count()).select_from(StockInfoModel))
        stock_count = result.scalar_one()
        parts.append(_metric_block(
            "tradingbuddy_stock_info_count",
            "Number of stocks in stock_info",
            "gauge",
            [_fmt("tradingbuddy_stock_info_count", stock_count)]
        ))

        # daily_kline 最新日期
        result = await session.execute(select(func.max(DailyKlineModel.trade_date)))
        latest_kline = result.scalar_one()
        kline_days_old = 999
        if latest_kline:
            from datetime import date
            kline_days_old = (date.today() - latest_kline).days
        parts.append(_metric_block(
            "tradingbuddy_daily_kline_days_old",
            "Days since latest daily_kline",
            "gauge",
            [_fmt("tradingbuddy_daily_kline_days_old", kline_days_old)]
        ))

        # 纸交易订单数
        result = await session.execute(select(func.count()).select_from(PaperOrderModel))
        paper_orders = result.scalar_one()
        parts.append(_metric_block(
            "tradingbuddy_paper_orders_total",
            "Total paper trading orders",
            "counter",
            [_fmt("tradingbuddy_paper_orders_total", paper_orders)]
        ))

        # 回测存档数
        result = await session.execute(select(func.count()).select_from(BacktestRunModel))
        backtest_runs = result.scalar_one()
        parts.append(_metric_block(
            "tradingbuddy_backtest_runs_total",
            "Total backtest runs archived",
            "counter",
            [_fmt("tradingbuddy_backtest_runs_total", backtest_runs)]
        ))

        # 风控规则数
        result = await session.execute(select(func.count()).select_from(RiskRuleModel))
        risk_rules = result.scalar_one()
        parts.append(_metric_block(
            "tradingbuddy_risk_rules_total",
            "Total risk rules configured",
            "gauge",
            [_fmt("tradingbuddy_risk_rules_total", risk_rules)]
        ))

        # 审计日志数（最近 24h）
        from datetime import datetime, timedelta
        since = datetime.now() - timedelta(hours=24)
        result = await session.execute(
            select(func.count()).select_from(AuditLogModel).where(AuditLogModel.created_at >= since)
        )
        audit_24h = result.scalar_one()
        parts.append(_metric_block(
            "tradingbuddy_audit_logs_24h",
            "Audit logs in last 24h",
            "gauge",
            [_fmt("tradingbuddy_audit_logs_24h", audit_24h)]
        ))

    # 3. Kill Switch
    killed = await is_killed()
    parts.append(_metric_block(
        "tradingbuddy_kill_switch_active",
        "Kill switch active (1=yes, 0=no)",
        "gauge",
        [_fmt("tradingbuddy_kill_switch_active", 1 if killed else 0)]
    ))

    # 4. Redis 队列深度（回测异步任务）
    if settings.redis.enabled:
        r = get_redis_client()
        if r is not None:
            try:
                queue_len = await r.llen("tb:backtest:job:queue")
                parts.append(_metric_block(
                    "tradingbuddy_backtest_queue_depth",
                    "Backtest async job queue depth",
                    "gauge",
                    [_fmt("tradingbuddy_backtest_queue_depth", queue_len)]
                ))
            except Exception:
                pass

    # 5. ClickHouse 指标
    if settings.clickhouse.enabled:
        try:
            from src.data.clickhouse.client import health_check as ch_health
            from src.data.clickhouse.repository import ClickHouseRepository

            ch_status = ch_health()
            ch_ok = 1 if ch_status.get("status") == "ok" else 0
            parts.append(_metric_block(
                "tradingbuddy_clickhouse_up",
                "ClickHouse connection status (1=ok, 0=error)",
                "gauge",
                [_fmt("tradingbuddy_clickhouse_up", ch_ok)]
            ))

            if ch_ok:
                repo = ClickHouseRepository()
                ch_count = repo.count_daily()
                parts.append(_metric_block(
                    "tradingbuddy_clickhouse_daily_kline_total",
                    "Total daily kline rows in ClickHouse",
                    "counter",
                    [_fmt("tradingbuddy_clickhouse_daily_kline_total", ch_count)]
                ))
        except Exception:
            pass

    # 6. 版本信息
    from src.common import __version__
    parts.append(_metric_block(
        "tradingbuddy_info",
        "Trading Buddy version info",
        "gauge",
        [_fmt("tradingbuddy_info", 1, {"version": __version__})]
    ))

    return "\n".join(parts)
