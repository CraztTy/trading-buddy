"""
涨停检测与相关工具函数
"""

from __future__ import annotations

from src.data.models import KLine, StockType


# 不同板块/类型的涨停阈值（%）
LIMIT_UP_PCT = {
    StockType.COMMON: 10.0,
    StockType.STAR: 20.0,
    StockType.GROWTH: 20.0,
    StockType.BEIJING: 30.0,
    StockType.ST: 5.0,
}


def get_limit_up_pct(stock_type: StockType) -> float:
    """获取指定股票类型的涨停阈值。"""
    return LIMIT_UP_PCT.get(stock_type, 10.0)


def is_limit_up(kline: KLine, stock_type: StockType) -> bool:
    """
    判断单日 K 线是否涨停。
    优先使用 pre_close 计算涨幅；若缺失则回退到 pct_change。
    """
    threshold = get_limit_up_pct(stock_type)
    if kline.pre_close is not None and kline.pre_close > 0:
        pct = (kline.close / kline.pre_close - 1.0) * 100.0
    elif kline.pct_change is not None:
        pct = kline.pct_change
    else:
        return False
    return pct >= threshold * 0.995  # 允许微小浮点误差（如 9.9% 视为 10%）


def find_limit_up_days(klines: list[KLine], stock_type: StockType) -> list[int]:
    """返回时间升序 K 线列表中，所有涨停日的索引。"""
    return [i for i, k in enumerate(klines) if is_limit_up(k, stock_type)]
