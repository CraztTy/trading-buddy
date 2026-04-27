"""
市场环境判断工具 — 第1层：大盘环境过滤。

提供基于大盘指数K线的趋势判断，用于选股与回测时控制整体仓位风险。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from src.data.models import KLine


@dataclass(frozen=True)
class MarketConditionResult:
    """大盘环境判断结果。"""

    passed: bool
    rules: list[str]
    market_index_code: str
    ma20: float | None = None
    ma60: float | None = None
    current_close: float | None = None

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "rules": self.rules,
            "market_index_code": self.market_index_code,
            "ma20": round(self.ma20, 4) if self.ma20 is not None else None,
            "ma60": round(self.ma60, 4) if self.ma60 is not None else None,
            "current_close": round(self.current_close, 4) if self.current_close is not None else None,
        }


def evaluate_market_condition(
    klines: list[KLine],
    *,
    market_index_code: str = "sh.000001",
    strict: bool = False,
    current_idx: int | None = None,
) -> MarketConditionResult:
    """
    基于大盘指数K线判断市场环境。

    Args:
        klines: 大盘指数日K线列表（时间升序）
        market_index_code: 指数代码
        strict: 严格模式（额外要求20日均线斜率向上）
        current_idx: 判断的日期索引，None 表示最后一天

    Returns:
        MarketConditionResult
    """
    if not klines:
        return MarketConditionResult(
            passed=False, rules=["无大盘数据"], market_index_code=market_index_code
        )

    df = pd.DataFrame(
        {
            "trade_date": [k.trade_date for k in klines],
            "close": [float(k.close) for k in klines],
            "open": [float(k.open) for k in klines],
            "high": [float(k.high) for k in klines],
            "low": [float(k.low) for k in klines],
        }
    )
    df = df.sort_values("trade_date").reset_index(drop=True)
    n = len(df)
    if n < 60:
        return MarketConditionResult(
            passed=False, rules=["大盘K线不足60根"], market_index_code=market_index_code
        )

    end = n - 1 if current_idx is None else current_idx
    if end < 0 or end >= n:
        return MarketConditionResult(
            passed=False, rules=["无效索引"], market_index_code=market_index_code
        )

    close = df["close"].astype(float)
    ma20 = close.rolling(20, min_periods=20).mean()
    ma60 = close.rolling(60, min_periods=60).mean()

    rules: list[str] = []
    current_close = float(close.iloc[end])
    ma20_val = float(ma20.iloc[end]) if pd.notna(ma20.iloc[end]) else None
    ma60_val = float(ma60.iloc[end]) if pd.notna(ma60.iloc[end]) else None

    if ma20_val is None or ma60_val is None:
        return MarketConditionResult(
            passed=False,
            rules=["均线未计算完成"],
            market_index_code=market_index_code,
            ma20=ma20_val,
            ma60=ma60_val,
            current_close=current_close,
        )

    # 核心判断：收盘价 > MA20 > MA60（多头排列）
    if current_close <= ma20_val:
        rules.append(f"大盘跌破20日线({ma20_val:.2f})")
        return MarketConditionResult(
            passed=False,
            rules=rules,
            market_index_code=market_index_code,
            ma20=ma20_val,
            ma60=ma60_val,
            current_close=current_close,
        )

    if current_close <= ma60_val:
        rules.append(f"大盘跌破60日线({ma60_val:.2f})")
        return MarketConditionResult(
            passed=False,
            rules=rules,
            market_index_code=market_index_code,
            ma20=ma20_val,
            ma60=ma60_val,
            current_close=current_close,
        )

    if ma20_val <= ma60_val:
        rules.append(f"20日线({ma20_val:.2f})未上穿60日线({ma60_val:.2f})")
        return MarketConditionResult(
            passed=False,
            rules=rules,
            market_index_code=market_index_code,
            ma20=ma20_val,
            ma60=ma60_val,
            current_close=current_close,
        )

    rules.append(f"大盘多头:close={current_close:.2f}>MA20={ma20_val:.2f}>MA60={ma60_val:.2f}")

    # 严格模式：20日均线斜率向上（最近5日）
    if strict and end >= 5:
        ma20_prev = float(ma20.iloc[end - 5])
        if ma20_val <= ma20_prev:
            rules.append(f"MA20斜率向下({ma20_prev:.2f}->{ma20_val:.2f})")
            return MarketConditionResult(
                passed=False,
                rules=rules,
                market_index_code=market_index_code,
                ma20=ma20_val,
                ma60=ma60_val,
                current_close=current_close,
            )
        rules.append("MA20斜率向上")

    return MarketConditionResult(
        passed=True,
        rules=rules,
        market_index_code=market_index_code,
        ma20=ma20_val,
        ma60=ma60_val,
        current_close=current_close,
    )
