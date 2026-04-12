"""因子预览 HTTP：http_test_client + 临时 SQLite。"""

from __future__ import annotations

from datetime import date, timedelta
from typing import get_args

import pytest

from src.api.routers.factors import OpName

from src.data.models import KLine
from src.data.storage import KlineRepository
from src.factors import (
    aroon,
    cci,
    dmi_adx_wilder,
    donchian,
    kdj_k_d_j,
    mfi,
    obv,
    roc,
    trix,
    vwap_cumulative,
    vwap_rolling,
    williams_r,
)


async def test_factors_catalog_lists_ops_and_matches_opname(http_test_client):
    r = http_test_client.get("/api/factors/catalog")
    assert r.status_code == 200
    b = r.json()
    assert b["preview_path"] == "/api/factors/preview"
    assert b["doc_ref"] == "docs/FACTORS.md"
    catalog_ids = {o["id"] for o in b["ops"]}
    opname_ids = set(get_args(OpName))
    assert catalog_ids == opname_ids
    window_ok = frozenset(("required", "optional", "unused"))
    column_ok = frozenset(("ohlcv", "ignored"))
    for o in b["ops"]:
        assert o["window"] in window_ok
        assert o["column"] in column_ok
        sk = o.get("series_keys") or []
        assert isinstance(sk, list) and sk
        for key in sk:
            assert isinstance(key, str) and key.strip()
    vwap = next(o for o in b["ops"] if o["id"] == "vwap")
    assert vwap["window"] == "optional"
    macd = next(o for o in b["ops"] if o["id"] == "macd")
    assert macd["window"] == "unused"
    assert macd["series_keys"] == ["dif", "dea", "hist"]


def _daily_row(code: str, d: date, close: float) -> KLine:
    o = close - 0.1
    return KLine(
        code=code,
        trade_date=d,
        open=o,
        high=close + 0.2,
        low=o - 0.1,
        close=close,
        volume=1000,
        amount=close * 1000,
        turnover_rate=None,
        pct_change=None,
    )


async def test_factors_preview_rolling_sum_volume(http_test_client, empty_sqlite_db):
    code = "sh.fsum"
    base = date(2024, 5, 1)
    vols = [100, 200, 300, 400]
    rows = [
        _daily_row(code, base + timedelta(days=i), 10.0 + i).model_copy(update={"volume": vols[i]})
        for i in range(4)
    ]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": code, "column": "volume", "op": "rolling_sum", "window": 2, "limit": 100},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["op"] == "rolling_sum"
    vals = body["series"]["value"]
    assert vals[0] is None
    assert vals[1] == 300.0
    assert vals[2] == 500.0
    assert vals[3] == 700.0


async def test_factors_preview_rolling_mean(http_test_client, empty_sqlite_db):
    code = "sh.fprev"
    base = date(2024, 6, 1)
    closes = [10.0, 11.0, 12.0, 13.0, 14.0]
    rows = [_daily_row(code, base + timedelta(days=i), closes[i]) for i in range(5)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": code, "column": "close", "op": "rolling_mean", "window": 3, "limit": 100},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == code
    assert body["op"] == "rolling_mean"
    assert body["window"] == 3
    assert body["bars"] == 5
    assert body.get("meta") is None
    vals = body["series"]["value"]
    assert vals[0] is None and vals[1] is None
    assert vals[2] == 11.0
    assert vals[3] == 12.0
    assert vals[4] == 13.0


async def test_factors_preview_atr_wilder(http_test_client, empty_sqlite_db):
    code = "sh.fatr"
    base = date(2024, 2, 1)
    rows = [
        _daily_row(code, base, 11.0),
        _daily_row(code, base + timedelta(days=1), 13.0).model_copy(update={"high": 14.0, "low": 12.0}),
        _daily_row(code, base + timedelta(days=2), 14.5).model_copy(update={"high": 15.0, "low": 14.0}),
    ]
    rows[0] = rows[0].model_copy(update={"high": 12.0, "low": 9.0})
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": code, "column": "close", "op": "atr", "window": 2, "limit": 50},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["op"] == "atr"
    vals = body["series"]["value"]
    assert vals[0] is None
    assert vals[1] == 3.0
    assert vals[2] == pytest.approx(2.5)


async def test_factors_preview_atr_missing_window_422(http_test_client, empty_sqlite_db):
    code = "sh.atbad"
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert([_daily_row(code, date(2024, 2, 10), 10.0)])

    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": code, "column": "close", "op": "atr", "limit": 50},
    )
    assert r.status_code == 422


