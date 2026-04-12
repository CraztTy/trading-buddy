"""看板 HTTP 路由：http_test_client + 临时 SQLite。"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient

from src.data.models import KLine, Market, StockInfo, StockType
from src.data.storage import KlineRepository, StockRepository


def _bar(code: str, d: date, close: float, pct: float | None) -> KLine:
    o = close - 0.2
    return KLine(
        code=code,
        trade_date=d,
        open=o,
        high=close + 0.3,
        low=o - 0.1,
        close=close,
        volume=1000,
        amount=close * 1000,
        turnover_rate=None,
        pct_change=pct,
    )


async def test_dashboard_overview_returns_indices_when_k_exists(
    http_test_client, empty_sqlite_db
):
    indices = ["sh.000001", "sz.399001", "sz.399006", "sh.000300"]
    d0 = date(2025, 2, 1)
    rows: list[KLine] = []
    for code in indices:
        rows.append(_bar(code, d0, 100.0, 0.5))
        rows.append(_bar(code, d0 + timedelta(days=1), 101.0, 1.0))
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get("/api/dashboard/overview")
    assert r.status_code == 200
    body = r.json()
    assert "indices" in body
    codes = {x["code"] for x in body["indices"]}
    assert codes == set(indices)
    for x in body["indices"]:
        assert "price" in x and "pct_change" in x


async def test_dashboard_gainers_orders_by_pct_desc(http_test_client, empty_sqlite_db):
    d_new = date(2025, 3, 10)
    rows = [
        _bar("sh.ga", d_new, 10.0, 5.0),
        _bar("sh.gb", d_new, 10.0, 9.0),
        _bar("sh.gc", d_new - timedelta(days=5), 10.0, 99.0),
    ]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get("/api/dashboard/gainers", params={"limit": 5})
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 2
    assert data[0]["code"] == "sh.gb"
    assert data[0]["pct_change"] == 9.0
    assert data[1]["code"] == "sh.ga"


async def test_dashboard_losers_orders_by_pct_asc(http_test_client, empty_sqlite_db):
    d_new = date(2025, 4, 1)
    rows = [
        _bar("sz.la", d_new, 10.0, -2.0),
        _bar("sz.lb", d_new, 10.0, -6.0),
    ]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get("/api/dashboard/losers", params={"limit": 5})
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 2
    assert data[0]["code"] == "sz.lb"
    assert data[0]["pct_change"] == -6.0


async def test_dashboard_turnover_global_rank_by_amount(http_test_client, empty_sqlite_db):
    """成交额榜为全市场交易中标的按当日 amount 降序，与 code 字典序无关。"""
    d = date(2025, 5, 1)
    async with empty_sqlite_db.session() as session:
        await StockRepository(session).bulk_upsert(
            [
                StockInfo(
                    code="sh.aaa",
                    name="甲",
                    market=Market.SH,
                    stock_type=StockType.COMMON,
                    is_trading=True,
                ),
                StockInfo(
                    code="sh.mmm",
                    name="乙",
                    market=Market.SH,
                    stock_type=StockType.COMMON,
                    is_trading=True,
                ),
                StockInfo(
                    code="sh.zzz",
                    name="丙",
                    market=Market.SH,
                    stock_type=StockType.COMMON,
                    is_trading=True,
                ),
            ]
        )
        rows = [
            _bar("sh.aaa", d, 10.0, 1.0).model_copy(update={"amount": 1_000_000.0}),
            _bar("sh.mmm", d, 20.0, 1.0).model_copy(update={"amount": 3_000_000.0}),
            _bar("sh.zzz", d, 30.0, 1.0).model_copy(update={"amount": 2_000_000.0}),
        ]
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get("/api/dashboard/turnover", params={"limit": 2})
    assert r.status_code == 200
    stocks = r.json()["stocks"]
    assert len(stocks) == 2
    assert [s["code"] for s in stocks] == ["sh.mmm", "sh.zzz"]
    assert stocks[0]["amount"] >= stocks[1]["amount"]


async def test_dashboard_turnover_respects_trade_date_param(
    http_test_client, empty_sqlite_db
):
    d_old = date(2025, 5, 1)
    d_new = date(2025, 5, 2)
    async with empty_sqlite_db.session() as session:
        await StockRepository(session).bulk_upsert(
            [
                StockInfo(
                    code="sh.dt1",
                    name="D1",
                    market=Market.SH,
                    stock_type=StockType.COMMON,
                    is_trading=True,
                ),
            ]
        )
        k_old = _bar("sh.dt1", d_old, 10.0, 1.0).model_copy(update={"amount": 5_000_000.0})
        k_new = _bar("sh.dt1", d_new, 11.0, 1.0).model_copy(update={"amount": 500_000.0})
        await KlineRepository(session).bulk_insert([k_old, k_new])

    r = http_test_client.get(
        "/api/dashboard/turnover",
        params={"trade_date": str(d_old), "limit": 5},
    )
    assert r.status_code == 200
    stocks = r.json()["stocks"]
    assert len(stocks) == 1
    assert stocks[0]["code"] == "sh.dt1"
    assert stocks[0]["amount"] == 5_000_000.0


async def test_dashboard_turnover_empty_when_no_klines(http_test_client, empty_sqlite_db):
    r = http_test_client.get("/api/dashboard/turnover", params={"limit": 5})
    assert r.status_code == 200
    assert r.json() == {"stocks": []}


async def test_dashboard_turnover_invalid_trade_date_422(http_test_client: TestClient):
    r = http_test_client.get(
        "/api/dashboard/turnover",
        params={"trade_date": "not-a-date", "limit": 3},
    )
    assert r.status_code == 422
