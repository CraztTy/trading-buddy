"""策略目录与 POST /api/strategies/signal。"""

from __future__ import annotations

from datetime import date, timedelta

from src.data.models import KLine, StockType
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


async def test_strategies_catalog_archive_kind_matches_backtest_engine_catalog(http_test_client):
    """策略目录 backtest_run.archive_kind 与回测引擎 catalog 逐条一致（契约 #3）。"""
    sc = http_test_client.get("/api/strategies/catalog")
    bc = http_test_client.get("/api/backtest/catalog")
    assert sc.status_code == 200 and bc.status_code == 200
    sc_body = sc.json()
    bc_body = bc.json()
    by_engine: dict[str, str] = {}
    for row in bc_body.get("strategies") or []:
        sid = row.get("strategy_id")
        ak = row.get("archive_kind")
        if isinstance(sid, str) and sid.strip() and isinstance(ak, str) and ak.strip():
            by_engine[sid.strip()] = ak.strip()
    assert by_engine, "backtest catalog strategies 为空或缺 archive_kind"
    for st in sc_body.get("strategies") or []:
        br = st.get("backtest_run") or {}
        sid = br.get("strategy_id")
        ak = br.get("archive_kind")
        assert isinstance(sid, str) and sid.strip()
        assert isinstance(ak, str) and ak.strip()
        sid_n, ak_n = sid.strip(), ak.strip()
        # 允许仅有选股扫描、无回测引擎的策略（如 limit_up_pullback）不在 backtest catalog 中
        if sid_n not in by_engine:
            continue
        assert (
            by_engine[sid_n] == ak_n
        ), f"archive_kind 不一致 strategy_id={sid_n!r} strategies={ak_n!r} backtest_engine={by_engine[sid_n]!r}"
    engine_ids = frozenset(by_engine)
    catalog_ids_with_engine = frozenset(
        (s.get("backtest_run") or {}).get("strategy_id", "").strip()
        for s in sc_body.get("strategies") or []
        if isinstance((s.get("backtest_run") or {}).get("strategy_id"), str)
        and (s.get("backtest_archive_kinds") or [])  # 仅要求有 backtest_archive_kinds 的须对齐
    )
    assert engine_ids == catalog_ids_with_engine, (
        f"回测 engine 与策略 catalog 的 strategy_id 集合须一致 "
        f"engine={sorted(engine_ids)!r} strategies={sorted(catalog_ids_with_engine)!r}"
    )


async def test_strategies_catalog_lists_ma_cross(http_test_client):
    r = http_test_client.get("/api/strategies/catalog")
    assert r.status_code == 200
    data = r.json()
    assert "strategies" in data
    ids = [s["id"] for s in data["strategies"]]
    assert "ma_cross" in ids
    assert "ma_cross_scan" in ids
    assert "buy_hold" in ids
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

    bh = next(s for s in data["strategies"] if s["id"] == "buy_hold")
    assert bh.get("backtest_archive_kinds") == ["buy_hold_single"]
    br_bh = bh.get("backtest_run") or {}
    assert br_bh.get("strategy_id") == "buy_hold"
    assert br_bh.get("archive_kind") == "buy_hold_single"
    ps_bh = br_bh.get("params_schema") or {}
    assert "code" in (ps_bh.get("required") or [])


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


async def test_strategies_catalog_lists_limit_up_pullback(http_test_client):
    r = http_test_client.get("/api/strategies/catalog")
    assert r.status_code == 200
    data = r.json()
    ids = [s["id"] for s in data["strategies"]]
    assert "limit_up_pullback" in ids
    assert "limit_up_pullback_scan" in ids
    lu = next(s for s in data["strategies"] if s["id"] == "limit_up_pullback")
    assert lu.get("backtest_archive_kinds") == ["limit_up_pullback_single"]
    assert lu.get("strategy_contract_version") == "1"
    br = lu.get("backtest_run") or {}
    assert br.get("strategy_id") == "limit_up_pullback"
    assert br.get("archive_kind") == "limit_up_pullback_single"
    lu_scan = next(s for s in data["strategies"] if s["id"] == "limit_up_pullback_scan")
    assert lu_scan.get("backtest_archive_kinds") == ["limit_up_pullback_scan"]
    br_scan = lu_scan.get("backtest_run") or {}
    assert br_scan.get("strategy_id") == "limit_up_pullback_scan"
    assert br_scan.get("archive_kind") == "limit_up_pullback_scan"


async def test_strategies_limit_up_pullback_scan_basic(http_test_client, empty_sqlite_db):
    from src.data.storage import StockRepository
    from src.data.models import StockInfo, Market

    code = "sh.lu1"
    base = date(2025, 9, 1)
    rows = [_bar(code, base + timedelta(days=i), 10.0 + (i % 3) * 0.1) for i in range(120)]
    # 制造一个涨停日（倒数第8天）
    lu_idx = len(rows) - 8
    rows[lu_idx].pre_close = 10.0
    rows[lu_idx].open = 10.0
    rows[lu_idx].close = 11.0
    rows[lu_idx].high = 11.1
    rows[lu_idx].low = 9.9
    rows[lu_idx].volume = 2000
    rows[lu_idx - 1].volume = 1000
    # 把涨停后调整到激进买点 11.0±2% 范围内（10.8 以上）
    for offset in range(1, 8):
        rows[lu_idx + offset].close = 10.8 + offset * 0.01
        rows[lu_idx + offset].open = rows[lu_idx + offset].close - 0.01
        rows[lu_idx + offset].high = rows[lu_idx + offset].close + 0.03
        rows[lu_idx + offset].low = rows[lu_idx + offset].close - 0.03
        rows[lu_idx + offset].volume = 800

    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)
        await StockRepository(session).bulk_upsert([
            StockInfo(
                code=code,
                name="涨停测试",
                market=Market.SH,
                stock_type=StockType.COMMON,  # type: ignore[arg-type]
                market_cap=100_000_000_000,
                is_trading=True,
            )
        ])

    as_of = rows[-1].trade_date.isoformat()
    r = http_test_client.post(
        "/api/strategies/limit-up-pullback/scan",
        json={
            "codes": code,
            "as_of_date": as_of,
            "buy_point_types": ["aggressive"],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["as_of_date"] == as_of
    assert body["total_scanned"] == 1
    assert isinstance(body["matches"], list)


async def test_strategies_limit_up_pullback_scan_422_on_bad_lookback(http_test_client):
    r = http_test_client.post(
        "/api/strategies/limit-up-pullback/scan",
        json={
            "codes": "sh.x",
            "limit_up_lookback_min": 15,
            "limit_up_lookback_max": 5,
        },
    )
    assert r.status_code == 422


async def test_strategies_limit_up_pullback_scan_400_on_empty_codes(http_test_client):
    r = http_test_client.post(
        "/api/strategies/limit-up-pullback/scan",
        json={"codes": "   "},
    )
    assert r.status_code == 400
    assert "为空" in r.json().get("detail", "")
