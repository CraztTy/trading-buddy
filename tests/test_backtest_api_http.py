"""回测 HTTP：单标的 ma-cross 最小 happy path。"""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

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


async def test_ma_cross_backtest_returns_metrics(http_test_client, empty_sqlite_db):
    code = "sh.btm1"
    base = date(2025, 5, 1)
    rows = [_bar(code, base + timedelta(days=i), 100.0 + i * 0.3) for i in range(80)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(
        "/api/backtest/ma-cross",
        params={"code": code, "fast": 5, "slow": 20, "limit": 80},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == code
    assert body["fast_period"] == 5
    assert body["slow_period"] == 20
    assert body["bars_used"] == 80
    assert "total_return_pct" in body
    assert isinstance(body.get("equity_curve"), list)
    assert len(body["equity_curve"]) >= 1


async def test_ma_cross_fast_ge_slow_400(http_test_client: TestClient):
    r = http_test_client.get(
        "/api/backtest/ma-cross",
        params={"code": "sh.x", "fast": 20, "slow": 10, "limit": 100},
    )
    assert r.status_code == 400


async def test_ma_cross_signal_ok(http_test_client, empty_sqlite_db):
    code = "sh.sigx"
    base = date(2025, 6, 1)
    rows = [_bar(code, base + timedelta(days=i), 10.0 + i * 0.5) for i in range(40)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)
    r = http_test_client.get(
        "/api/backtest/ma-cross/signal",
        params={"code": code, "fast": 5, "slow": 20, "limit": 40},
    )
    assert r.status_code == 200
    b = r.json()
    assert b["code"] == code
    assert b["position"] in ("long", "flat")
    assert b["as_of_date"]
    assert b["bars_used"] == 40
    assert "ma_fast" in b and "ma_slow" in b


async def test_ma_cross_signal_fast_ge_slow_400(http_test_client: TestClient):
    r = http_test_client.get(
        "/api/backtest/ma-cross/signal",
        params={"code": "sh.x", "fast": 20, "slow": 10, "limit": 100},
    )
    assert r.status_code == 400


async def test_ma_cross_signal_insufficient_klines_400(http_test_client, empty_sqlite_db):
    code = "sh.sigshort"
    base = date(2025, 7, 1)
    rows = [_bar(code, base + timedelta(days=i), 1.0) for i in range(10)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)
    r = http_test_client.get(
        "/api/backtest/ma-cross/signal",
        params={"code": code, "fast": 5, "slow": 20, "limit": 80},
    )
    assert r.status_code == 400
    assert "K 线不足" in r.json().get("detail", "")


async def test_ma_cross_backtest_no_klines_400(http_test_client, empty_sqlite_db):
    r = http_test_client.get(
        "/api/backtest/ma-cross",
        params={"code": "sh.no_rows", "fast": 5, "slow": 20, "limit": 80},
    )
    assert r.status_code == 400
    detail = r.json().get("detail", "")
    assert "K 线不足" in detail
    assert "当前 0" in detail


async def test_ma_cross_backtest_insufficient_bars_400(http_test_client, empty_sqlite_db):
    code = "sh.short_hist"
    base = date(2025, 9, 1)
    rows = [_bar(code, base + timedelta(days=i), 1.0 + i * 0.01) for i in range(10)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)
    r = http_test_client.get(
        "/api/backtest/ma-cross",
        params={"code": code, "fast": 5, "slow": 20, "limit": 80},
    )
    assert r.status_code == 400
    detail = r.json().get("detail", "")
    assert "K 线不足" in detail
    assert "当前 10" in detail


async def test_ma_cross_backtest_benchmark_missing_400(http_test_client, empty_sqlite_db):
    code = "sh.with_k_only"
    base = date(2025, 10, 1)
    rows = [_bar(code, base + timedelta(days=i), 100.0) for i in range(80)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)
    r = http_test_client.get(
        "/api/backtest/ma-cross",
        params={
            "code": code,
            "fast": 5,
            "slow": 20,
            "limit": 80,
            "benchmark_code": "sh.bench_missing",
        },
    )
    assert r.status_code == 400
    assert "基准" in r.json().get("detail", "")


async def test_ma_cross_backtest_with_benchmark_json(http_test_client, empty_sqlite_db):
    """单标的回测传入 benchmark_code：标的与基准同一日历对齐日 K。"""
    sym = "sh.single_sym"
    bench = "sh.single_bench"
    base = date(2025, 11, 1)
    rows: list[KLine] = []
    for i in range(80):
        d = base + timedelta(days=i)
        rows.append(_bar(sym, d, 150.0 + i * 0.12))
        rows.append(_bar(bench, d, 4000.0 + i * 0.03))
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(
        "/api/backtest/ma-cross",
        params={
            "code": sym,
            "benchmark_code": bench,
            "fast": 5,
            "slow": 20,
            "limit": 80,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == sym
    assert body["benchmark_code"] == bench
    assert body["bars_used"] == 80
    assert isinstance(body.get("underlying_beta"), (int, float))
    assert isinstance(body.get("underlying_alpha_ann_pct"), (int, float))


async def test_ma_cross_scan_json_two_codes(http_test_client, empty_sqlite_db):
    base = date(2025, 5, 1)
    rows: list[KLine] = []
    for code in ("sh.scan1", "sh.scan2"):
        rows.extend(
            [_bar(code, base + timedelta(days=i), 100.0 + i * 0.2) for i in range(80)]
        )
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(
        "/api/backtest/ma-cross/scan",
        params={
            "codes": "sh.scan1,sh.scan2",
            "fast": 5,
            "slow": 20,
            "limit": 80,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["fast_period"] == 5
    assert body["slow_period"] == 20
    assert len(body["items"]) == 2
    codes = {it["code"] for it in body["items"]}
    assert codes == {"sh.scan1", "sh.scan2"}
    for it in body["items"]:
        assert it.get("error") is None
        assert it["bars_used"] == 80
        assert "total_return_pct" in it


async def test_ma_cross_scan_csv_export(http_test_client, empty_sqlite_db):
    code = "sh.csv1"
    base = date(2025, 6, 1)
    rows = [_bar(code, base + timedelta(days=i), 50.0 + i * 0.1) for i in range(80)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(
        "/api/backtest/ma-cross/scan",
        params={"codes": code, "fast": 5, "slow": 20, "limit": 80, "export": "csv"},
    )
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")
    assert "attachment" in r.headers.get("content-disposition", "").lower()
    raw = r.content
    assert raw.startswith(b"\xef\xbb\xbf")
    assert b"sh.csv1" in raw


async def test_ma_cross_scan_with_benchmark_json(http_test_client, empty_sqlite_db):
    """扫描带 benchmark_code：标的与基准同一日历对齐日 K。"""
    sym = "sh.scan_sym"
    bench = "sh.bench300"
    base = date(2025, 8, 1)
    rows: list[KLine] = []
    for i in range(80):
        d = base + timedelta(days=i)
        rows.append(_bar(sym, d, 200.0 + i * 0.15))
        rows.append(_bar(bench, d, 3000.0 + i * 0.02))
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(
        "/api/backtest/ma-cross/scan",
        params={
            "codes": sym,
            "benchmark_code": bench,
            "fast": 5,
            "slow": 20,
            "limit": 80,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["benchmark_code"] == bench
    assert len(body["items"]) == 1
    it = body["items"][0]
    assert it["code"] == sym
    assert it.get("error") is None
    assert it["bars_used"] == 80
    assert isinstance(it.get("underlying_beta"), (int, float))


async def test_ma_cross_scan_benchmark_missing_400(http_test_client, empty_sqlite_db):
    code = "sh.bonly"
    base = date(2025, 7, 1)
    rows = [_bar(code, base + timedelta(days=i), 10.0 + i * 0.05) for i in range(80)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(
        "/api/backtest/ma-cross/scan",
        params={
            "codes": code,
            "benchmark_code": "sh.no_such_bench",
            "fast": 5,
            "slow": 20,
            "limit": 80,
        },
    )
    assert r.status_code == 400
    assert "基准" in r.json().get("detail", "")


async def test_ma_cross_scan_invalid_export_400(http_test_client: TestClient):
    r = http_test_client.get(
        "/api/backtest/ma-cross/scan",
        params={"codes": "sh.x", "export": "xml"},
    )
    assert r.status_code == 400


async def test_ma_cross_scan_empty_codes_400(http_test_client: TestClient):
    r = http_test_client.get(
        "/api/backtest/ma-cross/scan",
        params={"codes": ",", "fast": 5, "slow": 20, "limit": 80},
    )
    assert r.status_code == 400


async def test_ma_cross_scan_fast_ge_slow_400(http_test_client: TestClient):
    r = http_test_client.get(
        "/api/backtest/ma-cross/scan",
        params={"codes": "sh.a", "fast": 30, "slow": 10, "limit": 80},
    )
    assert r.status_code == 400


async def test_ma_cross_scan_invalid_sort_by_400(http_test_client: TestClient):
    r = http_test_client.get(
        "/api/backtest/ma-cross/scan",
        params={
            "codes": "sh.a",
            "fast": 5,
            "slow": 20,
            "limit": 80,
            "sort_by": "not_a_valid_metric",
        },
    )
    assert r.status_code == 400
    detail = r.json().get("detail", "")
    assert "sort_by" in detail


async def test_ma_cross_scan_fees_sum_over_limit_400(http_test_client: TestClient):
    r = http_test_client.get(
        "/api/backtest/ma-cross/scan",
        params={
            "codes": "sh.a",
            "fast": 5,
            "slow": 20,
            "limit": 80,
            "commission_rate": 0.05,
            "slippage_rate": 0.04,
        },
    )
    assert r.status_code == 400
    assert "0.08" in r.json().get("detail", "")


async def test_ma_cross_backtest_fees_sum_over_limit_400(http_test_client: TestClient):
    r = http_test_client.get(
        "/api/backtest/ma-cross",
        params={
            "code": "sh.a",
            "fast": 5,
            "slow": 20,
            "limit": 80,
            "commission_rate": 0.05,
            "slippage_rate": 0.04,
        },
    )
    assert r.status_code == 400
    assert "0.08" in r.json().get("detail", "")


async def test_ma_cross_backtest_start_after_end_400(http_test_client: TestClient):
    r = http_test_client.get(
        "/api/backtest/ma-cross",
        params={
            "code": "sh.a",
            "fast": 5,
            "slow": 20,
            "limit": 80,
            "start_date": "2025-06-01",
            "end_date": "2025-05-01",
        },
    )
    assert r.status_code == 400
    detail = r.json().get("detail", "")
    assert "start_date" in detail
    assert "end_date" in detail


async def test_ma_cross_scan_start_after_end_400(http_test_client: TestClient):
    r = http_test_client.get(
        "/api/backtest/ma-cross/scan",
        params={
            "codes": "sh.a",
            "fast": 5,
            "slow": 20,
            "limit": 80,
            "start_date": "2025-06-01",
            "end_date": "2025-05-01",
        },
    )
    assert r.status_code == 400
    detail = r.json().get("detail", "")
    assert "start_date" in detail
    assert "end_date" in detail


async def test_backtest_run_mvp_buy_hold_matches_get_buy_hold(http_test_client, empty_sqlite_db):
    code = "sh.bhrun"
    base = date(2025, 8, 10)
    rows = [_bar(code, base + timedelta(days=i), 50.0 + i * 0.2) for i in range(60)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    g = http_test_client.get(
        "/api/backtest/buy-hold",
        params={"code": code, "limit": 60},
    )
    assert g.status_code == 200
    p = http_test_client.post(
        "/api/backtest/run",
        json={
            "strategy_id": "buy_hold",
            "strategy_version": "1",
            "params": {"code": code, "limit": 60},
        },
    )
    assert p.status_code == 200
    body = p.json()
    assert body["engine_version"] == "0.1"
    assert body["strategy_id"] == "buy_hold"
    assert isinstance(body.get("assumptions"), list)
    assert len(body["assumptions"]) >= 2
    assert body["result"] == g.json()
    assert body.get("scan_result") is None


async def test_backtest_run_mvp_ma_cross_matches_get_ma_cross(http_test_client, empty_sqlite_db):
    code = "sh.runmvp"
    base = date(2025, 8, 10)
    rows = [_bar(code, base + timedelta(days=i), 50.0 + i * 0.2) for i in range(60)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    g = http_test_client.get(
        "/api/backtest/ma-cross",
        params={"code": code, "fast": 5, "slow": 20, "limit": 60},
    )
    assert g.status_code == 200
    p = http_test_client.post(
        "/api/backtest/run",
        json={
            "strategy_id": "ma_cross",
            "strategy_version": "1",
            "params": {"code": code, "fast": 5, "slow": 20, "limit": 60},
        },
    )
    assert p.status_code == 200
    body = p.json()
    assert body["engine_version"] == "0.1"
    assert body["strategy_id"] == "ma_cross"
    assert isinstance(body.get("assumptions"), list)
    assert len(body["assumptions"]) >= 2
    assert body["result"] == g.json()
    assert body.get("scan_result") is None


async def test_backtest_run_mvp_ma_cross_forward_placeholders_ignored(
    http_test_client, empty_sqlite_db
):
    """草案级占位字段与未知键不改变 MA 单标的结果（与无占位 POST 一致）。"""
    code = "sh.fwdmvp"
    base = date(2025, 8, 20)
    rows = [_bar(code, base + timedelta(days=i), 48.0 + i * 0.18) for i in range(58)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    minimal = {
        "strategy_id": "ma_cross",
        "strategy_version": "1",
        "params": {"code": code, "fast": 5, "slow": 20, "limit": 58},
    }
    baseline = http_test_client.post("/api/backtest/run", json=minimal)
    assert baseline.status_code == 200
    with_placeholders = http_test_client.post(
        "/api/backtest/run",
        json={
            **minimal,
            "universe": ["sh.600519", "sz.000001"],
            "interval": "1d",
            "start": "2020-01-01",
            "end": "2030-12-31",
            "initial_cash": 1_000_000.0,
            "commission": 0.0002,
            "slippage": 0.0001,
            "unknown_future_field": {"nested": True},
        },
    )
    assert with_placeholders.status_code == 200
    assert with_placeholders.json() == baseline.json()


async def test_backtest_run_mvp_ma_cross_scan_matches_get_scan(http_test_client, empty_sqlite_db):
    base = date(2025, 5, 1)
    rows: list[KLine] = []
    for code in ("sh.scan1", "sh.scan2"):
        rows.extend(
            [_bar(code, base + timedelta(days=i), 100.0 + i * 0.2) for i in range(80)]
        )
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    g = http_test_client.get(
        "/api/backtest/ma-cross/scan",
        params={
            "codes": "sh.scan1,sh.scan2",
            "fast": 5,
            "slow": 20,
            "limit": 80,
        },
    )
    assert g.status_code == 200
    p = http_test_client.post(
        "/api/backtest/run",
        json={
            "strategy_id": "ma_cross_scan",
            "strategy_version": "1",
            "params": {
                "codes": "sh.scan1,sh.scan2",
                "fast": 5,
                "slow": 20,
                "limit": 80,
            },
        },
    )
    assert p.status_code == 200
    body = p.json()
    assert body["engine_version"] == "0.1"
    assert body["strategy_id"] == "ma_cross_scan"
    assert body.get("result") is None
    assert isinstance(body.get("assumptions"), list)
    assert len(body["assumptions"]) >= 2
    assert body["scan_result"] == g.json()


async def test_backtest_run_mvp_ma_cross_scan_empty_codes_400(http_test_client: TestClient):
    r = http_test_client.post(
        "/api/backtest/run",
        json={
            "strategy_id": "ma_cross_scan",
            "strategy_version": "1",
            "params": {
                "codes": ",",
                "fast": 5,
                "slow": 20,
                "limit": 80,
            },
        },
    )
    assert r.status_code == 400


async def test_backtest_run_mvp_ma_cross_scan_wrong_version_400(http_test_client: TestClient):
    r = http_test_client.post(
        "/api/backtest/run",
        json={
            "strategy_id": "ma_cross_scan",
            "strategy_version": "2",
            "params": {"codes": "sh.a", "fast": 5, "slow": 20, "limit": 80},
        },
    )
    assert r.status_code == 400


async def test_backtest_run_mvp_unknown_strategy_400(http_test_client: TestClient):
    r = http_test_client.post(
        "/api/backtest/run",
        json={
            "strategy_id": "macd",
            "strategy_version": "1",
            "params": {"code": "sh.x", "fast": 5, "slow": 20, "limit": 100},
        },
    )
    assert r.status_code == 400
    detail = r.json().get("detail", "")
    assert "ma_cross" in detail
    assert "buy_hold" in detail


async def test_backtest_run_mvp_wrong_version_400(http_test_client: TestClient):
    r = http_test_client.post(
        "/api/backtest/run",
        json={
            "strategy_id": "ma_cross",
            "strategy_version": "2",
            "params": {"code": "sh.x", "fast": 5, "slow": 20, "limit": 100},
        },
    )
    assert r.status_code == 400


async def test_backtest_run_mvp_buy_hold_params_missing_code_422(http_test_client: TestClient):
    r = http_test_client.post(
        "/api/backtest/run",
        json={
            "strategy_id": "buy_hold",
            "strategy_version": "1",
            "params": {"limit": 100},
        },
    )
    assert r.status_code == 422
    detail = r.json().get("detail")
    assert isinstance(detail, list)
    assert any("code" in str(item).lower() for item in detail)


async def test_backtest_run_mvp_ma_cross_params_missing_code_422(http_test_client: TestClient):
    """``MaCrossRunParamsBody`` 与 GET 同形；缺 ``code`` 时 422（与 catalog ``params_schema`` 一致）。"""
    r = http_test_client.post(
        "/api/backtest/run",
        json={
            "strategy_id": "ma_cross",
            "strategy_version": "1",
            "params": {"fast": 5, "slow": 20, "limit": 100},
        },
    )
    assert r.status_code == 422
    detail = r.json().get("detail")
    assert isinstance(detail, list)
    assert any("code" in str(item).lower() for item in detail)


async def test_backtest_run_mvp_ma_cross_scan_params_missing_codes_422(http_test_client: TestClient):
    r = http_test_client.post(
        "/api/backtest/run",
        json={
            "strategy_id": "ma_cross_scan",
            "strategy_version": "1",
            "params": {"fast": 5, "slow": 20, "limit": 80},
        },
    )
    assert r.status_code == 422
    detail = r.json().get("detail")
    assert isinstance(detail, list)
    assert any("codes" in str(item).lower() for item in detail)


async def test_backtest_run_mvp_async_ma_cross_polls_to_completed(
    http_test_client, empty_sqlite_db
):
    code = "sh.asyncmvp"
    base = date(2025, 9, 1)
    rows = [_bar(code, base + timedelta(days=i), 50.0 + i * 0.15) for i in range(55)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    p = http_test_client.post(
        "/api/backtest/run?async=1",
        json={
            "strategy_id": "ma_cross",
            "strategy_version": "1",
            "params": {"code": code, "fast": 5, "slow": 20, "limit": 55},
        },
    )
    assert p.status_code == 202
    accepted = p.json()
    assert accepted.get("status") == "accepted"
    job_id = accepted.get("job_id")
    assert isinstance(job_id, str) and len(job_id) >= 16
    sp = accepted.get("status_path", "")
    assert job_id in sp

    last: str | None = None
    for _ in range(200):
        gr = http_test_client.get(f"/api/backtest/jobs/{job_id}")
        assert gr.status_code == 200
        body = gr.json()
        last = body.get("status")
        if last == "completed":
            assert body.get("async_job_persistence") == "memory"
            assert body.get("result") is not None
            assert body["result"]["strategy_id"] == "ma_cross"
            assert body["result"].get("result") is not None
            assert body["result"].get("scan_result") is None
            assert isinstance(body.get("queued_at"), str) and body["queued_at"].endswith("Z")
            assert isinstance(body.get("started_at"), str) and body["started_at"].endswith("Z")
            assert isinstance(body.get("finished_at"), str) and body["finished_at"].endswith("Z")
            break
        if last == "failed":
            raise AssertionError(body.get("error") or "async job failed")
        time.sleep(0.02)
    else:
        raise AssertionError(f"async job did not complete, last={last}")


async def test_backtest_run_mvp_async_job_unknown_404(http_test_client: TestClient):
    r = http_test_client.get("/api/backtest/jobs/ffffffffffffffffffffffffffffffff")
    assert r.status_code == 404


async def test_backtest_job_cancel_unknown_404(
    http_test_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("BACKTEST_ASYNC_JOB_STORE", "memory")
    r = http_test_client.post("/api/backtest/jobs/ffffffffffffffffffffffffffffffff/cancel")
    assert r.status_code == 404


async def test_backtest_job_cancel_pending_200(
    http_test_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("BACKTEST_ASYNC_JOB_STORE", "memory")
    from src.api.routers import backtest as br

    jid = "b" * 32
    async with br._mvp_jobs_lock:
        br._mvp_jobs[jid] = {
            "status": "pending",
            "queued_at": "2026-01-01T00:00:00Z",
            "started_at": None,
            "finished_at": None,
            "result": None,
            "error": None,
        }
    try:
        r = http_test_client.post(f"/api/backtest/jobs/{jid}/cancel")
        assert r.status_code == 200
        assert r.json() == {"job_id": jid, "status": "cancelled"}
        g = http_test_client.get(f"/api/backtest/jobs/{jid}")
        assert g.status_code == 200
        assert g.json()["status"] == "cancelled"
        assert g.json().get("result") is None
    finally:
        async with br._mvp_jobs_lock:
            br._mvp_jobs.pop(jid, None)


async def test_backtest_job_cancel_running_409(
    http_test_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("BACKTEST_ASYNC_JOB_STORE", "memory")
    from src.api.routers import backtest as br

    jid = "c" * 32
    async with br._mvp_jobs_lock:
        br._mvp_jobs[jid] = {
            "status": "running",
            "queued_at": "2026-01-01T00:00:00Z",
            "started_at": "2026-01-01T00:00:01Z",
            "finished_at": None,
            "result": None,
            "error": None,
        }
    try:
        r = http_test_client.post(f"/api/backtest/jobs/{jid}/cancel")
        assert r.status_code == 409
    finally:
        async with br._mvp_jobs_lock:
            br._mvp_jobs.pop(jid, None)


async def test_backtest_job_get_reclaims_stale_running(
    http_test_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    from src.api.routers import backtest as br
    from src.backtest.async_job_backend import STALE_RUNNING_RECLAIM_MSG

    monkeypatch.setenv("BACKTEST_ASYNC_JOB_STORE", "memory")
    monkeypatch.setenv("BACKTEST_ASYNC_JOB_STUCK_SEC", "30")
    old = (datetime.now(timezone.utc) - timedelta(seconds=120)).replace(microsecond=0)
    started = old.isoformat().replace("+00:00", "Z")
    jid = "d" * 32
    async with br._mvp_jobs_lock:
        br._mvp_jobs[jid] = {
            "status": "running",
            "queued_at": "2026-01-01T00:00:00Z",
            "started_at": started,
            "finished_at": None,
            "result": None,
            "error": None,
        }
    try:
        g = http_test_client.get(f"/api/backtest/jobs/{jid}")
        assert g.status_code == 200
        b = g.json()
        assert b["status"] == "failed"
        assert STALE_RUNNING_RECLAIM_MSG in (b.get("error") or "")
        assert isinstance(b.get("finished_at"), str) and b["finished_at"].endswith("Z")
    finally:
        async with br._mvp_jobs_lock:
            br._mvp_jobs.pop(jid, None)


async def test_backtest_job_get_does_not_reclaim_when_stuck_disabled(
    http_test_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    from src.api.routers import backtest as br

    monkeypatch.setenv("BACKTEST_ASYNC_JOB_STORE", "memory")
    monkeypatch.setenv("BACKTEST_ASYNC_JOB_STUCK_SEC", "0")
    old = (datetime.now(timezone.utc) - timedelta(seconds=3600)).replace(microsecond=0)
    started = old.isoformat().replace("+00:00", "Z")
    jid = "e" * 32
    async with br._mvp_jobs_lock:
        br._mvp_jobs[jid] = {
            "status": "running",
            "queued_at": "2026-01-01T00:00:00Z",
            "started_at": started,
            "finished_at": None,
            "result": None,
            "error": None,
        }
    try:
        g = http_test_client.get(f"/api/backtest/jobs/{jid}")
        assert g.status_code == 200
        assert g.json()["status"] == "running"
    finally:
        async with br._mvp_jobs_lock:
            br._mvp_jobs.pop(jid, None)


async def test_backtest_run_mvp_async_bad_strategy_400_no_job(http_test_client: TestClient):
    r = http_test_client.post(
        "/api/backtest/run?async=true",
        json={
            "strategy_id": "not_registered",
            "strategy_version": "1",
            "params": {"code": "sh.x", "fast": 5, "slow": 20, "limit": 100},
        },
    )
    assert r.status_code == 400


async def test_backtest_catalog_lists_registered_strategies(http_test_client: TestClient):
    r = http_test_client.get("/api/backtest/catalog")
    assert r.status_code == 200
    b = r.json()
    assert b["post_run_path"] == "/api/backtest/run"
    assert b["doc_ref"] == "docs/GENERIC_BACKTEST_DRAFT.md"
    assert b.get("async_run_query_param") == "async"
    assert b.get("async_job_status_path_template") == "/api/backtest/jobs/{job_id}"
    assert b.get("async_job_persistence") == "memory"
    assert b.get("async_job_queue_key") is None
    assert b.get("async_job_queue_depth") is None
    assert b.get("engine_version")
    ids = {(s["strategy_id"], s["strategy_version"]) for s in b["strategies"]}
    assert ("ma_cross", "1") in ids
    assert ("ma_cross_scan", "1") in ids
    assert ("buy_hold", "1") in ids
    single = next(s for s in b["strategies"] if s["strategy_id"] == "ma_cross")
    assert single["response_shape"] == "result"
    assert single.get("archive_kind") == "ma_cross_single"
    assert isinstance(single.get("title"), str) and single["title"].strip()
    assert isinstance(single.get("description"), str) and single["description"].strip()
    assert single["get_equivalent_paths"] == ["/api/backtest/ma-cross"]
    for p in single["get_equivalent_paths"]:
        assert isinstance(p, str) and p.startswith("/")
    scan = next(s for s in b["strategies"] if s["strategy_id"] == "ma_cross_scan")
    assert scan["response_shape"] == "scan_result"
    assert scan.get("archive_kind") == "ma_cross_scan"
    assert isinstance(scan.get("title"), str) and scan["title"].strip()
    assert isinstance(scan.get("description"), str) and scan["description"].strip()
    assert scan["get_equivalent_paths"] == ["/api/backtest/ma-cross/scan"]
    for p in scan["get_equivalent_paths"]:
        assert isinstance(p, str) and p.startswith("/")
    bh = next(s for s in b["strategies"] if s["strategy_id"] == "buy_hold")
    assert bh["response_shape"] == "result"
    assert bh.get("archive_kind") == "buy_hold_single"
    assert bh["get_equivalent_paths"] == ["/api/backtest/buy-hold"]
