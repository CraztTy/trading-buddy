"""ML / 因子挖掘 HTTP 路由。

端点（迭代 10 起步）:
- ``POST /api/ml/features/generate`` — 自动特征生成（基于 ``AutoFeatureEngine``）。
- ``POST /api/ml/factor/analyze``    — 因子有效性分析（IC/IR/分层，基于 ``FactorAnalyzer``）。

设计要点：
- 同步、轻量、无副作用；超长计算 / 大数据量任务应走 backtest 异步 job。
- 返回行尺寸由 ``limit`` 控制；前端无需一次性接收全部样本。
- 所有数值列在序列化时把 ``NaN`` 转 ``None``，避免 JSON 解析失败。
"""

from __future__ import annotations

from datetime import date
from math import isfinite
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.data.storage import KlineRepository, get_session
from src.factors import kline_float_series
from src.ml import AutoFeatureEngine, FactorAnalyzer

router = APIRouter()


# ---------------------------------------------------------------------------
# 共享工具
# ---------------------------------------------------------------------------


def _row_to_safe_dict(row: pd.Series) -> dict[str, Any]:
    """把单行 Series 转为 JSON 友好 dict（NaN/Inf -> None）。"""
    out: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, (pd.Timestamp, date)):
            out[str(k)] = v.isoformat()[:10] if hasattr(v, "isoformat") else str(v)
            continue
        if v is None:
            out[str(k)] = None
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            out[str(k)] = v
            continue
        if not isfinite(fv):
            out[str(k)] = None
        else:
            out[str(k)] = fv
    return out


# ---------------------------------------------------------------------------
# POST /api/ml/features/generate
# ---------------------------------------------------------------------------


class FeatureGenerateRequest(BaseModel):
    """自动特征生成请求体。"""

    code: str = Field(..., description="股票代码（如 ``sh.000001``）", min_length=1, max_length=24)
    start_date: date | None = Field(None, description="日 K 起始日期（含）；缺省取最早可用")
    end_date: date | None = Field(None, description="日 K 结束日期（含）；缺省取最新可用")
    limit: int = Field(500, ge=10, le=5000, description="拉取日 K 上限")
    base_columns: list[str] = Field(
        default_factory=lambda: ["close"],
        description="参与衍生的基础列（``close``/``open``/``high``/``low``/``volume``）",
    )
    rolling_windows: list[int] = Field(
        default_factory=lambda: [5, 10, 20],
        description="滚动窗口（每个值会衍生 mean/std/max/min 与 zscore）",
    )
    lags: list[int] = Field(default_factory=lambda: [1, 5], description="滞后期数")
    diff_periods: list[int] = Field(default_factory=lambda: [1, 5], description="差分阶数")
    log_return_periods: list[int] = Field(
        default_factory=lambda: [1, 5, 20],
        description="对数收益周期",
    )
    include_zscore: bool = Field(True, description="是否生成 ``rolling_zscore``")
    drop_na: bool = Field(False, description="是否剔除暖机阶段的 NaN 行")
    return_rows: int = Field(
        100,
        ge=0,
        le=2000,
        description="响应中实际返回的最近 N 行（0 表示不返回行，仅返回元信息）",
    )


class FeatureGenerateResponse(BaseModel):
    code: str
    n_rows: int
    n_features: int
    feature_names: list[str]
    dropped_warmup: bool
    rows: list[dict[str, Any]]


_VALID_COLUMNS: frozenset[str] = frozenset({"open", "high", "low", "close", "volume", "amount"})


