#!/usr/bin/env python3
"""
按交易日导出「价量截面」**CSV** 或 **Parquet**（读当前 .env 数据库），与 **docs/FACTORS.md**「截面因子数据模型（草案）」及 **docs/FACTOR_SNAPSHOT_AND_PERSISTENCE.md** 中 **`factor_exports`** 约定对齐。

默认从 **daily_kline** 取在 **--as-of-date** 当日有 K 的 code（**--max-codes** 截断）；也可用 **--codes-file** 指定标的列表。
各 code 的日 K 默认经 **`KlineRepository.get_daily_last_n_bars_per_code`** 一次（或分块 **IN**）批量拉取（**ROW_NUMBER** 窗口，MySQL **8+** / SQLite **3.25+**），再在进程内算 **pct_change_n**（列名 **ret_{N}d**）。**`--legacy-per-code-fetch`** 强制逐标的 **`get_daily`** + **`--max-concurrent`** 并发；**`--auto-legacy-fallback`** 在批量失败时自动切到同一路径（stderr 打 **warn**）。当日 bar 另输出 **volume**、**amount**、**turnover_rate**、**pct_change**（**pct_change** 与 **`daily_kline.change_pct`** 一致；**turnover_rate** / **pct_change** 可空）。

用法（项目根）:
  python scripts/export_factor_cross_section.py --as-of-date 2024-06-28 -o experiments/demo/outputs/cross_20240628.csv
  python scripts/export_factor_cross_section.py --as-of-date 2024-06-28 --codes-file pool.txt --period 10 -o out.csv
  python scripts/export_factor_cross_section.py --as-of-date 2024-06-28 --max-codes 500 -o -
  python scripts/export_factor_cross_section.py --as-of-date 2024-06-28 --dry-run
  python scripts/export_factor_cross_section.py --as-of-date 2024-06-28 --legacy-per-code-fetch --max-concurrent 8 -o out.csv
  python scripts/export_factor_cross_section.py --as-of-date 2024-06-28 --auto-legacy-fallback -o out.csv
  python scripts/export_factor_cross_section.py --as-of-date 2024-06-28 --period 20 --output-format parquet -o out.parquet
  python scripts/export_factor_cross_section.py --as-of-date 2024-06-28 -o cross.csv --print-manifest-snippet

**--dry-run**：只解析标的列表（**--codes-file** 或 **KlineRepository.list_codes_on_trade_date**），打印条数与首尾 code，不写 CSV、不拉 **period** 窗口。

退出码:
  0 — 成功（可无数据行，见 stderr 提示）
  1 — 数据库或其它运行时错误
  2 — 参数错误（非法日期、**--period** < 1、无可用标的等）
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

project_root = Path(__file__).resolve().parent.parent
_root_s = str(project_root)
if _root_s not in sys.path:
    sys.path.insert(0, _root_s)

from src.common.cli_iso_date import parse_cli_iso_date  # noqa: E402
from src.data.models import KLine  # noqa: E402
from src.factors.cross_section import (  # noqa: E402
    compute_cross_section_row,
    cross_section_factor_set_id,
)


def _read_codes_file(path: Path) -> list[str]:
    raw = path.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    for line in raw:
        s = line.split("#", 1)[0].strip()
        if s:
            out.append(s)
    return out


def _row_from_klines(
    klines: list[KLine],
    as_of: date,
    period: int,
    ret_key: str,
) -> dict[str, Any] | None:
    hit = compute_cross_section_row(klines, as_of, period)
    if hit is None:
        return None
    return {
        "as_of_trade_date": as_of.isoformat(),
        "code": hit.code,
        "close": hit.close,
        "volume": hit.volume,
        "amount": hit.amount,
        "turnover_rate": hit.turnover_rate,
        "pct_change": hit.pct_change,
        ret_key: hit.ret_pct,
        "meta_bars": hit.meta_bars,
    }


async def _legacy_row_for_code(
    as_of: date,
    period: int,
    code: str,
    ret_key: str,
    sem: asyncio.Semaphore,
) -> dict[str, Any] | None:
    from src.data.storage import KlineRepository, get_database

    async with sem:
        async with get_database().session() as session:
            repo = KlineRepository(session)
            klines = await repo.get_daily(
                code=code,
                end_date=as_of,
                limit=period + 1,
            )
    return _row_from_klines(klines, as_of, period, ret_key)


def _write_parquet(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    import pandas as pd

    df = pd.DataFrame(rows, columns=fieldnames)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def _emit_manifest_factor_snippet(
    *,
    output_path: str,
    as_of: date,
    period: int,
    row_count: int,
    fieldnames: list[str],
    fmt: str,
) -> None:
    rel = Path(output_path).as_posix()
    cli_fmt = "parquet" if fmt == "parquet" else "csv"
    snippet: dict[str, Any] = {
        "path": rel,
        "as_of_trade_date": as_of.isoformat(),
        "factor_set_id": cross_section_factor_set_id(period=period),
        "columns": fieldnames,
        "row_count": row_count,
        "cli": (
            "python scripts/export_factor_cross_section.py "
            f"--as-of-date {as_of.isoformat()} --period {period} "
            f"--output-format {cli_fmt} -o {rel}"
        ),
    }
    print(
        "\n# manifest.json 内 factor_exports[] 单条示例（粘贴前按需改 path）：\n"
        + json.dumps(snippet, ensure_ascii=False, indent=2),
        file=sys.stderr,
    )


async def _async_main(args: argparse.Namespace) -> int:
    from src.common.config import describe_database_write_target
    from src.data.storage import dispose_database, get_database

    try:
        as_of = parse_cli_iso_date("--as-of-date", args.as_of_date)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    assert as_of is not None

    period: int = args.period
    if period < 1:
        print("错误: --period 须 >= 1", file=sys.stderr)
        return 2

    fmt = str(getattr(args, "output_format", "csv") or "csv").strip().lower()
    if fmt not in ("csv", "parquet"):
        print(f"错误: --output-format 须为 csv|parquet，实际 {fmt!r}", file=sys.stderr)
        return 2
    out_path = args.output
    if fmt == "parquet" and (not out_path or str(out_path).strip() in ("", "-")):
        print("错误: Parquet 须指定 -o 文件路径（不可为 -）", file=sys.stderr)
        return 2

    ret_key = f"ret_{period}d"
    print(f"数据读取目标: {describe_database_write_target()}", file=sys.stderr)
    print(f"截面日 {as_of.isoformat()} 因子列 {ret_key}", file=sys.stderr)

    db = get_database()
    try:
        async with db.session() as session:
            from src.data.storage import KlineRepository

            repo = KlineRepository(session)
            if args.codes_file:
                codes = _read_codes_file(Path(args.codes_file))
                if not codes:
                    print("错误: --codes-file 无有效 code 行", file=sys.stderr)
                    return 2
            else:
                lim = args.max_codes if args.max_codes > 0 else None
                codes = await repo.list_codes_on_trade_date(as_of, max_codes=lim)
                if not codes:
                    print(
                        f"错误: {as_of.isoformat()} 在 daily_kline 中无行（或 --max-codes 截断为空）",
                        file=sys.stderr,
                    )
                    return 2

            if args.dry_run:
                print(f"[dry-run] 标的数 {len(codes)}", file=sys.stderr)
                if codes:
                    print(f"[dry-run] 首 {codes[0]!r} 末 {codes[-1]!r}", file=sys.stderr)
                return 0

            windows: dict[str, list[KLine]] | None = None
            use_legacy_collect = bool(args.legacy_per_code_fetch)
            if not use_legacy_collect:
                try:
                    windows = await repo.get_daily_last_n_bars_per_code(
                        codes, as_of, max_bars=period + 1
                    )
                except Exception as e:
                    if args.auto_legacy_fallback:
                        print(
                            "[warn] get_daily_last_n_bars_per_code 失败，"
                            "按 --auto-legacy-fallback 改用逐标的 get_daily: "
                            f"{e!r}",
                            file=sys.stderr,
                        )
                        use_legacy_collect = True
                    else:
                        print(
                            f"错误: 批量拉取日 K 失败（需 MySQL 8+ / SQLite 3.25+ 窗口函数；"
                            f"可加 --legacy-per-code-fetch 或 --auto-legacy-fallback）: {e!r}",
                            file=sys.stderr,
                        )
                        return 1

        rows: list[dict[str, Any]] = []
        if use_legacy_collect:
            print(
                "[info] 逐标的 get_daily + 并发 "
                f"(max_concurrent={max(1, int(args.max_concurrent))})",
                file=sys.stderr,
            )
            sem = asyncio.Semaphore(max(1, int(args.max_concurrent)))
            tasks = [
                _legacy_row_for_code(as_of, period, c, ret_key, sem) for c in codes
            ]
            raw_rows = await asyncio.gather(*tasks, return_exceptions=True)
            for c, item in zip(codes, raw_rows, strict=True):
                if isinstance(item, BaseException):
                    print(f"错误: {c}: {item!r}", file=sys.stderr)
                    return 1
                if item is not None:
                    rows.append(item)
        else:
            assert windows is not None
            for code in codes:
                r = _row_from_klines(windows.get(code, []), as_of, period, ret_key)
                if r is not None:
                    rows.append(r)

        rows.sort(key=lambda r: r["code"])
        if not rows:
            print("警告: 无有效行（标的在当日无 K 或不足 period+1 根）", file=sys.stderr)

        fieldnames = [
            "as_of_trade_date",
            "code",
            "close",
            "volume",
            "amount",
            "turnover_rate",
            "pct_change",
            ret_key,
            "meta_bars",
        ]
        if fmt == "parquet":
            outp = Path(str(out_path))
            _write_parquet(outp, fieldnames, rows)
            print(f"已写入 {len(rows)} 行 (parquet) -> {outp}", file=sys.stderr)
        elif out_path in (None, "-", ""):
            w = csv.DictWriter(sys.stdout, fieldnames=fieldnames, lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
        else:
            outp = Path(out_path)
            outp.parent.mkdir(parents=True, exist_ok=True)
            with outp.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
                w.writeheader()
                w.writerows(rows)
            print(f"已写入 {len(rows)} 行 -> {outp}", file=sys.stderr)

        if bool(getattr(args, "print_manifest_snippet", False)):
            if fmt == "parquet" or (out_path not in (None, "-", "")):
                _emit_manifest_factor_snippet(
                    output_path=str(out_path),
                    as_of=as_of,
                    period=period,
                    row_count=len(rows),
                    fieldnames=fieldnames,
                    fmt=fmt,
                )
            else:
                print(
                    "提示: --print-manifest-snippet 在输出为 stdout 时跳过（请使用 -o 文件路径）",
                    file=sys.stderr,
                )

        return 0
    finally:
        await dispose_database()


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="导出指定交易日的截面 ret_Nd、close、volume、amount、turnover_rate、pct_change（CSV 或 Parquet）"
    )
    p.add_argument("--as-of-date", required=True, help="截面交易日 YYYY-MM-DD")
    p.add_argument(
        "--period",
        type=int,
        default=20,
        help="pct_change_n 的 N（默认 20，列名 ret_20d）",
    )
    p.add_argument(
        "--max-codes",
        type=int,
        default=5000,
        help="无 --codes-file 时，从当日有 K 的 code 中取前多少个（0=不限制，慎用）",
    )
    p.add_argument(
        "--codes-file",
        default=None,
        help="每行一个 code，# 后为注释；与当日有 K 的交集在脚本内按最后一根 trade_date 校验",
    )
    p.add_argument(
        "--max-concurrent",
        type=int,
        default=16,
        help="逐标的拉数时：并发 get_daily 上限（默认 16；见 --legacy-per-code-fetch / --auto-legacy-fallback）",
    )
    p.add_argument(
        "--legacy-per-code-fetch",
        action="store_true",
        help="强制逐标的 get_daily（无 ROW_NUMBER 的老库）；默认用 get_daily_last_n_bars_per_code 单次批量",
    )
    p.add_argument(
        "--auto-legacy-fallback",
        action="store_true",
        help="批量窗口拉数失败时自动改为逐标的 get_daily（与 --legacy-per-code-fetch 二选一即可）",
    )
    p.add_argument(
        "-o",
        "--output",
        default="-",
        help="输出路径，**-** 表示 stdout（仅 csv）；parquet 须为文件路径",
    )
    p.add_argument(
        "--output-format",
        choices=("csv", "parquet"),
        default="csv",
        help="输出格式（parquet 依赖 PyArrow，见 requirements.txt）",
    )
    p.add_argument(
        "--print-manifest-snippet",
        action="store_true",
        help="成功写盘后向 stderr 打印 manifest.json 内 factor_exports[] 单条 JSON 示例",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="只解析标的并打印条数/首尾 code，不写 CSV、不计算因子",
    )
    ns = p.parse_args(list(argv) if argv is not None else None)
    return asyncio.run(_async_main(ns))


if __name__ == "__main__":
    raise SystemExit(main())
