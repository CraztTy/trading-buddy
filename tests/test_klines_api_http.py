"""K 线 HTTP 路由：与股票测共用 http_test_client + 临时 SQLite。"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient

from src.data.models import KLine
from src.data.storage import KlineRepository


def _daily_row(code: str, d: date, close: float) -> KLine:
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


async def test_klines_latest_returns_last_bar(http_test_client, empty_sqlite_db):
    code = "sh.klatest"
    d0 = date(2024, 10, 1)
    rows = [_daily_row(code, d0 + timedelta(days=i), 10.0 + i) for i in range(3)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(f"/api/klines/latest/{code}")
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == code
    assert body["close"] == 12.0


async def test_klines_series_respects_limit(http_test_client, empty_sqlite_db):
    code = "sh.kseries"
    base = date(2024, 11, 1)
    rows = [_daily_row(code, base + timedelta(days=i), 5.0) for i in range(10)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(f"/api/klines/{code}", params={"limit": 3})
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 3
    assert [x["trade_date"] for x in data] == [
        "2024-11-08",
        "2024-11-09",
        "2024-11-10",
    ]


async def test_klines_analysis_has_indicators_and_history(http_test_client, empty_sqlite_db):
    code = "sh.kanal"
    base = date(2024, 12, 1)
    rows = [_daily_row(code, base + timedelta(days=i), 100.0 + i * 0.5) for i in range(8)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(f"/api/klines/analysis/{code}", params={"limit": 8})
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == code
    assert body["name"] == code
    assert body["count"] == 8
    assert body["indicators"]["ma5"] is not None
    assert len(body["history"]) == 8


async def test_klines_latest_missing_returns_error(http_test_client: TestClient):
    r = http_test_client.get("/api/klines/latest/sh.no_k")
    assert r.status_code == 200
    assert r.json().get("error") == "No kline data"
