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
    sell_body = r_sell.json()
    # 买入 100×10，卖出按新 K 线收盘 11 撮合：
    # 印花税 = 1100 * 0.0005 = 0.55；净收入 = 1099.45
    # 1_000_000 - 1000 + 1099.45 = 1_000_099.45
    assert sell_body["cash_after"] == 1_000_099.45
    assert sell_body["stamp_tax"] == 0.55
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
    r = http_test_client.post("/api/paper/account/reset", json={"account_label": "default"})
    assert r.status_code == 200
    assert r.json()["cash"] == 1_000_000.0
    st = http_test_client.get("/api/paper/state").json()
    assert st["positions"] == []


async def test_paper_state_and_order_respect_adjust_flag(http_test_client, empty_sqlite_db):
    code = "sh.padj"
    base = date(2025, 8, 1)
    rows_unadj = [_bar(code, base + timedelta(days=i), 10.0) for i in range(3)]
    rows_adj = [_bar(code, base + timedelta(days=i), 20.0) for i in range(3)]
    for r in rows_adj:
        r.adjust_flag = "2"
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows_unadj + rows_adj)

    # state with adjust_flag=2 should price at 20
    st = http_test_client.get("/api/paper/state", params={"adjust_flag": "2"}).json()
    assert st["account"]["cash"] == 1_000_000.0

    # buy with adjust_flag=2 -> fill_price=20
    r = http_test_client.post(
        "/api/paper/orders",
        json={"code": code, "side": "buy", "quantity": 100, "adjust_flag": "2"},
    )
    assert r.status_code == 200
    assert r.json()["fill_price"] == 20.0
    assert r.json()["cash_after"] == 1_000_000.0 - 2000.0

    # state default (adjust_flag=3) should price at 10 after buy
    st2 = http_test_client.get("/api/paper/state").json()
    pos = st2["positions"][0]
    assert pos["last_close"] == 10.0
    assert pos["market_value"] == 1000.0


def _bar_with_preclose(code: str, d: date, close: float, pre_close: float) -> KLine:
    o = close - 0.1
    return KLine(
        code=code,
        trade_date=d,
        open=o,
        high=close + 0.2,
        low=o - 0.1,
        close=close,
        pre_close=pre_close,
        volume=1000,
        amount=close * 1000,
        turnover_rate=None,
        pct_change=None,
    )


async def test_paper_buy_limit_up_blocked(http_test_client, empty_sqlite_db):
    """涨停时不可买入。"""
    code = "sh.limitup"
    base = date(2025, 6, 1)
    # pre_close=10.0, close=11.0 = +10% 涨停
    rows = [_bar_with_preclose(code, base + timedelta(days=i), 11.0, 10.0) for i in range(3)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.post(
        "/api/paper/orders",
        json={"code": code, "side": "buy", "quantity": 100},
    )
    assert r.status_code == 400
    assert "涨停" in r.json().get("detail", "")


async def test_paper_sell_limit_down_blocked(http_test_client, empty_sqlite_db):
    """跌停时不可卖出。"""
    code = "sh.limitdown"
    base = date(2025, 6, 1)
    # pre_close=10.0, close=9.0 = -10% 跌停
    rows = [_bar_with_preclose(code, base + timedelta(days=i), 9.0, 10.0) for i in range(3)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    # 先买入
    assert http_test_client.post(
        "/api/paper/orders",
        json={"code": code, "side": "buy", "quantity": 100},
    ).status_code == 200

    # 次日跌停不可卖出
    rows2 = [_bar_with_preclose(code, base + timedelta(days=3), 8.1, 9.0)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows2)

    r = http_test_client.post(
        "/api/paper/orders",
        json={"code": code, "side": "sell", "quantity": 100},
    )
    assert r.status_code == 400
    assert "跌停" in r.json().get("detail", "")


async def test_paper_buy_no_limit_up_ok(http_test_client, empty_sqlite_db):
    """未涨停时可以正常买入。"""
    code = "sh.nolimit"
    base = date(2025, 6, 1)
    # pre_close=10.0, close=10.5 = +5% 未涨停
    rows = [_bar_with_preclose(code, base + timedelta(days=i), 10.5, 10.0) for i in range(3)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.post(
        "/api/paper/orders",
        json={"code": code, "side": "buy", "quantity": 100},
    )
    assert r.status_code == 200
    assert r.json()["fill_price"] == 10.5


async def test_paper_stamp_tax_buy_is_zero(http_test_client, empty_sqlite_db):
    """买入时印花税为 0。"""
    code = "sh.taxbuy"
    base = date(2025, 6, 1)
    rows = [_bar(code, base + timedelta(days=i), 10.0) for i in range(3)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.post(
        "/api/paper/orders",
        json={"code": code, "side": "buy", "quantity": 100},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["stamp_tax"] == 0.0
    assert body["cash_after"] == 1_000_000.0 - 1000.0
