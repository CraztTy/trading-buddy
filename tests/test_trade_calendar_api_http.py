"""交易日历状态 API。"""

from __future__ import annotations

from fastapi.testclient import TestClient


async def test_trade_calendar_options_default(http_test_client: TestClient):
    r = http_test_client.get("/api/data/trade-calendar/options")
    assert r.status_code == 200
    body = r.json()
    assert body["default_exchange"] == "cn"
    assert len(body["exchanges"]) >= 1
    assert body["exchanges"][0]["value"] == "cn"
    assert "label" in body["exchanges"][0]


async def test_trade_calendar_status_empty(http_test_client: TestClient):
    r = http_test_client.get("/api/data/trade-calendar/status")
    assert r.status_code == 200
    body = r.json()
    assert body["exchange"] == "cn"
    assert body["row_count"] == 0
    assert body["date_min"] is None
    assert body["date_max"] is None


async def test_trade_calendar_status_after_seed(
    http_test_client: TestClient, empty_sqlite_db
):
    from datetime import date

    from src.data.storage import TradeCalendarRepository

    async with empty_sqlite_db.session() as session:
        await TradeCalendarRepository(session).bulk_upsert_days(
            "cn",
            [(date(2024, 1, 2), True), (date(2024, 1, 3), False)],
        )

    r = http_test_client.get("/api/data/trade-calendar/status?exchange=cn")
    assert r.status_code == 200
    body = r.json()
    assert body["row_count"] == 2
    assert body["date_min"] == "2024-01-02"
    assert body["date_max"] == "2024-01-03"
