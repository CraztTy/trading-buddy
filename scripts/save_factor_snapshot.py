#!/usr/bin/env python3
"""
因子截面每日落库 CLI — 从 daily_kline 计算全市场因子并写入 factor_snapshot 表。

用法：
    python scripts/save_factor_snapshot.py --date 2026-04-21 --limit 100
    python scripts/save_factor_snapshot.py --date latest --batch-size 200
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select

from src.data.storage.database import Database
from src.data.storage.factor_snapshot_repository import FactorSnapshotRepository
from src.data.storage.models import DailyKlineModel, StockInfoModel
from src.factors.primitives import (
    atr_wilder,
    bollinger_bands,
    ema,
    kdj_k_d_j,
    macd_dif_dea_hist,
    pct_change_n,
    rsi_wilder,
    rolling_mean,
)


def _parse_date(s: str) -> date:
    if s.lower() == "latest":
        return date.today()
    return date.fromisoformat(s)


async def _get_stock_codes(session, limit: int | None = None) -> list[str]:
    stmt = select(StockInfoModel.code).order_by(StockInfoModel.code)
    if limit:
        stmt = stmt.limit(limit)
    result = await session.execute(stmt)
    return [r[0] for r in result.all()]


async def _get_klines_for_code(session, code: str, end_date: date, max_bars: int = 70):
    stmt = (
        select(DailyKlineModel)
        .where(
            DailyKlineModel.code == code,
            DailyKlineModel.trade_date <= end_date,
            DailyKlineModel.adjust_flag == "3",
        )
        .order_by(DailyKlineModel.trade_date.desc())
        .limit(max_bars)
    )
    result = await session.execute(stmt)
    rows = list(result.scalars().all())
    # 转回时间升序
    rows.reverse()
    return rows


def _compute_factors(klines: list) -> dict | None:
    """从 K 线列表计算因子值，返回 dict 供 upsert。"""
    if len(klines) < 20:
        return None

    closes = [float(k.close) for k in klines]
    highs = [float(k.high) for k in klines]
    lows = [float(k.low) for k in klines]
    volumes = [float(k.volume) for k in klines]

    last = klines[-1]

    # 收益率
    ret_5d = None
    ret_20d = None
    ret_60d = None
    if len(closes) >= 6:
        ret_5d = round(pct_change_n(closes, 5)[-1], 6)
    if len(closes) >= 21:
        ret_20d = round(pct_change_n(closes, 20)[-1], 6)
    if len(closes) >= 61:
        ret_60d = round(pct_change_n(closes, 60)[-1], 6)

    # 均线
    ma_5 = None
    ma_20 = None
    ma_60 = None
    if len(closes) >= 5:
        ma_5 = round(rolling_mean(closes, 5)[-1], 4)
    if len(closes) >= 20:
        ma_20 = round(rolling_mean(closes, 20)[-1], 4)
    if len(closes) >= 60:
        ma_60 = round(rolling_mean(closes, 60)[-1], 4)

    # RSI
    rsi_14 = None
    if len(closes) >= 15:
        rsi_14 = round(rsi_wilder(closes, 14)[-1], 4)

    # MACD
    macd_dif = None
    macd_dea = None
    macd_hist = None
    if len(closes) >= 35:
        dif, dea, hist = macd_dif_dea_hist(closes, 12, 26, 9)
        macd_dif = round(dif[-1], 4)
        macd_dea = round(dea[-1], 4)
        macd_hist = round(hist[-1], 4)

    # KDJ
    kdj_k = None
    kdj_d = None
    kdj_j = None
    if len(closes) >= 9:
        k, d, j = kdj_k_d_j(highs, lows, closes, 9, 3, 3)
        kdj_k = round(k[-1], 4)
        kdj_d = round(d[-1], 4)
        kdj_j = round(j[-1], 4)

    # ATR
    atr_14 = None
    if len(closes) >= 15:
        tr = [highs[i] - lows[i] for i in range(len(closes))]
        atr = atr_wilder(tr, 14)
        atr_14 = round(atr[-1], 4)

    # Bollinger
    boll_upper = None
    boll_lower = None
    if len(closes) >= 20:
        upper, lower = bollinger_bands(closes, 20, 2)
        boll_upper = round(upper[-1], 4)
        boll_lower = round(lower[-1], 4)

    return {
        "close": float(last.close),
        "volume": float(last.volume),
        "amount": float(last.amount),
        "turnover_rate": last.turnover_rate,
        "pct_change": last.pct_change,
        "ret_5d": ret_5d,
        "ret_20d": ret_20d,
        "ret_60d": ret_60d,
        "ma_5": ma_5,
        "ma_20": ma_20,
        "ma_60": ma_60,
        "rsi_14": rsi_14,
        "macd_dif": macd_dif,
        "macd_dea": macd_dea,
        "macd_hist": macd_hist,
        "kdj_k": kdj_k,
        "kdj_d": kdj_d,
        "kdj_j": kdj_j,
        "atr_14": atr_14,
        "boll_upper": boll_upper,
        "boll_lower": boll_lower,
        "meta_bars": len(klines),
        "source": "compute_v1",
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="因子截面每日落库")
    parser.add_argument("--date", default="latest", help="截面日期 (YYYY-MM-DD 或 latest)")
    parser.add_argument("--limit", type=int, default=None, help="最多处理多少只股票")
    parser.add_argument("--batch-size", type=int, default=100, help="每批提交数量")
    parser.add_argument("--dry-run", action="store_true", help="只计算不写入")
    args = parser.parse_args()

    trade_date = _parse_date(args.date)
    db = Database()

    async with db.session() as session:
        codes = await _get_stock_codes(session, limit=args.limit)
        print(f"日期: {trade_date}, 标的数: {len(codes)}")

        repo = FactorSnapshotRepository(session)
        saved = 0
        skipped = 0
        errors = 0

        for i, code in enumerate(codes):
            try:
                klines = await _get_klines_for_code(session, code, trade_date, max_bars=70)
                factors = _compute_factors(klines)
                if factors is None:
                    skipped += 1
                    continue

                if not args.dry_run:
                    await repo.upsert(trade_date=trade_date, code=code, **factors)

                saved += 1
                if (i + 1) % args.batch_size == 0:
                    if not args.dry_run:
                        await session.commit()
                    print(f"  进度: {i + 1}/{len(codes)} (saved={saved}, skipped={skipped})")
            except Exception as e:
                errors += 1
                print(f"  错误 {code}: {e}")

        if not args.dry_run:
            await session.commit()

    print(f"完成: saved={saved}, skipped={skipped}, errors={errors}")
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
