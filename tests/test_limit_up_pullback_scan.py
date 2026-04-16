"""涨停回调选股引擎单元测试。"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np

from src.data.models import KLine, Market, StockInfo, StockType
from src.strategies.limit_up_pullback_scan import (
    LimitUpPullbackScanParams,
    evaluate_stock,
)


def _make_klines(
    code: str,
    start_date: date,
    n_bars: int,
    base_price: float = 10.0,
) -> list[KLine]:
    """生成一条从 base_price 缓慢震荡上升的序列，最后构造涨停+回调。"""
    klines: list[KLine] = []
    prices = []
    volumes = []

    # 前段：缓慢上升
    for i in range(n_bars - 50):
        p = base_price * (0.85 + 0.15 * (i / max(1, n_bars - 50)))
        prices.append(p)
        volumes.append(1000)

    # 中段：底部横盘（约40根）
    for i in range(40):
        p = base_price + np.sin(i * 0.3) * 0.15
        prices.append(p)
        volumes.append(1000)

    # 涨停日
    prices.append(base_price * 1.10)
    volumes.append(2000)

    # 后段：缩量回调（约10根），保持在 1.08 倍 base_price 附近（激进买点 1.10±2%）
    for i in range(10):
        p = base_price * (1.08 + 0.005 * (i / 9.0))
        prices.append(p)
        volumes.append(800)

    # 确保总长度正确
    prices = prices[-n_bars:]
    volumes = volumes[-n_bars:]

    for i, (p, v) in enumerate(zip(prices, volumes)):
        d = start_date + timedelta(days=i)
        pre = prices[i - 1] if i > 0 else p * 0.99
        klines.append(
            KLine(
                code=code,
                trade_date=d,
                open=pre,
                high=p + 0.05,
                low=p - 0.05,
                close=p,
                pre_close=pre,
                volume=v,
                amount=p * v,
                pct_change=((p / pre) - 1.0) * 100.0 if pre > 0 else None,
            )
        )
    return klines


def _stock_info(code: str, market_cap: float | None = 100_000_000_000.0) -> StockInfo:
    # 默认 1000 亿；但策略默认上限是 500 亿，测试命中时请传 100_000_000_000 或更小
    return StockInfo(
        code=code,
        name="测试股",
        stock_type=StockType.COMMON,
        market=Market.SH,
        market_cap=market_cap,
        is_trading=True,
    )


def test_evaluate_stock_matches() -> None:
    base = date(2025, 1, 1)
    klines = _make_klines("sh.match", base, 120, base_price=10.0)
    as_of = klines[-1].trade_date
    info = _stock_info("sh.match", market_cap=10_000_000_000.0)
    params = LimitUpPullbackScanParams(
        as_of_date=as_of,
        buy_point_types=("aggressive",),
    )
    result = evaluate_stock(klines, info, params)
    assert result is not None
    assert result.code == "sh.match"
    assert result.buy_point_type == "aggressive"
    # 激进型买点价为涨停日收盘价
    assert abs(result.buy_point_price - 11.0) < 0.01
    # 止损价为涨停日最低价
    assert result.stop_loss_price == result.limit_up_low
    # 匹配规则应包含关键条目
    rules_text = " ".join(result.matched_rules)
    assert "涨停日" in rules_text
    assert "缩量合格" in rules_text
    assert "买点:aggressive" in rules_text


def test_evaluate_stock_excludes_st() -> None:
    base = date(2025, 1, 1)
    klines = _make_klines("sh.stok", base, 120, base_price=10.0)
    as_of = klines[-1].trade_date
    info = _stock_info("sh.stok")
    info.stock_type = StockType.ST
    params = LimitUpPullbackScanParams(
        as_of_date=as_of,
        exclude_st=True,
    )
    result = evaluate_stock(klines, info, params)
    assert result is None


def test_evaluate_stock_market_cap_out_of_range() -> None:
    base = date(2025, 1, 1)
    klines = _make_klines("sh.cap", base, 120, base_price=10.0)
    as_of = klines[-1].trade_date
    info = _stock_info("sh.cap", market_cap=1_000_000_000.0)  # 10亿，低于下限
    params = LimitUpPullbackScanParams(
        as_of_date=as_of,
        min_market_cap=5_000_000_000.0,
        max_market_cap=50_000_000_000.0,
    )
    result = evaluate_stock(klines, info, params)
    assert result is None


def test_evaluate_stock_wrong_buy_point() -> None:
    base = date(2025, 1, 1)
    klines = _make_klines("sh.bp", base, 120, base_price=10.0)
    # 把最后一日收盘价改得很高，使其不落在任何买点区间
    klines[-1].close = 15.0
    klines[-1].high = 15.1
    klines[-1].low = 14.9
    as_of = klines[-1].trade_date
    info = _stock_info("sh.bp")
    params = LimitUpPullbackScanParams(
        as_of_date=as_of,
        buy_point_types=("neutral", "aggressive", "conservative"),
    )
    result = evaluate_stock(klines, info, params)
    assert result is None
