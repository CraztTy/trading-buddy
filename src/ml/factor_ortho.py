"""因子正交化 — 去除因子间相关性，提高因子独立性。

常用方法:
- Gram-Schmidt 正交化
- 回归残差法（逐步正交化）
- PCA 降维

用法:
    from src.ml.factor_ortho import FactorOrthogonalizer
    ortho = FactorOrthogonalizer(method="regression")
    factors_ortho = ortho.fit_transform(factors_df, target_factor="momentum")
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.common import get_logger

logger = get_logger("factor_ortho")


class FactorOrthogonalizer:
    """因子正交化器。

    支持方法:
    - "regression": 回归残差法（推荐，保持目标因子暴露）
    - "gram_schmidt": Gram-Schmidt 正交化
    - "zscore": 仅标准化（不正交化）
    """

    def __init__(self, method: str = "regression"):
        """
        Args:
            method: "regression" | "gram_schmidt" | "zscore"
        """
        if method not in ("regression", "gram_schmidt", "zscore"):
            raise ValueError(f"Unknown method: {method}")
        self.method = method
        self._fitted = False
        self._params: dict = {}

    # ------------------------------------------------------------------
    # 回归残差法
    # ------------------------------------------------------------------

    def _fit_regression(
        self,
        factors: pd.DataFrame,
        target_factor: str | None = None,
    ) -> dict:
        """回归残差法：对目标因子，用其他因子回归取残差。

        保持目标因子的预测信息，去除与其他因子的共线性。
        """
        factor_cols = [c for c in factors.columns if c != "code"]
        if len(factor_cols) < 2:
            return {}

        # 如果没有指定目标因子，默认用第一个
        target = target_factor or factor_cols[0]
        others = [c for c in factor_cols if c != target]

        params = {
            "target": target,
            "others": others,
            "means": {},
            "stds": {},
            "betas": {},
        }

        # 标准化所有因子
        for col in factor_cols:
            params["means"][col] = float(factors[col].mean())
            params["stds"][col] = float(factors[col].std()) or 1.0

        # 计算回归系数（跨截面平均）
        beta_matrix = []
        for date_idx in factors.index.get_level_values(0).unique():
            day_data = factors.loc[date_idx]
            y = day_data[target].values
            X = day_data[others].values

            # 添加截距
            X_with_intercept = np.column_stack([np.ones(len(X)), X])

            try:
                beta = np.linalg.lstsq(X_with_intercept, y, rcond=None)[0]
                beta_matrix.append(beta)
            except Exception:
                continue

        if beta_matrix:
            params["betas"] = {
                "intercept": float(np.mean([b[0] for b in beta_matrix])),
            }
            for i, col in enumerate(others):
                params["betas"][col] = float(np.mean([b[i + 1] for b in beta_matrix]))

        return params

    def _transform_regression(
        self,
        factors: pd.DataFrame,
        params: dict,
    ) -> pd.DataFrame:
        """应用回归残差正交化。"""
        if not params:
            return factors

        result = factors.copy()
        target = params["target"]
        others = params["others"]
        betas = params["betas"]

        # 标准化
        for col in result.columns:
            if col in params["means"]:
                result[col] = (
                    result[col] - params["means"][col]
                ) / params["stds"][col]

        # 目标因子 = 残差（去除其他因子影响）
        intercept = betas.get("intercept", 0)
        residual = result[target] - intercept
        for col in others:
            residual -= result[col] * betas.get(col, 0)

        result[target] = residual
        return result

    # ------------------------------------------------------------------
    # Gram-Schmidt
    # ------------------------------------------------------------------

    def _fit_gram_schmidt(self, factors: pd.DataFrame) -> dict:
        """Gram-Schmidt 正交化参数。"""
        factor_cols = [c for c in factors.columns if c != "code"]
        return {"columns": factor_cols}

    def _transform_gram_schmidt(
        self,
        factors: pd.DataFrame,
        params: dict,
    ) -> pd.DataFrame:
        """Gram-Schmidt 正交化（逐截面）。"""
        cols = params["columns"]
        result = factors.copy()

        for date_idx in result.index.get_level_values(0).unique():
            day_data = result.loc[date_idx, cols].values.T  # (n_factors, n_stocks)

            # 逐因子正交化
            ortho = np.zeros_like(day_data)
            for i in range(len(cols)):
                v = day_data[i].copy()
                for j in range(i):
                    proj = np.dot(v, ortho[j]) / np.dot(ortho[j], ortho[j]) * ortho[j]
                    v -= proj
                ortho[i] = v

            for i, col in enumerate(cols):
                result.loc[date_idx, col] = ortho[i]

        return result

    # ------------------------------------------------------------------
    # Z-Score 标准化
    # ------------------------------------------------------------------

    @staticmethod
    def _fit_zscore(factors: pd.DataFrame) -> dict:
        params = {"means": {}, "stds": {}}
        for col in factors.columns:
            if col == "code":
                continue
            params["means"][col] = float(factors[col].mean())
            params["stds"][col] = float(factors[col].std()) or 1.0
        return params

    @staticmethod
    def _transform_zscore(
        factors: pd.DataFrame,
        params: dict,
    ) -> pd.DataFrame:
        result = factors.copy()
        for col in result.columns:
            if col == "code":
                continue
            if col in params["means"]:
                result[col] = (
                    result[col] - params["means"][col]
                ) / params["stds"][col]
        return result

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def fit(
        self,
        factors: pd.DataFrame,
        target_factor: str | None = None,
    ) -> "FactorOrthogonalizer":
        """拟合正交化参数。

        Args:
            factors: 因子值 DataFrame，index=(date, code)，columns=factor_names
            target_factor: 目标因子名（regression 方法需要）
        """
        if self.method == "regression":
            self._params = self._fit_regression(factors, target_factor)
        elif self.method == "gram_schmidt":
            self._params = self._fit_gram_schmidt(factors)
        elif self.method == "zscore":
            self._params = self._fit_zscore(factors)

        self._fitted = True
        return self

    def transform(self, factors: pd.DataFrame) -> pd.DataFrame:
        """应用正交化。"""
        if not self._fitted:
            raise RuntimeError("Must call fit() before transform()")

        if self.method == "regression":
            return self._transform_regression(factors, self._params)
        elif self.method == "gram_schmidt":
            return self._transform_gram_schmidt(factors, self._params)
        elif self.method == "zscore":
            return self._transform_zscore(factors, self._params)

        return factors

    def fit_transform(
        self,
        factors: pd.DataFrame,
        target_factor: str | None = None,
    ) -> pd.DataFrame:
        """拟合并转换。"""
        return self.fit(factors, target_factor).transform(factors)

    @staticmethod
    def correlation_matrix(factors: pd.DataFrame) -> pd.DataFrame:
        """计算因子相关系数矩阵。"""
        factor_cols = [c for c in factors.columns if c != "code"]
        return factors[factor_cols].corr()
