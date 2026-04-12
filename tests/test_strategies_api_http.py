"""策略目录与 POST /api/strategies/signal。"""

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


async def test_strategies_catalog_lists_ma_cross(http_test_client):
    r = http_test_client.get("/api/strategies/catalog")
    assert r.status_code == 200
    data = r.json()
    assert "strategies" in data
    ids = [s["id"] for s in data["strategies"]]
    assert "ma_cross" in ids
    assert "ma_cross_scan" in ids
    ma = next(s for s in data["strategies"] if s["id"] == "ma_cross")
    assert ma.get("backtest_archive_kinds") == ["ma_cross_single", "ma_cross_scan"]
    assert ma.get("strategy_contract_version") == "1"
    assert isinstance(ma.get("title"), str) and ma["title"].strip()
    assert isinstance(ma.get("description"), str) and ma["description"].strip()
    scan = next(s for s in data["strategies"] if s["id"] == "ma_cross_scan")
    assert scan.get("backtest_archive_kinds") == ["ma_cross_scan"]
    assert isinstance(scan.get("title"), str) and scan["title"].strip()
    assert isinstance(scan.get("description"), str) and scan["description"].strip()

    br_ma = ma.get("backtest_run") or {}
    assert br_ma.get("strategy_id") == "ma_cross"
    assert br_ma.get("strategy_version") == "1"
    assert br_ma.get("archive_kind") == "ma_cross_single"
    ps_ma = br_ma.get("params_schema") or {}
    assert ps_ma.get("type") == "object"
    assert "code" in (ps_ma.get("required") or [])

    br_sc = scan.get("backtest_run") or {}
    assert br_sc.get("strategy_id") == "ma_cross_scan"
    assert br_sc.get("archive_kind") == "ma_cross_scan"
    ps_sc = br_sc.get("params_schema") or {}
    assert "codes" in (ps_sc.get("required") or [])

    sig_sc = scan.get("signal_params") or {}
    assert sig_sc.get("maxProperties") == 0
    assert sig_sc.get("additionalProperties") is False


async def test_strategies_signal_ma_cross_scan_kind_400(http_test_client):
    r = http_test_client.post(
        "/api/strategies/signal",
        json={"code": "sh.000001", "kind": "ma_cross_scan", "params": {}},
    )
    assert r.status_code == 400
    detail = r.json().get("detail", "")
    assert "ma_cross_scan" in detail
    assert "ma_cross" in detail or "GET" in detail


async def test_strategies_signal_post_matches_get_ma_cross_signal(http_test_client, empty_sqlite_db):
    code = "sh.strat1"
    base = date(2025, 8, 1)
    rows = [_bar(code, base + timedelta(days=i), 10.0 + i * 0.4) for i in range(45)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    g = http_test_client.get(
        "/api/backtest/ma-cross/signal",
        params={"code": code, "fast": 5, "slow": 20, "limit": 45},
    )
    assert g.status_code == 200
    p = http_test_client.post(
        "/api/strategies/signal",
        json={
            "code": code,
            "kind": "ma_cross",
            "params": {"fast": 5, "slow": 20, "limit": 45},
        },
    )
    assert p.status_code == 200
    body = p.json()
    assert body["kind"] == "ma_cross"
    assert body["signal"] == g.json()


async def test_strategies_signal_unknown_kind_400(http_test_client):
    r = http_test_client.post(
        "/api/strategies/signal",
        json={"code": "sh.x", "kind": "nope", "params": {}},
    )
    assert r.status_code == 400
    assert "nope" in r.json().get("detail", "")


async def test_strategies_signal_fast_ge_slow_400(http_test_client, empty_sqlite_db):
    code = "sh.badfs"
    base = date(2025, 9, 1)
    rows = [_bar(code, base + timedelta(days=i), 1.0 + i * 0.01) for i in range(50)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)
    r = http_test_client.post(
        "/api/strategies/signal",
        json={
            "code": code,
            "kind": "ma_cross",
            "params": {"fast": 20, "slow": 10, "limit": 50},
        },
    )
    assert r.status_code == 400
