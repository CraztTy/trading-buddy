#!/usr/bin/env python3
"""
Trading Buddy - 统一数据拉取入口
数据源由 .env 中 DATA_SOURCE 决定（baostock / mock / tushare），可用 --source 覆盖。
链路: 数据源 -> 仓储 -> 库表，供 API 与 dashboard 读取。
可选 --with-calendar（--mode daily 或 all，且数据源为 baostock）在流程末尾刷新 trade_calendar 尾部，便于质量脚本 B+D 门控。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path

project_root = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(project_root))

from src.common import describe_database_write_target, get_logger
from src.data.storage import (
    KlineRepository,
    StockRepository,
    dispose_database,
    get_database,
)
from src.data.sources import DataSourceFactory

logger = get_logger("fetcher")


@asynccontextmanager
async def _timed_phase(phase: str):
    """记录本阶段 wall-clock 耗时（秒，一位小数），供运维与定时任务日志分析。"""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        logger.info(f"[timing] {phase} {time.perf_counter() - t0:.1f}s")


async def _get_daily_kline_with_retries(
    source,
    code: str,
    start: date,
    end: date,
    *,
    retries: int,
    backoff_sec: float,
    adjustflag: str = "3",
):
    """对单次拉取做有限次重试（网络抖动 / 上游短暂错误）。"""
    get_fn = getattr(source, "get_daily_kline")
    for attempt in range(max(1, retries)):
        try:
            return await get_fn(code, start, end, adjustflag=adjustflag)
        except Exception as e:
            if attempt + 1 >= max(1, retries):
                logger.warning(f"{code} K线在 {retries} 次尝试后仍失败: {e}")
                raise
            delay = backoff_sec * (2**attempt)
            logger.info(f"{code} K线失败（{e!r}），{delay:.1f}s 后重试 {attempt + 2}/{retries}")
            await asyncio.sleep(delay)


INDICES = [
    ("sh.000001", "上证指数"),
    ("sz.399001", "深证成指"),
    ("sz.399006", "创业板指"),
    ("sh.000300", "沪深300"),
]


def _baostock_last_trading_day_sync() -> date:
    import baostock as bs

    rs_login = bs.login()
    if rs_login.error_code != "0":
        raise ConnectionError(f"baostock 登录失败: {rs_login.error_msg}")
    try:
        today = date.today()
        for i in range(1, 10):
            check = today - timedelta(days=i)
            d = check.strftime("%Y-%m-%d")
            rs = bs.query_trade_dates(start_date=d, end_date=d)
            while rs.next():
                row = rs.get_row_data()
                if row[1] == "1":
                    return check
        return today - timedelta(days=1)
    finally:
        bs.logout()


async def kline_end_date(provider: str) -> date:
    if provider == "baostock":
        return await asyncio.to_thread(_baostock_last_trading_day_sync)
    return date.today()


async def fetch_stock_list(provider: str) -> list[str]:
    logger.info(f"拉取股票列表，数据源: {provider}")
    source = DataSourceFactory.create_from_settings(provider)
    db = get_database()
    try:
        await source.connect()
        stocks = await source.get_stock_list()
        logger.info(f"共 {len(stocks)} 只股票")
        async with db.session() as session:
            repo = StockRepository(session)
            await repo.bulk_upsert(stocks)
        return [s.code for s in stocks]
    finally:
        await source.disconnect()


async def fetch_daily_klines(
    provider: str,
    codes: list[str] | None,
    days: int,
    limit: int,
    delay_sec: float,
    *,
    incremental: bool = False,
    overlap_days: int = 7,
    kline_retries: int = 3,
    kline_retry_backoff_sec: float = 0.5,
    adjust_flags: list[str] | None = None,
) -> None:
    end = await kline_end_date(provider)
    window_start = end - timedelta(days=days)
    flags = adjust_flags or ["3"]
    mode = "增量" if incremental else "全窗口"
    logger.info(
        f"拉取日K线 {provider} ({mode}): 结束日 {end}, 无历史时回退窗口 {days} 天, "
        f"复权档={flags}"
    )

    source = DataSourceFactory.create_from_settings(provider)
    db = get_database()
    try:
        await source.connect()
        async with db.session() as session:
            stock_repo = StockRepository(session)
            kline_repo = KlineRepository(session)
            if not codes:
                codes = await stock_repo.get_all_codes(is_trading=True)
            if not codes:
                logger.warning("无股票代码，请先执行 --mode stocks")
                return
            if limit > 0:
                codes = codes[:limit]
                logger.info(f"限制条数: 仅处理前 {limit} 只")

            last_map: dict[str, date] = {}
            if incremental:
                last_map = await kline_repo.get_latest_trade_dates_for_codes(codes)
                logger.info(
                    f"增量模式: 已缓存 {len(last_map)}/{len(codes)} 只的最新交易日，重叠 {overlap_days} 天"
                )

            overlap = timedelta(days=overlap_days)
            total = 0
            skipped = 0
            for i, code in enumerate(codes):
                if incremental:
                    last = last_map.get(code)
                    if last and last >= end:
                        skipped += 1
                        if (i + 1) % 500 == 0:
                            logger.info(
                                f"进度 {i + 1}/{len(codes)}，跳过已最新 {skipped}，累计写入 {total} 条"
                            )
                        continue

                try:
                    for flag in flags:
                        if provider == "baostock" and delay_sec > 0:
                            await asyncio.sleep(delay_sec)

                        if incremental:
                            start = (
                                last - overlap
                                if last
                                else window_start
                            )
                        else:
                            start = window_start

                        if start > end:
                            start = end - timedelta(days=1)

                        klines = await _get_daily_kline_with_retries(
                            source,
                            code,
                            start,
                            end,
                            retries=kline_retries,
                            backoff_sec=kline_retry_backoff_sec,
                            adjustflag=flag,
                        )
                        if klines:
                            await kline_repo.bulk_insert(klines)
                            total += len(klines)
                    if (i + 1) % 200 == 0 or i == len(codes) - 1:
                        logger.info(
                            f"进度 {i + 1}/{len(codes)}，跳过已最新 {skipped}，累计K线 {total} 条"
                        )
                except Exception as e:
                    logger.warning(f"{code} K线失败: {e}")
            logger.info(
                f"日K线完成，写入约 {total} 条（增量跳过已最新 {skipped} 只）"
            )
    finally:
        await source.disconnect()


async def fetch_index_data(
    provider: str,
    index_days: int,
    *,
    incremental: bool = False,
    overlap_days: int = 7,
    kline_retries: int = 3,
    kline_retry_backoff_sec: float = 0.5,
) -> None:
    end = await kline_end_date(provider)
    window_start = end - timedelta(days=index_days)
    mode = "增量" if incremental else "全窗口"
    logger.info(f"拉取指数K线 {provider} ({mode}): 结束日 {end}")

    source = DataSourceFactory.create_from_settings(provider)
    db = get_database()
    index_codes = [c for c, _ in INDICES]
    try:
        await source.connect()
        last_map: dict[str, date] = {}
        if incremental:
            async with db.session() as session:
                kline_repo = KlineRepository(session)
                last_map = await kline_repo.get_latest_trade_dates_for_codes(
                    index_codes
                )

        overlap = timedelta(days=overlap_days)
        for code, name in INDICES:
            try:
                if incremental:
                    last = last_map.get(code)
                    if last and last >= end:
                        logger.info(f"{name} ({code}): 已最新，跳过")
                        continue
                    start = last - overlap if last else window_start
                else:
                    start = window_start

                if start > end:
                    start = end - timedelta(days=1)

                get_idx = getattr(source, "get_index_data")
                klines = []
                for attempt in range(max(1, kline_retries)):
                    try:
                        klines = await get_idx(code, start, end)
                        break
                    except Exception as e:
                        if attempt + 1 >= max(1, kline_retries):
                            raise
                        delay = kline_retry_backoff_sec * (2**attempt)
                        logger.info(
                            f"{name} ({code}) 失败（{e!r}），{delay:.1f}s 后重试 {attempt + 2}/{kline_retries}"
                        )
                        await asyncio.sleep(delay)
                if not klines:
                    logger.warning(
                        f"{name} ({code}): 数据源未返回K线（日期 {start}~{end} 或网络/限流）"
                    )
                    continue
                # 每个指数单独提交，避免一条失败导致同会话内其它指数一并回滚
                async with db.session() as session:
                    kline_repo = KlineRepository(session)
                    await kline_repo.bulk_insert(klines)
                logger.info(f"{name} ({code}): {len(klines)} 条已写入")
            except Exception as e:
                logger.warning(f"{name} ({code}) 失败: {e}")
    finally:
        await source.disconnect()


async def maybe_refresh_trade_calendar_tail(
    args: argparse.Namespace,
    provider: str,
) -> None:
    """``--with-calendar``：用 Baostock 刷新 ``trade_calendar`` 最近一截（与 ``--calendar-exchange`` / ``--calendar-chunk-days`` 共用）。"""
    if not args.with_calendar:
        return
    if provider != "baostock":
        logger.warning("--with-calendar 需要 baostock 数据源，已跳过")
        return
    from src.data.ingest import ingest_trade_calendar_from_baostock

    end = await kline_end_date(provider)
    span = max(1, int(args.with_calendar_span_days))
    start = end - timedelta(days=span)
    ex = args.calendar_exchange.strip().lower()
    chunk = max(1, int(args.calendar_chunk_days))
    logger.info(
        f"--with-calendar: exchange={ex} {start} ~ {end}（向前 {span} 自然日），chunk={chunk} 天"
    )
    n = await ingest_trade_calendar_from_baostock(
        start=start,
        end=end,
        exchange=ex,
        chunk_days=chunk,
    )
    logger.info(f"trade_calendar 尾部刷新完成，约 {n} 行 upsert")


async def run(args: argparse.Namespace) -> None:
    provider = (args.source or "").strip().lower() if args.source else None
    if provider:
        if provider not in DataSourceFactory.available_sources():
            raise SystemExit(
                f"未知数据源: {provider}，可选: {DataSourceFactory.available_sources()}"
            )
    else:
        from src.common import get_settings

        provider = get_settings().data_source.provider.strip().lower()

    logger.info(f"数据写入目标: {describe_database_write_target()}")

    kr = max(1, int(args.kline_retries))
    kb = float(args.kline_retry_backoff)

    run_t0 = time.perf_counter()
    try:
        codes: list[str] | None = list(args.codes) if args.codes else None

        # --mode all/klines 未显式指定 --days 时，自动扩展为 20 年历史窗口
        effective_days = args.days
        if args.mode in ("all", "klines") and args.days == 30:
            effective_days = 7300
            logger.info(
                f"--mode {args.mode} 未显式指定 --days，自动使用 20 年历史窗口 ({effective_days} 天)"
            )

        if args.mode == "calendar":
            if provider != "baostock":
                raise SystemExit(
                    f"交易日历仅支持数据源 baostock（当前为 {provider!r}），"
                    "请设置 DATA_SOURCE=baostock 或使用 --source baostock"
                )
            from src.data.ingest import ingest_trade_calendar_from_baostock

            cal_end = (
                date.fromisoformat(args.calendar_end)
                if args.calendar_end
                else date.today()
            )
            cal_start = (
                date.fromisoformat(args.calendar_start)
                if args.calendar_start
                else cal_end - timedelta(days=max(1, int(args.calendar_span_days)))
            )
            if cal_start > cal_end:
                raise SystemExit("--calendar-start 不能晚于 --calendar-end / 默认结束日")
            ex = args.calendar_exchange.strip().lower()
            chunk = max(1, int(args.calendar_chunk_days))
            logger.info(
                f"灌交易日历 baostock exchange={ex} {cal_start} ~ {cal_end} chunk={chunk} 天"
            )
            async with _timed_phase("calendar_ingest"):
                n = await ingest_trade_calendar_from_baostock(
                    start=cal_start,
                    end=cal_end,
                    exchange=ex,
                    chunk_days=chunk,
                )
            logger.info(f"交易日历完成，累计 upsert 约 {n} 行")
        elif args.mode == "daily":
            # 收盘后日常：刷新股票表 + 增量指数 + 增量个股日K（全市场，适合定时任务）
            async with _timed_phase("stocks"):
                await fetch_stock_list(provider)
            async with _timed_phase("indices"):
                await fetch_index_data(
                    provider,
                    index_days=args.index_days,
                    incremental=True,
                    overlap_days=args.overlap_days,
                    kline_retries=kr,
                    kline_retry_backoff_sec=kb,
                )
            async with _timed_phase("daily_klines"):
                await fetch_daily_klines(
                    provider,
                    codes,
                    days=effective_days,
                    limit=args.limit,
                    delay_sec=args.baostock_delay,
                    incremental=True,
                    overlap_days=args.overlap_days,
                    kline_retries=kr,
                    kline_retry_backoff_sec=kb,
                    adjust_flags=list(args.adjust_flags),
                )
        else:
            if args.mode in ("all", "stocks"):
                async with _timed_phase("stocks"):
                    await fetch_stock_list(provider)

            if args.mode in ("all", "klines"):
                if args.mode == "klines" and not codes:
                    async with _timed_phase("stocks_before_klines"):
                        await fetch_stock_list(provider)
                async with _timed_phase("klines"):
                    await fetch_daily_klines(
                        provider,
                        codes,
                        days=effective_days,
                        limit=args.limit,
                        delay_sec=args.baostock_delay,
                        incremental=args.incremental,
                        overlap_days=args.overlap_days,
                        kline_retries=kr,
                        kline_retry_backoff_sec=kb,
                        adjust_flags=list(args.adjust_flags),
                    )

            # 指数写入 daily_kline：all / indices 会跑；单独 klines 时也要跑——
            # klines 用的代码来自 stock_info，而 baostock 股票列表里已主动剔除了指数代码，
            # 若不在这里补拉，看板「主要指数」会一直为空。
            should_fetch_indices = args.mode in ("all", "indices") or (
                args.mode == "klines" and codes is None
            )
            if should_fetch_indices:
                async with _timed_phase("indices"):
                    await fetch_index_data(
                        provider,
                        index_days=args.index_days,
                        incremental=args.incremental,
                        overlap_days=args.overlap_days,
                        kline_retries=kr,
                        kline_retry_backoff_sec=kb,
                    )

        if args.mode in ("daily", "all"):
            async with _timed_phase("calendar_tail_refresh"):
                await maybe_refresh_trade_calendar_tail(args, provider)

        logger.info("数据拉取流程结束")
    finally:
        logger.info(f"[timing] run_total {time.perf_counter() - run_t0:.1f}s")
        await dispose_database()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Trading Buddy 数据拉取（与 DATA_SOURCE / --source 一致）"
    )
    p.add_argument(
        "--source",
        choices=DataSourceFactory.available_sources(),
        default=None,
        help="覆盖 .env 中的 DATA_SOURCE",
    )
    p.add_argument(
        "--mode",
        choices=["all", "stocks", "klines", "indices", "daily", "calendar"],
        default="all",
        help="calendar=仅灌 trade_calendar（Baostock，见 --calendar-*）; daily=日常增量; klines 无 --codes 时会拉主要指数",
    )
    p.add_argument(
        "--incremental",
        action="store_true",
        help="日K/指数：按库中最新交易日增量拉取（重叠天数见 --overlap-days）",
    )
    p.add_argument(
        "--overlap-days",
        type=int,
        default=7,
        help="增量模式下向前多取若干自然日，覆盖长假与修正已入库尾部",
    )
    p.add_argument("--codes", nargs="+", help="仅拉指定代码（K线模式）")
    p.add_argument(
        "--days",
        type=int,
        default=30,
        help="日K向前天数（相对结束交易日）；--mode all 未显式指定时自动扩展为 7300（约20年）",
    )
    p.add_argument(
        "--index-days",
        type=int,
        default=730,
        help="指数K线向前天数（默认约两年）",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=0,
        help="K线模式下最多处理股票数量，0 表示不限制（测试用小一点）",
    )
    p.add_argument(
        "--baostock-delay",
        type=float,
        default=0.12,
        help="baostock 请求间隔秒数，降低限流风险",
    )
    p.add_argument(
        "--kline-retries",
        type=int,
        default=3,
        help="单标的日 K / 指数拉取抛错时的最大尝试次数（含首次），≥1",
    )
    p.add_argument(
        "--kline-retry-backoff",
        type=float,
        default=0.5,
        help="重试基础等待秒数（指数退避：0.5, 1, 2, …）",
    )
    p.add_argument(
        "--calendar-start",
        default=None,
        metavar="YYYY-MM-DD",
        help="--mode calendar 起始日；省略则按 --calendar-end 与 --calendar-span-days 回推",
    )
    p.add_argument(
        "--calendar-end",
        default=None,
        metavar="YYYY-MM-DD",
        help="--mode calendar 结束日，默认今天",
    )
    p.add_argument(
        "--calendar-span-days",
        type=int,
        default=730,
        help="未指定 --calendar-start 时，从结束日向前回推的自然日跨度（默认约两年）",
    )
    p.add_argument(
        "--calendar-exchange",
        default="cn",
        help="trade_calendar.exchange，默认 cn",
    )
    p.add_argument(
        "--calendar-chunk-days",
        type=int,
        default=400,
        help="单次 Baostock query_trade_dates 覆盖的自然日跨度（亦用于 --with-calendar）",
    )
    p.add_argument(
        "--with-calendar",
        action="store_true",
        help="在 --mode daily 或 all 结束后，用 Baostock 灌 trade_calendar 最近区间（仅 baostock；见 --with-calendar-span-days）",
    )
    p.add_argument(
        "--with-calendar-span-days",
        type=int,
        default=450,
        metavar="N",
        help="--with-calendar 时从最后交易日起向前覆盖的自然日跨度（默认 450）",
    )
    p.add_argument(
        "--adjust-flags",
        nargs="+",
        default=["3"],
        choices=["1", "2", "3"],
        help="拉取的复权类型，可多个（1=后复权 2=前复权 3=不复权）；默认 3",
    )
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
