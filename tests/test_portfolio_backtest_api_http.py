"""Portfolio backtest HTTP integration tests."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.data.models import KLine
from src.data.storage import KlineRepository

pytestmark = pytest.mark.asyncio


def _bar(code: str, d: date, close: float, adjust_flag: str = "3") -> KLine:
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
        adjust_flag=adjust_flag,
    )


async def _seed_two_codes(
    empty_sqlite_db,
    code_a: str = "sh.pt1",
    code_b: str = "sh.pt2",
    n_bars: int = 80,
) -> tuple[str, str]:
    """Insert K-lines for two portfolio test codes."""
    base = date(2025, 5, 1)
    rows: list[KLine] = []
    for i in range(n_bars):
        d = base + timedelta(days=i)
        rows.append(_bar(code_a, d, 100.0 + i * 0.3))
        rows.append(_bar(code_b, d, 50.0 + i * 0.15))
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)
    return code_a, code_b


async def _seed_codes(
    empty_sqlite_db,
    codes: list[str],
    n_bars: int = 80,
) -> list[str]:
    """Insert K-lines for multiple portfolio test codes."""
    base = date(2025, 5, 1)
    rows: list[KLine] = []
    prices = [100.0, 50.0, 30.0, 80.0, 20.0, 60.0, 40.0, 70.0]
    for i in range(n_bars):
        d = base + timedelta(days=i)
        for idx, code in enumerate(codes):
            price = prices[idx % len(prices)] + i * 0.1
            rows.append(_bar(code, d, price))
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)
    return codes


async def test_portfolio_equal_weight_backtest_success(http_test_client, empty_sqlite_db):
    """组合回测等权：4 只标的（等权各 25% 不触发风控），月频再平衡，返回 200 和正确字段。"""
    client = http_test_client
    codes = await _seed_codes(empty_sqlite_db, ["sh.pt1", "sh.pt2", "sh.pt3", "sh.pt4"])
    payload = {
        "strategy_id": "portfolio_equal_weight",
        "strategy_version": "1",
        "params": {
            "codes": ",".join(codes),
            "limit": 100,
            "strategy_for_signal": "ma_cross",
            "weights_scheme": "equal",
            "rebalance_freq": "monthly",
            "fast": 5,
            "slow": 20,
            "max_codes": 25,
        }
    }
    r = client.post("/api/backtest/run", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["strategy_id"] == "portfolio_equal_weight"
    assert data["result"] is not None
    result = data["result"]
    assert "equity_curve" in result
    assert "total_return_pct" in result
    assert "sharpe_ratio" in result
    assert "max_drawdown_pct" in result
    assert data["assumptions"]
    assert "组合" in " ".join(data["assumptions"])


async def test_portfolio_value_weight_backtest_success(http_test_client, empty_sqlite_db):
    """组合回测市值加权：4 只标的，返回 200。"""
    client = http_test_client
    codes = await _seed_codes(empty_sqlite_db, ["sh.pt1", "sh.pt2", "sh.pt3", "sh.pt4"])
    payload = {
        "strategy_id": "portfolio_value_weight",
        "strategy_version": "1",
        "params": {
            "codes": ",".join(codes),
            "limit": 100,
            "weights_scheme": "value",
            "rebalance_freq": "weekly",
        }
    }
    r = client.post("/api/backtest/run", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["result"] is not None


async def test_portfolio_backtest_invalid_single_code(http_test_client, empty_sqlite_db):
    """组合回测只有 1 只标的应返回 400。"""
    client = http_test_client
    code_a = "sh.pt1"
    base = date(2025, 5, 1)
    rows = [_bar(code_a, base + timedelta(days=i), 100.0 + i * 0.3) for i in range(80)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    payload = {
        "strategy_id": "portfolio_equal_weight",
        "strategy_version": "1",
        "params": {
            "codes": code_a,
            "limit": 100,
        }
    }
    r = client.post("/api/backtest/run", json=payload)
    assert r.status_code == 400


async def test_portfolio_backtest_async_job(http_test_client, empty_sqlite_db):
    """组合回测异步模式：202 + job_id。"""
    client = http_test_client
    code_a, code_b = await _seed_two_codes(empty_sqlite_db)
    payload = {
        "strategy_id": "portfolio_equal_weight",
        "strategy_version": "1",
        "params": {
            "codes": f"{code_a},{code_b}",
            "limit": 100,
        }
    }
    r = client.post("/api/backtest/run?async=1", json=payload)
    assert r.status_code == 202
    data = r.json()
    assert "job_id" in data
    assert "status_path" in data


async def test_portfolio_backtest_buy_hold_signal(http_test_client, empty_sqlite_db):
    """组合回测使用 buy_hold 信号策略。"""
    client = http_test_client
    codes = await _seed_codes(empty_sqlite_db, ["sh.pt1", "sh.pt2", "sh.pt3", "sh.pt4"])
    payload = {
        "strategy_id": "portfolio_equal_weight",
        "strategy_version": "1",
        "params": {
            "codes": ",".join(codes),
            "limit": 100,
            "strategy_for_signal": "buy_hold",
        }
    }
    r = client.post("/api/backtest/run", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["result"] is not None
    assert "组合" in " ".join(data["assumptions"])


async def test_portfolio_backtest_invalid_weights_scheme(http_test_client, empty_sqlite_db):
    """组合回测非法 weights_scheme 返回 422。"""
    client = http_test_client
    code_a, code_b = await _seed_two_codes(empty_sqlite_db)
    payload = {
        "strategy_id": "portfolio_equal_weight",
        "strategy_version": "1",
        "params": {
            "codes": f"{code_a},{code_b}",
            "weights_scheme": "invalid",
        }
    }
    r = client.post("/api/backtest/run", json=payload)
    assert r.status_code == 422


async def test_portfolio_backtest_risk_rejected(http_test_client, empty_sqlite_db):
    """组合回测触发风控拦截（单票仓位超限）。

    默认风控引擎的单票仓位上限为 30%。等权组合中每只股票权重为 1/N，
    当 N >= 4 时权重 <= 25%，不会触发拦截。此测试验证：
    - 正常组合（2 只标的，等权 50%）会触发风控拦截
    - 返回 400 并包含风控相关提示
    """
    client = http_test_client
    code_a, code_b = await _seed_two_codes(empty_sqlite_db)
    payload = {
        "strategy_id": "portfolio_equal_weight",
        "strategy_version": "1",
        "params": {
            "codes": f"{code_a},{code_b}",
            "limit": 100,
            "weights_scheme": "equal",
        }
    }
    r = client.post("/api/backtest/run", json=payload)
    # 2 只标的等权 = 各 50%，超过默认 30% 单票上限，应被风控拦截
    assert r.status_code == 400
    detail = r.json().get("detail", "")
    assert "风控" in detail or "拦截" in detail


async def test_portfolio_backtest_catalog_includes_portfolio_strategies(http_test_client):
    """GET /api/backtest/catalog 包含 portfolio 策略条目。"""
    r = http_test_client.get("/api/backtest/catalog")
    assert r.status_code == 200
    data = r.json()
    ids = {s["strategy_id"] for s in data["strategies"]}
    assert "portfolio_equal_weight" in ids
    assert "portfolio_value_weight" in ids

    eq = next(s for s in data["strategies"] if s["strategy_id"] == "portfolio_equal_weight")
    assert eq["archive_kind"] == "portfolio_equal_weight"
    assert eq["response_shape"] == "result"

    vw = next(s for s in data["strategies"] if s["strategy_id"] == "portfolio_value_weight")
    assert vw["archive_kind"] == "portfolio_value_weight"
    assert vw["response_shape"] == "result"


async def test_portfolio_backtest_with_benchmark(http_test_client, empty_sqlite_db):
    """组合回测带基准代码。"""
    client = http_test_client
    codes = await _seed_codes(empty_sqlite_db, ["sh.pt1", "sh.pt2", "sh.pt3", "sh.pt4"], n_bars=80)
    bench = "sh.bench_pt"
    base = date(2025, 5, 1)
    bench_rows = [_bar(bench, base + timedelta(days=i), 3000.0 + i * 0.1) for i in range(80)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(bench_rows)

    payload = {
        "strategy_id": "portfolio_equal_weight",
        "strategy_version": "1",
        "params": {
            "codes": ",".join(codes),
            "limit": 100,
            "benchmark_code": bench,
            "strategy_for_signal": "buy_hold",
        }
    }
    r = client.post("/api/backtest/run", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["result"] is not None


async def test_portfolio_backtest_empty_codes_400(http_test_client):
    """组合回测空 codes 返回 400。"""
    client = http_test_client
    payload = {
        "strategy_id": "portfolio_equal_weight",
        "strategy_version": "1",
        "params": {
            "codes": ",",
            "limit": 100,
        }
    }
    r = client.post("/api/backtest/run", json=payload)
    assert r.status_code == 400


async def test_portfolio_backtest_fast_ge_slow_400(http_test_client, empty_sqlite_db):
    """组合回测 fast >= slow 返回 400。"""
    client = http_test_client
    code_a, code_b = await _seed_two_codes(empty_sqlite_db)
    payload = {
        "strategy_id": "portfolio_equal_weight",
        "strategy_version": "1",
        "params": {
            "codes": f"{code_a},{code_b}",
            "limit": 100,
            "fast": 20,
            "slow": 10,
        }
    }
    r = client.post("/api/backtest/run", json=payload)
    assert r.status_code == 400


async def test_portfolio_value_weight_matches_catalog(http_test_client, empty_sqlite_db):
    """portfolio_value_weight 策略通过 catalog 验证并执行成功。"""
    client = http_test_client
    codes = await _seed_codes(empty_sqlite_db, ["sh.pt1", "sh.pt2", "sh.pt3", "sh.pt4"])
    payload = {
        "strategy_id": "portfolio_value_weight",
        "strategy_version": "1",
        "params": {
            "codes": ",".join(codes),
            "limit": 100,
            "weights_scheme": "value",
            "rebalance_freq": "monthly",
        }
    }
    r = client.post("/api/backtest/run", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["strategy_id"] == "portfolio_value_weight"
    assert data["result"] is not None
    result = data["result"]
    assert "equity_curve" in result
    assert "total_return_pct" in result
    assert "sharpe_ratio" in result
    assert "max_drawdown_pct" in result


async def test_portfolio_backtest_commission_slippage_sum_over_limit_400(http_test_client):
    """组合回测 commission + slippage > 0.08 返回 400。"""
    client = http_test_client
    payload = {
        "strategy_id": "portfolio_equal_weight",
        "strategy_version": "1",
        "params": {
            "codes": "sh.a,sh.b",
            "commission_rate": 0.05,
            "slippage_rate": 0.04,
        }
    }
    r = client.post("/api/backtest/run", json=payload)
    assert r.status_code == 422
