"""股票 HTTP 路由：依赖覆盖为临时 SQLite（不读本机 .env 业务库）。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.routers.stocks import _clamp_list_offset
from src.data.models import Market, StockInfo, StockType
from src.data.storage import StockRepository


def test_clamp_list_offset_total_zero():
    assert _clamp_list_offset(0, 10, 99) == 0


def test_clamp_list_offset_within_range():
    assert _clamp_list_offset(10, 3, 6) == 6


def test_clamp_list_offset_past_last_page_start():
    assert _clamp_list_offset(6, 2, 100) == 4


def test_clamp_list_offset_partial_last_page():
    """total=5、limit=2 时末页起点为 4，仅 1 条。"""
    assert _clamp_list_offset(5, 2, 999) == 4


async def test_stocks_list_empty(http_test_client: TestClient):
    r = http_test_client.get("/api/stocks/list")
    assert r.status_code == 200
    assert r.json() == {
        "items": [],
        "total": 0,
        "limit": 100,
        "offset": 0,
    }


async def test_stocks_list_echoes_limit_offset_params(http_test_client: TestClient):
    r = http_test_client.get("/api/stocks/list", params={"limit": 37, "offset": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["limit"] == 37
    assert body["offset"] == 0
    assert body["total"] == 0
    assert body["items"] == []


async def test_stocks_list_offset_clamped_to_last_page(http_test_client, empty_sqlite_db):
    async with empty_sqlite_db.session() as session:
        await StockRepository(session).bulk_upsert(
            [
                StockInfo(
                    code=f"sh.cl{i}",
                    name=f"钳{i}",
                    market=Market.SH,
                    stock_type=StockType.COMMON,
                    industry="越界钳",
                    is_trading=True,
                )
                for i in range(6)
            ]
        )
    r = http_test_client.get(
        "/api/stocks/list",
        params={"industry": "越界钳", "limit": 2, "offset": 100},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 6
    assert body["limit"] == 2
    assert body["offset"] == 4
    assert [x["code"] for x in body["items"]] == ["sh.cl4", "sh.cl5"]


async def test_stocks_list_partial_last_page_when_clamped(
    http_test_client, empty_sqlite_db
):
    """总数不能整除 limit 时，钳到末页后 items 可少于 limit。"""
    async with empty_sqlite_db.session() as session:
        await StockRepository(session).bulk_upsert(
            [
                StockInfo(
                    code=f"sh.pt{i}",
                    name=f"末{i}",
                    market=Market.SH,
                    stock_type=StockType.COMMON,
                    industry="末页半",
                    is_trading=True,
                )
                for i in range(5)
            ]
        )
    r = http_test_client.get(
        "/api/stocks/list",
        params={"industry": "末页半", "limit": 2, "offset": 999},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 5
    assert body["offset"] == 4
    assert [x["code"] for x in body["items"]] == ["sh.pt4"]
    assert len(body["items"]) == 1


async def test_stocks_list_industry_prefix_and_name(http_test_client, empty_sqlite_db):
    async with empty_sqlite_db.session() as session:
        await StockRepository(session).bulk_upsert(
            [
                StockInfo(
                    code="sh.api1",
                    name="接口甲",
                    market=Market.SH,
                    stock_type=StockType.COMMON,
                    industry="新能源 整车",
                    is_trading=True,
                ),
                StockInfo(
                    code="sz.api2",
                    name="接口乙",
                    market=Market.SZ,
                    stock_type=StockType.COMMON,
                    industry="银行",
                    is_trading=True,
                ),
            ]
        )

    r = http_test_client.get(
        "/api/stocks/list", params={"industry": "新能源", "market": "sh"}
    )
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["code"] == "sh.api1"
    assert data["items"][0]["name"] == "接口甲"
    assert data["items"][0]["status"] == "ok"


async def test_stocks_industry_path_returns_models(http_test_client, empty_sqlite_db):
    async with empty_sqlite_db.session() as session:
        await StockRepository(session).bulk_upsert(
            [
                StockInfo(
                    code="sh.api3",
                    name="路径测",
                    market=Market.SH,
                    stock_type=StockType.COMMON,
                    industry="半导体设备",
                    is_trading=True,
                ),
            ]
        )

    r = http_test_client.get("/api/stocks/industry/%E5%8D%8A%E5%AF%BC%E4%BD%93")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["code"] == "sh.api3"
    assert rows[0]["industry"] == "半导体设备"


async def test_stocks_detail_not_found(http_test_client: TestClient):
    r = http_test_client.get("/api/stocks/sh.no_such")
    assert r.status_code == 200
    body = r.json()
    assert body.get("error") == "Stock not found"
    assert body.get("code") == "sh.no_such"


async def test_stocks_list_total_exceeds_page_size(http_test_client, empty_sqlite_db):
    async with empty_sqlite_db.session() as session:
        await StockRepository(session).bulk_upsert(
            [
                StockInfo(
                    code=f"sh.t{i}",
                    name=f"总{i}",
                    market=Market.SH,
                    stock_type=StockType.COMMON,
                    industry="总计测",
                    is_trading=True,
                )
                for i in range(5)
            ]
        )
    r = http_test_client.get(
        "/api/stocks/list",
        params={"industry": "总计测", "limit": 2, "offset": 0},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 5
    assert body["limit"] == 2
    assert body["offset"] == 0
    assert len(body["items"]) == 2


async def test_stocks_list_limit_offset_pagination(http_test_client, empty_sqlite_db):
    async with empty_sqlite_db.session() as session:
        await StockRepository(session).bulk_upsert(
            [
                StockInfo(
                    code=f"sh.pg{i}",
                    name=f"页{i}",
                    market=Market.SH,
                    stock_type=StockType.COMMON,
                    industry="分页测",
                    is_trading=True,
                )
                for i in range(3)
            ]
        )

    r0 = http_test_client.get(
        "/api/stocks/list",
        params={"industry": "分页测", "limit": 2, "offset": 0},
    )
    r1 = http_test_client.get(
        "/api/stocks/list",
        params={"industry": "分页测", "limit": 2, "offset": 1},
    )
    assert r0.status_code == 200 and r1.status_code == 200
    j0, j1 = r0.json(), r1.json()
    assert j0["total"] == 3 and j1["total"] == 3
    assert [x["code"] for x in j0["items"]] == ["sh.pg0", "sh.pg1"]
    assert [x["code"] for x in j1["items"]] == ["sh.pg1", "sh.pg2"]


async def test_stocks_list_does_not_shadow_code_named_list(
    http_test_client, empty_sqlite_db
):
    """路由顺序：/list 须优先于 /{code}。"""
    async with empty_sqlite_db.session() as session:
        await StockRepository(session).bulk_upsert(
            [
                StockInfo(
                    code="list",
                    name="代码就叫 list",
                    market=Market.SH,
                    stock_type=StockType.COMMON,
                    is_trading=True,
                ),
            ]
        )
    r_list = http_test_client.get("/api/stocks/list")
    r_code = http_test_client.get("/api/stocks/list", params={"market": "sh"})
    assert r_list.status_code == 200
    assert isinstance(r_list.json().get("items"), list)
    assert r_code.status_code == 200
    codes = {x["code"] for x in r_code.json()["items"]}
    assert "list" in codes
