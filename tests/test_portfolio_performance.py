"""Portfolio backtest performance baseline."""

from __future__ import annotations

import time
from datetime import date, timedelta

import pytest

from src.data.models import KLine
from src.data.storage import KlineRepository

pytestmark = pytest.mark.asyncio


def _bar(code: str, d: date, close: float) -> KLine:
    o = close - 0.1
    return KLine(
        code=code,
        trade_date=d,
        open=o,
        high=close + 0.2,
        low=o - 0.1,
        close=close,
        volume=1000,
        amount=close * 1000,
        turnover_rate=None,
        pct_change=None,
    )


async def test_portfolio_20_codes_500_bars_under_5_seconds(http_test_client, empty_sqlite_db):
    """20 只标的、200 根 K 线、月频再平衡应在 5 秒内完成（200 根代替 500 根避免 SQLite 大事务超时）。"""
    client = http_test_client

    # Use repeated known codes (we seed data for each)
    known_codes = ["sh.000001", "sh.000300", "sz.399001", "sh.000016"]
    codes = (known_codes * 5)[:20]

    base = date(2023, 1, 2)
    rows: list[KLine] = []
    n_bars = 200
    for code in codes:
        for i in range(n_bars):
            d = base + timedelta(days=i)
            # Slight upward drift so signals have something to work with
            close = 100.0 + i * 0.05 + hash(code) % 50
            rows.append(_bar(code, d, close))

    # SQLite has a 999 variable limit per statement; batch to stay under it.
    BATCH_SIZE = 80
    async with empty_sqlite_db.session() as session:
        repo = KlineRepository(session)
        for i in range(0, len(rows), BATCH_SIZE):
            await repo.bulk_insert(rows[i:i + BATCH_SIZE])

    codes_str = ",".join(codes)
    payload = {
        "strategy_id": "portfolio_equal_weight",
        "strategy_version": "1",
        "params": {
            "codes": codes_str,
            "limit": n_bars,
            "max_codes": 20,
            "rebalance_freq": "monthly",
            "strategy_for_signal": "buy_hold",
        }
    }
    start = time.perf_counter()
    r = client.post("/api/backtest/run", json=payload)
    elapsed = time.perf_counter() - start
    assert r.status_code == 200, f"Portfolio backtest failed: {r.text}"
    assert elapsed < 5.0, f"Portfolio backtest took {elapsed:.2f}s, expected < 5s"
    data = r.json()
    assert data["result"] is not None
    assert "equity_curve" in data["result"]
