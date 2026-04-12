#!/usr/bin/env python3
"""
将 FastAPI ``app.openapi()`` 写入 ``docs/openapi.json``（UTF-8，无 BOM）。

用于客户端 / CI 与当前路由契约对齐；改路由或 Pydantic 模型后请在仓库根执行::

    python scripts/export_openapi.py

``--dry-run`` 仅打印路径与 schema 数量。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
DEFAULT_OUT = project_root / "docs" / "openapi.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0].strip())
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUT,
        help="输出路径（默认: docs/openapi.json）",
    )
    parser.add_argument("--dry-run", action="store_true", help="不写文件，只打印摘要")
    args = parser.parse_args()

    sys.path.insert(0, str(project_root))
    from src.api.main import app

    spec = app.openapi()
    n_schemas = len(spec.get("components", {}).get("schemas", {}))
    n_paths = len(spec.get("paths", {}))
    out = args.output.resolve()
    print(f"  paths: {n_paths}  components.schemas: {n_schemas}")
    print(f"  输出: {out}")

    if args.dry_run:
        return 0

    out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(spec, ensure_ascii=False, indent=2)
    out.write_text(text + "\n", encoding="utf-8", newline="\n")
    print("  已写入（UTF-8）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
