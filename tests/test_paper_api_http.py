"""纸交易 HTTP：状态、下单、重置；A 股 100 股整数倍、卖出 T+1。"""

from __future__ import annotations

from datetime import date, timedelta

from src.data.models import KLine
from src.data.storage import KlineRepository


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


async def test_paper_state_creates_account(http_test_client, empty_sqlite_db):
    r = http_test_client.get("/api/paper/state")
    assert r.status_code == 200
    body = r.json()
    assert body["account"]["label"] == "default"
    assert body["account"]["cash"] == 1_000_000.0
    assert body["positions"] == []
    assert body["equity"] == 1_000_000.0


async def test_paper_buy_then_next_day_sell(http_test_client, empty_sqlite_db):
    code = "sh.paper1"
    base = date(2025, 6, 1)
    rows = [_bar(code, base + timedelta(days=i), 10.0) for i in range(8)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r_buy = http_test_client.post(
        "/api/paper/orders",
        json={"code": code, "side": "buy", "quantity": 100},
    )
    assert r_buy.status_code == 200
    st = http_test_client.get("/api/paper/state").json()
    assert st["positions"][0]["quantity"] == 100
    assert st["positions"][0]["sellable_quantity"] == 0

    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert([_bar(code, base + timedelta(days=8), 11.0)])

    st2 = http_test_client.get("/api/paper/state").json()
    assert st2["positions"][0]["sellable_quantity"] == 100

    r_sell = http_test_client.post(
        "/api/paper/orders",
        json={"code": code, "side": "sell", "quantity": 100},
    )
    assert r_sell.status_code == 200
    # 买入 100×10，卖出按新 K 线收盘 11 撮合：1_000_000 - 1000 + 1100
    assert r_sell.json()["cash_after"] == 1_000_100.0
    st3 = http_test_client.get("/api/paper/state").json()
    assert st3["positions"] == []


async def test_paper_same_day_sell_blocked(http_test_client, empty_sqlite_db):
    code = "sh.same1"
    base = date(2025, 8, 1)
    rows = [_bar(code, base + timedelta(days=i), 10.0) for i in range(5)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)
    assert http_test_client.post(
        "/api/paper/orders",
        json={"code": code, "side": "buy", "quantity": 100},
    ).status_code == 200
    r = http_test_client.post(
        "/api/paper/orders",
        json={"code": code, "side": "sell", "quantity": 100},
    )
    assert r.status_code == 400
    assert "T+1" in r.json().get("detail", "")


async def test_paper_quantity_not_lot_422(http_test_client, empty_sqlite_db):
    code = "sh.lot1"
    base = date(2025, 9, 1)
    rows = [_bar(code, base + timedelta(days=i), 10.0) for i in range(3)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)
    r = http_test_client.post(
        "/api/paper/orders",
        json={"code": code, "side": "buy", "quantity": 50},
    )
    assert r.status_code == 422


async def test_paper_buy_insufficient_cash_400(http_test_client, empty_sqlite_db):
    code = "sh.paper2"
    base = date(2025, 7, 1)
    rows = [_bar(code, base + timedelta(days=i), 1_000_000.0) for i in range(3)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.post(
        "/api/paper/orders",
        json={"code": code, "side": "buy", "quantity": 100},
    )
    assert r.status_code == 400
    assert "现金不足" in r.json().get("detail", "")


async def test_paper_no_kline_400(http_test_client, empty_sqlite_db):
    r = http_test_client.post(
        "/api/paper/orders",
        json={"code": "sh.nokline", "side": "buy", "quantity": 100},
    )
    assert r.status_code == 400


async def test_paper_orders_list_pagination(http_test_client, empty_sqlite_db):
    code = "sh.page1"
    base = date(2025, 10, 1)
    rows = [_bar(code, base + timedelta(days=i), 10.0) for i in range(5)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)
    for _ in range(3):
        r = http_test_client.post(
            "/api/paper/orders",
            json={"code": code, "side": "buy", "quantity": 100},
        )
        assert r.status_code == 200
    p1 = http_test_client.get("/api/paper/orders", params={"limit": 2, "offset": 0})
    assert p1.status_code == 200
    b1 = p1.json()
    assert b1["total"] == 3
    assert len(b1["items"]) == 2
    p2 = http_test_client.get("/api/paper/orders", params={"limit": 2, "offset": 2})
    assert len(p2.json()["items"]) == 1


async def test_paper_orders_code_filter(http_test_client, empty_sqlite_db):
    base = date(2025, 11, 1)
    for code in ("sh.filta", "sh.filtb"):
        rows = [_bar(code, base + timedelta(days=i), 5.0) for i in range(4)]
        async with empty_sqlite_db.session() as session:
            await KlineRepository(session).bulk_insert(rows)
        assert (
            http_test_client.post(
                "/api/paper/orders",
                json={"code": code, "side": "buy", "quantity": 100},
            ).status_code
            == 200
        )
    r = http_test_client.get("/api/paper/orders", params={"code": "sh.filta"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["code"] == "sh.filta"


async def test_paper_reset(http_test_client, empty_sqlite_db):
    code = "sh.paper3"
    base = date(2025, 8, 1)
    rows = [_bar(code, base + timedelta(days=i), 5.0) for i in range(10)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)
    http_test_client.post("/api/paper/orders", json={"code": code, "side": "buy", "quantity": 200})
    r = http_test_client.post("/api/paper/account/reset")
    assert r.status_code == 200
    assert r.json()["cash"] == 1_000_000.0
    st = http_test_client.get("/api/paper/state").json()
    assert st["positions"] == []
