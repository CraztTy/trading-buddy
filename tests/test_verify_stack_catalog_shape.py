"""``scripts/verify_stack`` 内 catalog 形态校验函数的单元覆盖（无 DB）。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.backtest.runner import ENGINE_VERSION

project_root = Path(__file__).resolve().parent.parent

_BT_CATALOG_ASYNC_DEFAULTS = {
    "async_run_query_param": "async",
    "async_job_status_path_template": "/api/backtest/jobs/{job_id}",
    "async_job_persistence": "memory",
    "async_job_queue_key": None,
    "async_job_queue_depth": None,
}


def _bt_catalog_row(
    strategy_id: str,
    archive_kind: str,
    *,
    response_shape: str = "result",
    paths: list[str] | None = None,
) -> dict:
    if paths is None:
        if strategy_id == "ma_cross":
            paths = ["/api/backtest/ma-cross"]
        elif strategy_id == "ma_cross_scan":
            paths = ["/api/backtest/ma-cross/scan"]
        elif strategy_id == "buy_hold":
            paths = ["/api/backtest/buy-hold"]
        else:
            paths = ["/api/backtest/ma-cross"]
    return {
        "strategy_id": strategy_id,
        "strategy_version": "1",
        "title": "t",
        "description": "d",
        "response_shape": response_shape,
        "archive_kind": archive_kind,
        "get_equivalent_paths": paths,
    }


def _bt_catalog_body(*rows: dict) -> dict:
    rows_list = list(rows)
    _defaults = {
        "buy_hold": ("buy_hold_single", "result", ["/api/backtest/buy-hold"]),
        "limit_up_pullback": ("limit_up_pullback_single", "result", ["/api/backtest/limit-up-pullback"]),
        "limit_up_pullback_scan": ("limit_up_pullback_scan", "scan_result", ["/api/backtest/limit-up-pullback/scan"]),
    }
    for sid, (ak, shape, paths) in _defaults.items():
        if not any(isinstance(r, dict) and r.get("strategy_id") == sid for r in rows_list):
            rows_list.append(
                _bt_catalog_row(sid, ak, response_shape=shape, paths=paths)
            )
    return {
        "engine_version": ENGINE_VERSION,
        "post_run_path": "/api/backtest/run",
        "doc_ref": "docs/GENERIC_BACKTEST_DRAFT.md",
        **_BT_CATALOG_ASYNC_DEFAULTS,
        "strategies": rows_list,
    }


@pytest.fixture(scope="module")
def verify_stack_mod():
    spec = importlib.util.spec_from_file_location(
        "verify_stack_mod",
        project_root / "scripts" / "verify_stack.py",
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_factors_catalog_shape_errors_bad_window_policy(verify_stack_mod) -> None:
    err = verify_stack_mod._factors_catalog_shape_errors(
        {
            "ops": [
                {
                    "id": "ema",
                    "window": "sometimes",
                    "column": "ohlcv",
                    "series_keys": ["value"],
                }
            ]
        }
    )
    assert err and "window" in err


def test_factors_catalog_shape_errors_bad_column_policy(verify_stack_mod) -> None:
    err = verify_stack_mod._factors_catalog_shape_errors(
        {
            "ops": [
                {
                    "id": "ema",
                    "window": "required",
                    "column": "close_only",
                    "series_keys": ["value"],
                }
            ]
        }
    )
    assert err and "column" in err


def test_strategies_catalog_shape_errors_archive_kind_not_in_kinds(verify_stack_mod) -> None:
    body = {
        "strategies": [
            {
                "id": "ma_cross",
                "title": "MA 交叉",
                "description": "单标的与扫描",
                "strategy_contract_version": "1",
                "signal_params": {"type": "object"},
                "backtest_archive_kinds": ["ma_cross_single", "ma_cross_scan"],
                "backtest_run": {
                    "strategy_id": "ma_cross",
                    "strategy_version": "1",
                    "archive_kind": "bogus_kind",
                    "params_schema": {"type": "object"},
                },
            },
            {
                "id": "ma_cross_scan",
                "title": "MA 扫描",
                "description": "仅扫描",
                "strategy_contract_version": "1",
                "signal_params": {"type": "object"},
                "backtest_archive_kinds": ["ma_cross_scan"],
                "backtest_run": {
                    "strategy_id": "ma_cross_scan",
                    "strategy_version": "1",
                    "archive_kind": "ma_cross_scan",
                    "params_schema": {"type": "object"},
                },
            },
        ]
    }
    err = verify_stack_mod._strategies_catalog_shape_errors(body)
    assert err and "不在 backtest_archive_kinds" in err


def test_factors_catalog_shape_errors_empty_ops(verify_stack_mod) -> None:
    err = verify_stack_mod._factors_catalog_shape_errors({"ops": []})
    assert err and "为空" in err


def test_factors_catalog_shape_errors_missing_series_keys(verify_stack_mod) -> None:
    err = verify_stack_mod._factors_catalog_shape_errors(
        {"ops": [{"id": "x", "window": "required", "column": "ohlcv"}]}
    )
    assert err and "series_keys" in err


def test_strategies_catalog_shape_errors_missing_ma_cross_scan(verify_stack_mod) -> None:
    body = {
        "strategies": [
            {
                "id": "ma_cross",
                "title": "MA 交叉",
                "description": "单标的",
                "strategy_contract_version": "1",
                "signal_params": {"type": "object"},
                "backtest_archive_kinds": ["ma_cross_single", "ma_cross_scan"],
                "backtest_run": {
                    "strategy_id": "ma_cross",
                    "strategy_version": "1",
                    "archive_kind": "ma_cross_single",
                    "params_schema": {"type": "object"},
                },
            }
        ]
    }
    err = verify_stack_mod._strategies_catalog_shape_errors(body)
    assert err and "ma_cross_scan" in err


def test_strategies_catalog_shape_errors_id_mismatch_backtest_run(verify_stack_mod) -> None:
    body = {
        "strategies": [
            {
                "id": "ma_cross",
                "title": "MA 交叉",
                "description": "单标的",
                "strategy_contract_version": "1",
                "signal_params": {"type": "object"},
                "backtest_archive_kinds": ["ma_cross_single", "ma_cross_scan"],
                "backtest_run": {
                    "strategy_id": "ma_cross_scan",
                    "strategy_version": "1",
                    "archive_kind": "ma_cross_single",
                    "params_schema": {"type": "object"},
                },
            },
            {
                "id": "ma_cross_scan",
                "title": "MA 扫描",
                "description": "扫描",
                "strategy_contract_version": "1",
                "signal_params": {"type": "object"},
                "backtest_archive_kinds": ["ma_cross_scan"],
                "backtest_run": {
                    "strategy_id": "ma_cross_scan",
                    "strategy_version": "1",
                    "archive_kind": "ma_cross_scan",
                    "params_schema": {"type": "object"},
                },
            },
        ]
    }
    err = verify_stack_mod._strategies_catalog_shape_errors(body)
    assert err and "不一致" in err


def test_strategies_catalog_shape_errors_wrong_backtest_archive_kinds(verify_stack_mod) -> None:
    body = {
        "strategies": [
            {
                "id": "ma_cross",
                "title": "MA 交叉",
                "description": "单标的",
                "strategy_contract_version": "1",
                "signal_params": {"type": "object"},
                "backtest_archive_kinds": ["ma_cross_scan"],
                "backtest_run": {
                    "strategy_id": "ma_cross",
                    "strategy_version": "1",
                    "archive_kind": "ma_cross_single",
                    "params_schema": {"type": "object"},
                },
            },
            {
                "id": "ma_cross_scan",
                "title": "MA 扫描",
                "description": "扫描",
                "strategy_contract_version": "1",
                "signal_params": {"type": "object"},
                "backtest_archive_kinds": ["ma_cross_scan"],
                "backtest_run": {
                    "strategy_id": "ma_cross_scan",
                    "strategy_version": "1",
                    "archive_kind": "ma_cross_scan",
                    "params_schema": {"type": "object"},
                },
            },
        ]
    }
    err = verify_stack_mod._strategies_catalog_shape_errors(body)
    assert err and "backtest_archive_kinds" in err


def test_strategies_catalog_shape_errors_missing_backtest_run(verify_stack_mod) -> None:
    err = verify_stack_mod._strategies_catalog_shape_errors(
        {
            "strategies": [
                {
                    "id": "ma_cross",
                    "title": "t1",
                    "description": "d1",
                    "strategy_contract_version": "1",
                },
                {
                    "id": "ma_cross_scan",
                    "title": "t2",
                    "description": "d2",
                    "strategy_contract_version": "1",
                },
            ]
        }
    )
    assert err and "backtest_run" in err


def test_factors_catalog_op_ids_match_opname_errors_extra(verify_stack_mod) -> None:
    body = {
        "ops": [
            {"id": "rolling_mean", "window": "required", "column": "ohlcv", "series_keys": ["value"]},
            {"id": "bogus_op", "window": "required", "column": "ohlcv", "series_keys": ["value"]},
        ]
    }
    err = verify_stack_mod._factors_catalog_op_ids_match_opname(body)
    assert err and ("extra" in err or "bogus" in err)


def test_factors_catalog_op_ids_match_opname_errors_missing_members(verify_stack_mod) -> None:
    body = {
        "ops": [
            {"id": "ema", "window": "required", "column": "ohlcv", "series_keys": ["value"]},
        ]
    }
    err = verify_stack_mod._factors_catalog_op_ids_match_opname(body)
    assert err and "missing=" in err


def test_factors_catalog_op_ids_match_opname_root_not_object(verify_stack_mod) -> None:
    err = verify_stack_mod._factors_catalog_op_ids_match_opname(None)
    assert err and "OpName" in err and "不是 JSON 对象" in err


def test_factors_catalog_op_ids_match_opname_ops_not_list(verify_stack_mod) -> None:
    err = verify_stack_mod._factors_catalog_op_ids_match_opname({"ops": {}})
    assert err and "ops 非列表" in err


def test_factors_catalog_op_ids_match_opname_op_row_not_object(verify_stack_mod) -> None:
    err = verify_stack_mod._factors_catalog_op_ids_match_opname({"ops": ["not-a-dict"]})
    assert err and "OpName" in err and "不是对象" in err


def test_factors_catalog_live_passes_opname_helper(verify_stack_mod) -> None:
    with TestClient(app) as client:
        body = client.get("/api/factors/catalog").json()
    assert verify_stack_mod._factors_catalog_op_ids_match_opname(body) is None


def test_factors_catalog_top_level_errors_doc_ref(verify_stack_mod) -> None:
    err = verify_stack_mod._factors_catalog_top_level_errors(
        {"preview_path": "/api/factors/preview", "doc_ref": "wrong.md", "ops": []}
    )
    assert err and "doc_ref" in err


def test_factors_catalog_top_level_errors_bad_preview_path(verify_stack_mod) -> None:
    err = verify_stack_mod._factors_catalog_top_level_errors(
        {"preview_path": "/wrong/preview", "doc_ref": "docs/FACTORS.md", "ops": []}
    )
    assert err and "preview_path" in err


def test_factors_catalog_live_top_level_passes_helper(verify_stack_mod) -> None:
    with TestClient(app) as client:
        body = client.get("/api/factors/catalog").json()
    assert verify_stack_mod._factors_catalog_top_level_errors(body) is None


def test_strategies_catalog_shape_errors_wrong_contract_version(verify_stack_mod) -> None:
    with TestClient(app) as client:
        body = client.get("/api/strategies/catalog").json()
    body["strategies"][0]["strategy_contract_version"] = "2"
    err = verify_stack_mod._strategies_catalog_shape_errors(body)
    assert err and "strategy_contract_version" in err


def test_strategies_catalog_shape_errors_wrong_backtest_run_version(verify_stack_mod) -> None:
    with TestClient(app) as client:
        body = client.get("/api/strategies/catalog").json()
    body["strategies"][0]["backtest_run"]["strategy_version"] = "9"
    err = verify_stack_mod._strategies_catalog_shape_errors(body)
    assert err and "backtest_run.strategy_version" in err


def test_strategies_catalog_live_passes_shape_helper(verify_stack_mod) -> None:
    """运行时 GET 与 ``verify_stack`` 形态断言一致（不依赖 DB）。"""
    with TestClient(app) as client:
        body = client.get("/api/strategies/catalog").json()
    assert verify_stack_mod._strategies_catalog_shape_errors(body) is None


def test_backtest_catalog_archive_errors_extra_strategy_id(verify_stack_mod) -> None:
    body = _bt_catalog_body(
        _bt_catalog_row("ma_cross", "ma_cross_single", response_shape="result"),
        _bt_catalog_row("ma_cross_scan", "ma_cross_scan", response_shape="scan_result"),
        _bt_catalog_row("not_registered", "ma_cross_single", response_shape="result", paths=[]),
    )
    err = verify_stack_mod._backtest_catalog_archive_kind_errors(body)
    assert err and "strategy_id 集合" in err


def test_backtest_catalog_live_passes_contract_helper(verify_stack_mod) -> None:
    with TestClient(app) as client:
        body = client.get("/api/backtest/catalog").json()
    assert verify_stack_mod._backtest_catalog_archive_kind_errors(body) is None


def test_backtest_catalog_archive_errors_bad_kind(verify_stack_mod) -> None:
    body = _bt_catalog_body(
        _bt_catalog_row("ma_cross", "wrong", response_shape="result"),
        _bt_catalog_row("ma_cross_scan", "ma_cross_scan", response_shape="scan_result"),
    )
    err = verify_stack_mod._backtest_catalog_archive_kind_errors(body)
    assert err and "ma_cross_single" in err


def test_backtest_catalog_archive_errors_engine_version_mismatch(verify_stack_mod) -> None:
    body = {
        "engine_version": "not-a-real-engine",
        "post_run_path": "/api/backtest/run",
        "doc_ref": "docs/GENERIC_BACKTEST_DRAFT.md",
        **_BT_CATALOG_ASYNC_DEFAULTS,
        "strategies": [
            _bt_catalog_row("ma_cross", "ma_cross_single", response_shape="result"),
            _bt_catalog_row("ma_cross_scan", "ma_cross_scan", response_shape="scan_result"),
            _bt_catalog_row("buy_hold", "buy_hold_single", response_shape="result"),
        ],
    }
    err = verify_stack_mod._backtest_catalog_archive_kind_errors(body)
    assert err and "engine_version" in err


def test_backtest_catalog_archive_errors_response_shape_mismatch(verify_stack_mod) -> None:
    body = _bt_catalog_body(
        _bt_catalog_row("ma_cross", "ma_cross_single", response_shape="scan_result"),
        _bt_catalog_row("ma_cross_scan", "ma_cross_scan", response_shape="scan_result"),
    )
    err = verify_stack_mod._backtest_catalog_archive_kind_errors(body)
    assert err and "response_shape" in err


def test_backtest_catalog_archive_errors_get_equivalent_paths_mismatch(verify_stack_mod) -> None:
    body = _bt_catalog_body(
        _bt_catalog_row(
            "ma_cross",
            "ma_cross_single",
            response_shape="result",
            paths=["/api/wrong"],
        ),
        _bt_catalog_row("ma_cross_scan", "ma_cross_scan", response_shape="scan_result"),
    )
    err = verify_stack_mod._backtest_catalog_archive_kind_errors(body)
    assert err and "get_equivalent_paths" in err


def test_backtest_catalog_archive_errors_path_not_slash_prefix(verify_stack_mod) -> None:
    body = _bt_catalog_body(
        _bt_catalog_row(
            "ma_cross",
            "ma_cross_single",
            response_shape="result",
            paths=["api/backtest/ma-cross"],
        ),
        _bt_catalog_row("ma_cross_scan", "ma_cross_scan", response_shape="scan_result"),
    )
    err = verify_stack_mod._backtest_catalog_archive_kind_errors(body)
    assert err and "get_equivalent_paths" in err


def test_backtest_catalog_archive_errors_equivalent_path_whitespace_only(verify_stack_mod) -> None:
    body = _bt_catalog_body(
        _bt_catalog_row(
            "ma_cross",
            "ma_cross_single",
            response_shape="result",
            paths=["   "],
        ),
        _bt_catalog_row("ma_cross_scan", "ma_cross_scan", response_shape="scan_result"),
    )
    err = verify_stack_mod._backtest_catalog_archive_kind_errors(body)
    assert err and "get_equivalent_paths" in err


def test_backtest_catalog_archive_errors_strategy_version_not_1(verify_stack_mod) -> None:
    row = _bt_catalog_row("ma_cross", "ma_cross_single", response_shape="result")
    row["strategy_version"] = "2"
    body = _bt_catalog_body(
        row,
        _bt_catalog_row("ma_cross_scan", "ma_cross_scan", response_shape="scan_result"),
    )
    err = verify_stack_mod._backtest_catalog_archive_kind_errors(body)
    assert err and "strategy_version" in err


def test_backtest_catalog_archive_errors_post_run_path_mismatch(verify_stack_mod) -> None:
    body = {
        "engine_version": ENGINE_VERSION,
        "post_run_path": "/wrong",
        "doc_ref": "docs/GENERIC_BACKTEST_DRAFT.md",
        **_BT_CATALOG_ASYNC_DEFAULTS,
        "strategies": [
            _bt_catalog_row("ma_cross", "ma_cross_single", response_shape="result"),
            _bt_catalog_row("ma_cross_scan", "ma_cross_scan", response_shape="scan_result"),
            _bt_catalog_row("buy_hold", "buy_hold_single", response_shape="result"),
        ],
    }
    err = verify_stack_mod._backtest_catalog_archive_kind_errors(body)
    assert err and "post_run_path" in err


def test_backtest_catalog_archive_errors_doc_ref_mismatch(verify_stack_mod) -> None:
    body = {
        "engine_version": ENGINE_VERSION,
        "post_run_path": "/api/backtest/run",
        "doc_ref": "docs/WRONG.md",
        **_BT_CATALOG_ASYNC_DEFAULTS,
        "strategies": [
            _bt_catalog_row("ma_cross", "ma_cross_single", response_shape="result"),
            _bt_catalog_row("ma_cross_scan", "ma_cross_scan", response_shape="scan_result"),
            _bt_catalog_row("buy_hold", "buy_hold_single", response_shape="result"),
        ],
    }
    err = verify_stack_mod._backtest_catalog_archive_kind_errors(body)
    assert err and "doc_ref" in err


def test_backtest_catalog_archive_errors_async_run_query_param_mismatch(
    verify_stack_mod,
) -> None:
    body = {
        "engine_version": ENGINE_VERSION,
        "post_run_path": "/api/backtest/run",
        "doc_ref": "docs/GENERIC_BACKTEST_DRAFT.md",
        "async_run_query_param": "wrong",
        "async_job_status_path_template": "/api/backtest/jobs/{job_id}",
        "async_job_persistence": "memory",
        "strategies": [
            _bt_catalog_row("ma_cross", "ma_cross_single", response_shape="result"),
            _bt_catalog_row("ma_cross_scan", "ma_cross_scan", response_shape="scan_result"),
            _bt_catalog_row("buy_hold", "buy_hold_single", response_shape="result"),
        ],
    }
    err = verify_stack_mod._backtest_catalog_archive_kind_errors(body)
    assert err and "async_run_query_param" in err


def test_backtest_catalog_archive_errors_async_job_template_mismatch(
    verify_stack_mod,
) -> None:
    body = {
        "engine_version": ENGINE_VERSION,
        "post_run_path": "/api/backtest/run",
        "doc_ref": "docs/GENERIC_BACKTEST_DRAFT.md",
        "async_run_query_param": "async",
        "async_job_status_path_template": "/api/wrong/{job_id}",
        "async_job_persistence": "memory",
        "strategies": [
            _bt_catalog_row("ma_cross", "ma_cross_single", response_shape="result"),
            _bt_catalog_row("ma_cross_scan", "ma_cross_scan", response_shape="scan_result"),
            _bt_catalog_row("buy_hold", "buy_hold_single", response_shape="result"),
        ],
    }
    err = verify_stack_mod._backtest_catalog_archive_kind_errors(body)
    assert err and "async_job_status_path_template" in err


def test_backtest_catalog_archive_errors_async_queue_key_when_memory(
    verify_stack_mod,
) -> None:
    body = _bt_catalog_body(
        _bt_catalog_row("ma_cross", "ma_cross_single", response_shape="result"),
        _bt_catalog_row("ma_cross_scan", "ma_cross_scan", response_shape="scan_result"),
    )
    body["async_job_queue_key"] = "tb:backtest:job:queue"
    err = verify_stack_mod._backtest_catalog_archive_kind_errors(body)
    assert err and "async_job_queue_key" in err


def test_backtest_catalog_archive_errors_async_queue_when_redis_key_wrong(
    verify_stack_mod, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.backtest.async_job_backend import QUEUE_KEY

    monkeypatch.setattr(
        "src.backtest.async_job_backend.catalog_async_job_persistence",
        lambda: "redis",
    )
    body = {
        "engine_version": ENGINE_VERSION,
        "post_run_path": "/api/backtest/run",
        "doc_ref": "docs/GENERIC_BACKTEST_DRAFT.md",
        "async_run_query_param": "async",
        "async_job_status_path_template": "/api/backtest/jobs/{job_id}",
        "async_job_persistence": "redis",
        "async_job_queue_key": "wrong-queue",
        "async_job_queue_depth": 0,
        "strategies": [
            _bt_catalog_row("ma_cross", "ma_cross_single", response_shape="result"),
            _bt_catalog_row("ma_cross_scan", "ma_cross_scan", response_shape="scan_result"),
            _bt_catalog_row("buy_hold", "buy_hold_single", response_shape="result"),
        ],
    }
    err = verify_stack_mod._backtest_catalog_archive_kind_errors(body)
    assert err and "async_job_queue_key" in err and QUEUE_KEY in err


def test_backtest_catalog_archive_errors_async_queue_depth_bad_type_when_redis(
    verify_stack_mod, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.backtest.async_job_backend import QUEUE_KEY

    monkeypatch.setattr(
        "src.backtest.async_job_backend.catalog_async_job_persistence",
        lambda: "redis",
    )
    body = {
        "engine_version": ENGINE_VERSION,
        "post_run_path": "/api/backtest/run",
        "doc_ref": "docs/GENERIC_BACKTEST_DRAFT.md",
        "async_run_query_param": "async",
        "async_job_status_path_template": "/api/backtest/jobs/{job_id}",
        "async_job_persistence": "redis",
        "async_job_queue_key": QUEUE_KEY,
        "async_job_queue_depth": 1.5,
        "strategies": [
            _bt_catalog_row("ma_cross", "ma_cross_single", response_shape="result"),
            _bt_catalog_row("ma_cross_scan", "ma_cross_scan", response_shape="scan_result"),
            _bt_catalog_row("buy_hold", "buy_hold_single", response_shape="result"),
        ],
    }
    err = verify_stack_mod._backtest_catalog_archive_kind_errors(body)
    assert err and "async_job_queue_depth" in err


def test_backtest_catalog_archive_errors_async_job_persistence_invalid(
    verify_stack_mod,
) -> None:
    body = {
        "engine_version": ENGINE_VERSION,
        "post_run_path": "/api/backtest/run",
        "doc_ref": "docs/GENERIC_BACKTEST_DRAFT.md",
        "async_run_query_param": "async",
        "async_job_status_path_template": "/api/backtest/jobs/{job_id}",
        "async_job_persistence": "disk",
        "strategies": [
            _bt_catalog_row("ma_cross", "ma_cross_single", response_shape="result"),
            _bt_catalog_row("ma_cross_scan", "ma_cross_scan", response_shape="scan_result"),
            _bt_catalog_row("buy_hold", "buy_hold_single", response_shape="result"),
        ],
    }
    err = verify_stack_mod._backtest_catalog_archive_kind_errors(body)
    assert err and "async_job_persistence" in err


def test_backtest_catalog_archive_errors_empty_title(verify_stack_mod) -> None:
    row = _bt_catalog_row("ma_cross", "ma_cross_single", response_shape="result")
    row["title"] = "   "
    body = _bt_catalog_body(
        row,
        _bt_catalog_row("ma_cross_scan", "ma_cross_scan", response_shape="scan_result"),
    )
    err = verify_stack_mod._backtest_catalog_archive_kind_errors(body)
    assert err and "title" in err


def test_backtest_catalog_archive_errors_empty_description(verify_stack_mod) -> None:
    row = _bt_catalog_row("ma_cross", "ma_cross_single", response_shape="result")
    row["description"] = "\n"
    body = _bt_catalog_body(
        row,
        _bt_catalog_row("ma_cross_scan", "ma_cross_scan", response_shape="scan_result"),
    )
    err = verify_stack_mod._backtest_catalog_archive_kind_errors(body)
    assert err and "description" in err


def test_factors_catalog_shape_errors_empty_series_key(verify_stack_mod) -> None:
    err = verify_stack_mod._factors_catalog_shape_errors(
        {
            "ops": [
                {
                    "id": "ema",
                    "window": "required",
                    "column": "ohlcv",
                    "series_keys": ["value", ""],
                }
            ]
        }
    )
    assert err and "series_keys" in err


def test_factors_catalog_shape_errors_series_keys_not_list(verify_stack_mod) -> None:
    err = verify_stack_mod._factors_catalog_shape_errors(
        {
            "ops": [
                {
                    "id": "ema",
                    "window": "required",
                    "column": "ohlcv",
                    "series_keys": "value",
                }
            ]
        }
    )
    assert err and "series_keys" in err


def test_factors_catalog_shape_errors_root_not_object(verify_stack_mod) -> None:
    err = verify_stack_mod._factors_catalog_shape_errors(None)
    assert err and "不是 JSON 对象" in err


def test_factors_catalog_shape_errors_ops_not_list(verify_stack_mod) -> None:
    err = verify_stack_mod._factors_catalog_shape_errors({"ops": ()})
    assert err and "ops" in err and ("缺失" in err or "为空" in err)


def test_factors_catalog_shape_errors_op_entry_not_object(verify_stack_mod) -> None:
    err = verify_stack_mod._factors_catalog_shape_errors({"ops": [None]})
    assert err and "ops[0]" in err and "不是对象" in err


def test_factors_catalog_shape_errors_missing_id_field(verify_stack_mod) -> None:
    err = verify_stack_mod._factors_catalog_shape_errors(
        {
            "ops": [
                {"window": "required", "column": "ohlcv", "series_keys": ["value"]},
            ]
        }
    )
    assert err and "缺字段" in err and "id" in err


def test_factors_catalog_shape_errors_series_key_element_not_string(verify_stack_mod) -> None:
    err = verify_stack_mod._factors_catalog_shape_errors(
        {
            "ops": [
                {
                    "id": "ema",
                    "window": "required",
                    "column": "ohlcv",
                    "series_keys": ["value", 1],
                }
            ]
        }
    )
    assert err and "series_keys[1]" in err


def test_factors_catalog_shape_errors_blank_op_id(verify_stack_mod) -> None:
    err = verify_stack_mod._factors_catalog_shape_errors(
        {
            "ops": [
                {
                    "id": "   ",
                    "window": "required",
                    "column": "ohlcv",
                    "series_keys": ["value"],
                }
            ]
        }
    )
    assert err and "id 无效" in err


def test_strategies_catalog_shape_errors_blank_title(verify_stack_mod) -> None:
    body = {
        "strategies": [
            {
                "id": "ma_cross",
                "title": "\t",
                "description": "d",
                "strategy_contract_version": "1",
                "signal_params": {"type": "object"},
                "backtest_archive_kinds": ["ma_cross_single", "ma_cross_scan"],
                "backtest_run": {
                    "strategy_id": "ma_cross",
                    "strategy_version": "1",
                    "archive_kind": "ma_cross_single",
                    "params_schema": {"type": "object"},
                },
            },
            {
                "id": "ma_cross_scan",
                "title": "t2",
                "description": "d2",
                "strategy_contract_version": "1",
                "signal_params": {"type": "object"},
                "backtest_archive_kinds": ["ma_cross_scan"],
                "backtest_run": {
                    "strategy_id": "ma_cross_scan",
                    "strategy_version": "1",
                    "archive_kind": "ma_cross_scan",
                    "params_schema": {"type": "object"},
                },
            },
        ]
    }
    err = verify_stack_mod._strategies_catalog_shape_errors(body)
    assert err and "title" in err


def test_strategies_catalog_shape_errors_missing_title(verify_stack_mod) -> None:
    body = {
        "strategies": [
            {
                "id": "ma_cross",
                "description": "d",
                "strategy_contract_version": "1",
                "signal_params": {"type": "object"},
                "backtest_archive_kinds": ["ma_cross_single", "ma_cross_scan"],
                "backtest_run": {
                    "strategy_id": "ma_cross",
                    "strategy_version": "1",
                    "archive_kind": "ma_cross_single",
                    "params_schema": {"type": "object"},
                },
            },
            {
                "id": "ma_cross_scan",
                "title": "t2",
                "description": "d2",
                "strategy_contract_version": "1",
                "signal_params": {"type": "object"},
                "backtest_archive_kinds": ["ma_cross_scan"],
                "backtest_run": {
                    "strategy_id": "ma_cross_scan",
                    "strategy_version": "1",
                    "archive_kind": "ma_cross_scan",
                    "params_schema": {"type": "object"},
                },
            },
        ]
    }
    err = verify_stack_mod._strategies_catalog_shape_errors(body)
    assert err and "title" in err


def test_strategies_catalog_shape_errors_signal_params_not_object(verify_stack_mod) -> None:
    body = {
        "strategies": [
            {
                "id": "ma_cross",
                "title": "t1",
                "description": "d",
                "strategy_contract_version": "1",
                "signal_params": [],
                "backtest_archive_kinds": ["ma_cross_single", "ma_cross_scan"],
                "backtest_run": {
                    "strategy_id": "ma_cross",
                    "strategy_version": "1",
                    "archive_kind": "ma_cross_single",
                    "params_schema": {"type": "object"},
                },
            },
            {
                "id": "ma_cross_scan",
                "title": "t2",
                "description": "d2",
                "strategy_contract_version": "1",
                "signal_params": {"type": "object"},
                "backtest_archive_kinds": ["ma_cross_scan"],
                "backtest_run": {
                    "strategy_id": "ma_cross_scan",
                    "strategy_version": "1",
                    "archive_kind": "ma_cross_scan",
                    "params_schema": {"type": "object"},
                },
            },
        ]
    }
    err = verify_stack_mod._strategies_catalog_shape_errors(body)
    assert err and "signal_params" in err


def test_strategies_catalog_shape_errors_params_schema_not_object(verify_stack_mod) -> None:
    body = {
        "strategies": [
            {
                "id": "ma_cross",
                "title": "t1",
                "description": "d",
                "strategy_contract_version": "1",
                "signal_params": {"type": "object"},
                "backtest_archive_kinds": ["ma_cross_single", "ma_cross_scan"],
                "backtest_run": {
                    "strategy_id": "ma_cross",
                    "strategy_version": "1",
                    "archive_kind": "ma_cross_single",
                    "params_schema": "not-an-object",
                },
            },
            {
                "id": "ma_cross_scan",
                "title": "t2",
                "description": "d2",
                "strategy_contract_version": "1",
                "signal_params": {"type": "object"},
                "backtest_archive_kinds": ["ma_cross_scan"],
                "backtest_run": {
                    "strategy_id": "ma_cross_scan",
                    "strategy_version": "1",
                    "archive_kind": "ma_cross_scan",
                    "params_schema": {"type": "object"},
                },
            },
        ]
    }
    err = verify_stack_mod._strategies_catalog_shape_errors(body)
    assert err and "params_schema" in err


def test_strategies_catalog_shape_errors_blank_description(verify_stack_mod) -> None:
    body = {
        "strategies": [
            {
                "id": "ma_cross",
                "title": "t1",
                "description": "  ",
                "strategy_contract_version": "1",
                "signal_params": {"type": "object"},
                "backtest_archive_kinds": ["ma_cross_single", "ma_cross_scan"],
                "backtest_run": {
                    "strategy_id": "ma_cross",
                    "strategy_version": "1",
                    "archive_kind": "ma_cross_single",
                    "params_schema": {"type": "object"},
                },
            },
            {
                "id": "ma_cross_scan",
                "title": "t2",
                "description": "d2",
                "strategy_contract_version": "1",
                "signal_params": {"type": "object"},
                "backtest_archive_kinds": ["ma_cross_scan"],
                "backtest_run": {
                    "strategy_id": "ma_cross_scan",
                    "strategy_version": "1",
                    "archive_kind": "ma_cross_scan",
                    "params_schema": {"type": "object"},
                },
            },
        ]
    }
    err = verify_stack_mod._strategies_catalog_shape_errors(body)
    assert err and "description" in err


def test_strategies_catalog_shape_errors_root_not_object(verify_stack_mod) -> None:
    err = verify_stack_mod._strategies_catalog_shape_errors([])
    assert err and "不是 JSON 对象" in err


def test_strategies_catalog_shape_errors_strategies_empty(verify_stack_mod) -> None:
    err = verify_stack_mod._strategies_catalog_shape_errors({"strategies": []})
    assert err and ("缺失" in err or "为空" in err)


def test_strategies_catalog_shape_errors_entry_not_object(verify_stack_mod) -> None:
    err = verify_stack_mod._strategies_catalog_shape_errors({"strategies": ["not-a-dict"]})
    assert err and "不是对象" in err


def test_strategies_catalog_shape_errors_title_not_string(verify_stack_mod) -> None:
    body = {
        "strategies": [
            {
                "id": "ma_cross",
                "title": 99,
                "description": "d",
                "strategy_contract_version": "1",
                "signal_params": {"type": "object"},
                "backtest_archive_kinds": ["ma_cross_single", "ma_cross_scan"],
                "backtest_run": {
                    "strategy_id": "ma_cross",
                    "strategy_version": "1",
                    "archive_kind": "ma_cross_single",
                    "params_schema": {"type": "object"},
                },
            },
            {
                "id": "ma_cross_scan",
                "title": "t2",
                "description": "d2",
                "strategy_contract_version": "1",
                "signal_params": {"type": "object"},
                "backtest_archive_kinds": ["ma_cross_scan"],
                "backtest_run": {
                    "strategy_id": "ma_cross_scan",
                    "strategy_version": "1",
                    "archive_kind": "ma_cross_scan",
                    "params_schema": {"type": "object"},
                },
            },
        ]
    }
    err = verify_stack_mod._strategies_catalog_shape_errors(body)
    assert err and "title" in err


def test_strategies_catalog_shape_errors_catalog_missing_ma_cross(verify_stack_mod) -> None:
    """仅注册 scan 时须在末尾命中「缺少 id=ma_cross」。"""
    body = {
        "strategies": [
            {
                "id": "ma_cross_scan",
                "title": "t2",
                "description": "d2",
                "strategy_contract_version": "1",
                "signal_params": {"type": "object"},
                "backtest_archive_kinds": ["ma_cross_scan"],
                "backtest_run": {
                    "strategy_id": "ma_cross_scan",
                    "strategy_version": "1",
                    "archive_kind": "ma_cross_scan",
                    "params_schema": {"type": "object"},
                },
            },
        ]
    }
    err = verify_stack_mod._strategies_catalog_shape_errors(body)
    assert err and "ma_cross" in err


def test_strategies_catalog_shape_errors_catalog_missing_ma_cross_scan(verify_stack_mod) -> None:
    """仅注册 ma_cross 时须在末尾命中「缺少 id=ma_cross_scan」。"""
    body = {
        "strategies": [
            {
                "id": "ma_cross",
                "title": "t1",
                "description": "d1",
                "strategy_contract_version": "1",
                "signal_params": {"type": "object"},
                "backtest_archive_kinds": ["ma_cross_single", "ma_cross_scan"],
                "backtest_run": {
                    "strategy_id": "ma_cross",
                    "strategy_version": "1",
                    "archive_kind": "ma_cross_single",
                    "params_schema": {"type": "object"},
                },
            },
        ]
    }
    err = verify_stack_mod._strategies_catalog_shape_errors(body)
    assert err and "ma_cross_scan" in err


def test_strategies_catalog_shape_errors_missing_strategies_key(verify_stack_mod) -> None:
    err = verify_stack_mod._strategies_catalog_shape_errors({})
    assert err and ("缺失" in err or "为空" in err)


def test_strategies_catalog_shape_errors_backtest_archive_kinds_not_list(verify_stack_mod) -> None:
    body = {
        "strategies": [
            {
                "id": "ma_cross",
                "title": "t1",
                "description": "d1",
                "strategy_contract_version": "1",
                "signal_params": {"type": "object"},
                "backtest_archive_kinds": "ma_cross_single",
                "backtest_run": {
                    "strategy_id": "ma_cross",
                    "strategy_version": "1",
                    "archive_kind": "ma_cross_single",
                    "params_schema": {"type": "object"},
                },
            },
            {
                "id": "ma_cross_scan",
                "title": "t2",
                "description": "d2",
                "strategy_contract_version": "1",
                "signal_params": {"type": "object"},
                "backtest_archive_kinds": ["ma_cross_scan"],
                "backtest_run": {
                    "strategy_id": "ma_cross_scan",
                    "strategy_version": "1",
                    "archive_kind": "ma_cross_scan",
                    "params_schema": {"type": "object"},
                },
            },
        ]
    }
    err = verify_stack_mod._strategies_catalog_shape_errors(body)
    assert err and "backtest_archive_kinds" in err


def test_strategies_catalog_shape_errors_backtest_archive_kinds_empty(verify_stack_mod) -> None:
    body = {
        "strategies": [
            {
                "id": "ma_cross",
                "title": "t1",
                "description": "d1",
                "strategy_contract_version": "1",
                "signal_params": {"type": "object"},
                "backtest_archive_kinds": [],
                "backtest_run": {
                    "strategy_id": "ma_cross",
                    "strategy_version": "1",
                    "archive_kind": "ma_cross_single",
                    "params_schema": {"type": "object"},
                },
            },
            {
                "id": "ma_cross_scan",
                "title": "t2",
                "description": "d2",
                "strategy_contract_version": "1",
                "signal_params": {"type": "object"},
                "backtest_archive_kinds": ["ma_cross_scan"],
                "backtest_run": {
                    "strategy_id": "ma_cross_scan",
                    "strategy_version": "1",
                    "archive_kind": "ma_cross_scan",
                    "params_schema": {"type": "object"},
                },
            },
        ]
    }
    err = verify_stack_mod._strategies_catalog_shape_errors(body)
    assert err and "backtest_archive_kinds" in err


def test_strategies_catalog_shape_errors_backtest_archive_kinds_non_string_element(
    verify_stack_mod,
) -> None:
    """非 ma_cross / ma_cross_scan 的占位条可命中「须为字符串列表」分支。"""
    body = {
        "strategies": [
            {
                "id": "other",
                "title": "t0",
                "description": "d0",
                "strategy_contract_version": "1",
                "signal_params": {"type": "object"},
                "backtest_archive_kinds": ["x", 1],
                "backtest_run": {
                    "strategy_id": "other",
                    "strategy_version": "1",
                    "archive_kind": "x",
                    "params_schema": {"type": "object"},
                },
            },
            {
                "id": "ma_cross",
                "title": "t1",
                "description": "d1",
                "strategy_contract_version": "1",
                "signal_params": {"type": "object"},
                "backtest_archive_kinds": ["ma_cross_single", "ma_cross_scan"],
                "backtest_run": {
                    "strategy_id": "ma_cross",
                    "strategy_version": "1",
                    "archive_kind": "ma_cross_single",
                    "params_schema": {"type": "object"},
                },
            },
            {
                "id": "ma_cross_scan",
                "title": "t2",
                "description": "d2",
                "strategy_contract_version": "1",
                "signal_params": {"type": "object"},
                "backtest_archive_kinds": ["ma_cross_scan"],
                "backtest_run": {
                    "strategy_id": "ma_cross_scan",
                    "strategy_version": "1",
                    "archive_kind": "ma_cross_scan",
                    "params_schema": {"type": "object"},
                },
            },
        ]
    }
    err = verify_stack_mod._strategies_catalog_shape_errors(body)
    assert err and "字符串列表" in err


def test_strategies_catalog_shape_errors_description_not_string(verify_stack_mod) -> None:
    body = {
        "strategies": [
            {
                "id": "ma_cross",
                "title": "t1",
                "description": None,
                "strategy_contract_version": "1",
                "signal_params": {"type": "object"},
                "backtest_archive_kinds": ["ma_cross_single", "ma_cross_scan"],
                "backtest_run": {
                    "strategy_id": "ma_cross",
                    "strategy_version": "1",
                    "archive_kind": "ma_cross_single",
                    "params_schema": {"type": "object"},
                },
            },
            {
                "id": "ma_cross_scan",
                "title": "t2",
                "description": "d2",
                "strategy_contract_version": "1",
                "signal_params": {"type": "object"},
                "backtest_archive_kinds": ["ma_cross_scan"],
                "backtest_run": {
                    "strategy_id": "ma_cross_scan",
                    "strategy_version": "1",
                    "archive_kind": "ma_cross_scan",
                    "params_schema": {"type": "object"},
                },
            },
        ]
    }
    err = verify_stack_mod._strategies_catalog_shape_errors(body)
    assert err and "description" in err


def test_backtest_catalog_archive_errors_root_not_object(verify_stack_mod) -> None:
    err = verify_stack_mod._backtest_catalog_archive_kind_errors(None)
    assert err and "不是 JSON 对象" in err


def test_backtest_catalog_archive_errors_strategies_empty(verify_stack_mod) -> None:
    body = {
        "engine_version": ENGINE_VERSION,
        "post_run_path": "/api/backtest/run",
        "doc_ref": "docs/GENERIC_BACKTEST_DRAFT.md",
        **_BT_CATALOG_ASYNC_DEFAULTS,
        "strategies": [],
    }
    err = verify_stack_mod._backtest_catalog_archive_kind_errors(body)
    assert err and ("缺失" in err or "为空" in err)


def test_backtest_catalog_archive_errors_strategy_row_not_object(verify_stack_mod) -> None:
    body = {
        "engine_version": ENGINE_VERSION,
        "post_run_path": "/api/backtest/run",
        "doc_ref": "docs/GENERIC_BACKTEST_DRAFT.md",
        **_BT_CATALOG_ASYNC_DEFAULTS,
        "strategies": [
            "not-a-dict",
            _bt_catalog_row("ma_cross_scan", "ma_cross_scan", response_shape="scan_result"),
        ],
    }
    err = verify_stack_mod._backtest_catalog_archive_kind_errors(body)
    assert err and "不是对象" in err


def test_backtest_catalog_archive_errors_get_equivalent_paths_not_list(verify_stack_mod) -> None:
    row = _bt_catalog_row("ma_cross", "ma_cross_single", response_shape="result")
    row["get_equivalent_paths"] = "/api/backtest/ma-cross"
    body = _bt_catalog_body(
        row,
        _bt_catalog_row("ma_cross_scan", "ma_cross_scan", response_shape="scan_result"),
    )
    err = verify_stack_mod._backtest_catalog_archive_kind_errors(body)
    assert err and "get_equivalent_paths 非列表" in err


def test_backtest_catalog_archive_errors_missing_get_equivalent_paths(verify_stack_mod) -> None:
    row = _bt_catalog_row("ma_cross", "ma_cross_single", response_shape="result")
    del row["get_equivalent_paths"]
    body = _bt_catalog_body(
        row,
        _bt_catalog_row("ma_cross_scan", "ma_cross_scan", response_shape="scan_result"),
    )
    err = verify_stack_mod._backtest_catalog_archive_kind_errors(body)
    assert err and "get_equivalent_paths 非列表" in err


def test_backtest_catalog_archive_errors_ma_cross_wrong_archive_kind(verify_stack_mod) -> None:
    body = _bt_catalog_body(
        _bt_catalog_row("ma_cross", "ma_cross_scan", response_shape="result"),
        _bt_catalog_row("ma_cross_scan", "ma_cross_scan", response_shape="scan_result"),
    )
    err = verify_stack_mod._backtest_catalog_archive_kind_errors(body)
    assert err and "ma_cross_single" in err


def test_backtest_catalog_archive_errors_bad_response_shape_value(verify_stack_mod) -> None:
    body = _bt_catalog_body(
        _bt_catalog_row("ma_cross", "ma_cross_single", response_shape="payload"),
        _bt_catalog_row("ma_cross_scan", "ma_cross_scan", response_shape="scan_result"),
    )
    err = verify_stack_mod._backtest_catalog_archive_kind_errors(body)
    assert err and "response_shape" in err


def test_backtest_catalog_archive_errors_missing_strategy_id(verify_stack_mod) -> None:
    row = _bt_catalog_row("ma_cross", "ma_cross_single", response_shape="result")
    del row["strategy_id"]
    body = _bt_catalog_body(
        row,
        _bt_catalog_row("ma_cross_scan", "ma_cross_scan", response_shape="scan_result"),
    )
    err = verify_stack_mod._backtest_catalog_archive_kind_errors(body)
    assert err and "strategy_id" in err


def test_backtest_catalog_archive_errors_blank_strategy_id(verify_stack_mod) -> None:
    row = _bt_catalog_row("ma_cross", "ma_cross_single", response_shape="result")
    row["strategy_id"] = "  "
    body = _bt_catalog_body(
        row,
        _bt_catalog_row("ma_cross_scan", "ma_cross_scan", response_shape="scan_result"),
    )
    err = verify_stack_mod._backtest_catalog_archive_kind_errors(body)
    assert err and "strategy_id" in err


def test_factors_catalog_top_level_errors_root_not_object(verify_stack_mod) -> None:
    err = verify_stack_mod._factors_catalog_top_level_errors([])
    assert err and "不是 JSON 对象" in err


def test_backtest_catalog_archive_errors_duplicate_strategy_id(verify_stack_mod) -> None:
    body = _bt_catalog_body(
        _bt_catalog_row("ma_cross", "ma_cross_single", response_shape="result"),
        _bt_catalog_row("ma_cross", "ma_cross_single", response_shape="result"),
    )
    err = verify_stack_mod._backtest_catalog_archive_kind_errors(body)
    assert err and "重复" in err


def test_backtest_catalog_archive_errors_missing_response_shape(verify_stack_mod) -> None:
    row = _bt_catalog_row("ma_cross", "ma_cross_single", response_shape="result")
    del row["response_shape"]
    body = _bt_catalog_body(
        row,
        _bt_catalog_row("ma_cross_scan", "ma_cross_scan", response_shape="scan_result"),
    )
    err = verify_stack_mod._backtest_catalog_archive_kind_errors(body)
    assert err and "response_shape" in err


def test_strategies_catalog_shape_errors_entry_id_blank(verify_stack_mod) -> None:
    body = {
        "strategies": [
            {
                "id": "   ",
                "title": "t",
                "description": "d",
                "strategy_contract_version": "1",
                "signal_params": {"type": "object"},
                "backtest_archive_kinds": ["ma_cross_single", "ma_cross_scan"],
                "backtest_run": {
                    "strategy_id": "ma_cross",
                    "strategy_version": "1",
                    "archive_kind": "ma_cross_single",
                    "params_schema": {"type": "object"},
                },
            },
            {
                "id": "ma_cross_scan",
                "title": "t2",
                "description": "d2",
                "strategy_contract_version": "1",
                "signal_params": {"type": "object"},
                "backtest_archive_kinds": ["ma_cross_scan"],
                "backtest_run": {
                    "strategy_id": "ma_cross_scan",
                    "strategy_version": "1",
                    "archive_kind": "ma_cross_scan",
                    "params_schema": {"type": "object"},
                },
            },
        ]
    }
    err = verify_stack_mod._strategies_catalog_shape_errors(body)
    assert err and ".id 无效" in err


def test_strategies_catalog_shape_errors_backtest_run_archive_kind_blank(
    verify_stack_mod,
) -> None:
    body = {
        "strategies": [
            {
                "id": "ma_cross",
                "title": "t1",
                "description": "d1",
                "strategy_contract_version": "1",
                "signal_params": {"type": "object"},
                "backtest_archive_kinds": ["ma_cross_single", "ma_cross_scan"],
                "backtest_run": {
                    "strategy_id": "ma_cross",
                    "strategy_version": "1",
                    "archive_kind": "  ",
                    "params_schema": {"type": "object"},
                },
            },
            {
                "id": "ma_cross_scan",
                "title": "t2",
                "description": "d2",
                "strategy_contract_version": "1",
                "signal_params": {"type": "object"},
                "backtest_archive_kinds": ["ma_cross_scan"],
                "backtest_run": {
                    "strategy_id": "ma_cross_scan",
                    "strategy_version": "1",
                    "archive_kind": "ma_cross_scan",
                    "params_schema": {"type": "object"},
                },
            },
        ]
    }
    err = verify_stack_mod._strategies_catalog_shape_errors(body)
    assert err and "archive_kind 无效" in err


def test_strategies_catalog_shape_errors_backtest_run_strategy_id_blank(
    verify_stack_mod,
) -> None:
    body = {
        "strategies": [
            {
                "id": "ma_cross",
                "title": "t1",
                "description": "d1",
                "strategy_contract_version": "1",
                "signal_params": {"type": "object"},
                "backtest_archive_kinds": ["ma_cross_single", "ma_cross_scan"],
                "backtest_run": {
                    "strategy_id": "  ",
                    "strategy_version": "1",
                    "archive_kind": "ma_cross_single",
                    "params_schema": {"type": "object"},
                },
            },
            {
                "id": "ma_cross_scan",
                "title": "t2",
                "description": "d2",
                "strategy_contract_version": "1",
                "signal_params": {"type": "object"},
                "backtest_archive_kinds": ["ma_cross_scan"],
                "backtest_run": {
                    "strategy_id": "ma_cross_scan",
                    "strategy_version": "1",
                    "archive_kind": "ma_cross_scan",
                    "params_schema": {"type": "object"},
                },
            },
        ]
    }
    err = verify_stack_mod._strategies_catalog_shape_errors(body)
    assert err and "backtest_run.strategy_id 无效" in err


def test_backtest_catalog_archive_errors_missing_archive_kind(verify_stack_mod) -> None:
    row = _bt_catalog_row("ma_cross", "ma_cross_single", response_shape="result")
    del row["archive_kind"]
    body = _bt_catalog_body(
        row,
        _bt_catalog_row("ma_cross_scan", "ma_cross_scan", response_shape="scan_result"),
    )
    err = verify_stack_mod._backtest_catalog_archive_kind_errors(body)
    assert err and "archive_kind" in err


def test_backtest_catalog_archive_errors_blank_archive_kind(verify_stack_mod) -> None:
    row = _bt_catalog_row("ma_cross", "ma_cross_single", response_shape="result")
    row["archive_kind"] = "\t"
    body = _bt_catalog_body(
        row,
        _bt_catalog_row("ma_cross_scan", "ma_cross_scan", response_shape="scan_result"),
    )
    err = verify_stack_mod._backtest_catalog_archive_kind_errors(body)
    assert err and "archive_kind" in err


def test_backtest_catalog_archive_errors_missing_engine_version_key(verify_stack_mod) -> None:
    body = {
        "post_run_path": "/api/backtest/run",
        "doc_ref": "docs/GENERIC_BACKTEST_DRAFT.md",
        **_BT_CATALOG_ASYNC_DEFAULTS,
        "strategies": [
            _bt_catalog_row("ma_cross", "ma_cross_single", response_shape="result"),
            _bt_catalog_row("ma_cross_scan", "ma_cross_scan", response_shape="scan_result"),
            _bt_catalog_row("buy_hold", "buy_hold_single", response_shape="result"),
        ],
    }
    err = verify_stack_mod._backtest_catalog_archive_kind_errors(body)
    assert err and "engine_version" in err


def test_factors_catalog_shape_errors_missing_window_key(verify_stack_mod) -> None:
    err = verify_stack_mod._factors_catalog_shape_errors(
        {
            "ops": [
                {
                    "id": "ema",
                    "column": "ohlcv",
                    "series_keys": ["value"],
                }
            ]
        }
    )
    assert err and "缺字段" in err and "window" in err


def test_factors_catalog_op_ids_match_opname_blank_op_id(verify_stack_mod) -> None:
    err = verify_stack_mod._factors_catalog_op_ids_match_opname(
        {
            "ops": [
                {
                    "id": "   ",
                    "window": "required",
                    "column": "ohlcv",
                    "series_keys": ["value"],
                }
            ]
        }
    )
    assert err and "id 无效" in err


def test_verify_api_catalog_contracts_live_passes(verify_stack_mod) -> None:
    """``_verify_api_catalog_contracts``：双 catalog + archive 对齐 + 因子（与 ``verify_stack`` 主流程一致）。"""
    assert verify_stack_mod._verify_api_catalog_contracts() is None


def test_factors_cross_section_body_errors_passes(verify_stack_mod) -> None:
    body = {
        "as_of_trade_date": "2024-06-11",
        "period": 20,
        "max_codes_requested": 20,
        "row_count": 1,
        "doc_ref": "docs/FACTORS.md",
        "rows": [
            {
                "code": "sh.tz",
                "close": 10.0,
                "volume": 100,
                "amount": 1000.0,
                "turnover_rate": None,
                "pct_change": None,
                "ret_pct": 25.0,
                "meta_bars": 3,
            }
        ],
    }
    assert (
        verify_stack_mod._factors_cross_section_body_errors(
            body,
            expect_as_of="2024-06-11",
            expect_period=20,
            expect_max_codes=20,
        )
        is None
    )


def test_factors_cross_section_body_errors_doc_ref(verify_stack_mod) -> None:
    body = {
        "as_of_trade_date": "2024-06-11",
        "period": 20,
        "max_codes_requested": 20,
        "row_count": 0,
        "doc_ref": "wrong.md",
        "rows": [],
    }
    err = verify_stack_mod._factors_cross_section_body_errors(
        body,
        expect_as_of="2024-06-11",
        expect_period=20,
        expect_max_codes=20,
    )
    assert err and "doc_ref" in err


def test_factors_cross_section_body_errors_row_keys(verify_stack_mod) -> None:
    body = {
        "as_of_trade_date": "2024-06-11",
        "period": 20,
        "max_codes_requested": 20,
        "row_count": 1,
        "doc_ref": "docs/FACTORS.md",
        "rows": [{"code": "sh.tz", "close": 1.0, "volume": 1, "amount": 1.0, "meta_bars": 2}],
    }
    err = verify_stack_mod._factors_cross_section_body_errors(
        body,
        expect_as_of="2024-06-11",
        expect_period=20,
        expect_max_codes=20,
    )
    assert err and "键集合" in err


def test_verify_factors_cross_section_smoke_returns_structured(verify_stack_mod) -> None:
    """连真实配置库：成功 ``(None, False)`` 或 overview 无指数 ``(None, True)``；失败时第一项非空。"""
    err, skip = verify_stack_mod._verify_factors_cross_section_smoke()
    assert isinstance(skip, bool)
    if err is not None:
        assert skip is False
        assert isinstance(err, str) and err.strip()
