"""``src.common.cli_iso_date`` 与依赖它的 CLI 脚本（可 importlib 加载）。"""

from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path

from src.common.cli_iso_date import check_cli_date_order, parse_cli_iso_date


def test_parse_cli_iso_date_none_and_valid():
    assert parse_cli_iso_date("--start-date", None) is None
    assert parse_cli_iso_date("--start-date", "") is None
    assert parse_cli_iso_date("--start-date", "  2024-06-01  ") == date(2024, 6, 1)


def test_check_cli_date_order():
    assert check_cli_date_order(None, None) is None
    assert check_cli_date_order(date(2024, 1, 1), None) is None
    assert check_cli_date_order(None, date(2024, 1, 2)) is None
    assert check_cli_date_order(date(2024, 1, 1), date(2024, 1, 1)) is None
    msg = check_cli_date_order(date(2024, 6, 1), date(2024, 1, 1))
    assert msg is not None
    assert "不能晚于" in msg


def test_parse_cli_iso_date_invalid_raises():
    try:
        parse_cli_iso_date("--start-date", "not-a-date")
    except ValueError as e:
        assert "YYYY-MM-DD" in str(e)
        assert "not-a-date" in str(e)
    else:
        raise AssertionError("expected ValueError")


def _load_script(name: str):
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"_script_{name}", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_run_backtest_and_scan_scripts_load():
    """顶层 ``sys.path`` + ``from src.common…`` 在 importlib 加载下不报错。"""
    assert callable(_load_script("run_backtest.py").main)
    assert callable(_load_script("scan_backtest.py").main)


def test_trend_v0_archive_and_compare_scripts_load():
    assert callable(_load_script("trend_v0_archive_baseline.py").main)
    assert callable(_load_script("trend_v0_backtest_compare.py").main)


def test_export_factor_cross_section_script_load():
    assert callable(_load_script("export_factor_cross_section.py").main)
