"""回测结果存档 HTTP。"""

from __future__ import annotations


def _single_payload():
    return {
        "kind": "ma_cross_single",
        "request_params": {"code": "sh.000001", "fast": 5, "slow": 20, "limit": 120},
        "response_payload": {
            "code": "sh.000001",
            "fast_period": 5,
            "slow_period": 20,
            "bars_used": 120,
            "total_return_pct": 1.5,
            "buy_hold_return_pct": 0.8,
            "equity_curve": [],
            "note": "test",
        },
    }


def _buy_hold_payload():
    return {
        "kind": "buy_hold_single",
        "request_params": {"code": "sh.000001", "limit": 120},
        "response_payload": {
            "code": "sh.000001",
            "fast_period": 1,
            "slow_period": 2,
            "bars_used": 120,
            "total_return_pct": 2.5,
            "buy_hold_return_pct": 2.5,
            "equity_curve": [],
            "note": "test buy_hold",
        },
    }


def _scan_payload():
    return {
        "kind": "ma_cross_scan",
        "request_params": {"fast": "5", "slow": "20", "codes": "sh.a\nsh.b"},
        "response_payload": {
            "fast_period": 5,
            "slow_period": 20,
            "limit": 500,
            "commission_rate": 0.0,
            "slippage_rate": 0.0,
            "sort_by": "total_return",
            "max_concurrent": 8,
            "items": [
                {"code": "sh.a", "error": None, "total_return_pct": 1.0},
                {"code": "sh.b", "error": "no data"},
            ],
        },
    }


async def test_backtest_run_create_and_list(http_test_client, empty_sqlite_db):
    c = http_test_client.post("/api/backtest/runs", json=_single_payload())
    assert c.status_code == 201
    b = c.json()
    assert b["id"] >= 1
    assert "MA" in b["summary"]

    lst = http_test_client.get("/api/backtest/runs", params={"limit": 10, "offset": 0})
    assert lst.status_code == 200
    body = lst.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == b["id"]


async def test_backtest_run_detail(http_test_client, empty_sqlite_db):
    rid = http_test_client.post("/api/backtest/runs", json=_scan_payload()).json()["id"]
    d = http_test_client.get(f"/api/backtest/runs/{rid}")
    assert d.status_code == 200
    x = d.json()
    assert x["kind"] == "ma_cross_scan"
    assert x["request_params"]["codes"] == "sh.a\nsh.b"
    assert len(x["response_payload"]["items"]) == 2


async def test_backtest_run_detail_404(http_test_client, empty_sqlite_db):
    assert http_test_client.get("/api/backtest/runs/99999").status_code == 404


async def test_backtest_run_bad_kind_400(http_test_client, empty_sqlite_db):
    p = _single_payload()
    p["kind"] = "other"
    r = http_test_client.post("/api/backtest/runs", json=p)
    assert r.status_code == 422


async def test_backtest_runs_list_filter_kind(http_test_client, empty_sqlite_db):
    single_id = http_test_client.post("/api/backtest/runs", json=_single_payload()).json()["id"]
    scan_id = http_test_client.post("/api/backtest/runs", json=_scan_payload()).json()["id"]
    bh_id = http_test_client.post("/api/backtest/runs", json=_buy_hold_payload()).json()["id"]
    only_scan = http_test_client.get("/api/backtest/runs", params={"kind": "ma_cross_scan", "limit": 20, "offset": 0})
    assert only_scan.status_code == 200
    body = only_scan.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == scan_id
    only_single = http_test_client.get("/api/backtest/runs", params={"kind": "ma_cross_single"})
    assert only_single.json()["total"] == 1
    assert only_single.json()["items"][0]["id"] == single_id
    only_bh = http_test_client.get("/api/backtest/runs", params={"kind": "buy_hold_single"})
    assert only_bh.json()["total"] == 1
    assert only_bh.json()["items"][0]["id"] == bh_id
    all_rows = http_test_client.get("/api/backtest/runs", params={"limit": 50, "offset": 0})
    assert all_rows.json()["total"] == 3


async def test_backtest_runs_list_bad_kind_query_422(http_test_client, empty_sqlite_db):
    r = http_test_client.get("/api/backtest/runs", params={"kind": "nope"})
    assert r.status_code == 422


async def test_backtest_run_delete(http_test_client, empty_sqlite_db):
    rid = http_test_client.post("/api/backtest/runs", json=_single_payload()).json()["id"]
    d = http_test_client.delete(f"/api/backtest/runs/{rid}")
    assert d.status_code == 204
    assert d.content == b""
    assert http_test_client.get(f"/api/backtest/runs/{rid}").status_code == 404
    assert http_test_client.get("/api/backtest/runs").json()["total"] == 0


async def test_backtest_run_delete_404(http_test_client, empty_sqlite_db):
    assert http_test_client.delete("/api/backtest/runs/99999").status_code == 404


async def test_backtest_runs_list_filter_summary_q(http_test_client, empty_sqlite_db):
    single_id = http_test_client.post("/api/backtest/runs", json=_single_payload()).json()["id"]
    scan_id = http_test_client.post("/api/backtest/runs", json=_scan_payload()).json()["id"]
    hit = http_test_client.get("/api/backtest/runs", params={"q": "批量", "limit": 20, "offset": 0})
    assert hit.status_code == 200
    body = hit.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == scan_id
    miss = http_test_client.get("/api/backtest/runs", params={"q": "no_such_substring_xyz"})
    assert miss.json()["total"] == 0
    both = http_test_client.get("/api/backtest/runs", params={"q": "MA", "kind": "ma_cross_single"})
    assert both.json()["total"] == 1
    assert both.json()["items"][0]["id"] == single_id
