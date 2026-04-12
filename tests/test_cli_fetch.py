"""拉数脚本 CLI 契约（不连库、不跑 baostock）。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run_feed_dashboard_dry_run(extra: list[str]) -> str:
    """Run feed_dashboard.py in dry-run; return merged stdout+stderr (UTF-8)."""
    script = ROOT / "scripts" / "feed_dashboard.py"
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run(
        [sys.executable, str(script), "--dry-run", *extra],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    assert r.returncode == 0, (r.stderr, r.stdout)
    return (r.stdout or "") + (r.stderr or "")


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


def test_feed_dashboard_dry_run_quick_prints_expected_steps():
    out = _run_feed_dashboard_dry_run(["--profile", "quick"])
    assert "init_db.py" in out
    assert "fetch_data.py" in out
    assert "--mode stocks" in out
    assert "--mode indices" in out
    assert "--mode klines" in out
    assert "--mode calendar" in out
    assert "--source baostock" in out
    assert "dry-run" in out.lower()


def test_feed_dashboard_dry_run_quick_skip_calendar_omits_calendar_mode():
    out = _run_feed_dashboard_dry_run(["--profile", "quick", "--skip-calendar"])
    assert "--mode calendar" not in out


def test_feed_dashboard_dry_run_daily_includes_with_calendar():
    out = _run_feed_dashboard_dry_run(["--profile", "daily", "--skip-init"])
    assert "--mode daily" in out
    assert "--with-calendar" in out
    assert "init_db.py" not in out


def test_feed_dashboard_dry_run_daily_skip_calendar_omits_with_calendar():
    out = _run_feed_dashboard_dry_run(["--profile", "daily", "--skip-init", "--skip-calendar"])
    assert "--mode daily" in out
    assert "--with-calendar" not in out