@router.post("/features/generate", response_model=FeatureGenerateResponse)
async def generate_features_endpoint(
    payload: FeatureGenerateRequest,
    session: AsyncSession = Depends(get_session),
) -> FeatureGenerateResponse:
    """根据日 K 序列自动衍生特征矩阵。"""
    if payload.start_date and payload.end_date and payload.start_date > payload.end_date:
        raise HTTPException(status_code=400, detail="start_date 不能晚于 end_date")

    bad = [c for c in payload.base_columns if c not in _VALID_COLUMNS]
    if bad:
        raise HTTPException(
            status_code=422,
            detail=f"base_columns 含未知列 {bad}；合法列：{sorted(_VALID_COLUMNS)}",
        )

    repo = KlineRepository(session)
    klines = await repo.get_daily(
        code=payload.code.strip().lower(),
        start_date=payload.start_date,
        end_date=payload.end_date,
        limit=payload.limit,
    )
    if not klines:
        raise HTTPException(status_code=400, detail="无可用日 K（检查 code / 日期范围）")

    # 装配为 DataFrame
    df = pd.DataFrame(
        {
            "open": kline_float_series(klines, "open"),
            "high": kline_float_series(klines, "high"),
            "low": kline_float_series(klines, "low"),
            "close": kline_float_series(klines, "close"),
            "volume": kline_float_series(klines, "volume"),
            "amount": kline_float_series(klines, "amount"),
        },
        index=pd.DatetimeIndex([k.trade_date for k in klines], name="trade_date"),
    )

    try:
        engine = AutoFeatureEngine(
            base_columns=tuple(payload.base_columns),
            rolling_windows=tuple(payload.rolling_windows),
            lags=tuple(payload.lags),
            diff_periods=tuple(payload.diff_periods),
            log_return_periods=tuple(payload.log_return_periods),
            include_zscore=payload.include_zscore,
            drop_na=payload.drop_na,
        )
        out = engine.fit_transform(df)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"特征生成失败：{exc}") from exc

    feature_names = engine.feature_names

    # 仅返回最近 N 行
    rows: list[dict[str, Any]] = []
    if payload.return_rows > 0:
        tail = out.tail(payload.return_rows)
        for ts, row in tail.iterrows():
            d = _row_to_safe_dict(row)
            d["trade_date"] = ts.date().isoformat() if isinstance(ts, pd.Timestamp) else str(ts)
            rows.append(d)

    return FeatureGenerateResponse(
        code=payload.code,
        n_rows=len(out),
        n_features=len(feature_names),
        feature_names=feature_names,
        dropped_warmup=payload.drop_na,
        rows=rows,
    )


# ---------------------------------------------------------------------------
# POST /api/ml/factor/analyze
# ---------------------------------------------------------------------------


class FactorPanelEntry(BaseModel):
    """因子分析单条记录：(date, code, factor_value, forward_return)。"""

    date: date
    code: str = Field(..., min_length=1, max_length=24)
    factor: float
    forward_return: float = Field(..., description="未来 N 日收益率（pct）")


class FactorAnalyzeRequest(BaseModel):
    panel: list[FactorPanelEntry] = Field(
        ...,
        min_length=20,
        description="因子面板（至少 20 条记录，跨多个日期）",
    )
    n_quantiles: int = Field(5, ge=2, le=20, description="分层层数")
    method: str = Field("spearman", pattern="^(spearman|pearson)$")


class FactorAnalyzeResponse(BaseModel):
    n_records: int
    n_dates: int
    n_codes: int
    ic: dict[str, Any]
    quantile: dict[str, Any]
    turnover_mean: float
    assessment: str


@router.post("/factor/analyze", response_model=FactorAnalyzeResponse)
async def analyze_factor_endpoint(payload: FactorAnalyzeRequest) -> FactorAnalyzeResponse:
    """因子有效性分析（IC/IR、分层收益、turnover、综合评级）。"""
    df = pd.DataFrame(
        [
            {"date": e.date, "code": e.code, "factor": e.factor, "fwd": e.forward_return}
            for e in payload.panel
        ]
    )
    n_dates = df["date"].nunique()
    n_codes = df["code"].nunique()
    if n_dates < 2:
        raise HTTPException(
            status_code=422,
            detail=f"至少需要 2 个不同的日期（当前 {n_dates}）",
        )

    try:
        factor_wide = df.pivot(index="date", columns="code", values="factor")
        forward_wide = df.pivot(index="date", columns="code", values="fwd")
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"面板 pivot 失败（可能存在 (date, code) 重复）：{exc}",
        ) from exc

    analyzer = FactorAnalyzer()
    report = analyzer.analyze_factor(factor_wide, forward_wide, n_quantiles=payload.n_quantiles)

    return FactorAnalyzeResponse(
        n_records=len(df),
        n_dates=n_dates,
        n_codes=n_codes,
        ic=report["ic"],
        quantile=report["quantile"],
        turnover_mean=float(report["turnover_mean"]),
        assessment=report["assessment"],
    )
