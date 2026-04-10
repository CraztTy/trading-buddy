"""拉数脚本 CLI 契约（不连库、不跑 baostock）。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _run_script_help(rel: str) -> str:
    script = ROOT / rel
    r = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_fetch_data_help_lists_daily_and_incremental():
    out = _run_script_help("scripts/fetch_data.py")
    assert "daily" in out
    assert "incremental" in out.lower() or "--incremental" in out


def test_feed_dashboard_help_lists_daily_profile():
    out = _run_script_help("scripts/feed_dashboard.py")
    assert "daily" in out
