"""scripts/export_all_e2e_catalogs.py 聚合导出（dry-run）。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_export_all_e2e_catalogs_dry_run_exit_0():
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "export_all_e2e_catalogs.py"), "--dry-run"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert r.returncode == 0, r.stderr
    assert "export_factor_catalog_fixture.py" in r.stdout or "factor-catalog" in r.stdout
    assert "export_backtest_catalog_fixture.py" in r.stdout or "backtest-catalog" in r.stdout


def test_export_all_e2e_catalogs_dry_run_with_openapi_exit_0():
    r = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "export_all_e2e_catalogs.py"),
            "--dry-run",
            "--with-openapi",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert r.returncode == 0, r.stderr
    assert "export_openapi.py" in r.stdout
