"""
因子原语只读预览：拉日 K → 抽列 → 与 ``src/factors/primitives`` 对齐计算。
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal, get_args

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.data.storage import KlineRepository, get_session
from src.factors import (
    atr_wilder,
    aroon,
    bollinger_bands,
    donchian,
    cci,
    dmi_adx_wilder,
    diff_n,
    ema,
    kdj_k_d_j,
    macd_dif_dea_hist,
    mfi,
    obv,
    kline_float_series,
    kline_true_range,
    pct_change_1,
    pct_change_n,
    roc,
    trix,
    vwap_cumulative,
    vwap_rolling,
    rolling_max,
    rolling_mean,
    rolling_min,
    rolling_std,
    rolling_sum,
    rolling_zscore,
    rsi_wilder,
    williams_r,
)

router = APIRouter()

ColumnName = Literal["open", "high", "low", "close", "volume", "amount"]
OpName = Literal[
    "rolling_sum",
    "rolling_mean",
    "rolling_std",
    "rolling_zscore",
    "rolling_max",
    "rolling_min",
    "ema",
    "pct_change_1",
    "pct_change_n",
    "diff_n",
    "rsi",
    "atr",
    "bollinger",
    "macd",
    "kdj",
    "cci",
    "obv",
    "williams_r",
    "mfi",
    "roc",
    "trix",
    "adx",
    "aroon",
    "donchian",
    "vwap",
]

_ROLLING_OPS: frozenset[str] = frozenset(
    {
        "rolling_sum",
        "rolling_mean",
        "rolling_std",
        "rolling_zscore",
        "rolling_max",
        "rolling_min",
    }
)


class FactorOpCatalogEntry(BaseModel):
    """GET /api/factors/preview 支持的算子一条元数据（与 OpName / 校验逻辑对齐）。"""

    id: str
    window: Literal["required", "optional", "unused"] = Field(
        ...,
        description="required：须传 window；optional：vwap 累计可不传、滚动须传；unused：忽略 window",
    )
    column: Literal["ohlcv", "ignored"] = Field(
        ...,
        description="ohlcv：按 column 取价量列；ignored：内部用 H/L/C/V，column 可填 close 占位",
    )
    series_keys: list[str] = Field(
        ...,
        description="响应 body.series 中的键，与 trade_dates 等长",
    )
    notes: str | None = Field(
        None,
        description="额外查询参数或边界（如 macd_fast/slow、bb_k、kdj_m1）",
    )


class FactorCatalogResponse(BaseModel):
    preview_path: str = "/api/factors/preview"
    ops: list[FactorOpCatalogEntry]
    doc_ref: str = "docs/FACTORS.md"


def _factor_ops_catalog_entries() -> list[FactorOpCatalogEntry]:
    """单一来源：与 OpName 成员一一对应，避免漏登记。"""
    raw: dict[str, tuple[Literal["required", "optional", "unused"], Literal["ohlcv", "ignored"], tuple[str, ...], str | None]] = {
        "rolling_sum": ("required", "ohlcv", ("value",), None),
        "rolling_mean": ("required", "ohlcv", ("value",), None),
        "rolling_std": ("required", "ohlcv", ("value",), None),
        "rolling_zscore": ("required", "ohlcv", ("value",), None),
        "rolling_max": ("required", "ohlcv", ("value",), None),
        "rolling_min": ("required", "ohlcv", ("value",), None),
        "ema": ("required", "ohlcv", ("value",), "window 为 EMA span"),
        "pct_change_1": ("unused", "ohlcv", ("value",), None),
        "pct_change_n": ("required", "ohlcv", ("value",), "window 为滞后周期 n"),
        "diff_n": ("required", "ohlcv", ("value",), "window 为阶数 n"),
        "rsi": ("required", "ohlcv", ("value",), "Wilder 周期 period=window"),
        "atr": ("required", "ignored", ("value",), "H/L/C True Range → Wilder ATR"),
        "bollinger": ("required", "ohlcv", ("mid", "upper", "lower"), "查询参数 bb_k 默认 2"),
        "macd": ("unused", "ohlcv", ("dif", "dea", "hist"), "macd_fast/slow/signal 默认 12/26/9，须 fast<slow"),
        "kdj": ("required", "ignored", ("k", "d", "j"), "window 为 RSV 周期 n≥2；kdj_m1/m2 默认 3"),
        "cci": ("required", "ignored", ("value",), "典型价 H/L/C"),
        "obv": ("unused", "ignored", ("value",), "close+volume"),
        "williams_r": ("required", "ignored", ("value",), None),
        "mfi": ("required", "ignored", ("value",), None),
        "roc": ("required", "ohlcv", ("value",), "window 为 ROC 周期"),
        "trix": ("required", "ohlcv", ("value",), "window 为三重 EMA span"),
        "adx": ("required", "ignored", ("plus_di", "minus_di", "adx"), "window=period≥2"),
        "aroon": ("required", "ignored", ("aroon_up", "aroon_down", "aroon_osc"), "window=period≥2"),
        "donchian": ("required", "ignored", ("dc_upper", "dc_mid", "dc_lower"), "window=通道宽度≥1"),
        "vwap": ("optional", "ignored", ("value",), "不传 window 为累计 VWAP；传 window 为滚动"),
    }
    expected = frozenset(get_args(OpName))
    if frozenset(raw.keys()) != expected:
        missing = expected - frozenset(raw.keys())
        extra = frozenset(raw.keys()) - expected
        raise RuntimeError(f"因子 catalog 与 OpName 不一致: missing={missing!r} extra={extra!r}")
    return [
        FactorOpCatalogEntry(id=op, window=raw[op][0], column=raw[op][1], series_keys=list(raw[op][2]), notes=raw[op][3])
        for op in sorted(raw.keys())
    ]


class FactorPreviewResponse(BaseModel):
    code: str
    column: str
    op: str
    window: int | None = Field(
        None,
        description="rolling_*、ema、pct_change_n、roc、trix、diff_n、rsi、atr、bollinger、kdj、cci、williams_r、mfi、adx、aroon、donchian 使用 window；vwap 滚动须传 window；macd、obv、pct_change_1、vwap（日级累计不传 window）响应 window 可为 null",
    )
    limit: int
    bars: int = Field(..., description="与 series 中各序列长度一致")
    trade_dates: list[str] = Field(default_factory=list, description="与各 series 列对齐的 ISO 日期")
    series: dict[str, list[float | None]] = Field(
        default_factory=dict,
        description='单轨 {"value"}（含 atr、cci、mfi、obv、williams_r、roc、trix、vwap）；adx {"plus_di","minus_di","adx"}；aroon {"aroon_up","aroon_down","aroon_osc"}；donchian {"dc_upper","dc_mid","dc_lower"}；bollinger {"mid","upper","lower"}；macd {"dif","dea","hist"}；kdj {"k","d","j"}',
    )
    meta: dict[str, Any] | None = Field(
        default=None,
        description="bollinger: bb_k；macd: fast/slow/signal；kdj: n,m1,m2；adx/aroon/donchian: period；vwap: mode=cumulative|rolling（rolling 时含 period）；atr/cci/mfi/obv/williams_r/roc/trix 等单轨多为 null",
    )


def _csv_value_cell(v: float | None) -> str:
    if v is None:
        return ""
    s = f"{float(v):.12g}"
    if "," in s or '"' in s or "\n" in s or "\r" in s:
        return '"' + s.replace('"', '""') + '"'
    return s


def _factor_preview_csv_attachment(body: FactorPreviewResponse) -> Response:
    if body.op == "bollinger":
        mid = body.series.get("mid", [])
        upper = body.series.get("upper", [])
        lower = body.series.get("lower", [])
        lines = ["trade_date,mid,upper,lower"]
        for d, m, u, lo in zip(body.trade_dates, mid, upper, lower):
            lines.append(
                f"{d},{_csv_value_cell(m)},{_csv_value_cell(u)},{_csv_value_cell(lo)}",
            )
    elif body.op == "macd":
        dif = body.series.get("dif", [])
        dea = body.series.get("dea", [])
        hist = body.series.get("hist", [])
        lines = ["trade_date,dif,dea,hist"]
        for d, di, de, hi in zip(body.trade_dates, dif, dea, hist):
            lines.append(
                f"{d},{_csv_value_cell(di)},{_csv_value_cell(de)},{_csv_value_cell(hi)}",
            )
    elif body.op == "kdj":
        kk = body.series.get("k", [])
        kd = body.series.get("d", [])
        kj = body.series.get("j", [])
        lines = ["trade_date,k,d,j"]
        for d, kv, dv, jv in zip(body.trade_dates, kk, kd, kj):
            lines.append(f"{d},{_csv_value_cell(kv)},{_csv_value_cell(dv)},{_csv_value_cell(jv)}")
    elif body.op == "adx":
        pdi = body.series.get("plus_di", [])
        mdi = body.series.get("minus_di", [])
        ax = body.series.get("adx", [])
        lines = ["trade_date,plus_di,minus_di,adx"]
        for d, pv, mv, av in zip(body.trade_dates, pdi, mdi, ax):
            lines.append(f"{d},{_csv_value_cell(pv)},{_csv_value_cell(mv)},{_csv_value_cell(av)}")
    elif body.op == "aroon":
        au = body.series.get("aroon_up", [])
        ad = body.series.get("aroon_down", [])
        ao = body.series.get("aroon_osc", [])
        lines = ["trade_date,aroon_up,aroon_down,aroon_osc"]
        for d, u, dn, o in zip(body.trade_dates, au, ad, ao):
            lines.append(f"{d},{_csv_value_cell(u)},{_csv_value_cell(dn)},{_csv_value_cell(o)}")
    elif body.op == "donchian":
        du = body.series.get("dc_upper", [])
        dm = body.series.get("dc_mid", [])
        dl = body.series.get("dc_lower", [])
        lines = ["trade_date,dc_upper,dc_mid,dc_lower"]
        for d, uu, mm, ll in zip(body.trade_dates, du, dm, dl):
            lines.append(f"{d},{_csv_value_cell(uu)},{_csv_value_cell(mm)},{_csv_value_cell(ll)}")
    else:
        vals = body.series.get("value", [])
        lines = ["trade_date,value"]
        for d, v in zip(body.trade_dates, vals):
            lines.append(f"{d},{_csv_value_cell(v)}")
    text = "\ufeff" + "\n".join(lines) + "\n"
    safe = body.code.replace("/", "_").replace("\\", "_")
    fname = f"{safe}_{body.column}_{body.op}.csv"
    return Response(
        content=text.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


def _bars_from_series(series: dict[str, list[float | None]]) -> int:
    if not series:
        return 0
    return len(next(iter(series.values())))


async def _factor_preview_compute(
    session: AsyncSession,
    code: str,
    column: ColumnName,
    op: OpName,
    window: int | None,
    limit: int,
    start_date: date | None,
    end_date: date | None,
    bb_k: float,
    macd_fast: int,
    macd_slow: int,
    macd_signal: int,
    kdj_m1: int,
    kdj_m2: int,
) -> FactorPreviewResponse:
    if op in _ROLLING_OPS:
        if window is None:
            raise HTTPException(status_code=422, detail=f"op={op!r} 须传 window")
    elif op == "pct_change_n":
        if window is None:
            raise HTTPException(status_code=422, detail="op=pct_change_n 须传 window 作为周期 n")
    elif op == "roc":
        if window is None:
            raise HTTPException(status_code=422, detail="op=roc 须传 window 作为 ROC 周期 period（如 12）")
    elif op == "trix":
        if window is None:
            raise HTTPException(status_code=422, detail="op=trix 须传 window 作为三重 EMA 的 span（如 14，须 >= 1）")
    elif op == "diff_n":
        if window is None:
            raise HTTPException(status_code=422, detail="op=diff_n 须传 window 作为滞后阶数 n")
    elif op == "ema":
        if window is None:
            raise HTTPException(status_code=422, detail="op=ema 须传 window 作为 span（对应 alpha=2/(span+1)）")
    elif op == "rsi":
        if window is None:
            raise HTTPException(status_code=422, detail="op=rsi 须传 window 作为 Wilder 周期 period（如 14）")
    elif op == "atr":
        if window is None:
            raise HTTPException(status_code=422, detail="op=atr 须传 window 作为 Wilder ATR 周期 period（如 14）")
    elif op == "bollinger":
        if window is None:
            raise HTTPException(status_code=422, detail="op=bollinger 须传 window 作为 SMA / 标准差窗口（如 20）")
    elif op == "macd":
        if macd_fast >= macd_slow:
            raise HTTPException(
                status_code=422,
                detail="op=macd 须满足 macd_fast < macd_slow（常见为 12 / 26）",
            )
    elif op == "kdj":
        if window is None:
            raise HTTPException(status_code=422, detail="op=kdj 须传 window 作为 RSV 周期 n（如 9，须 >= 2）")
        if window < 2:
            raise HTTPException(status_code=422, detail="op=kdj 的 window（RSV 周期 n）须 >= 2")
    elif op == "cci":
        if window is None:
            raise HTTPException(status_code=422, detail="op=cci 须传 window 作为周期 period（如 20，须 >= 2）")
        if window < 2:
            raise HTTPException(status_code=422, detail="op=cci 的 window（period）须 >= 2")
    elif op == "williams_r":
        if window is None:
            raise HTTPException(
                status_code=422,
                detail="op=williams_r 须传 window 作为周期 period（如 14，须 >= 2）",
            )
        if window < 2:
            raise HTTPException(status_code=422, detail="op=williams_r 的 window（period）须 >= 2")
    elif op == "mfi":
        if window is None:
            raise HTTPException(status_code=422, detail="op=mfi 须传 window 作为周期 period（如 14，须 >= 2）")
        if window < 2:
            raise HTTPException(status_code=422, detail="op=mfi 的 window（period）须 >= 2")
    elif op == "adx":
        if window is None:
            raise HTTPException(status_code=422, detail="op=adx 须传 window 作为 DMI/ADX 周期 period（如 14，须 >= 2）")
        if window < 2:
            raise HTTPException(status_code=422, detail="op=adx 的 window（period）须 >= 2")
    elif op == "aroon":
        if window is None:
            raise HTTPException(status_code=422, detail="op=aroon 须传 window 作为周期 period（如 14，须 >= 2）")
        if window < 2:
            raise HTTPException(status_code=422, detail="op=aroon 的 window（period）须 >= 2")
    elif op == "donchian":
        if window is None:
            raise HTTPException(status_code=422, detail="op=donchian 须传 window 作为通道窗口（如 20，须 >= 1）")
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date 不能晚于 end_date")

    repo = KlineRepository(session)
    klines = await repo.get_daily(
        code=code.strip().lower(),
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
    if not klines:
        raise HTTPException(status_code=400, detail="无可用日 K")

    w = window if window is not None else 0
    meta: dict[str, Any] | None = None

    if op == "atr":
        tr = kline_true_range(klines)
        out = atr_wilder(tr, w)
        series = {"value": out}
    elif op == "bollinger":
        price = kline_float_series(klines, column)
        mid, upper, lower = bollinger_bands(price, w, bb_k)
        series = {"mid": mid, "upper": upper, "lower": lower}
        meta = {"bb_k": float(bb_k)}
    elif op == "macd":
        price = kline_float_series(klines, column)
        dif, dea, hist = macd_dif_dea_hist(price, macd_fast, macd_slow, macd_signal)
        series = {"dif": dif, "dea": dea, "hist": hist}
        meta = {"fast": macd_fast, "slow": macd_slow, "signal": macd_signal}
    elif op == "kdj":
        hi = kline_float_series(klines, "high")
        lo = kline_float_series(klines, "low")
        cl = kline_float_series(klines, "close")
        k_s, d_s, j_s = kdj_k_d_j(hi, lo, cl, w, kdj_m1, kdj_m2)
        series = {"k": k_s, "d": d_s, "j": j_s}
        meta = {"n": w, "m1": kdj_m1, "m2": kdj_m2}
    elif op == "cci":
        hi = kline_float_series(klines, "high")
        lo = kline_float_series(klines, "low")
        cl = kline_float_series(klines, "close")
        series = {"value": cci(hi, lo, cl, w)}
    elif op == "williams_r":
        hi = kline_float_series(klines, "high")
        lo = kline_float_series(klines, "low")
        cl = kline_float_series(klines, "close")
        series = {"value": williams_r(hi, lo, cl, w)}
    elif op == "mfi":
        hi = kline_float_series(klines, "high")
        lo = kline_float_series(klines, "low")
        cl = kline_float_series(klines, "close")
        vol = kline_float_series(klines, "volume")
        series = {"value": mfi(hi, lo, cl, vol, w)}
    elif op == "obv":
        cl = kline_float_series(klines, "close")
        vol = kline_float_series(klines, "volume")
        series = {"value": obv(cl, vol)}
    elif op == "adx":
        hi = kline_float_series(klines, "high")
        lo = kline_float_series(klines, "low")
        cl = kline_float_series(klines, "close")
        pdi, mdi, ax = dmi_adx_wilder(hi, lo, cl, w)
        series = {"plus_di": pdi, "minus_di": mdi, "adx": ax}
        meta = {"period": w}
    elif op == "aroon":
        hi = kline_float_series(klines, "high")
        lo = kline_float_series(klines, "low")
        au, ad, ao = aroon(hi, lo, w)
        series = {"aroon_up": au, "aroon_down": ad, "aroon_osc": ao}
        meta = {"period": w}
    elif op == "donchian":
        hi = kline_float_series(klines, "high")
        lo = kline_float_series(klines, "low")
        du, dl, dm = donchian(hi, lo, w)
        series = {"dc_upper": du, "dc_lower": dl, "dc_mid": dm}
        meta = {"period": w}
    elif op == "vwap":
        hi = kline_float_series(klines, "high")
        lo = kline_float_series(klines, "low")
        cl = kline_float_series(klines, "close")
        vol = kline_float_series(klines, "volume")
        if window is None:
            series = {"value": vwap_cumulative(hi, lo, cl, vol)}
            meta = {"mode": "cumulative"}
        else:
            series = {"value": vwap_rolling(hi, lo, cl, vol, window)}
            meta = {"mode": "rolling", "period": window}
    else:
        price = kline_float_series(klines, column)
        if op == "rolling_sum":
            out = rolling_sum(price, w)
        elif op == "rolling_mean":
            out = rolling_mean(price, w)
        elif op == "rolling_std":
            out = rolling_std(price, w)
        elif op == "rolling_zscore":
            out = rolling_zscore(price, w)
        elif op == "rolling_max":
            out = rolling_max(price, w)
        elif op == "rolling_min":
            out = rolling_min(price, w)
        elif op == "pct_change_1":
            out = pct_change_1(price)
        elif op == "pct_change_n":
            out = pct_change_n(price, w)
        elif op == "roc":
            out = roc(price, w)
        elif op == "trix":
            out = trix(price, w)
        elif op == "diff_n":
            out = diff_n(price, w)
        elif op == "ema":
            out = ema(price, w)
        elif op == "rsi":
            out = rsi_wilder(price, w)
        else:
            raise HTTPException(status_code=400, detail=f"未知 op={op!r}")
        series = {"value": out}

    dates = [k.trade_date.isoformat() for k in klines]
    resp_window: int | None = window
    if op in ("pct_change_1", "macd", "obv"):
        resp_window = None
    elif op == "vwap" and window is None:
        resp_window = None
    return FactorPreviewResponse(
        code=code.strip().lower(),
        column=column,
        op=op,
        window=resp_window,
        limit=limit,
        bars=_bars_from_series(series),
        trade_dates=dates,
        series=series,
        meta=meta,
    )


@router.get("/catalog", response_model=FactorCatalogResponse)
async def factors_ops_catalog():
    """列出因子预览 API 支持的算子及 window/column 约定，供 UI 与外部脚本发现。"""
    return FactorCatalogResponse(ops=_factor_ops_catalog_entries())


@router.get("/preview")
async def factor_preview(
    code: str = Query(..., min_length=1, max_length=64, description="标的代码"),
    column: ColumnName = Query(
        ...,
        description="K 线列；op=atr/kdj/cci/williams_r/mfi/obv/adx/aroon/donchian/vwap 时忽略（obv 用 close+volume；mfi/vwap 用 H/L/C/V；adx/aroon/donchian 用 H/L；可填 close）；roc/trix 与 rolling_* 等同按 column 取列",
    ),
    op: OpName = Query(..., description="原语算子"),
    window: int | None = Query(
        None,
        ge=1,
        le=500,
        description="rolling_*、ema、atr、bollinger、kdj、cci、williams_r、mfi、roc、trix、adx、aroon、donchian 等须传 window；vwap 滚动时须传 window（日级累计不传）；pct_change_n/roc/diff_n/rsi 为 n 或 period；trix 的 window 为 EMA span；adx/aroon 的 window 为 period；donchian 的 window 为通道宽度；pct_change_1、macd、obv 忽略",
    ),
    bb_k: float = Query(
        2.0,
        ge=0.25,
        le=12.0,
        description="仅 op=bollinger：上下轨 k 倍 rolling_std；写入 meta.bb_k",
    ),
    macd_fast: int = Query(12, ge=1, le=200, description="op=macd：快线 EMA span（须 < macd_slow）"),
    macd_slow: int = Query(26, ge=1, le=200, description="op=macd：慢线 EMA span"),
    macd_signal: int = Query(9, ge=1, le=200, description="op=macd：DEA 对 DIF 的 EMA span；写入 meta.signal"),
    kdj_m1: int = Query(3, ge=1, le=30, description="op=kdj：K 平滑参数 m1（默认 3）；写入 meta.m1"),
    kdj_m2: int = Query(3, ge=1, le=30, description="op=kdj：D 平滑参数 m2（默认 3）；写入 meta.m2"),
    limit: int = Query(500, ge=30, le=5000, description="拉取日 K 根数上限（从新到旧再正序）"),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    response_format: Literal["json", "csv"] = Query(
        "json",
        description="json：series/meta；csv：value / bollinger / macd / kdj / adx / aroon / donchian / vwap",
    ),
    session: AsyncSession = Depends(get_session),
):
    """对单列日 K 序列跑一项因子原语，不落库。"""
    body = await _factor_preview_compute(
        session,
        code,
        column,
        op,
        window,
        limit,
        start_date,
        end_date,
        bb_k,
        macd_fast,
        macd_slow,
        macd_signal,
        kdj_m1,
        kdj_m2,
    )
    if response_format == "csv":
        return _factor_preview_csv_attachment(body)
    return body


__all__ = ["router"]
