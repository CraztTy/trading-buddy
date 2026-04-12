#!/usr/bin/env python3
"""
将 GET /api/backtest/catalog 的 JSON 体写入 E2E fixture（UTF-8，无 BOM）。

在仓库根执行；与 ``src/api/routers/backtest.py`` 中 ``_backtest_engine_catalog_payload`` 对齐。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
DEFAULT_OUT = project_root / "frontend" / "e2e" / "fixtures" / "backtest-catalog.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUT,
        help="输出路径（默认: frontend/e2e/fixtures/backtest-catalog.json）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印路径与策略条数，不写文件")
    args = parser.parse_args()

    sys.path.insert(0, str(project_root))
    from src.api.routers.backtest import _backtest_engine_catalog_payload

    payload = _backtest_engine_catalog_payload().model_dump()
    n = len(payload.get("strategies") or [])
    out = args.output.resolve()
    print(f"  strategies 条数: {n}")
    print(f"  engine_version: {payload.get('engine_version')!r}")
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
