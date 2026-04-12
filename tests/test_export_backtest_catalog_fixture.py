"""scripts/export_backtest_catalog_fixture.py 契约（不写仓库文件）。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_export_backtest_catalog_fixture_dry_run_exit_0():
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "export_backtest_catalog_fixture.py"), "--dry-run"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert r.returncode == 0, r.stderr
    assert "strategies" in r.stdout or "engine_version" in r.stdout
    assert "backtest-catalog.json" in r.stdout
