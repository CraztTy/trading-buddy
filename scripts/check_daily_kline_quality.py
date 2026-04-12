#!/usr/bin/env python3
"""
日 K / 股票基础表数据质量摘要。依赖项目根目录 .env 数据库配置。

用法（项目根）:
  python scripts/check_daily_kline_quality.py
  python scripts/check_daily_kline_quality.py --json
  python scripts/check_daily_kline_quality.py --kline-only
  python scripts/check_daily_kline_quality.py --gap-sample 50 --gap-seed-offset 0
  python scripts/check_daily_kline_quality.py --gap-sample 50 --gap-exchange cn
  python scripts/check_daily_kline_quality.py --gap-sample 50 --gap-exchange none

退出码:
  0 — 无阻塞项（仍可能打印 orphan 等提示，见 --strict）
  1 — 存在 orphan 日 K、stock_info 空名称、或 stock 缺 K 线等（需 --strict）
  2 — 重复 (code, trade_date)、非法 OHLC、或负成交量
  3 — **交易日历门控（B+D）**：`--gap-sample>0` 且 `--gap-exchange` 非 none 时，
      `trade_calendar` 无数据或 `date_max` 早于 min(日K全局 trade_date_max, 今天) 减 `--gap-calendar-grace-days`

对照: docs/ROADMAP.md 阶段 A；口径见 docs/DATA_AND_ADJUSTMENT.md。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


def _exit_code(
    kline: dict,
    stock: dict | None,
    *,
    strict: bool,
    calendar_gate_ok: bool,
) -> int:
    if (
        kline["duplicate_code_date_groups"] > 0
        or kline.get("invalid_ohlc_rows", 0) > 0
        or kline.get("negative_volume_rows", 0) > 0
    ):
        return 2
    if not calendar_gate_ok:
        return 3
    if strict and stock is not None:
        if (
            kline.get("orphan_kline_rows", 0) > 0
            or stock.get("empty_name_rows", 0) > 0
            or kline.get("stock_info_codes_without_kline", 0) > 0
        ):
            return 1
    return 0


def _print_gap_section(rg: dict) -> None:
    if not rg.get("enabled"):
        print()
        print("calendar_gap_sample: 已关闭（sample_size<=0）。")
        return
    print()
    print("--- 抽样缺口（公历 + 可选交易日 trade_calendar）---")
    print(f"请求样本数: {rg.get('sample_size_requested')}  offset: {rg.get('seed_offset', 0)}")
    print(f"gap_exchange: {rg.get('gap_exchange') or '—（仅公历）'}")
    print(f"trade_calendar 行数: {rg.get('trading_calendar_row_count', 0)}")
    tmin, tmax = rg.get("trading_calendar_date_min"), rg.get("trading_calendar_date_max")
    if tmin or tmax:
        print(f"trade_calendar 覆盖: {tmin or '—'} ~ {tmax or '—'}")
    print(f"表内 distinct code 总数: {rg.get('distinct_codes_in_table')}")
    print(f"本抽样本数: {rg.get('codes_sampled')}")
    print(f"其中 ≥2 根 K 的标的数: {rg.get('codes_with_at_least_two_bars')}")
    mx = rg.get("max_interior_gap_calendar_days_in_sample")
    print(f"样本内最大公历缺口（间隔−1）: {mx if mx is not None else '—'}")
    print(f"样本内最差 code（公历）: {rg.get('worst_code_in_sample') or '—'}")
    mxt = rg.get("max_missing_trading_sessions_in_sample")
    print(f"样本内最大「中间缺失交易日」根数: {mxt if mxt is not None else '—'}")
    print(f"样本内最差 code（交易日）: {rg.get('worst_code_trading_gap_in_sample') or '—'}")
    tops = rg.get("top_by_max_gap") or []
    if tops:
        print("按公历缺口降序（--gap-top-k）:")
        for row in tops:
            td = row.get("max_missing_trading_sessions_between_klines")
            print(
                f"  {row['code']}: calendar_gap={row['max_interior_gap_calendar_days']}  "
                f"missing_td={td if td is not None else '—'}  bars={row['bar_count']}"
            )
    tops_td = rg.get("top_by_missing_trading_sessions") or []
    if tops_td:
        print("按缺失交易日根数降序:")
        for row in tops_td:
            print(
                f"  {row['code']}: missing_td={row['max_missing_trading_sessions_between_klines']}  "
                f"bars={row['bar_count']}"
            )
    print(rg.get("note", ""))


def _print_trade_calendar_table_section(tc: dict) -> None:
    print()
    print("--- trade_calendar 全表摘要 ---")
    print(f"表 {tc.get('table', 'trade_calendar')}: 总行数 {tc.get('total_row_count', 0)}")
    print(f"distinct exchange 数: {tc.get('distinct_exchange_count', 0)}")
    for row in tc.get("by_exchange") or []:
        print(f"  {row.get('exchange', '?')}: {row.get('row_count', 0)} 行")


async def _main(
    as_json: bool,
    kline_only: bool,
    strict: bool,
    gap_sample: int,
    gap_seed_offset: int,
    gap_top_k: int,
    gap_exchange: str,
    gap_calendar_grace_days: int,
) -> int:
    from src.data.quality.daily_kline import daily_kline_quality_report
    from src.data.quality.kline_calendar_gaps import calendar_gap_sample_report
    from src.data.quality.stock_info import stock_info_quality_report
    from src.data.quality.trade_calendar_gate import evaluate_trade_calendar_gate
    from src.data.quality.trade_calendar_table import trade_calendar_table_summary
    from src.data.storage import dispose_database, get_database

    db = get_database()
    try:
        async with db.session() as session:
            report_k = await daily_kline_quality_report(session)
            report_s = None if kline_only else await stock_info_quality_report(session)
            report_g = await calendar_gap_sample_report(
                session,
                sample_size=gap_sample,
                seed_offset=gap_seed_offset,
                top_k=gap_top_k,
                gap_exchange=gap_exchange,
            )
            report_tc = await trade_calendar_table_summary(session)
    finally:
        await dispose_database()

    gate_ok, gate_messages = evaluate_trade_calendar_gate(
        report_k,
        report_g,
        grace_days=gap_calendar_grace_days,
    )

    if as_json:
        out: dict = {
            "daily_kline": report_k,
            "calendar_gap_sample": report_g,
            "trade_calendar": report_tc,
            "trade_calendar_gate": {
                "ok": gate_ok,
                "messages": gate_messages,
                "grace_days": gap_calendar_grace_days,
            },
        }
        if report_s is not None:
            out["stock_info"] = report_s
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        rk = report_k
        print(f"表 {rk['table']}: 行数 {rk['row_count']}")
        print(f"distinct code 数: {rk.get('distinct_codes', 0)}")
        print(f"trade_date 范围: {rk['trade_date_min']} ~ {rk['trade_date_max']}")
        rmax = rk.get("rows_on_max_trade_date")
        if rmax is not None:
            print(f"最新交易日行数: {rmax}")
        print(f"仅 1 根日 K 的标的数: {rk.get('codes_with_single_bar', 0)}")
        print(f"无 stock_info 匹配的日 K 行数: {rk.get('orphan_kline_rows', 0)}")
        print(f"非法 OHLC 行数: {rk.get('invalid_ohlc_rows', 0)}")
        print(f"负成交量行数: {rk.get('negative_volume_rows', 0)}")
        print(f"stock_info 行数: {rk.get('stock_info_row_count', 0)}")
        print(f"stock_info 中尚无日 K 的标的数: {rk.get('stock_info_codes_without_kline', 0)}")
        print(f"重复 (code, trade_date) 组数: {rk['duplicate_code_date_groups']}")
        if rk["duplicate_examples"]:
            print("示例（最多 20 条）:")
            for ex in rk["duplicate_examples"]:
                print(f"  {ex}")
        print(rk["note"])
        if report_s is not None:
            rs = report_s
            print()
            print(f"表 {rs['table']}: 行数 {rs['row_count']}")
            print(f"name 为空的行数: {rs.get('empty_name_rows', 0)}")
            print(f"交易中但缺 list_date 行数: {rs.get('is_trading_rows_missing_list_date', 0)}")
            print(rs["note"])
        _print_gap_section(report_g)
        _print_trade_calendar_table_section(report_tc)
        if not gate_ok:
            print()
            print("--- trade_calendar 门控（B+D）失败 ---")
            for m in gate_messages:
                print(f"  {m}")

    stock = None if kline_only else report_s
    return _exit_code(report_k, stock, strict=strict, calendar_gate_ok=gate_ok)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument(
        "--json",
        action="store_true",
        help="输出 JSON（含 stock_info、trade_calendar 全表行数摘要、trade_calendar_gate 等）",
    )
    p.add_argument(
        "--kline-only",
        action="store_true",
        help="仅检查 daily_kline（不跑 stock_info 节）",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="存在 orphan 日 K、空名称或 stock 无 K 线时以退出码 1 失败",
    )
    p.add_argument(
        "--gap-sample",
        type=int,
        default=0,
        metavar="N",
        help="按 code 排序抽样 N 只，统计相邻 trade_date 公历缺口（0=关闭）",
    )
    p.add_argument(
        "--gap-seed-offset",
        type=int,
        default=0,
        help="在 distinct code 有序列表上的起始偏移（换一批抽样）",
    )
    p.add_argument(
        "--gap-top-k",
        type=int,
        default=10,
        help="打印缺口最大的前 K 个标的（JSON 同字段 top_by_max_gap）",
    )
    p.add_argument(
        "--gap-exchange",
        default="cn",
        metavar="ID",
        help="trade_calendar.exchange；none/off 关闭交易日缺口与 B+D 门控，仅保留公历缺口",
    )
    p.add_argument(
        "--gap-calendar-grace-days",
        type=int,
        default=7,
        metavar="N",
        help="B+D 门控：date_max 须 ≥ min(日K trade_date_max,今天) 减 N 自然日（默认 7）",
    )
    args = p.parse_args()
    raise SystemExit(
        asyncio.run(
            _main(
                args.json,
                args.kline_only,
                args.strict,
                args.gap_sample,
                args.gap_seed_offset,
                args.gap_top_k,
                args.gap_exchange,
                args.gap_calendar_grace_days,
            )
        )
    )
