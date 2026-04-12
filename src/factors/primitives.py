"""
无状态价量原语：滚动和/均值/标准差/最值、滚动 Z 分数、Wilder ATR（对 TR 序列）、True Range、DMI/+DI/-DI/ADX（Wilder）、**Aroon**、**Donchian（唐奇安通道）**、**VWAP**（典型价加权；累计自首根 / 滚动窗口）、CCI、Williams %R、MFI、OBV、ROC（变动率）、TRIX（三重 EMA 变动率）、N 期涨跌幅（简单收益，非对数）。

约定：输入按时间**升序**（旧 → 新）；前若干根因窗口不足输出 ``None``（``ema`` 除外，见各函数说明）。
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence


def rolling_mean(values: Sequence[float], window: int) -> list[float | None]:
    if window < 1:
        raise ValueError("window 须 >= 1")
    n = len(values)
    out: list[float | None] = [None] * n
    if n == 0:
        return out
    acc = 0.0
    for i in range(n):
        acc += float(values[i])
        if i >= window:
            acc -= float(values[i - window])
        if i >= window - 1:
            out[i] = acc / window
    return out


def rolling_sum(values: Sequence[float], window: int) -> list[float | None]:
    """滚动窗口求和；与 ``rolling_mean`` 相同索引约定（前 ``window-1`` 根为 ``None``）。"""
    if window < 1:
        raise ValueError("window 须 >= 1")
    n = len(values)
    out: list[float | None] = [None] * n
    if n == 0:
        return out
    acc = 0.0
    for i in range(n):
        acc += float(values[i])
        if i >= window:
            acc -= float(values[i - window])
        if i >= window - 1:
            out[i] = acc
    return out


def rolling_std(values: Sequence[float], window: int) -> list[float | None]:
    """
    滚动总体标准差（方差为对窗口内样本的总体方差：``E[X^2] - E[X]^2``）。

    与 ``rolling_mean`` 相同约定：时间升序；前 ``window-1`` 根为 ``None``；
    ``window == 1`` 时各有效位置为 ``0.0``（单点无离散度）。
    """
    if window < 1:
        raise ValueError("window 须 >= 1")
    n = len(values)
    out: list[float | None] = [None] * n
    if n == 0:
        return out
    acc = 0.0
    acc_sq = 0.0
    w = float(window)
    for i in range(n):
        v = float(values[i])
        acc += v
        acc_sq += v * v
        if i >= window:
            ov = float(values[i - window])
            acc -= ov
            acc_sq -= ov * ov
        if i >= window - 1:
            mean = acc / w
            var = acc_sq / w - mean * mean
            if var < 0.0 and var > -1e-12:
                var = 0.0
            out[i] = var**0.5
    return out


def rolling_zscore(values: Sequence[float], window: int) -> list[float | None]:
    """
    滚动 Z 分数：``(x[i] - rolling_mean[i]) / rolling_std[i]``，与 ``rolling_mean`` / ``rolling_std``
    同索引；``rolling_std[i]`` 为 ``0`` 或 ``None`` 时输出 ``None``。
    """
    if window < 1:
        raise ValueError("window 须 >= 1")
    m = rolling_mean(values, window)
    s = rolling_std(values, window)
    n = len(values)
    out: list[float | None] = [None] * n
    for i in range(n):
        mi, si = m[i], s[i]
        if mi is None or si is None:
            out[i] = None
            continue
        if si == 0.0:
            out[i] = None
            continue
        out[i] = (float(values[i]) - mi) / si
    return out


def rolling_max(values: Sequence[float], window: int) -> list[float | None]:
    """
    滚动窗口最大值（单调队列 ``O(n)``）。

    与 ``rolling_mean`` 相同索引约定；可用于 high 序列上的 N 日最高价等。
    """
    if window < 1:
        raise ValueError("window 须 >= 1")
    n = len(values)
    out: list[float | None] = [None] * n
    if n == 0:
        return out
    dq: deque[int] = deque()
    for i in range(n):
        x = float(values[i])
        while dq and dq[0] <= i - window:
            dq.popleft()
        while dq and float(values[dq[-1]]) <= x:
            dq.pop()
        dq.append(i)
        if i >= window - 1:
            out[i] = float(values[dq[0]])
    return out


def rolling_min(values: Sequence[float], window: int) -> list[float | None]:
    """
    滚动窗口最小值（单调队列 ``O(n)``）。

    与 ``rolling_mean`` 相同索引约定；可用于 low 序列上的 N 日最低价等。
    """
    if window < 1:
        raise ValueError("window 须 >= 1")
    n = len(values)
    out: list[float | None] = [None] * n
    if n == 0:
        return out
    dq: deque[int] = deque()
    for i in range(n):
        x = float(values[i])
        while dq and dq[0] <= i - window:
            dq.popleft()
        while dq and float(values[dq[-1]]) >= x:
            dq.pop()
        dq.append(i)
        if i >= window - 1:
            out[i] = float(values[dq[0]])
    return out


def pct_change_1(close: Sequence[float]) -> list[float | None]:
    """相邻收盘涨跌幅 %：(c[t]/c[t-1]-1)*100，首根为 None。"""
    n = len(close)
    out: list[float | None] = [None] * n
    for i in range(1, n):
        prev = float(close[i - 1])
        if prev == 0.0:
            out[i] = None
        else:
            out[i] = (float(close[i]) / prev - 1.0) * 100.0
    return out


def pct_change_n(close: Sequence[float], n: int) -> list[float | None]:
    """N 期前收盘到当期的涨跌幅 %；前 n 根为 None。n 须 >= 1。"""
    if n < 1:
        raise ValueError("n 须 >= 1")
    m = len(close)
    out: list[float | None] = [None] * m
    for i in range(n, m):
        base = float(close[i - n])
        if base == 0.0:
            out[i] = None
        else:
            out[i] = (float(close[i]) / base - 1.0) * 100.0
    return out


def roc(close: Sequence[float], period: int) -> list[float | None]:
    """
    变动率 ROC（%，对输入列）：``(close[i]/close[i-period]-1)*100``；前 ``period`` 根为 ``None``。

    与 ``pct_change_n(close, period)`` 数值等价（常见行情软件中的 ROC 命名）；``period`` 须 >= 1；
    基期价为 ``0`` 时该点为 ``None``。
    """
    return pct_change_n(close, period)


def trix(close: Sequence[float], span: int) -> list[float | None]:
    """
    TRIX：对 ``close`` 连续三次 **同 span** 的递归 ``ema`` 得 ``e3``，再取相邻变动率（%）。

    ``e1=EMA(close,span)``，``e2=EMA(e1,span)``，``e3=EMA(e2,span)``（与 ``ema`` 相同首值约定）；
    ``trix[i]=(e3[i]/e3[i-1]-1)*100``（``i>=1``）；索引 ``0`` 为 ``None``；``e3[i-1]==0`` 时为 ``None``。
    ``span`` 须 >= 1。与部分行情软件用 ``×10000`` 展示仅差常数倍，此处与 ``roc`` 一样用 **%**。
    """
    if span < 1:
        raise ValueError("span 须 >= 1")
    m = len(close)
    out: list[float | None] = [None] * m
    if m == 0:
        return out
    e1 = ema(close, span)
    e2 = ema(e1, span)
    e3 = ema(e2, span)
    for i in range(1, m):
        prev = e3[i - 1]
        if prev == 0.0:
            out[i] = None
        else:
            out[i] = (e3[i] / prev - 1.0) * 100.0
    return out


def diff_n(values: Sequence[float], n: int) -> list[float | None]:
    """N 阶滞后差分 ``x[t] - x[t-n]``；前 ``n`` 根为 ``None``。``n=1`` 为相邻一阶差分。n 须 >= 1。"""
    if n < 1:
        raise ValueError("n 须 >= 1")
    m = len(values)
    out: list[float | None] = [None] * m
    for i in range(n, m):
        out[i] = float(values[i]) - float(values[i - n])
    return out


def ema(values: Sequence[float], span: int) -> list[float]:
    """
    指数移动平均（递归）：``alpha = 2/(span+1)``，``ema[0]=x[0]``，
    ``ema[t] = alpha*x[t] + (1-alpha)*ema[t-1]``（``t>=1``）。

    与 ``rolling_mean`` 不同：**不为前列留 None**，序列非空时每根均有标量值。span 须 >= 1。
    """
    if span < 1:
        raise ValueError("span 须 >= 1")
    m = len(values)
    if m == 0:
        return []
    alpha = 2.0 / (float(span) + 1.0)
    out: list[float] = [0.0] * m
    out[0] = float(values[0])
    prev = out[0]
    for i in range(1, m):
        prev = alpha * float(values[i]) + (1.0 - alpha) * prev
        out[i] = prev
    return out


def macd_dif_dea_hist(
    close: Sequence[float],
    fast: int,
    slow: int,
    signal: int,
) -> tuple[list[float], list[float], list[float]]:
    """
    MACD：``DIF = EMA(close, fast) − EMA(close, slow)``，``DEA = EMA(DIF, signal)``，``HIST = DIF − DEA``。

    ``ema`` 与现有实现一致（``ema[0]=close[0]``，递归平滑）。须 ``fast >= 1``、``slow >= 1``、``signal >= 1`` 且 **``fast < slow``**。
    返回与 ``close`` 等长的三列浮点（无 ``None`` 填充位）。
    """
    if fast < 1 or slow < 1 or signal < 1:
        raise ValueError("fast/slow/signal 须 >= 1")
    if fast >= slow:
        raise ValueError("MACD 须满足 fast < slow")
    m = len(close)
    if m == 0:
        return [], [], []
    ef = ema(close, fast)
    es = ema(close, slow)
    dif: list[float] = [ef[i] - es[i] for i in range(m)]
    dea = ema(dif, signal)
    hist = [dif[i] - dea[i] for i in range(m)]
    return dif, dea, hist


def kdj_k_d_j(
    high: Sequence[float],
    low: Sequence[float],
    close: Sequence[float],
    n: int,
    m1: int = 3,
    m2: int = 3,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """
    KDJ：``RSV`` 为 ``n`` 日内（含当日）``(close-LL)/(HH-LL)*100``（``HH==LL`` 时 RSV=50）；
    ``K``、``D`` 为 RSV/K 的递归平滑：``K=(m1-1)/m1*K_prev + RSV/m1``，首根有效 ``K=D=RSV``；
    ``D`` 同理对 ``K``；``J=3K-2D``。与输入等长，前 ``n-1`` 根为 ``None``。
    """
    if n < 2:
        raise ValueError("RSV 周期 n 须 >= 2")
    if m1 < 1 or m2 < 1:
        raise ValueError("m1/m2 须 >= 1")
    m = len(close)
    k_out: list[float | None] = [None] * m
    d_out: list[float | None] = [None] * m
    j_out: list[float | None] = [None] * m
    if m == 0:
        return k_out, d_out, j_out
    if not (len(high) == m and len(low) == m):
        raise ValueError("high/low/close 须等长")

    rsv: list[float | None] = [None] * m
    for i in range(n - 1, m):
        lo = min(float(low[j]) for j in range(i - n + 1, i + 1))
        hi = max(float(high[j]) for j in range(i - n + 1, i + 1))
        if hi <= lo:
            rsv[i] = 50.0
        else:
            rsv[i] = (float(close[i]) - lo) / (hi - lo) * 100.0

    i0 = n - 1
    r0 = rsv[i0]
    assert r0 is not None
    k_prev = r0
    d_prev = r0
    k_out[i0] = k_prev
    d_out[i0] = d_prev
    j_out[i0] = 3.0 * k_prev - 2.0 * d_prev

    for i in range(i0 + 1, m):
        ri = rsv[i]
        assert ri is not None
        k_i = (float(m1 - 1) * k_prev + ri) / float(m1)
        d_i = (float(m2 - 1) * d_prev + k_i) / float(m2)
        j_i = 3.0 * k_i - 2.0 * d_i
        k_out[i] = k_i
        d_out[i] = d_i
        j_out[i] = j_i
        k_prev, d_prev = k_i, d_i

    return k_out, d_out, j_out


def cci(high: Sequence[float], low: Sequence[float], close: Sequence[float], period: int) -> list[float | None]:
    """
    商品通道指数（CCI）：典型价 ``TP=(H+L+C)/3``；``SMA`` 为 ``TP`` 的 ``period`` 期简单均值；
    平均绝对偏差 ``MD = mean(|TP_j - SMA|)``（同窗口、相对当前 ``SMA``）；
    ``CCI = (TP - SMA) / (0.015 * MD)``。前 ``period-1`` 根为 ``None``；``period < 2`` 或 ``MD≈0`` 时为 ``None``。
    """
    if period < 2:
        raise ValueError("CCI 周期 period 须 >= 2")
    m = len(close)
    out: list[float | None] = [None] * m
    if m == 0:
        return out
    if not (len(high) == m and len(low) == m):
        raise ValueError("high/low/close 须等长")

    tp: list[float] = [(float(high[i]) + float(low[i]) + float(close[i])) / 3.0 for i in range(m)]
    const = 0.015
    for i in range(period - 1, m):
        s = 0.0
        for j in range(i - period + 1, i + 1):
            s += tp[j]
        sma = s / float(period)
        md = 0.0
        for j in range(i - period + 1, i + 1):
            md += abs(tp[j] - sma)
        md /= float(period)
        if md < 1e-12:
            out[i] = None
        else:
            out[i] = (tp[i] - sma) / (const * md)
    return out


def williams_r(
    high: Sequence[float],
    low: Sequence[float],
    close: Sequence[float],
    period: int,
) -> list[float | None]:
    """
    Williams %R：在含当根的 ``period`` 根内 ``HH=max(high)``、``LL=min(low)``；
    ``%R = -100 * (HH - close) / (HH - LL)``（常见软件区间约 **-100～0**）。
    前 ``period-1`` 根为 ``None``；``period < 2`` 或 ``HH<=LL`` 时为 ``None``。
    """
    if period < 2:
        raise ValueError("Williams %R 周期 period 须 >= 2")
    m = len(close)
    out: list[float | None] = [None] * m
    if m == 0:
        return out
    if not (len(high) == m and len(low) == m):
        raise ValueError("high/low/close 须等长")

    for i in range(period - 1, m):
        hh = max(float(high[j]) for j in range(i - period + 1, i + 1))
        ll = min(float(low[j]) for j in range(i - period + 1, i + 1))
        if hh <= ll:
            out[i] = None
        else:
            out[i] = -100.0 * (hh - float(close[i])) / (hh - ll)
    return out


def mfi(
    high: Sequence[float],
    low: Sequence[float],
    close: Sequence[float],
    volume: Sequence[float | int],
    period: int,
) -> list[float | None]:
    """
    资金流量指标（MFI）：典型价 ``TP=(H+L+C)/3``，原始资金流 ``RMF=TP*volume``；
    在窗口 ``[i-period+1, i]`` 内，若 ``TP[j]>TP[j-1]`` 则计入 **正** 资金流，若 ``TP[j]<TP[j-1]`` 则计入 **负** 资金流（持平不计）。
    ``MFI = 100 - 100/(1 + MR)``，``MR=正/负``；全窗口无正负分时为 ``None``；``负=0`` 且 ``正>0`` 时为 **100**；``正=0`` 且 ``负>0`` 时为 **0**。
    前 ``period`` 根（索引 ``0 … period-1``）为 ``None``；首根有效在索引 ``period``；``period`` 须 ``>= 2``。
    """
    if period < 2:
        raise ValueError("MFI 周期 period 须 >= 2")
    m = len(close)
    out: list[float | None] = [None] * m
    if m == 0:
        return out
    if not (len(high) == m and len(low) == m and len(volume) == m):
        raise ValueError("high/low/close/volume 须等长")

    tp = [(float(high[i]) + float(low[i]) + float(close[i])) / 3.0 for i in range(m)]

    for i in range(period, m):
        pos = 0.0
        neg = 0.0
        for j in range(i - period + 1, i + 1):
            rmf = tp[j] * float(volume[j])
            if tp[j] > tp[j - 1]:
                pos += rmf
            elif tp[j] < tp[j - 1]:
                neg += rmf
        if pos == 0.0 and neg == 0.0:
            out[i] = None
        elif neg <= 0.0:
            out[i] = 100.0 if pos > 0.0 else None
        elif pos <= 0.0:
            out[i] = 0.0
        else:
            mr = pos / neg
            out[i] = 100.0 - 100.0 / (1.0 + mr)
    return out


def true_range(high: Sequence[float], low: Sequence[float], close: Sequence[float]) -> list[float]:
    """
    True Range 序列（与 ``kline_true_range`` 同式）：首根 ``high-low``；其后
    ``max(high-low, |high-prev_close|, |low-prev_close|)``。须 **时间升序** 且三列等长。
    """
    m = len(close)
    if m == 0:
        return []
    if len(high) != m or len(low) != m:
        raise ValueError("high/low/close 须等长")
    out: list[float] = [0.0] * m
    out[0] = float(high[0]) - float(low[0])
    for i in range(1, m):
        h = float(high[i])
        l = float(low[i])
        pc = float(close[i - 1])
        hl = h - l
        out[i] = max(hl, abs(h - pc), abs(l - pc))
    return out


def obv(close: Sequence[float], volume: Sequence[float | int]) -> list[float]:
    """
    能量潮（OBV）：``OBV[0]=volume[0]``（浮点）；之后若 ``close[i]>close[i-1]`` 则加 ``volume[i]``，
    若收低则减 ``volume[i]``，持平则不变。与 ``close`` 等长；``len==0`` 时返回空列表。
    """
    m = len(close)
    if m == 0:
        return []
    if len(volume) != m:
        raise ValueError("close/volume 须等长")
    out: list[float] = [0.0] * m
    out[0] = float(volume[0])
    for i in range(1, m):
        c = float(close[i])
        pc = float(close[i - 1])
        v = float(volume[i])
        prev = out[i - 1]
        if c > pc:
            out[i] = prev + v
        elif c < pc:
            out[i] = prev - v
        else:
            out[i] = prev
    return out


def atr_wilder(tr: Sequence[float], period: int) -> list[float | None]:
    """
    Wilder ATR：对 **True Range** 序列做 Wilder 平滑。

    首根 ATR 在索引 ``period-1``（前 ``period`` 根 TR 的简单平均）；``period==1`` 时退化为逐根 TR。
    ``period`` 须 >= 1；``len(tr) < period`` 时全 ``None``（``period>1``）。
    """
    if period < 1:
        raise ValueError("period 须 >= 1")
    m = len(tr)
    out: list[float | None] = [None] * m
    if m == 0:
        return out
    if period == 1:
        return [float(x) for x in tr]
    if m < period:
        return out
    s0 = sum(float(tr[i]) for i in range(period))
    out[period - 1] = s0 / float(period)
    prev = out[period - 1]
    assert prev is not None
    for i in range(period, m):
        prev = (prev * float(period - 1) + float(tr[i])) / float(period)
        out[i] = prev
    return out


def dmi_adx_wilder(
    high: Sequence[float],
    low: Sequence[float],
    close: Sequence[float],
    period: int,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """
    DMI / ADX（Wilder）：``+DM``/``-DM`` 按经典规则取定向变动；``TR`` 用 ``true_range``；
    对 ``+DM``、``-DM``、``TR`` 分别做与 ``atr_wilder`` **相同** 的 Wilder 平滑得 ``+DI``、``-DI``（``×100/TR``）。

    ``DX = 100*|+DI - -DI| / (+DI + -DI)``（分母 ``<=0`` 时为 ``None``）；``ADX`` 为 ``DX`` 的 Wilder 平滑：
    首根 ``ADX`` 在索引 ``2*period - 2``，为 ``DX[period-1 … 2*period-2]`` 的简单平均；其后
    ``adx[i] = (adx[i-1]*(period-1) + DX[i]) / period``。若某步 ``DX`` 为 ``None``，则该根 ``ADX`` 为 ``None`` 且
    不改变平滑状态。``period`` 须 ``>= 2``；与输入等长。
    """
    if period < 2:
        raise ValueError("DMI/ADX 周期 period 须 >= 2")
    m = len(close)
    plus_di: list[float | None] = [None] * m
    minus_di: list[float | None] = [None] * m
    adx: list[float | None] = [None] * m
    if m == 0:
        return plus_di, minus_di, adx
    if len(high) != m or len(low) != m:
        raise ValueError("high/low/close 须等长")

    tr = true_range(high, low, close)
    plus_dm = [0.0] * m
    minus_dm = [0.0] * m
    for i in range(1, m):
        up = float(high[i]) - float(high[i - 1])
        down = float(low[i - 1]) - float(low[i])
        if up > down and up > 0.0:
            plus_dm[i] = up
        if down > up and down > 0.0:
            minus_dm[i] = down

    sm_tr = atr_wilder(tr, period)
    sm_plus = atr_wilder(plus_dm, period)
    sm_minus = atr_wilder(minus_dm, period)

    for i in range(m):
        st, sp, sn = sm_tr[i], sm_plus[i], sm_minus[i]
        if st is None or st <= 0.0 or sp is None or sn is None:
            continue
        plus_di[i] = 100.0 * float(sp) / float(st)
        minus_di[i] = 100.0 * float(sn) / float(st)

    dx: list[float | None] = [None] * m
    for i in range(m):
        p, n = plus_di[i], minus_di[i]
        if p is None or n is None:
            continue
        s = float(p) + float(n)
        if s <= 0.0:
            continue
        dx[i] = 100.0 * abs(float(p) - float(n)) / s

    first_adx = 2 * period - 2
    if m <= first_adx:
        return plus_di, minus_di, adx

    def _dx_segment_mean(start: int) -> float | None:
        acc = 0.0
        for j in range(start, start + period):
            v = dx[j]
            if v is None:
                return None
            acc += float(v)
        return acc / float(period)

    init = _dx_segment_mean(period - 1)
    if init is not None:
        adx[first_adx] = init
        prev = init
        for i in range(first_adx + 1, m):
            dxi = dx[i]
            if dxi is None:
                adx[i] = None
                continue
            prev = (prev * float(period - 1) + float(dxi)) / float(period)
            adx[i] = prev
    return plus_di, minus_di, adx


def aroon(
    high: Sequence[float],
    low: Sequence[float],
    period: int,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """
    Aroon：在 ``period`` 根滑动窗口（含当日）内，``AroonUp = (period - bars_since_HH) / period * 100``，
    ``AroonDown`` 同理对 **最低价**；``bars_since`` 为窗口内最高/最低出现位置距当日的根数（并列取 **最近** 一根）。
    ``aroon_osc = AroonUp - AroonDown``。前 ``period-1`` 根三列均为 ``None``；``period`` 须 ``>= 2``。
    """
    if period < 2:
        raise ValueError("Aroon 周期 period 须 >= 2")
    m = len(high)
    up: list[float | None] = [None] * m
    down: list[float | None] = [None] * m
    osc: list[float | None] = [None] * m
    if m == 0:
        return up, down, osc
    if len(low) != m:
        raise ValueError("high/low 须等长")
    n = float(period)
    for i in range(period - 1, m):
        start = i - period + 1
        j_h = start
        max_h = float(high[start])
        for j in range(start + 1, i + 1):
            hj = float(high[j])
            if hj >= max_h:
                max_h = hj
                j_h = j
        j_l = start
        min_l = float(low[start])
        for j in range(start + 1, i + 1):
            lj = float(low[j])
            if lj <= min_l:
                min_l = lj
                j_l = j
        au = (float(period) - float(i - j_h)) / n * 100.0
        ad = (float(period) - float(i - j_l)) / n * 100.0
        up[i] = au
        down[i] = ad
        osc[i] = au - ad
    return up, down, osc


def donchian(
    high: Sequence[float],
    low: Sequence[float],
    window: int,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """
    唐奇安通道：上轨 = ``rolling_max(high, window)``，下轨 = ``rolling_min(low, window)``，
    中轨 = ``(上轨 + 下轨) / 2``（仅在上、下轨均有值处）。``window`` 须 ``>= 1``；``high`` / ``low`` 须等长。
    """
    if window < 1:
        raise ValueError("Donchian window 须 >= 1")
    m = len(high)
    if len(low) != m:
        raise ValueError("high/low 须等长")
    upper = rolling_max(high, window)
    lower = rolling_min(low, window)
    mid: list[float | None] = [None] * m
    for i in range(m):
        u, lo = upper[i], lower[i]
        if u is not None and lo is not None:
            mid[i] = (float(u) + float(lo)) / 2.0
    return upper, lower, mid


def vwap_cumulative(
    high: Sequence[float],
    low: Sequence[float],
    close: Sequence[float],
    volume: Sequence[float],
) -> list[float | None]:
    """
    自序列**首根**起累计 VWAP：逐根累加 ``典型价 × 成交量`` 与 ``成交量``，输出 ``累加_TP×V / 累加_V``。
    典型价 ``TP = (high + low + close) / 3``（与 MFI 等常用口径一致）。``volume`` 须 **≥ 0**；若截至当前累加成交量为 **0** 则为 ``None``。
    """
    m = len(high)
    if len(low) != m or len(close) != m or len(volume) != m:
        raise ValueError("high/low/close/volume 须等长")
    out: list[float | None] = [None] * m
    cum_pv = 0.0
    cum_v = 0.0
    for i in range(m):
        tp = (float(high[i]) + float(low[i]) + float(close[i])) / 3.0
        vi = float(volume[i])
        if vi < 0.0:
            raise ValueError("volume 须 >= 0")
        cum_pv += tp * vi
        cum_v += vi
        if cum_v <= 0.0:
            out[i] = None
        else:
            out[i] = cum_pv / cum_v
    return out


def vwap_rolling(
    high: Sequence[float],
    low: Sequence[float],
    close: Sequence[float],
    volume: Sequence[float],
    window: int,
) -> list[float | None]:
    """
    滚动 ``window`` 根 VWAP：每根为窗口内 ``sum(TP×V)/sum(V)``；前 ``window-1`` 根为 ``None``。
    ``window`` 须 **≥ 1**；``volume`` 须 **≥ 0**；窗口内成交量和为 **0** 时为 ``None``。
    """
    if window < 1:
        raise ValueError("VWAP 滚动 window 须 >= 1")
    m = len(high)
    if len(low) != m or len(close) != m or len(volume) != m:
        raise ValueError("high/low/close/volume 须等长")
    out: list[float | None] = [None] * m
    for i in range(window - 1, m):
        s_pv = 0.0
        s_v = 0.0
        for j in range(i - window + 1, i + 1):
            tp = (float(high[j]) + float(low[j]) + float(close[j])) / 3.0
            vj = float(volume[j])
            if vj < 0.0:
                raise ValueError("volume 须 >= 0")
            s_pv += tp * vj
            s_v += vj
        if s_v <= 0.0:
            out[i] = None
        else:
            out[i] = s_pv / s_v
    return out


def _rsi_from_avg_gain_loss(avg_g: float, avg_l: float) -> float:
    if avg_l == 0.0:
        if avg_g > 0.0:
            return 100.0
        return 50.0
    rs = avg_g / avg_l
    return 100.0 - 100.0 / (1.0 + rs)


def bollinger_bands(
    values: Sequence[float],
    window: int,
    k: float = 2.0,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """
    布林带（中轨 = ``rolling_mean``，带宽 = ``k * rolling_std``，与现有 ``rolling_std`` 同为窗口总体标准差）。

    返回 ``(mid, upper, lower)``，与输入等长；窗口不足处三轨均为 ``None``。
    ``k`` 通常取 ``2``；须 ``window >= 1``、``k > 0``。
    """
    if window < 1:
        raise ValueError("window 须 >= 1")
    if k <= 0.0:
        raise ValueError("k 须 > 0")
    mid = rolling_mean(values, window)
    std = rolling_std(values, window)
    n = len(values)
    upper: list[float | None] = [None] * n
    lower: list[float | None] = [None] * n
    for i in range(n):
        mi, si = mid[i], std[i]
        if mi is None or si is None:
            upper[i] = None
            lower[i] = None
            continue
        upper[i] = float(mi) + k * float(si)
        lower[i] = float(mi) - k * float(si)
    return mid, upper, lower


def rsi_wilder(close: Sequence[float], period: int) -> list[float | None]:
    """
    Wilder RSI（周期 ``period``）：首根有效值在索引 ``period``（至少 ``period+1`` 根 K 线）；
    首段用前 ``period`` 个 **日涨跌** 的涨/跌简单平均；其后 ``avg = (avg*(period-1)+x)/period``。

    输入须 **时间升序**；通常对 **close** 列调用。``period`` 须 >= 1。
    """
    if period < 1:
        raise ValueError("period 须 >= 1")
    m = len(close)
    out: list[float | None] = [None] * m
    if m < period + 1:
        return out

    gains = [0.0] * m
    losses = [0.0] * m
    for i in range(1, m):
        d = float(close[i]) - float(close[i - 1])
        if d >= 0.0:
            gains[i] = d
        else:
            losses[i] = -d

    avg_g = sum(gains[1 : period + 1]) / float(period)
    avg_l = sum(losses[1 : period + 1]) / float(period)
    out[period] = _rsi_from_avg_gain_loss(avg_g, avg_l)

    for i in range(period + 1, m):
        avg_g = (avg_g * float(period - 1) + gains[i]) / float(period)
        avg_l = (avg_l * float(period - 1) + losses[i]) / float(period)
        out[i] = _rsi_from_avg_gain_loss(avg_g, avg_l)

    return out
