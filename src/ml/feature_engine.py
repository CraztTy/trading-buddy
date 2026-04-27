"""自动特征生成引擎 — 从 OHLCV 时序自动衍生统计 / 滞后 / 差分特征。

设计目标：
- 输入：``pandas.DataFrame``，至少含 ``close`` 列；可含 ``open/high/low/volume/amount`` 等。
- 输出：包含原列 + 衍生特征列的 ``DataFrame``，列名可预测、可追溯。
- 与 ``src.factors.primitives`` 解耦：本模块面向「数据科学侧」研究流程，使用 pandas 高效批处理；
  ``primitives`` 面向「工程侧」纯函数原语供线上路径调用。两者算法等价但实现独立。

衍生策略（默认配置覆盖常见研究开关）:
- 滚动统计 ``rolling_*``：均值、标准差、最大、最小（``rolling_windows``）
- Z 分数 ``zscore_*``：滚动 Z 分数（``rolling_windows``）
- 差分 ``diff_*``：N 期差分（``diff_periods``）
- 滞后 ``lag_*``：N 期滞后（``lags``）
- 对数收益 ``log_return_*``：N 期对数收益（``log_return_periods``）

用法::

    engine = AutoFeatureEngine(
        rolling_windows=(5, 10, 20),
        lags=(1, 5),
        diff_periods=(1, 5),
        log_return_periods=(1, 5, 20),
        base_columns=("close", "volume"),
    )
    features = engine.fit_transform(df)

每个 ``base_column`` 会被衍生为多个特征列。``fit`` 仅记录列名（无状态参数），
``transform`` 是无副作用纯计算 — 因此可在训练 / 推理两侧重复调用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import numpy as np
import pandas as pd

from src.common import get_logger

logger = get_logger("auto_feature_engine")


@dataclass
class AutoFeatureEngine:
    """自动特征生成器（无状态 transformer，fit 仅记录列名）。"""

    rolling_windows: tuple[int, ...] = (5, 10, 20)
    lags: tuple[int, ...] = (1, 5)
    diff_periods: tuple[int, ...] = (1, 5)
    log_return_periods: tuple[int, ...] = (1, 5, 20)
    base_columns: tuple[str, ...] = ("close",)
    include_rolling_stats: tuple[str, ...] = ("mean", "std", "max", "min")
    include_zscore: bool = True
    drop_na: bool = False

    _feature_names: list[str] = field(default_factory=list, init=False, repr=False)
    _fitted: bool = field(default=False, init=False, repr=False)

    def fit(self, df: pd.DataFrame) -> "AutoFeatureEngine":
        """记录将要生成的列名。"""
        self._validate_input(df)
        # transform 一次以确定列名，但丢弃结果（fit 仅是契约）。
        out = self._compute_features(df)
        self._feature_names = [c for c in out.columns if c not in df.columns]
        self._fitted = True
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """生成特征矩阵（不要求先 fit；fit 只是 sklearn 风格契约）。"""
        self._validate_input(df)
        out = self._compute_features(df)
        if self.drop_na:
            out = out.dropna()
        return out

    def fit_transform(self, df: pd.DataFrame) -> pd.DataFrame:
        return self.fit(df).transform(df)

    @property
    def feature_names(self) -> list[str]:
        if not self._fitted:
            raise RuntimeError("AutoFeatureEngine.fit() must be called before reading feature_names")
        return list(self._feature_names)

    def _validate_input(self, df: pd.DataFrame) -> None:
        if not isinstance(df, pd.DataFrame):
            raise TypeError(f"Expected pandas DataFrame, got {type(df).__name__}")
        missing = [c for c in self.base_columns if c not in df.columns]
        if missing:
            raise ValueError(
                f"DataFrame missing required base_columns: {missing}; have {list(df.columns)}"
            )
        for w in self.rolling_windows:
            if w < 2:
                raise ValueError(f"rolling_windows entries must be >= 2, got {w}")
        for p in self.lags:
            if p < 1:
                raise ValueError(f"lags entries must be >= 1, got {p}")
        for p in self.diff_periods:
            if p < 1:
                raise ValueError(f"diff_periods entries must be >= 1, got {p}")
        for p in self.log_return_periods:
            if p < 1:
                raise ValueError(f"log_return_periods entries must be >= 1, got {p}")
        for stat in self.include_rolling_stats:
            if stat not in {"mean", "std", "max", "min", "median", "sum"}:
                raise ValueError(f"Unknown rolling stat: {stat!r}")

    def _compute_features(self, df: pd.DataFrame) -> pd.DataFrame:
        result = df.copy()
        for col in self.base_columns:
            series = df[col]
            self._add_rolling(result, series, col)
            if self.include_zscore:
                self._add_zscore(result, series, col)
            self._add_lags(result, series, col)
            self._add_diffs(result, series, col)
            self._add_log_returns(result, series, col)
        return result

    def _add_rolling(self, out: pd.DataFrame, series: pd.Series, col: str) -> None:
        for w in self.rolling_windows:
            roll = series.rolling(window=w, min_periods=w)
            for stat in self.include_rolling_stats:
                key = f"{col}_rolling_{stat}_{w}"
                if stat == "mean":
                    out[key] = roll.mean()
                elif stat == "std":
                    out[key] = roll.std(ddof=0)
                elif stat == "max":
                    out[key] = roll.max()
                elif stat == "min":
                    out[key] = roll.min()
                elif stat == "median":
                    out[key] = roll.median()
                elif stat == "sum":
                    out[key] = roll.sum()

    def _add_zscore(self, out: pd.DataFrame, series: pd.Series, col: str) -> None:
        for w in self.rolling_windows:
            roll = series.rolling(window=w, min_periods=w)
            mean = roll.mean()
            std = roll.std(ddof=0)
            out[f"{col}_zscore_{w}"] = (series - mean) / std.where(std != 0, np.nan)

    def _add_lags(self, out: pd.DataFrame, series: pd.Series, col: str) -> None:
        for p in self.lags:
            out[f"{col}_lag_{p}"] = series.shift(p)

    def _add_diffs(self, out: pd.DataFrame, series: pd.Series, col: str) -> None:
        for p in self.diff_periods:
            out[f"{col}_diff_{p}"] = series.diff(p)

    def _add_log_returns(self, out: pd.DataFrame, series: pd.Series, col: str) -> None:
        # log returns 仅对正值有意义 (close/volume > 0)
        positive = series.where(series > 0, np.nan)
        log_series = np.log(positive)
        for p in self.log_return_periods:
            out[f"{col}_log_return_{p}"] = log_series.diff(p)


def generate_features(
    df: pd.DataFrame,
    base_columns: Iterable[str] = ("close",),
    rolling_windows: Iterable[int] = (5, 10, 20),
    lags: Iterable[int] = (1, 5),
    diff_periods: Iterable[int] = (1, 5),
    log_return_periods: Iterable[int] = (1, 5, 20),
    include_zscore: bool = True,
    drop_na: bool = False,
) -> pd.DataFrame:
    """函数式包装 — 一次性生成默认特征矩阵。"""
    engine = AutoFeatureEngine(
        base_columns=tuple(base_columns),
        rolling_windows=tuple(rolling_windows),
        lags=tuple(lags),
        diff_periods=tuple(diff_periods),
        log_return_periods=tuple(log_return_periods),
        include_zscore=include_zscore,
        drop_na=drop_na,
    )
    return engine.fit_transform(df)
