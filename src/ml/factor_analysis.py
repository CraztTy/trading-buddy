"""因子分析工具 — IC/IR、收益率分层、 turnover 分析。

因子有效性评估指标：
- IC (Information Coefficient): 因子值与未来收益率的秩相关系数
- IR (Information Ratio): IC 的均值 / IC 的标准差
- 分层收益率: 按因子值分 N 组，看各组未来收益率差异
- Turnover: 因子值的变化率（换手率）

用法:
    from src.ml.factor_analysis import FactorAnalyzer
    analyzer = FactorAnalyzer()

    # IC 分析
    ic_series = analyzer.information_coefficient(factor_df, returns_df)
    ic_mean, ic_ir = analyzer.ic_summary(ic_series)

    # 分层分析
    quintile_returns = analyzer.quantile_returns(factor_df, returns_df, n_quantiles=5)
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from src.common import get_logger

logger = get_logger("factor_analysis")


class FactorAnalyzer:
    """因子分析器 — 评估因子预测能力和稳定性。"""

    # ------------------------------------------------------------------
    # IC 分析
    # ------------------------------------------------------------------

    @staticmethod
    def information_coefficient(
        factor_values: pd.Series | pd.DataFrame,
        forward_returns: pd.Series | pd.DataFrame,
        method: str = "spearman",
    ) -> pd.Series:
        """计算逐期 IC（信息系数）。

        Args:
            factor_values: 因子值，index=(date, code) 或 date 为行、code 为列
            forward_returns: 未来收益率，同上格式
            method: "spearman"(秩相关,默认) 或 "pearson"

        Returns:
            每期 IC 值的 Series（index=date）
        """
        # 统一为宽格式（date 为行，code 为列）
        if isinstance(factor_values, pd.Series):
            f_wide = factor_values.unstack(level=1)
        else:
            f_wide = factor_values

        if isinstance(forward_returns, pd.Series):
            r_wide = forward_returns.unstack(level=1)
        else:
            r_wide = forward_returns

        # 对齐列
        common_codes = f_wide.columns.intersection(r_wide.columns)
        f_aligned = f_wide[common_codes]
        r_aligned = r_wide[common_codes]

        # 计算每期 IC
        ic_list = []
        dates = []
        for date_idx in f_aligned.index.intersection(r_aligned.index):
            f_day = f_aligned.loc[date_idx].dropna()
            r_day = r_aligned.loc[date_idx].dropna()
            common = f_day.index.intersection(r_day.index)

            if len(common) < 10:  # 至少需要 10 个样本
                continue

            if method == "spearman":
                ic = f_day[common].corr(r_day[common], method="spearman")
            else:
                ic = f_day[common].corr(r_day[common], method="pearson")

            if not np.isnan(ic):
                ic_list.append(ic)
                dates.append(date_idx)

        return pd.Series(ic_list, index=dates, name="IC")

    @staticmethod
    def ic_summary(ic_series: pd.Series) -> dict[str, float]:
        """IC 统计摘要。

        Returns:
            {
                "ic_mean": IC 均值,
                "ic_std": IC 标准差,
                "ic_ir": 信息比率,
                "ic_positive_pct": IC > 0 的比例,
                "ic_significant_pct": |IC| > 0.02 的比例,
            }
        """
        if len(ic_series) == 0:
            return {
                "ic_mean": 0.0,
                "ic_std": 0.0,
                "ic_ir": 0.0,
                "ic_positive_pct": 0.0,
                "ic_significant_pct": 0.0,
                "count": 0,
            }

        mean = float(ic_series.mean())
        std = float(ic_series.std())
        # Guard against pathological tiny std (e.g. all-equal series under float drift)
        ir = mean / std if std > 1e-12 else 0.0

        positive_pct = (ic_series > 0).sum() / len(ic_series)
        significant_pct = (ic_series.abs() > 0.02).sum() / len(ic_series)

        return {
            "ic_mean": round(mean, 4),
            "ic_std": round(std, 4),
            "ic_ir": round(ir, 4),
            "ic_positive_pct": round(positive_pct, 4),
            "ic_significant_pct": round(significant_pct, 4),
            "count": len(ic_series),
        }

    # ------------------------------------------------------------------
    # 收益率分层
    # ------------------------------------------------------------------

    @staticmethod
    def quantile_returns(
        factor_values: pd.DataFrame,
        forward_returns: pd.DataFrame,
        n_quantiles: int = 5,
    ) -> pd.DataFrame:
        """按因子值分层，计算每层未来收益率。

        Args:
            factor_values: 因子值，行=date，列=code
            forward_returns: 未来收益率，同上格式
            n_quantiles: 分层层数（默认 5）

        Returns:
            DataFrame，行=date，列=quantile_1 ~ quantile_N
        """
        common_codes = factor_values.columns.intersection(forward_returns.columns)
        f = factor_values[common_codes]
        r = forward_returns[common_codes]

        results = []
        for date_idx in f.index.intersection(r.index):
            f_day = f.loc[date_idx].dropna()
            r_day = r.loc[date_idx]
            common = f_day.index.intersection(r_day.index)

            if len(common) < n_quantiles * 2:
                continue

            # 按因子值分组
            f_common = f_day[common]
            r_common = r_day[common]

            try:
                quantiles = pd.qcut(f_common, q=n_quantiles, labels=False, duplicates="drop")
            except ValueError:
                continue

            day_result = {}
            for q in range(n_quantiles):
                mask = quantiles == q
                if mask.sum() > 0:
                    day_result[f"quantile_{q+1}"] = float(r_common[mask].mean())

            if day_result:
                day_result["date"] = date_idx
                results.append(day_result)

        if not results:
            return pd.DataFrame()

        df = pd.DataFrame(results).set_index("date")
        return df

    @staticmethod
    def quantile_summary(quantile_df: pd.DataFrame) -> dict[str, Any]:
        """分层收益率统计摘要。

        Returns:
            {
                "long_short_return": 多空收益率（top - bottom），
                "monotonicity": 单调性评分（-1 ~ 1），
                "quantile_means": 各层平均收益率，
            }
        """
        if quantile_df.empty:
            return {
                "long_short_return": 0.0,
                "monotonicity": 0.0,
                "quantile_means": {},
            }

        # 多空收益率：最高层 - 最低层
        q_cols = sorted([c for c in quantile_df.columns if c.startswith("quantile_")])
        if len(q_cols) >= 2:
            long_short = quantile_df[q_cols[-1]] - quantile_df[q_cols[0]]
            ls_mean = float(long_short.mean())
        else:
            ls_mean = 0.0

        # 各层平均收益率
        quantile_means = {
            col: round(float(quantile_df[col].mean()), 4)
            for col in q_cols
            if col in quantile_df.columns
        }

        # 单调性：Spearman 秩相关（层号 vs 平均收益）
        if len(quantile_means) >= 3:
            ranks = np.arange(1, len(quantile_means) + 1)
            means = list(quantile_means.values())
            monotonicity = np.corrcoef(ranks, means)[0, 1]
            if np.isnan(monotonicity):
                monotonicity = 0.0
        else:
            monotonicity = 0.0

        return {
            "long_short_return": round(ls_mean, 4),
            "monotonicity": round(float(monotonicity), 4),
            "quantile_means": quantile_means,
        }

    # ------------------------------------------------------------------
    # Turnover 分析
    # ------------------------------------------------------------------

    @staticmethod
    def factor_turnover(
        factor_values: pd.DataFrame,
        n_quantiles: int = 5,
    ) -> pd.Series:
        """计算因子换手率（top/bottom 层股票变化率）。

        Returns:
            Series，index=date，value=turnover_rate
        """
        turnover_list = []
        dates = []

        prev_top = set()
        prev_bottom = set()

        for date_idx in factor_values.index:
            f_day = factor_values.loc[date_idx].dropna()
            if len(f_day) < n_quantiles * 2:
                continue

            try:
                quantiles = pd.qcut(f_day, q=n_quantiles, labels=False, duplicates="drop")
            except ValueError:
                continue

            top = set(quantiles[quantiles == quantiles.max()].index)
            bottom = set(quantiles[quantiles == quantiles.min()].index)

            if prev_top:
                top_turnover = len(top.symmetric_difference(prev_top)) / len(top.union(prev_top))
                bottom_turnover = len(bottom.symmetric_difference(prev_bottom)) / len(bottom.union(prev_bottom))
                avg_turnover = (top_turnover + bottom_turnover) / 2
                turnover_list.append(avg_turnover)
                dates.append(date_idx)

            prev_top = top
            prev_bottom = bottom

        return pd.Series(turnover_list, index=dates, name="turnover")

    # ------------------------------------------------------------------
    # 综合报告
    # ------------------------------------------------------------------

    def analyze_factor(
        self,
        factor_values: pd.DataFrame | pd.Series,
        forward_returns: pd.DataFrame | pd.Series,
        n_quantiles: int = 5,
    ) -> dict[str, Any]:
        """综合因子分析报告。

        Returns:
            完整的因子有效性评估报告
        """
        # IC 分析
        ic_series = self.information_coefficient(factor_values, forward_returns)
        ic_stats = self.ic_summary(ic_series)

        # 分层分析
        q_df = self.quantile_returns(factor_values, forward_returns, n_quantiles)
        q_stats = self.quantile_summary(q_df)

        # Turnover
        turnover = self.factor_turnover(factor_values, n_quantiles)
        turnover_mean = float(turnover.mean()) if len(turnover) > 0 else 0.0

        return {
            "ic": ic_stats,
            "quantile": q_stats,
            "turnover_mean": round(turnover_mean, 4),
            "assessment": self._assess_factor(ic_stats, q_stats, turnover_mean),
        }

    @staticmethod
    def _assess_factor(
        ic_stats: dict,
        q_stats: dict,
        turnover_mean: float,
    ) -> str:
        """根据指标给出因子有效性评估。"""
        ic_ir = ic_stats.get("ic_ir", 0)
        ic_mean = ic_stats.get("ic_mean", 0)
        ls_return = q_stats.get("long_short_return", 0)
        monotonicity = q_stats.get("monotonicity", 0)

        # 评分标准
        score = 0
        reasons = []

        if ic_ir > 0.3:
            score += 2
            reasons.append(f"IR={ic_ir:.2f} > 0.3，预测能力强")
        elif ic_ir > 0.1:
            score += 1
            reasons.append(f"IR={ic_ir:.2f} > 0.1，有一定预测能力")
        else:
            reasons.append(f"IR={ic_ir:.2f} <= 0.1，预测能力弱")

        if ic_mean > 0.02:
            score += 1
            reasons.append(f"IC均值={ic_mean:.3f} > 0.02，正向预测")
        elif ic_mean < -0.02:
            score += 1
            reasons.append(f"IC均值={ic_mean:.3f} < -0.02，反向预测（可反转使用）")

        if ls_return > 0:
            score += 1
            reasons.append(f"多空收益={ls_return:.4f} > 0")

        if abs(monotonicity) > 0.5:
            score += 1
            reasons.append(f"单调性={monotonicity:.2f}，分层效果较好")

        if turnover_mean < 0.3:
            score += 1
            reasons.append(f"换手率={turnover_mean:.2f} < 0.3，稳定性好")
        else:
            reasons.append(f"换手率={turnover_mean:.2f} >= 0.3，换手较高")

        # 评级
        if score >= 5:
            grade = "优秀"
        elif score >= 3:
            grade = "良好"
        elif score >= 2:
            grade = "一般"
        else:
            grade = "较差"

        return f"{grade}（评分 {score}/6）：" + "；".join(reasons)
