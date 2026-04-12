"""OpenAPI 与契约字段（含 ``archive_kind``）对齐的静态断言。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.api.main import app

project_root = Path(__file__).resolve().parent.parent
OPENAPI_DOC = project_root / "docs" / "openapi.json"


def test_backtest_catalog_live_strategy_ids_match_post_run_constants() -> None:
    """``GET /api/backtest/catalog`` 的 ``strategy_id`` 与 ``POST /run`` 支持的常量一致。"""
    from fastapi.testclient import TestClient

    from src.backtest.runner import STRATEGY_ID_MA_CROSS, STRATEGY_ID_MA_CROSS_SCAN

    with TestClient(app) as client:
        r = client.get("/api/backtest/catalog")
    assert r.status_code == 200
    strategies = r.json().get("strategies") or []
    ids = {s["strategy_id"] for s in strategies if isinstance(s, dict) and "strategy_id" in s}
    assert ids == {STRATEGY_ID_MA_CROSS, STRATEGY_ID_MA_CROSS_SCAN}


def test_backtest_catalog_live_strategy_shape_and_paths_match_kernel() -> None:
    """各 ``strategy_id`` 的 ``response_shape`` / ``get_equivalent_paths`` 与内核约定一致。"""
    from fastapi.testclient import TestClient

    from src.backtest.runner import STRATEGY_ID_MA_CROSS, STRATEGY_ID_MA_CROSS_SCAN

    want = {
        STRATEGY_ID_MA_CROSS: ("result", ["/api/backtest/ma-cross"]),
        STRATEGY_ID_MA_CROSS_SCAN: ("scan_result", ["/api/backtest/ma-cross/scan"]),
    }
    with TestClient(app) as client:
        r = client.get("/api/backtest/catalog")
    assert r.status_code == 200
    for row in r.json().get("strategies") or []:
        sid = row.get("strategy_id")
        if sid not in want:
            continue
        shape, paths = want[sid]
        assert row.get("response_shape") == shape
        assert row.get("get_equivalent_paths") == paths
        assert row.get("strategy_version") == "1"
        assert isinstance(row.get("title"), str) and row["title"].strip()
        assert isinstance(row.get("description"), str) and row["description"].strip()
        for p in row.get("get_equivalent_paths") or []:
            assert isinstance(p, str) and p.startswith("/")


def test_backtest_catalog_live_top_level_matches_contract_defaults() -> None:
    """顶层 ``engine_version`` / ``post_run_path`` / ``doc_ref`` 与内核及 Pydantic 默认值一致。"""
    from fastapi.testclient import TestClient

    from src.backtest.runner import ENGINE_VERSION

    with TestClient(app) as client:
        r = client.get("/api/backtest/catalog")
    assert r.status_code == 200
    j = r.json()
    assert j.get("engine_version") == ENGINE_VERSION
    assert j.get("post_run_path") == "/api/backtest/run"
    assert j.get("doc_ref") == "docs/GENERIC_BACKTEST_DRAFT.md"
    assert j.get("async_run_query_param") == "async"
    assert j.get("async_job_status_path_template") == "/api/backtest/jobs/{job_id}"
    assert j.get("async_job_queue_key") is None
    assert j.get("async_job_queue_depth") is None


def test_openapi_backtest_catalog_path_uses_engine_catalog_response() -> None:
    spec = app.openapi()
    ref = (
        spec["paths"]["/api/backtest/catalog"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]["$ref"]
    )
    assert ref == "#/components/schemas/BacktestEngineCatalogResponse"


def test_openapi_backtest_strategy_catalog_entry_requires_archive_kind() -> None:
    spec = app.openapi()
    entry = spec["components"]["schemas"]["BacktestStrategyCatalogEntry"]
    assert "archive_kind" in entry["required"]
    assert "archive_kind" in entry["properties"]
    assert entry["properties"]["archive_kind"]["type"] == "string"


def test_openapi_backtest_engine_catalog_strategies_items_ref() -> None:
    spec = app.openapi()
    strat = spec["components"]["schemas"]["BacktestEngineCatalogResponse"]["properties"][
        "strategies"
    ]
    assert strat["type"] == "array"
    assert strat["items"]["$ref"] == "#/components/schemas/BacktestStrategyCatalogEntry"


def test_openapi_backtest_engine_catalog_top_level_defaults() -> None:
    spec = app.openapi()
    props = spec["components"]["schemas"]["BacktestEngineCatalogResponse"]["properties"]
    assert props["post_run_path"]["default"] == "/api/backtest/run"
    assert props["doc_ref"]["default"] == "docs/GENERIC_BACKTEST_DRAFT.md"
    assert props["async_run_query_param"]["default"] == "async"
    assert props["async_job_status_path_template"]["default"] == "/api/backtest/jobs/{job_id}"
    assert props["async_job_persistence"]["default"] == "memory"
    assert props["async_job_queue_key"].get("default") is None
    assert props["async_job_queue_depth"].get("default") is None


def test_openapi_backtest_jobs_path_uses_job_status_schema() -> None:
    spec = app.openapi()
    assert "/api/backtest/jobs/{job_id}" in spec["paths"]
    ref = (
        spec["paths"]["/api/backtest/jobs/{job_id}"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]["$ref"]
    )
    assert ref == "#/components/schemas/BacktestRunJobStatusResponse"


def test_openapi_backtest_job_status_schema_requires_async_job_persistence() -> None:
    spec = app.openapi()
    js = spec["components"]["schemas"]["BacktestRunJobStatusResponse"]
    req = js.get("required") or []
    assert "async_job_persistence" in req
    assert "job_id" in req
    assert "status" in req


def test_openapi_backtest_run_post_documents_async_202() -> None:
    spec = app.openapi()
    post = spec["paths"]["/api/backtest/run"]["post"]
    assert "202" in post.get("responses", {})


def test_openapi_factors_catalog_path_uses_factor_catalog_response() -> None:
    spec = app.openapi()
    ref = (
        spec["paths"]["/api/factors/catalog"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]["$ref"]
    )
    assert ref == "#/components/schemas/FactorCatalogResponse"


def test_openapi_factor_op_catalog_entry_core_required() -> None:
    spec = app.openapi()
    entry = spec["components"]["schemas"]["FactorOpCatalogEntry"]
    for key in ("id", "window", "column", "series_keys"):
        assert key in entry["required"], f"missing required: {key}"
    assert entry["properties"]["series_keys"]["type"] == "array"


def test_openapi_factor_catalog_ops_items_ref() -> None:
    spec = app.openapi()
    ops = spec["components"]["schemas"]["FactorCatalogResponse"]["properties"]["ops"]
    assert ops["type"] == "array"
    assert ops["items"]["$ref"] == "#/components/schemas/FactorOpCatalogEntry"


def test_openapi_factor_catalog_top_level_defaults() -> None:
    spec = app.openapi()
    props = spec["components"]["schemas"]["FactorCatalogResponse"]["properties"]
    assert props["preview_path"]["default"] == "/api/factors/preview"
    assert props["doc_ref"]["default"] == "docs/FACTORS.md"


def test_openapi_trade_calendar_options_path_schema() -> None:
    spec = app.openapi()
    ref = (
        spec["paths"]["/api/data/trade-calendar/options"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]["$ref"]
    )
    assert ref == "#/components/schemas/TradeCalendarOptionsResponse"


def test_openapi_trade_calendar_status_path_schema() -> None:
    spec = app.openapi()
    ref = (
        spec["paths"]["/api/data/trade-calendar/status"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]["$ref"]
    )
    assert ref == "#/components/schemas/TradeCalendarStatus"


def test_strategies_catalog_live_entry_fields_consistent_with_contract() -> None:
    """``id`` / ``backtest_run.strategy_id``、``signal_params``、``backtest_archive_kinds``、``params_schema``。"""
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        r = client.get("/api/strategies/catalog")
    assert r.status_code == 200
    for st in r.json().get("strategies") or []:
        assert isinstance(st.get("signal_params"), dict)
        bak = st.get("backtest_archive_kinds")
        assert isinstance(bak, list) and len(bak) >= 1
        br = st.get("backtest_run") or {}
        assert isinstance(br.get("params_schema"), dict)
        assert st.get("id") == br.get("strategy_id")
        assert isinstance(st.get("title"), str) and st["title"].strip()
        assert isinstance(st.get("description"), str) and st["description"].strip()
        eid = st.get("id")
        if eid == "ma_cross":
            assert bak == ["ma_cross_single", "ma_cross_scan"]
        elif eid == "ma_cross_scan":
            assert bak == ["ma_cross_scan"]
        assert br.get("archive_kind") in bak


def test_openapi_strategies_catalog_path_has_response_schema() -> None:
    spec = app.openapi()
    ref = (
        spec["paths"]["/api/strategies/catalog"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]["$ref"]
    )
    assert ref == "#/components/schemas/StrategyCatalogResponse"
    strat = spec["components"]["schemas"]["StrategyCatalogResponse"]
    assert "strategies" in strat.get("required", [])
    props = strat.get("properties") or {}
    assert props.get("strategies", {}).get("type") == "array"


def test_factors_catalog_live_response_ops_shape() -> None:
    """与 ``scripts/verify_stack`` 中因子 catalog 形态断言一致（不依赖 DB）。"""
    from typing import get_args

    from fastapi.testclient import TestClient

    from src.api.routers.factors import OpName

    with TestClient(app) as client:
        r = client.get("/api/factors/catalog")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body.get("ops"), list) and body["ops"]
    for row in body["ops"]:
        assert all(k in row for k in ("id", "window", "column", "series_keys"))
        assert isinstance(row["series_keys"], list)
        assert isinstance(row["id"], str) and row["id"].strip()
    ids = {row["id"] for row in body["ops"]}
    assert ids == frozenset(get_args(OpName))
    assert body.get("preview_path") == "/api/factors/preview"
    assert body.get("doc_ref") == "docs/FACTORS.md"
    for row in body["ops"]:
        for k in row.get("series_keys") or []:
            assert isinstance(k, str) and k.strip()


def test_docs_openapi_json_matches_app() -> None:
    """提交 ``docs/openapi.json`` 后，与当前 ``app.openapi()`` 一致（规范化 JSON 比较）。"""
    if not OPENAPI_DOC.is_file():
        pytest.skip(f"缺少 {OPENAPI_DOC.relative_to(project_root)}，请运行: python scripts/export_openapi.py")

    disk = json.loads(OPENAPI_DOC.read_text(encoding="utf-8"))
    live = app.openapi()
    assert json.dumps(disk, sort_keys=True) == json.dumps(live, sort_keys=True), (
        "docs/openapi.json 与当前应用不一致；请执行: python scripts/export_openapi.py"
    )


def test_openapi_json_route_exists() -> None:
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        r = client.get("/openapi.json")
    assert r.status_code == 200
    body = r.json()
    assert body["openapi"].startswith("3.")


def test_export_openapi_script_dry_run_exit_0() -> None:
    r = subprocess.run(
        [sys.executable, str(project_root / "scripts" / "export_openapi.py"), "--dry-run"],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stderr + r.stdout
