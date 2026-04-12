#!/usr/bin/env python3
"""
依次导出 E2E 所需的只读 catalog 固件（UTF-8）。

等价于连续执行：
  python scripts/export_factor_catalog_fixture.py
  python scripts/export_backtest_catalog_fixture.py

可选 **--with-openapi**：最后再执行 **``python scripts/export_openapi.py``**，刷新 **``docs/openapi.json``**
（改路由或 Pydantic 响应后与 CI 快照一致）。

在仓库根执行；**--dry-run** 会传给各子脚本（仅打印条数与路径，不写文件）；**--with-openapi** 与
**--dry-run** 同时使用时，OpenAPI 子脚本也会 **--dry-run**（不写 ``docs/openapi.json``）。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent

CHILDREN = (
    "export_factor_catalog_fixture.py",
    "export_backtest_catalog_fixture.py",
)
OPENAPI_SCRIPT = "export_openapi.py"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="传给各子脚本，仅打印不写文件",
    )
    parser.add_argument(
        "--with-openapi",
        action="store_true",
        help=f"最后追加执行 {OPENAPI_SCRIPT}（刷新 docs/openapi.json）",
    )
    args = parser.parse_args()

    for name in CHILDREN:
        script = project_root / "scripts" / name
        cmd = [sys.executable, str(script)]
        if args.dry_run:
            cmd.append("--dry-run")
        print(f"\n>>> {name}")
        r = subprocess.run(cmd, cwd=str(project_root))
        if r.returncode != 0:
            print(f"[FAIL] {name} 退出码 {r.returncode}", file=sys.stderr)
            return r.returncode

    if args.with_openapi:
        script = project_root / "scripts" / OPENAPI_SCRIPT
        cmd = [sys.executable, str(script)]
        if args.dry_run:
            cmd.append("--dry-run")
        print(f"\n>>> {OPENAPI_SCRIPT}")
        r = subprocess.run(cmd, cwd=str(project_root))
        if r.returncode != 0:
            print(f"[FAIL] {OPENAPI_SCRIPT} 退出码 {r.returncode}", file=sys.stderr)
            return r.returncode

    print("\n全部完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
