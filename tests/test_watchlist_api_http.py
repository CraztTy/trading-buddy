"""自选股 HTTP：列表、添加、删除、重复与不存在。"""

from __future__ import annotations

from src.data.models import StockInfo, Market, StockType
from src.data.storage import StockRepository


async def test_watchlist_empty_then_add_list(http_test_client, empty_sqlite_db):
    r0 = http_test_client.get("/api/watchlist/items")
    assert r0.status_code == 200
    b0 = r0.json()
    assert b0["watchlist_id"] >= 1
    assert b0["items"] == []

    r1 = http_test_client.post("/api/watchlist/items", json={"code": "sh.600000"})
    assert r1.status_code == 201

    r2 = http_test_client.get("/api/watchlist/items")
    assert r2.status_code == 200
    items = r2.json()["items"]
    assert len(items) == 1
    assert items[0]["code"] == "sh.600000"


async def test_watchlist_joins_name(http_test_client, empty_sqlite_db):
    async with empty_sqlite_db.session() as session:
        await StockRepository(session).bulk_upsert(
            [
                StockInfo(
                    code="sz.000001",
                    name="JoinName-e2e",
                    market=Market.SZ,
                    stock_type=StockType.COMMON,
                    is_trading=True,
                )
            ]
        )
    assert http_test_client.post("/api/watchlist/items", json={"code": "sz.000001"}).status_code == 201
    items = http_test_client.get("/api/watchlist/items").json()["items"]
    assert items[0]["name"] == "JoinName-e2e"


async def test_watchlist_duplicate_409(http_test_client, empty_sqlite_db):
    http_test_client.post("/api/watchlist/items", json={"code": "sh.600036"})
    r = http_test_client.post("/api/watchlist/items", json={"code": "SH.600036"})
    assert r.status_code == 409


async def test_watchlist_delete_and_404(http_test_client, empty_sqlite_db):
    http_test_client.post("/api/watchlist/items", json={"code": "bj.430047"})
    d = http_test_client.delete("/api/watchlist/items/bj.430047")
    assert d.status_code == 200
    assert http_test_client.get("/api/watchlist/items").json()["items"] == []
    n = http_test_client.delete("/api/watchlist/items/bj.430047")
    assert n.status_code == 404


async def test_watchlist_bad_code_400(http_test_client, empty_sqlite_db):
    assert http_test_client.post("/api/watchlist/items", json={"code": "invalid"}).status_code == 400
