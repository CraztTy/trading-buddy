#!/usr/bin/env python3
"""
将 GET /api/factors/catalog 的 JSON 体写入 E2E fixture（UTF-8，无 BOM）。

在仓库根执行（修改 ``OpName`` / ``_factor_ops_catalog_entries`` 后跑一遍，再提交
``frontend/e2e/fixtures/factor-catalog.json``，Playwright 与 ``installApiMocks`` 即与后端一致）。

勿用 PowerShell ``>`` 重定向 ``python -c`` 输出到 JSON 文件，易生成 UTF-16。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
DEFAULT_OUT = project_root / "frontend" / "e2e" / "fixtures" / "factor-catalog.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUT,
        help="输出路径（默认: frontend/e2e/fixtures/factor-catalog.json）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印将写入的路径与算子数量，不写文件",
    )
    args = parser.parse_args()

    sys.path.insert(0, str(project_root))
    from src.api.routers.factors import FactorCatalogResponse, _factor_ops_catalog_entries

    payload = FactorCatalogResponse(ops=_factor_ops_catalog_entries()).model_dump()
    n = len(payload.get("ops") or [])
    out = args.output.resolve()
    print(f"  ops 条数: {n}")
    print(f"  输出: {out}")

    if args.dry_run:
        return 0

    out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    out.write_text(text, encoding="utf-8", newline="\n")
    print("  已写入（UTF-8）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