async def test_factors_preview_rsi_wilder(http_test_client, empty_sqlite_db):
    code = "sh.frsi"
    base = date(2024, 3, 1)
    closes = [10.0, 11.0, 12.0, 13.0]
    rows = [_daily_row(code, base + timedelta(days=i), closes[i]) for i in range(4)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": code, "column": "close", "op": "rsi", "window": 2, "limit": 50},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["op"] == "rsi"
    assert body["window"] == 2
    vals = body["series"]["value"]
    assert vals[0] is vals[1] is None
    assert vals[2] == 100.0
    assert vals[3] == 100.0


async def test_factors_preview_rsi_missing_window_422(http_test_client, empty_sqlite_db):
    code = "sh.frnone"
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert([_daily_row(code, date(2024, 3, 10), 1.0)])

    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": code, "column": "close", "op": "rsi", "limit": 50},
    )
    assert r.status_code == 422
    assert "period" in str(r.json()["detail"]).lower() or "window" in str(r.json()["detail"]).lower()


async def test_factors_preview_rolling_zscore(http_test_client, empty_sqlite_db):
    code = "sh.fzsc"
    base = date(2024, 4, 1)
    closes = [1.0, 2.0, 3.0, 4.0]
    rows = [_daily_row(code, base + timedelta(days=i), closes[i]) for i in range(4)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": code, "column": "close", "op": "rolling_zscore", "window": 3, "limit": 50},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["op"] == "rolling_zscore"
    vals = body["series"]["value"]
    assert vals[0] is vals[1] is None
    std2 = (2.0 / 3.0) ** 0.5
    assert vals[2] == pytest.approx((3.0 - 2.0) / std2)


async def test_factors_preview_ema_span2(http_test_client, empty_sqlite_db):
    code = "sh.fema"
    base = date(2024, 8, 1)
    closes = [10.0, 12.0, 11.0, 13.0]
    rows = [_daily_row(code, base + timedelta(days=i), closes[i]) for i in range(4)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": code, "column": "close", "op": "ema", "window": 2, "limit": 50},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["op"] == "ema"
    assert body["window"] == 2
    vals = body["series"]["value"]
    assert vals[0] == 10.0
    alpha = 2.0 / 3.0
    assert vals[1] == pytest.approx(alpha * 12.0 + (1.0 - alpha) * 10.0)


async def test_factors_preview_diff_n_window1(http_test_client, empty_sqlite_db):
    code = "sh.fdiff"
    base = date(2024, 11, 10)
    closes = [10.0, 12.0, 11.0]
    rows = [_daily_row(code, base + timedelta(days=i), closes[i]) for i in range(3)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": code, "column": "close", "op": "diff_n", "window": 1, "limit": 50},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["op"] == "diff_n"
    assert body["window"] == 1
    vals = body["series"]["value"]
    assert vals[0] is None
    assert vals[1] == 2.0
    assert vals[2] == -1.0


async def test_factors_preview_pct_change_1_no_window(http_test_client, empty_sqlite_db):
    code = "sh.fpct1"
    base = date(2024, 7, 1)
    rows = [_daily_row(code, base + timedelta(days=i), 100.0 + float(i)) for i in range(3)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": code, "column": "close", "op": "pct_change_1", "limit": 50},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["window"] is None
    vals = body["series"]["value"]
    assert vals[0] is None
    assert vals[1] == pytest.approx(1.0)
    assert vals[2] == pytest.approx((102.0 / 101.0 - 1.0) * 100.0)


async def test_factors_preview_ema_missing_window_422(http_test_client, empty_sqlite_db):
    code = "sh.fembad"
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert([_daily_row(code, date(2024, 12, 15), 1.0)])

    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": code, "column": "close", "op": "ema", "limit": 50},
    )
    assert r.status_code == 422
    assert "span" in str(r.json()["detail"]).lower() or "window" in str(r.json()["detail"]).lower()


async def test_factors_preview_diff_n_missing_window_422(http_test_client, empty_sqlite_db):
    code = "sh.fdnow"
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert([_daily_row(code, date(2024, 12, 1), 1.0)])

    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": code, "column": "close", "op": "diff_n", "limit": 50},
    )
    assert r.status_code == 422
    assert "window" in str(r.json()["detail"]).lower()


async def test_factors_preview_rolling_missing_window_422(http_test_client, empty_sqlite_db):
    code = "sh.fnowin"
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert([_daily_row(code, date(2024, 8, 1), 1.0)])

    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": code, "column": "close", "op": "rolling_mean", "limit": 50},
    )
    assert r.status_code == 422
    assert "window" in str(r.json()["detail"]).lower()


async def test_factors_preview_no_klines_400(http_test_client):
    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": "sh.nodata", "column": "close", "op": "pct_change_1", "limit": 50},
    )
    assert r.status_code == 400


