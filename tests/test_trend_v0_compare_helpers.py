"""进程内无 DB：校验 ``scripts/trend_v0_backtest_compare.py`` 的请求体与指纹辅助函数。"""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_compare_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "trend_v0_backtest_compare.py"
    spec = importlib.util.spec_from_file_location("_trend_v0_compare_helpers", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_buy_hold_body_has_no_fast_slow():
    mod = _load_compare_module()
    b = mod._buy_hold_body(
        "sh.600519",
        commission_rate=0.00015,
        slippage_rate=0.00005,
        limit=120,
    )
    assert b["strategy_id"] == "buy_hold"
    assert b["strategy_version"] == "1"
    p = b["params"]
    assert p["code"] == "sh.600519"
    assert p["limit"] == 120
    assert "fast" not in p and "slow" not in p


def test_buy_hold_body_optional_dates():
    mod = _load_compare_module()
    b = mod._buy_hold_body(
        "sz.000001",
        commission_rate=0.0,
        slippage_rate=0.0,
        limit=500,
        start_date="2023-01-01",
        end_date="2024-01-01",
    )
    assert b["params"]["start_date"] == "2023-01-01"
    assert b["params"]["end_date"] == "2024-01-01"


def test_fingerprint_single_rounds_metrics():
    mod = _load_compare_module()
    data = {
        "engine_version": "0.1",
        "result": {
            "code": "sh.600519",
            "bars_used": 58,
            "total_return_pct": 2.87551234,
            "max_drawdown_pct": -10.4823,
            "sharpe_ratio": 0.583612,
            "signal_changes": 0,
        },
    }
    fp = mod._fingerprint_single(data)
    assert fp[0] == "0.1"
    assert fp[1] == "sh.600519"
    assert fp[2] == 58
    assert fp[3] == 2.875512
    assert fp[4] == -10.4823
    assert fp[5] == 0.583612
    assert fp[6] == 0


def test_httpx_api_bridge_joins_base_and_path():
    mod = _load_compare_module()
    recorded: list[tuple[str, dict[str, int]]] = []

    class _FakeClient:
        def post(self, url: str, json: dict[str, int] | None = None, timeout: float = 0) -> object:
            recorded.append((url, json or {}))
            return object()

    fake = _FakeClient()
    bridge = mod._HttpxApiBridge(fake, "http://127.0.0.1:8000")
    bridge.post("/api/backtest/run", json={"x": 1}, timeout=30.0)
    assert recorded[0][0] == "http://127.0.0.1:8000/api/backtest/run"
    assert recorded[0][1] == {"x": 1}


def test_fingerprint_scan_sorts_codes():
    mod = _load_compare_module()
    data = {
        "engine_version": "0.1",
        "scan_result": {
            "sort_by": "total_return",
            "items": [
                {"code": "sz.000001", "total_return_pct": 1.0, "error": None},
                {"code": "sh.600519", "total_return_pct": 2.5, "error": None},
            ],
        },
    }
    fp = mod._fingerprint_scan(data)
    assert fp[0] == "0.1"
    assert fp[1] == "total_return"
    rows = fp[2]
    assert rows[0][0] == "sh.600519"
    assert rows[1][0] == "sz.000001"
