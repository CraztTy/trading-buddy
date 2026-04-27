"""
涨停回调选股引擎 — 五层过滤（文档 v2.0）。

当前实现范围：
- 第3层：个股基础筛选（市值、ST、涨停基因）
- 第4层：技术形态（涨停时间、历史波动、底部横盘、突破量能、调整模式、均线状态、趋势支撑）
- 第5层：买点定位（激进/中性/保守）
- 第1、2层（大盘/板块/政策）由调用方通过可选参数控制。

公共过滤函数（``check_filters_at_idx``）同时供选股引擎与回测引擎复用，
确保两者对"符合策略条件"的定义完全一致。
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
from src.strategies.market_env import evaluate_market_condition


# ---------------------------------------------------------------------------
# 参数与结果类型
# ---------------------------------------------------------------------------

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
    # 第2层：板块/政策
    sector_codes: list[str] | None = field(default=None)
    require_policy: bool = False
    policy_lookback_days: int = 14
    # 第1层：大盘环境
    market_index_code: str | None = None  # 如 "sh.000001"
    require_market_bull: bool = False
    market_strict: bool = False


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


@dataclass(frozen=True)
class FilterResult:
    """选股过滤检查结果，供选股引擎与回测引擎共用。"""

    passed: bool
    matched_rules: list[str]
    limit_up_idx: int | None = None
    limit_up_date: date | None = None
    limit_up_open: float = 0.0
    limit_up_close: float = 0.0
    limit_up_low: float = 0.0
    limit_up_volume: int = 0
    buy_point_type: str = ""
    buy_point_price: float = 0.0
    stop_loss_price: float = 0.0


# ---------------------------------------------------------------------------
# DataFrame 转换
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 底层工具函数（供选股与回测共用）
# ---------------------------------------------------------------------------

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


def _find_recent_limit_up(
    df: pd.DataFrame, stock_type: StockType, lookback_min: int, lookback_max: int, current_idx: int | None = None
) -> int | None:
    """
    从 DataFrame 指定位置往前，找到落在 [lookback_min, lookback_max] 交易日范围内的涨停日索引。
    current_idx 为 None 时取最后一根。返回最近的一个涨停日索引；若无则返回 None。
    """
    n = len(df)
    if n < lookback_max + 1:
        return None
    end = n - 1 if current_idx is None else current_idx
    if end < lookback_max:
        return None

    limit_ups = []
    for i in range(end - lookback_max, end + 1):
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
            distance = end - i
            if lookback_min <= distance <= lookback_max:
                limit_ups.append(i)
    if not limit_ups:
        return None
    return limit_ups[-1]  # 最近的一个


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
            stop = limit_up_open * 0.98
            return "conservative", limit_up_open, stop
    return None


# ---------------------------------------------------------------------------
# 核心过滤函数（选股与回测共用）
# ---------------------------------------------------------------------------

def check_filters_at_idx(
    df: pd.DataFrame,
    stock_info: StockInfo | None,
    stock_type: StockType,
    params: LimitUpPullbackScanParams,
    current_idx: int | None = None,
) -> FilterResult:
    """
    在给定索引位置检查全部五层过滤条件。

    Args:
        df: 升序 DataFrame（须包含 open/high/low/close/pre_close/volume 列）
        stock_info: 股票信息（用于市值/ST筛选），为 None 时跳过市值检查
        stock_type: 股票类型（用于涨停阈值）
        params: 选股参数
        current_idx: 检查的日期索引，None 表示最后一天

    Returns:
        FilterResult 对象，passed=True 表示全部通过
    """
    n = len(df)
    if n < 80:
        return FilterResult(passed=False, matched_rules=[])

    end = n - 1 if current_idx is None else current_idx
    if end < 0 or end >= n:
        return FilterResult(passed=False, matched_rules=[])

    rules: list[str] = []

    # ========== 第3层：个股基础筛选 ==========
    if params.exclude_st and stock_type == StockType.ST:
        return FilterResult(passed=False, matched_rules=[])

    if stock_info is not None:
        if params.min_market_cap is not None or params.max_market_cap is not None:
            cap = stock_info.market_cap
            if cap is not None:
                if params.min_market_cap is not None and cap < params.min_market_cap:
                    return FilterResult(passed=False, matched_rules=[])
                if params.max_market_cap is not None and cap > params.max_market_cap:
                    return FilterResult(passed=False, matched_rules=[])

    # 近3个月涨停次数（约60个交易日）
    start_3m = max(0, end - 60)
    limit_up_3m = _count_limit_up_in_range(df, stock_type, start_3m, end)
    if not (params.min_limit_up_3m <= limit_up_3m <= params.max_limit_up_3m):
        return FilterResult(passed=False, matched_rules=[])
    rules.append(f"近3月涨停{limit_up_3m}次")

    # ========== 第4层：技术形态 ==========
    # 4.1 近5~10交易日内有涨停
    lu_idx = _find_recent_limit_up(df, stock_type, params.limit_up_lookback_min, params.limit_up_lookback_max, end)
    if lu_idx is None:
        return FilterResult(passed=False, matched_rules=[])
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
            return FilterResult(passed=False, matched_rules=[])
    else:
        range_1m = 0.0

    days_2m = max(0, lu_idx - 40)
    if lu_idx > days_2m:
        range_2m = df["high"].iloc[days_2m:lu_idx].max() / df["low"].iloc[days_2m:lu_idx].min() - 1.0
        if range_2m > params.pre_2m_volatility_max:
            return FilterResult(passed=False, matched_rules=[])
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
            return FilterResult(passed=False, matched_rules=[])
        max_consec = _max_consecutive_limit_ups(df, stock_type, bottom_start, lu_idx - 1)
        if max_consec >= 2:
            return FilterResult(passed=False, matched_rules=[])
    rules.append("底部横盘合格")

    # 突破量能（倍量起涨）
    if lu_idx > 0:
        pre_volume = int(df.at[lu_idx - 1, "volume"])
        if pre_volume > 0 and limit_up_volume / pre_volume < params.breakout_volume_ratio_min:
            return FilterResult(passed=False, matched_rules=[])
        rules.append(f"倍量起涨{limit_up_volume/pre_volume:.1f}")
    else:
        return FilterResult(passed=False, matched_rules=[])

    # 4.4 调整模式（涨停后）
    adj_start = lu_idx + 1
    adj_end = end
    adj_days = adj_end - adj_start + 1
    if adj_days < params.adjustment_days_min:
        return FilterResult(passed=False, matched_rules=[])

    if adj_days > 0:
        adj_avg_vol = df["volume"].iloc[adj_start:adj_end + 1].mean()
        if limit_up_volume > 0 and adj_avg_vol / limit_up_volume > params.adjustment_volume_ratio_max:
            return FilterResult(passed=False, matched_rules=[])
        adj_amplitude = (
            (df["high"] - df["low"]) / df["low"]
        ).iloc[adj_start:adj_end + 1].mean()
        if adj_amplitude > params.adjustment_amplitude_max:
            return FilterResult(passed=False, matched_rules=[])
        if _has_consecutive_big_drops(df, adj_start, adj_end, drop_pct=-5.0):
            return FilterResult(passed=False, matched_rules=[])
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
            if end - offset < 0:
                ok = False
                break
            i = end - offset
            if not (ma5.iloc[i] > ma10.iloc[i] > ma20.iloc[i]):
                ok = False
                break
        if not ok:
            return FilterResult(passed=False, matched_rules=[])
        rules.append("均线严格多头")
    else:
        ok = True
        for offset in range(1, 4):
            i = end - offset
            if i < 0 or close.iloc[i] <= ma10.iloc[i]:
                ok = False
                break
        if not ok:
            return FilterResult(passed=False, matched_rules=[])
        rules.append("站稳10日线")

    # 4.6 趋势与K线形态（20/60日线支撑 + 调整期无大阴线）
    current_close = float(close.iloc[end])
    if current_close <= ma20.iloc[end]:
        return FilterResult(passed=False, matched_rules=[])
    if current_close <= ma60.iloc[end]:
        return FilterResult(passed=False, matched_rules=[])
    for i in range(adj_start, adj_end + 1):
        if i < 1:
            continue
        pct = (close.iloc[i] / close.iloc[i - 1] - 1.0) * 100.0
        if pct <= -7.0:
            return FilterResult(passed=False, matched_rules=[])
    rules.append("20/60日线支撑有效")

    # ========== 第5层：买点定位 ==========
    buy = _check_buy_point(current_close, limit_up_open, limit_up_close, limit_up_low, params.buy_point_types)
    if buy is None:
        return FilterResult(passed=False, matched_rules=[])
    buy_type, buy_price, stop_loss = buy
    rules.append(f"买点:{buy_type}")

    # 保守型止损：优先使用涨停日前一日收盘价
    if buy_type == "conservative" and lu_idx > 0:
        pre_close_val = df.at[lu_idx, "pre_close"]
        if pd.notna(pre_close_val) and pre_close_val > 0:
            stop_loss = float(pre_close_val)

    return FilterResult(
        passed=True,
        matched_rules=rules,
        limit_up_idx=lu_idx,
        limit_up_date=limit_up_date,
        limit_up_open=limit_up_open,
        limit_up_close=limit_up_close,
        limit_up_low=limit_up_low,
        limit_up_volume=limit_up_volume,
        buy_point_type=buy_type,
        buy_point_price=buy_price,
        stop_loss_price=stop_loss,
    )


# ---------------------------------------------------------------------------
# 选股引擎（基于公共过滤函数）
# ---------------------------------------------------------------------------

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

    df = _to_df(klines)
    if df.empty:
        return None

    # 确保 as_of_date 在数据中
    if df["trade_date"].iloc[-1] != params.as_of_date:
        mask = df["trade_date"] == params.as_of_date
        if not mask.any():
            return None
        idx = int(mask.idxmax())
        df = df.iloc[: idx + 1].reset_index(drop=True)

    result = check_filters_at_idx(df, stock_info, stock_type, params)
    if not result.passed:
        return None

    return LimitUpPullbackMatch(
        code=code,
        name=name,
        buy_point_type=result.buy_point_type,
        buy_point_price=result.buy_point_price,
        stop_loss_price=result.stop_loss_price,
        limit_up_date=result.limit_up_date,
        limit_up_close=result.limit_up_close,
        limit_up_open=result.limit_up_open,
        limit_up_low=result.limit_up_low,
        current_close=float(df["close"].iloc[-1]),
        matched_rules=result.matched_rules,
        note="符合涨停回调选股策略 v2.0 技术条件",
    )


# ---------------------------------------------------------------------------
# 异步批量扫描
# ---------------------------------------------------------------------------

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

    # 可选：第1层 大盘环境预过滤
    market_ok = True
    market_rules: list[str] = []
    if params.require_market_bull and params.market_index_code:
        market_klines = await kline_repo.get_daily(
            code=params.market_index_code,
            end_date=params.as_of_date,
            limit=80,
            adjust_flag="3",
        )
        if market_klines:
            market_result = evaluate_market_condition(
                market_klines,
                market_index_code=params.market_index_code,
                strict=params.market_strict,
            )
            market_ok = market_result.passed
            market_rules = market_result.rules
        else:
            market_ok = False
            market_rules = ["大盘K线缺失"]
        if not market_ok:
            return []

    # 可选：第2层 板块/政策预过滤
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
            # 将大盘信息附加到 note
            if market_rules:
                match = LimitUpPullbackMatch(
                    code=match.code,
                    name=match.name,
                    buy_point_type=match.buy_point_type,
                    buy_point_price=match.buy_point_price,
                    stop_loss_price=match.stop_loss_price,
                    limit_up_date=match.limit_up_date,
                    limit_up_close=match.limit_up_close,
                    limit_up_open=match.limit_up_open,
                    limit_up_low=match.limit_up_low,
                    current_close=match.current_close,
                    matched_rules=match.matched_rules + market_rules,
                    note=match.note + "; " + "; ".join(market_rules),
                )
            results.append(match)

    return results
