"""
涨停回调选股引擎 — 五层过滤（文档 v2.0）。

当前实现范围：
- 第3层：个股基础筛选（市值、ST、涨停基因）
- 第4层：技术形态（涨停时间、历史波动、底部横盘、突破量能、调整模式、均线状态、趋势支撑）
- 第5层：买点定位（激进/中性/保守）
- 第1、2层（大盘/板块/政策）由调用方通过可选参数控制。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from src.data.models import KLine, StockInfo, StockType
from src.data.storage import KlineRepository, PolicyRepository, SectorRepository, StockRepository
from src.strategies.limit_up_utils import find_limit_up_days, is_limit_up


@dataclass(frozen=True)
class LimitUpPullbackScanParams:
    """选股参数；数值均与文档 v2.0 对齐。"""

    as_of_date: date
    # 第3层
    min_market_cap: float | None = 5_000_000_000.0  # 50亿（元）
    max_market_cap: float | None = 50_000_000_000.0  # 500亿（元）
    exclude_st: bool = True
    min_limit_up_3m: int = 1
    max_limit_up_3m: int = 3
    # 第4层
    limit_up_lookback_min: int = 5
    limit_up_lookback_max: int = 10
    pre_1m_volatility_max: float = 0.25
    pre_2m_volatility_max: float = 0.35
    bottom_consolidation_months: float = 2.0
    bottom_consolidation_range_max: float = 0.20
    breakout_volume_ratio_min: float = 2.0
    adjustment_days_min: int = 5
    adjustment_volume_ratio_max: float = 0.50
    adjustment_amplitude_max: float = 0.05
    ma_strict: bool = False
    # 第5层
    buy_point_types: tuple[str, ...] = ("neutral",)
    # 板块/政策
    sector_codes: list[str] | None = field(default=None)
    require_policy: bool = False
    policy_lookback_days: int = 14


@dataclass(frozen=True)
class LimitUpPullbackMatch:
    code: str
    name: str
    buy_point_type: str
    buy_point_price: float
    stop_loss_price: float
    limit_up_date: date
    limit_up_close: float
    limit_up_open: float
    limit_up_low: float
    current_close: float
    matched_rules: list[str]
    note: str

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "buy_point_type": self.buy_point_type,
            "buy_point_price": round(self.buy_point_price, 4),
            "stop_loss_price": round(self.stop_loss_price, 4),
            "limit_up_date": self.limit_up_date.isoformat(),
            "limit_up_close": round(self.limit_up_close, 4),
            "limit_up_open": round(self.limit_up_open, 4),
            "limit_up_low": round(self.limit_up_low, 4),
            "current_close": round(self.current_close, 4),
            "matched_rules": self.matched_rules,
            "note": self.note,
        }


def _to_df(klines: list[KLine]) -> pd.DataFrame:
    """将 KLine 列表转为升序 DataFrame。"""
    if not klines:
        return pd.DataFrame()
    df = pd.DataFrame(
        {
            "trade_date": [k.trade_date for k in klines],
            "open": [float(k.open) for k in klines],
            "high": [float(k.high) for k in klines],
            "low": [float(k.low) for k in klines],
            "close": [float(k.close) for k in klines],
            "pre_close": [float(k.pre_close) if k.pre_close is not None else np.nan for k in klines],
            "volume": [int(k.volume or 0) for k in klines],
            "amount": [float(k.amount or 0.0) for k in klines],
        }
    )
    df = df.sort_values("trade_date").reset_index(drop=True)
    return df


def _find_recent_limit_up(df: pd.DataFrame, stock_type: StockType, lookback_min: int, lookback_max: int) -> int | None:
    """
    从 DataFrame 末尾往前，找到落在 [lookback_min, lookback_max] 交易日范围内的涨停日索引。
    返回最近的一个涨停日索引；若无则返回 None。
    """
    n = len(df)
    if n < lookback_max + 1:
        return None
    # 只检查最后 lookback_max 根（不含当前日；n-1 为当前日，n-2 距离为1）
    limit_ups = []
    for i in range(n - lookback_max - 1, n):
        if i < 0:
            continue
        k = KLine(
            code="",
            trade_date=df.at[i, "trade_date"],
            open=df.at[i, "open"],
            high=df.at[i, "high"],
            low=df.at[i, "low"],
            close=df.at[i, "close"],
            pre_close=df.at[i, "pre_close"] if pd.notna(df.at[i, "pre_close"]) else None,
            volume=df.at[i, "volume"],
            amount=0.0,
            pct_change=None,
        )
        if is_limit_up(k, stock_type):
            distance = n - 1 - i
            if lookback_min <= distance <= lookback_max:
                limit_ups.append(i)
    if not limit_ups:
        return None
    return limit_ups[-1]  # 最近的一个


def _count_limit_up_in_range(df: pd.DataFrame, stock_type: StockType, start_idx: int, end_idx: int) -> int:
    """统计闭区间 [start_idx, end_idx] 内的涨停次数。"""
    cnt = 0
    for i in range(max(0, start_idx), min(len(df), end_idx + 1)):
        k = KLine(
            code="",
            trade_date=df.at[i, "trade_date"],
            open=df.at[i, "open"],
            high=df.at[i, "high"],
            low=df.at[i, "low"],
            close=df.at[i, "close"],
            pre_close=df.at[i, "pre_close"] if pd.notna(df.at[i, "pre_close"]) else None,
            volume=df.at[i, "volume"],
            amount=0.0,
            pct_change=None,
        )
        if is_limit_up(k, stock_type):
            cnt += 1
    return cnt


def _max_consecutive_limit_ups(df: pd.DataFrame, stock_type: StockType, start_idx: int, end_idx: int) -> int:
    """统计闭区间内的最大连续涨停天数。"""
    max_streak = 0
    streak = 0
    for i in range(max(0, start_idx), min(len(df), end_idx + 1)):
        k = KLine(
            code="",
            trade_date=df.at[i, "trade_date"],
            open=df.at[i, "open"],
            high=df.at[i, "high"],
            low=df.at[i, "low"],
            close=df.at[i, "close"],
            pre_close=df.at[i, "pre_close"] if pd.notna(df.at[i, "pre_close"]) else None,
            volume=df.at[i, "volume"],
            amount=0.0,
            pct_change=None,
        )
        if is_limit_up(k, stock_type):
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    return max_streak


def _has_consecutive_big_drops(df: pd.DataFrame, start_idx: int, end_idx: int, drop_pct: float = -5.0) -> bool:
    """是否存在连续2天跌幅均超过 |drop_pct|。"""
    consec = 0
    for i in range(max(1, start_idx), min(len(df), end_idx + 1)):
        pct = (df.at[i, "close"] / df.at[i - 1, "close"] - 1.0) * 100.0
        if pct <= drop_pct:
            consec += 1
            if consec >= 2:
                return True
        else:
            consec = 0
    return False


def _check_buy_point(
    current_close: float,
    limit_up_open: float,
    limit_up_close: float,
    limit_up_low: float,
    buy_types: tuple[str, ...],
) -> tuple[str, float, float] | None:
    """
    检查买点定位。
    返回 (买点类型, 买点参考价, 止损价) 或 None。
    """
    # 激进型：涨停日收盘价 ±2%
    if "aggressive" in buy_types:
        dev = abs(current_close - limit_up_close) / limit_up_close
        if dev <= 0.02:
            stop = limit_up_low  # 跌破涨停日最低价
            return "aggressive", limit_up_close, stop
    # 中性型：涨停日阳线实体 1/2 处 ±2%
    if "neutral" in buy_types:
        mid = (limit_up_open + limit_up_close) / 2.0
        dev = abs(current_close - mid) / mid if mid > 0 else float("inf")
        if dev <= 0.02:
            stop = limit_up_open  # 跌破涨停日开盘价
            return "neutral", mid, stop
    # 保守型：涨停日开盘价 ±2%
    if "conservative" in buy_types:
        dev = abs(current_close - limit_up_open) / limit_up_open if limit_up_open > 0 else float("inf")
        if dev <= 0.02:
            # 止损位：涨停日前一日收盘价；若拿不到则用涨停日开盘价下方 2%
            stop = limit_up_open * 0.98
            return "conservative", limit_up_open, stop
    return None


def evaluate_stock(
    klines: list[KLine],
    stock_info: StockInfo,
    params: LimitUpPullbackScanParams,
) -> LimitUpPullbackMatch | None:
    """
    对单只股票执行五层过滤选股逻辑。
    返回匹配结果或 None（不符合条件）。
    """
    code = stock_info.code
    name = stock_info.name or code
    stock_type = stock_info.stock_type
    rules: list[str] = []

    df = _to_df(klines)
    if df.empty:
        print("DEBUG REJECT: df empty")
        return None

    # 确保 as_of_date 在数据中
    if df["trade_date"].iloc[-1] != params.as_of_date:
        mask = df["trade_date"] == params.as_of_date
        if not mask.any():
            print("DEBUG REJECT: as_of_date not found")
            return None
        idx = int(mask.idxmax())
        df = df.iloc[: idx + 1].reset_index(drop=True)

    n = len(df)
    if n < 80:
        print("DEBUG REJECT: n < 80")
        return None

    # ========== 第3层：个股基础筛选 ==========
    if params.exclude_st and stock_type == StockType.ST:
        print("DEBUG REJECT: ST")
        return None

    if params.min_market_cap is not None or params.max_market_cap is not None:
        cap = stock_info.market_cap
        if cap is not None:
            if params.min_market_cap is not None and cap < params.min_market_cap:
                print("DEBUG REJECT: cap too low")
                return None
            if params.max_market_cap is not None and cap > params.max_market_cap:
                print("DEBUG REJECT: cap too high")
                return None

    # 近3个月涨停次数（约60个交易日）
    start_3m = max(0, n - 60)
    limit_up_3m = _count_limit_up_in_range(df, stock_type, start_3m, n - 1)
    if not (params.min_limit_up_3m <= limit_up_3m <= params.max_limit_up_3m):
        print(f"DEBUG REJECT: limit_up_3m={limit_up_3m}")
        return None
    rules.append(f"近3月涨停{limit_up_3m}次")

    # ========== 第4层：技术形态 ==========
    # 4.1 近5~10交易日内有涨停
    lu_idx = _find_recent_limit_up(df, stock_type, params.limit_up_lookback_min, params.limit_up_lookback_max)
    if lu_idx is None:
        print("DEBUG REJECT: no recent limit up")
        return None
    limit_up_date = df.at[lu_idx, "trade_date"]
    limit_up_open = float(df.at[lu_idx, "open"])
    limit_up_close = float(df.at[lu_idx, "close"])
    limit_up_low = float(df.at[lu_idx, "low"])
    limit_up_volume = int(df.at[lu_idx, "volume"])
    rules.append(f"涨停日{limit_up_date}")

    # 4.2 历史稳定性（涨停前波动幅度）
    days_1m = max(0, lu_idx - 20)
    if lu_idx > days_1m:
        range_1m = df["high"].iloc[days_1m:lu_idx].max() / df["low"].iloc[days_1m:lu_idx].min() - 1.0
        if range_1m > params.pre_1m_volatility_max:
            print(f"DEBUG REJECT: range_1m={range_1m}")
            return None
    else:
        range_1m = 0.0

    days_2m = max(0, lu_idx - 40)
    if lu_idx > days_2m:
        range_2m = df["high"].iloc[days_2m:lu_idx].max() / df["low"].iloc[days_2m:lu_idx].min() - 1.0
        if range_2m > params.pre_2m_volatility_max:
            print(f"DEBUG REJECT: range_2m={range_2m}")
            return None
    else:
        range_2m = 0.0
    rules.append(f"涨停前波动1M={range_1m:.2%} 2M={range_2m:.2%}")

    # 4.3 底部形态（涨停前2个月横盘，无连板）
    consolidation_days = int(params.bottom_consolidation_months * 20)
    bottom_start = max(0, lu_idx - consolidation_days)
    if lu_idx > bottom_start:
        close_range = (
            df["close"].iloc[bottom_start:lu_idx].max() / df["close"].iloc[bottom_start:lu_idx].min() - 1.0
        )
        if close_range > params.bottom_consolidation_range_max:
            print(f"DEBUG REJECT: bottom_range={close_range}")
            return None
        max_consec = _max_consecutive_limit_ups(df, stock_type, bottom_start, lu_idx - 1)
        if max_consec >= 2:
            print(f"DEBUG REJECT: max_consec={max_consec}")
            return None
    rules.append("底部横盘合格")

    # 突破量能（倍量起涨）
    if lu_idx > 0:
        pre_volume = int(df.at[lu_idx - 1, "volume"])
        if pre_volume > 0 and limit_up_volume / pre_volume < params.breakout_volume_ratio_min:
            print(f"DEBUG REJECT: breakout ratio={limit_up_volume/pre_volume}")
            return None
        rules.append(f"倍量起涨{limit_up_volume/pre_volume:.1f}")
    else:
        print("DEBUG REJECT: lu_idx=0")
        return None

    # 4.4 调整模式（涨停后）
    adj_start = lu_idx + 1
    adj_end = n - 1
    adj_days = adj_end - adj_start + 1
    if adj_days < params.adjustment_days_min:
        print(f"DEBUG REJECT: adj_days={adj_days}")
        return None

    if adj_days > 0:
        adj_avg_vol = df["volume"].iloc[adj_start:adj_end + 1].mean()
        if limit_up_volume > 0 and adj_avg_vol / limit_up_volume > params.adjustment_volume_ratio_max:
            print(f"DEBUG REJECT: adj_vol_ratio={adj_avg_vol/limit_up_volume}")
            return None
        adj_amplitude = (
            (df["high"] - df["low"]) / df["low"]
        ).iloc[adj_start:adj_end + 1].mean()
        if adj_amplitude > params.adjustment_amplitude_max:
            print(f"DEBUG REJECT: adj_amplitude={adj_amplitude}")
            return None
        if _has_consecutive_big_drops(df, adj_start, adj_end, drop_pct=-5.0):
            print("DEBUG REJECT: consecutive big drops")
            return None
    rules.append(f"调整{adj_days}天 缩量合格")

    # 4.5 均线状态
    close = df["close"].astype(float)
    ma5 = close.rolling(5, min_periods=5).mean()
    ma10 = close.rolling(10, min_periods=10).mean()
    ma20 = close.rolling(20, min_periods=20).mean()
    ma60 = close.rolling(60, min_periods=60).mean()

    if params.ma_strict:
        ok = True
        for offset in range(1, 4):
            if n - offset < 0:
                ok = False
                break
            i = n - offset
            if not (ma5.iloc[i] > ma10.iloc[i] > ma20.iloc[i]):
                ok = False
                break
        if not ok:
            print("DEBUG REJECT: ma strict")
            return None
        rules.append("均线严格多头")
    else:
        ok = True
        for offset in range(1, 4):
            i = n - offset
            if i < 0 or close.iloc[i] <= ma10.iloc[i]:
                ok = False
                break
        if not ok:
            print("DEBUG REJECT: ma loose")
            return None
        rules.append("站稳10日线")

    # 4.6 趋势与K线形态（20/60日线支撑）
    current_close = float(close.iloc[-1])
    if current_close <= ma20.iloc[-1]:
        print("DEBUG REJECT: below ma20")
        return None
    if current_close <= ma60.iloc[-1]:
        print("DEBUG REJECT: below ma60")
        return None
    # 检查调整期间无高位放量大阴线（简化：无单日跌幅 > 7%）
    for i in range(adj_start, adj_end + 1):
        pct = (close.iloc[i] / close.iloc[i - 1] - 1.0) * 100.0
        if pct <= -7.0:
            print(f"DEBUG REJECT: big drop day {i} pct={pct}")
            return None
    rules.append("20/60日线支撑有效")

    # ========== 第5层：买点定位 ==========
    buy = _check_buy_point(current_close, limit_up_open, limit_up_close, limit_up_low, params.buy_point_types)
    if buy is None:
        print("DEBUG REJECT: no buy point")
        return None
    buy_type, buy_price, stop_loss = buy
    rules.append(f"买点:{buy_type}")

    # 前一日收盘价用于保守型止损（若可用）
    if buy_type == "conservative" and lu_idx > 0:
        pre_close_val = df.at[lu_idx, "pre_close"]
        if pd.notna(pre_close_val) and pre_close_val > 0:
            stop_loss = float(pre_close_val)

    return LimitUpPullbackMatch(
        code=code,
        name=name,
        buy_point_type=buy_type,
        buy_point_price=buy_price,
        stop_loss_price=stop_loss,
        limit_up_date=limit_up_date,
        limit_up_close=limit_up_close,
        limit_up_open=limit_up_open,
        limit_up_low=limit_up_low,
        current_close=current_close,
        matched_rules=rules,
        note="符合涨停回调选股策略 v2.0 技术条件",
    )


async def scan_stocks(
    session: AsyncSession,
    codes: list[str],
    params: LimitUpPullbackScanParams,
) -> list[LimitUpPullbackMatch]:
    """
    异步扫描多只股票，返回符合五层过滤条件的候选列表。
    """
    stock_repo = StockRepository(session)
    kline_repo = KlineRepository(session)
    sector_repo = SectorRepository(session)
    policy_repo = PolicyRepository(session)

    # 可选：板块/政策预过滤
    if params.sector_codes:
        sector_stocks = await sector_repo.get_stocks_by_sectors(params.sector_codes)
        sector_set = set(sector_stocks)
        codes = [c for c in codes if c in sector_set]
        if not codes:
            return []

    if params.require_policy and params.sector_codes:
        has_policy = await policy_repo.has_recent_events(
            params.sector_codes, days=params.policy_lookback_days, as_of_date=params.as_of_date
        )
        if not has_policy:
            return []

    # 批量拉取股票信息
    stock_infos: dict[str, StockInfo] = {}
    for c in codes:
        info = await stock_repo.get_by_code(c)
        if info:
            stock_infos[c] = info

    # 批量拉取 K 线（取最近 150 根，足够计算 2 个月历史 + 60 日均线）
    klines_map = await kline_repo.get_daily_last_n_bars_per_code(
        codes=list(stock_infos.keys()),
        end_date=params.as_of_date,
        max_bars=150,
        adjust_flag="3",
    )

    results: list[LimitUpPullbackMatch] = []
    for code, info in stock_infos.items():
        klines = klines_map.get(code)
        if not klines:
            continue
        match = evaluate_stock(klines, info, params)
        if match:
            results.append(match)

    return results