async def test_factors_preview_csv_bom_and_rows(http_test_client, empty_sqlite_db):
    code = "sh.fcsv"
    base = date(2024, 9, 1)
    rows = [_daily_row(code, base + timedelta(days=i), float(10 + i)) for i in range(3)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(
        "/api/factors/preview",
        params={
            "code": code,
            "column": "close",
            "op": "pct_change_1",
            "limit": 50,
            "response_format": "csv",
        },
    )
    assert r.status_code == 200
    assert "text/csv" in (r.headers.get("content-type") or "")
    assert "attachment" in (r.headers.get("content-disposition") or "").lower()
    raw = r.content
    assert raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    lines = [ln for ln in text.strip().split("\n") if ln]
    assert lines[0] == "trade_date,value"
    assert len(lines) == 4


async def test_factors_preview_respects_start_end_date(http_test_client, empty_sqlite_db):
    code = "sh.frange"
    base = date(2024, 10, 1)
    rows = [_daily_row(code, base + timedelta(days=i), 1.0) for i in range(10)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(
        "/api/factors/preview",
        params={
            "code": code,
            "column": "close",
            "op": "rolling_mean",
            "window": 2,
            "limit": 500,
            "start_date": "2024-10-03",
            "end_date": "2024-10-06",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["bars"] == 4
    assert body["trade_dates"] == [
        "2024-10-03",
        "2024-10-04",
        "2024-10-05",
        "2024-10-06",
    ]


async def test_factors_preview_bollinger_json(http_test_client, empty_sqlite_db):
    code = "sh.fbb"
    base = date(2024, 12, 1)
    closes = [10.0, 11.0, 12.0, 13.0]
    rows = [_daily_row(code, base + timedelta(days=i), closes[i]) for i in range(4)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(
        "/api/factors/preview",
        params={
            "code": code,
            "column": "close",
            "op": "bollinger",
            "window": 3,
            "bb_k": 2.0,
            "limit": 50,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["op"] == "bollinger"
    assert body["window"] == 3
    assert body["meta"] == {"bb_k": 2.0}
    std2 = (2.0 / 3.0) ** 0.5
    s = body["series"]
    assert s["mid"][2] == 11.0
    assert s["upper"][2] == pytest.approx(11.0 + 2.0 * std2)
    assert s["lower"][2] == pytest.approx(11.0 - 2.0 * std2)


async def test_factors_preview_bollinger_missing_window_422(http_test_client, empty_sqlite_db):
    code = "sh.fbbnw"
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert([_daily_row(code, date(2024, 12, 10), 1.0)])

    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": code, "column": "close", "op": "bollinger", "limit": 50},
    )
    assert r.status_code == 422


async def test_factors_preview_bollinger_csv_four_columns(http_test_client, empty_sqlite_db):
    code = "sh.fbbcsv"
    base = date(2024, 11, 1)
    rows = [_daily_row(code, base + timedelta(days=i), float(10 + i)) for i in range(4)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(
        "/api/factors/preview",
        params={
            "code": code,
            "column": "close",
            "op": "bollinger",
            "window": 2,
            "bb_k": 1.5,
            "limit": 50,
            "response_format": "csv",
        },
    )
    assert r.status_code == 200
    text = r.content.decode("utf-8-sig")
    lines = [ln for ln in text.strip().split("\n") if ln]
    assert lines[0] == "trade_date,mid,upper,lower"
    assert len(lines) == 5


async def test_factors_preview_macd_json(http_test_client, empty_sqlite_db):
    code = "sh.fmacd"
    base = date(2025, 1, 1)
    closes = [10.0 + float(i) * 0.5 for i in range(40)]
    rows = [_daily_row(code, base + timedelta(days=i), closes[i]) for i in range(40)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(
        "/api/factors/preview",
        params={
            "code": code,
            "column": "close",
            "op": "macd",
            "macd_fast": 5,
            "macd_slow": 13,
            "macd_signal": 4,
            "limit": 120,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["op"] == "macd"
    assert body["window"] is None
    assert body["meta"] == {"fast": 5, "slow": 13, "signal": 4}
    s = body["series"]
    assert set(s.keys()) == {"dif", "dea", "hist"}
    assert len(s["dif"]) == body["bars"] == 40


async def test_factors_preview_macd_fast_ge_slow_422(http_test_client, empty_sqlite_db):
    code = "sh.fmbad"
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert([_daily_row(code, date(2025, 1, 10), 10.0)])

    r = http_test_client.get(
        "/api/factors/preview",
        params={
            "code": code,
            "column": "close",
            "op": "macd",
            "macd_fast": 20,
            "macd_slow": 10,
            "limit": 50,
        },
    )
    assert r.status_code == 422


async def test_factors_preview_macd_csv_four_columns(http_test_client, empty_sqlite_db):
    code = "sh.fmcsv"
    base = date(2025, 2, 1)
    rows = [_daily_row(code, base + timedelta(days=i), 50.0 + float(i)) for i in range(6)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(
        "/api/factors/preview",
        params={
            "code": code,
            "column": "close",
            "op": "macd",
            "macd_fast": 2,
            "macd_slow": 4,
            "macd_signal": 2,
            "limit": 50,
            "response_format": "csv",
        },
    )
    assert r.status_code == 200
    text = r.content.decode("utf-8-sig")
    lines = [ln for ln in text.strip().split("\n") if ln]
    assert lines[0] == "trade_date,dif,dea,hist"
    assert len(lines) == 7


async def test_factors_preview_kdj_json_matches_primitive(http_test_client, empty_sqlite_db):
    code = "sh.fkdj"
    base = date(2024, 9, 1)
    closes = [10.0 + float(i) * 0.3 for i in range(18)]
    rows = [_daily_row(code, base + timedelta(days=i), closes[i]) for i in range(18)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(
        "/api/factors/preview",
        params={
            "code": code,
            "column": "volume",
            "op": "kdj",
            "window": 5,
            "kdj_m1": 3,
            "kdj_m2": 3,
            "limit": 80,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["op"] == "kdj"
    assert body["window"] == 5
    assert body["meta"] == {"n": 5, "m1": 3, "m2": 3}
    assert set(body["series"].keys()) == {"k", "d", "j"}
    hi = [float(x.high) for x in rows]
    lo = [float(x.low) for x in rows]
    cl = [float(x.close) for x in rows]
    ek, ed, ej = kdj_k_d_j(hi, lo, cl, 5, 3, 3)
    assert body["series"]["k"] == ek
    assert body["series"]["d"] == ed
    assert body["series"]["j"] == ej


async def test_factors_preview_kdj_missing_window_422(http_test_client, empty_sqlite_db):
    code = "sh.kdjbad"
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert([_daily_row(code, date(2024, 9, 10), 10.0)])

    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": code, "column": "close", "op": "kdj", "limit": 50},
    )
    assert r.status_code == 422


async def test_factors_preview_kdj_window_lt_2_422(http_test_client, empty_sqlite_db):
    code = "sh.kdjw1"
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert([_daily_row(code, date(2024, 9, 11), 10.0)])

    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": code, "column": "close", "op": "kdj", "window": 1, "limit": 50},
    )
    assert r.status_code == 422


async def test_factors_preview_kdj_csv_four_columns(http_test_client, empty_sqlite_db):
    code = "sh.kdjcsv"
    base = date(2024, 10, 1)
    rows = [_daily_row(code, base + timedelta(days=i), 20.0 + float(i)) for i in range(5)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(
        "/api/factors/preview",
        params={
            "code": code,
            "column": "close",
            "op": "kdj",
            "window": 3,
            "limit": 50,
            "response_format": "csv",
        },
    )
    assert r.status_code == 200
    text = r.content.decode("utf-8-sig")
    lines = [ln for ln in text.strip().split("\n") if ln]
    assert lines[0] == "trade_date,k,d,j"
    assert len(lines) == 6


async def test_factors_preview_cci_json_matches_primitive(http_test_client, empty_sqlite_db):
    code = "sh.fcci"
    base = date(2024, 12, 1)
    closes = [10.0 + 0.2 * float(i) for i in range(25)]
    rows = [_daily_row(code, base + timedelta(days=i), closes[i]) for i in range(25)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": code, "column": "volume", "op": "cci", "window": 10, "limit": 80},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["op"] == "cci"
    assert body["window"] == 10
    assert body.get("meta") is None
    vals = body["series"]["value"]
    hi = [float(x.high) for x in rows]
    lo = [float(x.low) for x in rows]
    cl = [float(x.close) for x in rows]
    assert vals == cci(hi, lo, cl, 10)


async def test_factors_preview_cci_missing_window_422(http_test_client, empty_sqlite_db):
    code = "sh.ccibad"
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert([_daily_row(code, date(2024, 12, 10), 10.0)])

    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": code, "column": "close", "op": "cci", "limit": 50},
    )
    assert r.status_code == 422


async def test_factors_preview_cci_window_lt_2_422(http_test_client, empty_sqlite_db):
    code = "sh.cciw1"
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert([_daily_row(code, date(2024, 12, 11), 10.0)])

    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": code, "column": "close", "op": "cci", "window": 1, "limit": 50},
    )
    assert r.status_code == 422


async def test_factors_preview_cci_csv_value_column(http_test_client, empty_sqlite_db):
    code = "sh.ccicsv"
    base = date(2024, 12, 15)
    rows = [_daily_row(code, base + timedelta(days=i), 100.0 + float(i)) for i in range(8)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(
        "/api/factors/preview",
        params={
            "code": code,
            "column": "close",
            "op": "cci",
            "window": 4,
            "limit": 50,
            "response_format": "csv",
        },
    )
    assert r.status_code == 200
    text = r.content.decode("utf-8-sig")
    lines = [ln for ln in text.strip().split("\n") if ln]
    assert lines[0] == "trade_date,value"
    assert len(lines) == 9


async def test_factors_preview_obv_json_window_null(http_test_client, empty_sqlite_db):
    code = "sh.fobv"
    base = date(2025, 3, 1)
    closes = [10.0, 11.0, 10.5, 10.5, 12.0]
    vols = [1000, 2000, 1500, 1800, 2200]
    rows = [
        _daily_row(code, base + timedelta(days=i), closes[i]).model_copy(update={"volume": vols[i]})
        for i in range(5)
    ]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": code, "column": "volume", "op": "obv", "limit": 80},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["op"] == "obv"
    assert body["window"] is None
    assert body.get("meta") is None
    cl = [float(x.close) for x in rows]
    vv = [float(x.volume) for x in rows]
    assert body["series"]["value"] == obv(cl, vv)


async def test_factors_preview_obv_csv(http_test_client, empty_sqlite_db):
    code = "sh.obvcsv"
    base = date(2025, 3, 10)
    rows = [_daily_row(code, base + timedelta(days=i), 50.0 + float(i)) for i in range(4)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(
        "/api/factors/preview",
        params={
            "code": code,
            "column": "close",
            "op": "obv",
            "limit": 50,
            "response_format": "csv",
        },
    )
    assert r.status_code == 200
    text = r.content.decode("utf-8-sig")
    lines = [ln for ln in text.strip().split("\n") if ln]
    assert lines[0] == "trade_date,value"
    assert len(lines) == 5


async def test_factors_preview_mfi_json_matches_primitive(http_test_client, empty_sqlite_db):
    code = "sh.fmfi"
    base = date(2025, 5, 1)
    closes = [10.0 + 0.12 * float(i) + (0.3 if i % 5 == 0 else 0.0) for i in range(24)]
    rows = [_daily_row(code, base + timedelta(days=i), closes[i]) for i in range(24)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": code, "column": "amount", "op": "mfi", "window": 8, "limit": 80},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["op"] == "mfi"
    assert body["window"] == 8
    hi = [float(x.high) for x in rows]
    lo = [float(x.low) for x in rows]
    cl = [float(x.close) for x in rows]
    vol = [float(x.volume) for x in rows]
    assert body["series"]["value"] == mfi(hi, lo, cl, vol, 8)


async def test_factors_preview_mfi_missing_window_422(http_test_client, empty_sqlite_db):
    code = "sh.mfibad"
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert([_daily_row(code, date(2025, 5, 10), 10.0)])

    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": code, "column": "close", "op": "mfi", "limit": 50},
    )
    assert r.status_code == 422


async def test_factors_preview_mfi_window_lt_2_422(http_test_client, empty_sqlite_db):
    code = "sh.mfiw1"
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert([_daily_row(code, date(2025, 5, 11), 10.0)])

    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": code, "column": "close", "op": "mfi", "window": 1, "limit": 50},
    )
    assert r.status_code == 422


async def test_factors_preview_roc_json_matches_primitive(http_test_client, empty_sqlite_db):
    code = "sh.froc"
    base = date(2025, 6, 1)
    closes = [100.0 + 0.4 * float(i) + (0.2 if i % 3 == 0 else 0.0) for i in range(18)]
    rows = [_daily_row(code, base + timedelta(days=i), closes[i]) for i in range(18)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": code, "column": "amount", "op": "roc", "window": 5, "limit": 80},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["op"] == "roc"
    assert body["window"] == 5
    amt = [float(x.amount) for x in rows]
    assert body["series"]["value"] == roc(amt, 5)


async def test_factors_preview_roc_missing_window_422(http_test_client, empty_sqlite_db):
    code = "sh.rocbad"
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert([_daily_row(code, date(2025, 6, 10), 10.0)])

    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": code, "column": "close", "op": "roc", "limit": 50},
    )
    assert r.status_code == 422


async def test_factors_preview_trix_json_matches_primitive(http_test_client, empty_sqlite_db):
    code = "sh.ftrix"
    base = date(2025, 7, 1)
    closes = [50.0 + 0.35 * float(i) + (0.1 if i % 2 == 0 else 0.0) for i in range(25)]
    rows = [_daily_row(code, base + timedelta(days=i), closes[i]) for i in range(25)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": code, "column": "close", "op": "trix", "window": 6, "limit": 80},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["op"] == "trix"
    assert body["window"] == 6
    cl = [float(x.close) for x in rows]
    assert body["series"]["value"] == trix(cl, 6)


async def test_factors_preview_trix_missing_window_422(http_test_client, empty_sqlite_db):
    code = "sh.trixbad"
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert([_daily_row(code, date(2025, 7, 10), 10.0)])

    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": code, "column": "close", "op": "trix", "limit": 50},
    )
    assert r.status_code == 422


async def test_factors_preview_adx_json_matches_primitive(http_test_client, empty_sqlite_db):
    code = "sh.fadx"
    base = date(2025, 8, 1)
    closes = [10.0 + 0.08 * float(i) + (0.15 if i % 3 == 0 else 0.0) for i in range(30)]
    rows = [_daily_row(code, base + timedelta(days=i), closes[i]) for i in range(30)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": code, "column": "amount", "op": "adx", "window": 7, "limit": 80},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["op"] == "adx"
    assert body["window"] == 7
    assert body.get("meta") == {"period": 7}
    hi = [float(x.high) for x in rows]
    lo = [float(x.low) for x in rows]
    cl = [float(x.close) for x in rows]
    exp_p, exp_m, exp_a = dmi_adx_wilder(hi, lo, cl, 7)
    assert body["series"]["plus_di"] == exp_p
    assert body["series"]["minus_di"] == exp_m
    assert body["series"]["adx"] == exp_a


async def test_factors_preview_adx_missing_window_422(http_test_client, empty_sqlite_db):
    code = "sh.adxbad"
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert([_daily_row(code, date(2025, 8, 10), 10.0)])

    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": code, "column": "close", "op": "adx", "limit": 50},
    )
    assert r.status_code == 422


async def test_factors_preview_adx_window_lt_2_422(http_test_client, empty_sqlite_db):
    code = "sh.adxw1"
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert([_daily_row(code, date(2025, 8, 11), 10.0)])

    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": code, "column": "close", "op": "adx", "window": 1, "limit": 50},
    )
    assert r.status_code == 422


async def test_factors_preview_adx_csv(http_test_client, empty_sqlite_db):
    code = "sh.adxcsv"
    base = date(2025, 8, 20)
    rows = [_daily_row(code, base + timedelta(days=i), 10.0 + float(i) * 0.05) for i in range(8)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(
        "/api/factors/preview",
        params={
            "code": code,
            "column": "close",
            "op": "adx",
            "window": 3,
            "limit": 50,
            "response_format": "csv",
        },
    )
    assert r.status_code == 200
    text = r.content.decode("utf-8-sig")
    lines = [ln for ln in text.strip().split("\n") if ln]
    assert lines[0] == "trade_date,plus_di,minus_di,adx"
    assert len(lines) == 9


async def test_factors_preview_aroon_json_matches_primitive(http_test_client, empty_sqlite_db):
    code = "sh.faroon"
    base = date(2025, 9, 1)
    closes = [10.0 + 0.08 * float(i) + (0.15 if i % 3 == 0 else 0.0) for i in range(30)]
    rows = [_daily_row(code, base + timedelta(days=i), closes[i]) for i in range(30)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": code, "column": "amount", "op": "aroon", "window": 7, "limit": 80},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["op"] == "aroon"
    assert body["window"] == 7
    assert body.get("meta") == {"period": 7}
    hi = [float(x.high) for x in rows]
    lo = [float(x.low) for x in rows]
    exp_u, exp_d, exp_o = aroon(hi, lo, 7)
    assert body["series"]["aroon_up"] == exp_u
    assert body["series"]["aroon_down"] == exp_d
    assert body["series"]["aroon_osc"] == exp_o


async def test_factors_preview_aroon_missing_window_422(http_test_client, empty_sqlite_db):
    code = "sh.aroonbad"
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert([_daily_row(code, date(2025, 9, 10), 10.0)])

    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": code, "column": "close", "op": "aroon", "limit": 50},
    )
    assert r.status_code == 422


async def test_factors_preview_aroon_window_lt_2_422(http_test_client, empty_sqlite_db):
    code = "sh.aroonw1"
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert([_daily_row(code, date(2025, 9, 11), 10.0)])

    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": code, "column": "close", "op": "aroon", "window": 1, "limit": 50},
    )
    assert r.status_code == 422


async def test_factors_preview_aroon_csv(http_test_client, empty_sqlite_db):
    code = "sh.arooncsv"
    base = date(2025, 9, 20)
    rows = [_daily_row(code, base + timedelta(days=i), 10.0 + float(i) * 0.05) for i in range(8)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(
        "/api/factors/preview",
        params={
            "code": code,
            "column": "close",
            "op": "aroon",
            "window": 3,
            "limit": 50,
            "response_format": "csv",
        },
    )
    assert r.status_code == 200
    text = r.content.decode("utf-8-sig")
    lines = [ln for ln in text.strip().split("\n") if ln]
    assert lines[0] == "trade_date,aroon_up,aroon_down,aroon_osc"
    assert len(lines) == 9


async def test_factors_preview_donchian_json_matches_primitive(http_test_client, empty_sqlite_db):
    code = "sh.fdc"
    base = date(2025, 10, 1)
    closes = [10.0 + 0.08 * float(i) + (0.15 if i % 3 == 0 else 0.0) for i in range(30)]
    rows = [_daily_row(code, base + timedelta(days=i), closes[i]) for i in range(30)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": code, "column": "amount", "op": "donchian", "window": 7, "limit": 80},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["op"] == "donchian"
    assert body["window"] == 7
    assert body.get("meta") == {"period": 7}
    hi = [float(x.high) for x in rows]
    lo = [float(x.low) for x in rows]
    exp_u, exp_l, exp_m = donchian(hi, lo, 7)
    assert body["series"]["dc_upper"] == exp_u
    assert body["series"]["dc_lower"] == exp_l
    assert body["series"]["dc_mid"] == exp_m


async def test_factors_preview_donchian_missing_window_422(http_test_client, empty_sqlite_db):
    code = "sh.dcbad"
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert([_daily_row(code, date(2025, 10, 10), 10.0)])

    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": code, "column": "close", "op": "donchian", "limit": 50},
    )
    assert r.status_code == 422


async def test_factors_preview_donchian_csv(http_test_client, empty_sqlite_db):
    code = "sh.dccsv"
    base = date(2025, 10, 20)
    rows = [_daily_row(code, base + timedelta(days=i), 10.0 + float(i) * 0.05) for i in range(5)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(
        "/api/factors/preview",
        params={
            "code": code,
            "column": "close",
            "op": "donchian",
            "window": 2,
            "limit": 50,
            "response_format": "csv",
        },
    )
    assert r.status_code == 200
    text = r.content.decode("utf-8-sig")
    lines = [ln for ln in text.strip().split("\n") if ln]
    assert lines[0] == "trade_date,dc_upper,dc_mid,dc_lower"
    assert len(lines) == 6


async def test_factors_preview_vwap_cumulative_json(http_test_client, empty_sqlite_db):
    code = "sh.fvwc"
    base = date(2025, 11, 1)
    rows = [_daily_row(code, base + timedelta(days=i), 10.0 + float(i) * 0.05) for i in range(6)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": code, "column": "close", "op": "vwap", "limit": 50},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["op"] == "vwap"
    assert body["window"] is None
    assert body["meta"] == {"mode": "cumulative"}
    hi = [float(x.high) for x in rows]
    lo = [float(x.low) for x in rows]
    cl = [float(x.close) for x in rows]
    vol = [float(x.volume) for x in rows]
    assert body["series"]["value"] == vwap_cumulative(hi, lo, cl, vol)


async def test_factors_preview_vwap_rolling_json_matches_primitive(http_test_client, empty_sqlite_db):
    code = "sh.fvwr"
    base = date(2025, 11, 10)
    rows = [_daily_row(code, base + timedelta(days=i), 10.0 + float(i) * 0.06) for i in range(25)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": code, "column": "amount", "op": "vwap", "window": 7, "limit": 80},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["op"] == "vwap"
    assert body["window"] == 7
    assert body["meta"] == {"mode": "rolling", "period": 7}
    hi = [float(x.high) for x in rows]
    lo = [float(x.low) for x in rows]
    cl = [float(x.close) for x in rows]
    vol = [float(x.volume) for x in rows]
    assert body["series"]["value"] == vwap_rolling(hi, lo, cl, vol, 7)


async def test_factors_preview_vwap_csv_cumulative(http_test_client, empty_sqlite_db):
    code = "sh.vwcsv"
    base = date(2025, 11, 20)
    rows = [_daily_row(code, base + timedelta(days=i), 10.0 + float(i) * 0.02) for i in range(4)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(
        "/api/factors/preview",
        params={
            "code": code,
            "column": "close",
            "op": "vwap",
            "limit": 50,
            "response_format": "csv",
        },
    )
    assert r.status_code == 200
    text = r.content.decode("utf-8-sig")
    lines = [ln for ln in text.strip().split("\n") if ln]
    assert lines[0] == "trade_date,value"
    assert len(lines) == 5


async def test_factors_preview_williams_r_json_matches_primitive(http_test_client, empty_sqlite_db):
    code = "sh.fwr"
    base = date(2025, 4, 1)
    closes = [10.0 + 0.15 * float(i) + (0.5 if i % 4 == 0 else 0.0) for i in range(22)]
    rows = [_daily_row(code, base + timedelta(days=i), closes[i]) for i in range(22)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": code, "column": "amount", "op": "williams_r", "window": 7, "limit": 80},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["op"] == "williams_r"
    assert body["window"] == 7
    hi = [float(x.high) for x in rows]
    lo = [float(x.low) for x in rows]
    cl = [float(x.close) for x in rows]
    assert body["series"]["value"] == williams_r(hi, lo, cl, 7)


async def test_factors_preview_williams_r_missing_window_422(http_test_client, empty_sqlite_db):
    code = "sh.wrbad"
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert([_daily_row(code, date(2025, 4, 10), 10.0)])

    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": code, "column": "close", "op": "williams_r", "limit": 50},
    )
    assert r.status_code == 422


async def test_factors_preview_williams_r_window_lt_2_422(http_test_client, empty_sqlite_db):
    code = "sh.wrw1"
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert([_daily_row(code, date(2025, 4, 11), 10.0)])

    r = http_test_client.get(
        "/api/factors/preview",
        params={"code": code, "column": "close", "op": "williams_r", "window": 1, "limit": 50},
    )
    assert r.status_code == 422
