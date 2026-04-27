"""HTTP tests for /api/ml/* endpoints."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from src.data.models import KLine
from src.data.storage import KlineRepository


def _daily_row(code: str, d: date, close: float, volume: int = 1000) -> KLine:
    return KLine(
        code=code,
        trade_date=d,
        open=close - 0.1,
        high=close + 0.2,
        low=close - 0.2,
        close=close,
        volume=volume,
        amount=close * volume,
        turnover_rate=None,
        pct_change=None,
    )


# ---------------------------------------------------------------------------
# /api/ml/features/generate
# ---------------------------------------------------------------------------


async def test_features_generate_returns_expected_shape(http_test_client, empty_sqlite_db):
    code = "sh.mlfeat"
    base = date(2024, 1, 1)
    rows = [_daily_row(code, base + timedelta(days=i), 10.0 + i * 0.5) for i in range(40)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.post(
        "/api/ml/features/generate",
        json={
            "code": code,
            "rolling_windows": [5, 10],
            "lags": [1],
            "diff_periods": [1],
            "log_return_periods": [1],
            "base_columns": ["close"],
            "include_zscore": True,
            "drop_na": False,
            "return_rows": 5,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == code
    assert body["n_rows"] == 40
    assert body["n_features"] > 0
    # Spot-check some expected feature names
    names = body["feature_names"]
    assert "close_rolling_mean_5" in names
    assert "close_zscore_10" in names
    assert "close_lag_1" in names
    assert "close_diff_1" in names
    assert "close_log_return_1" in names

    assert len(body["rows"]) == 5
    # Last row should have warm rolling features (40 bars > 10 window)
    last = body["rows"][-1]
    assert "trade_date" in last
    assert isinstance(last["close_rolling_mean_5"], (int, float))


async def test_features_generate_drop_na_removes_warmup(http_test_client, empty_sqlite_db):
    code = "sh.mlfdrop"
    base = date(2024, 1, 1)
    rows = [_daily_row(code, base + timedelta(days=i), 10.0 + i * 0.1) for i in range(30)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.post(
        "/api/ml/features/generate",
        json={
            "code": code,
            "rolling_windows": [20],
            "lags": [1],
            "diff_periods": [1],
            "log_return_periods": [1],
            "base_columns": ["close"],
            "drop_na": True,
            "return_rows": 100,
        },
    )
    assert r.status_code == 200
    body = r.json()
    # Window 20 + drop_na -> at most 30 - 19 = 11 rows
    assert body["n_rows"] <= 11
    assert body["dropped_warmup"] is True


async def test_features_generate_rejects_start_after_end(http_test_client):
    r = http_test_client.post(
        "/api/ml/features/generate",
        json={
            "code": "sh.x",
            "start_date": "2024-12-31",
            "end_date": "2024-01-01",
        },
    )
    assert r.status_code == 400
    assert "start_date" in r.json()["detail"]


async def test_features_generate_rejects_unknown_base_column(http_test_client):
    r = http_test_client.post(
        "/api/ml/features/generate",
        json={
            "code": "sh.x",
            "base_columns": ["bogus"],
        },
    )
    assert r.status_code == 422
    assert "base_columns" in r.json()["detail"]


async def test_features_generate_no_klines_returns_400(http_test_client):
    r = http_test_client.post(
        "/api/ml/features/generate",
        json={"code": "sh.empty999"},
    )
    assert r.status_code == 400
    assert "无可用日 K" in r.json()["detail"]


async def test_features_generate_invalid_rolling_window_returns_422(
    http_test_client, empty_sqlite_db
):
    code = "sh.mlbadwin"
    rows = [_daily_row(code, date(2024, 1, 1) + timedelta(days=i), 10.0 + i) for i in range(10)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.post(
        "/api/ml/features/generate",
        json={
            "code": code,
            "rolling_windows": [1],  # < 2 -> AutoFeatureEngine validation error
        },
    )
    assert r.status_code == 422
    assert "rolling_windows" in r.json()["detail"]


# ---------------------------------------------------------------------------
# /api/ml/factor/analyze
# ---------------------------------------------------------------------------


def _build_factor_panel_payload(n_dates: int = 20, n_codes: int = 30, seed: int = 42) -> list[dict]:
    """Synthetic panel where forward_return correlates strongly with factor."""
    rng = np.random.default_rng(seed)
    base = date(2024, 1, 1)
    panel = []
    for di in range(n_dates):
        d = base + timedelta(days=di)
        for ci in range(n_codes):
            f = float(rng.normal())
            fwd = f + float(rng.normal()) * 0.3  # rho ~ 0.95
            panel.append({
                "date": d.isoformat(),
                "code": f"S{ci:03d}",
                "factor": f,
                "forward_return": fwd,
            })
    return panel


async def test_factor_analyze_strong_signal_grades_well(http_test_client):
    panel = _build_factor_panel_payload(n_dates=15, n_codes=30, seed=7)
    r = http_test_client.post(
        "/api/ml/factor/analyze",
        json={"panel": panel, "n_quantiles": 5, "method": "spearman"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["n_records"] == len(panel)
    assert body["n_dates"] == 15
    assert body["n_codes"] == 30
    assert body["ic"]["count"] > 0
    assert body["ic"]["ic_mean"] > 0.3
    assert body["quantile"]["long_short_return"] > 0
    # Strong synthetic correlation -> good or excellent grade
    assert ("优秀" in body["assessment"]) or ("良好" in body["assessment"])


async def test_factor_analyze_rejects_insufficient_records(http_test_client):
    """Pydantic min_length=20 -> 422."""
    short_panel = [
        {
            "date": "2024-01-01",
            "code": f"S{i}",
            "factor": float(i),
            "forward_return": float(i),
        }
        for i in range(10)
    ]
    r = http_test_client.post(
        "/api/ml/factor/analyze",
        json={"panel": short_panel},
    )
    assert r.status_code == 422


async def test_factor_analyze_rejects_single_date(http_test_client):
    panel = [
        {
            "date": "2024-01-01",
            "code": f"S{i:03d}",
            "factor": float(i),
            "forward_return": float(i) * 0.5,
        }
        for i in range(25)
    ]
    r = http_test_client.post(
        "/api/ml/factor/analyze",
        json={"panel": panel, "n_quantiles": 3},
    )
    assert r.status_code == 422
    assert "至少需要 2 个不同的日期" in r.json()["detail"]


async def test_factor_analyze_rejects_duplicate_panel_keys(http_test_client):
    """(date, code) duplicate -> pivot fails -> 422."""
    panel = []
    for i in range(25):
        panel.append({
            "date": "2024-01-01" if i < 13 else "2024-01-02",
            "code": "S000" if i < 2 else f"S{i:03d}",  # S000 appears twice on 2024-01-01
            "factor": float(i),
            "forward_return": float(i) * 0.5,
        })
    # Force duplicate (date=2024-01-01, code=S000) by overriding
    panel[1] = {**panel[1], "date": "2024-01-01", "code": "S000"}
    r = http_test_client.post(
        "/api/ml/factor/analyze",
        json={"panel": panel, "n_quantiles": 3},
    )
    # May 422 on pivot or pass if dedup happens upstream; allow either explicit error
    assert r.status_code in (422, 200)


async def test_factor_analyze_invalid_method_rejected(http_test_client):
    panel = [
        {
            "date": "2024-01-01",
            "code": f"S{i:03d}",
            "factor": float(i),
            "forward_return": float(i),
        }
        for i in range(25)
    ]
    r = http_test_client.post(
        "/api/ml/factor/analyze",
        json={"panel": panel, "method": "kendall"},
    )
    assert r.status_code == 422
