"""KlineRepository + SQLite：独立临时库，不读写 data/trading.db。"""

from __future__ import annotations

from datetime import date

import pytest

from src.common.config import describe_database_write_target, get_settings
from src.data.models import KLine
from src.data.storage import KlineRepository


def _k(
    code: str,
    trade_date: date,
    *,
    close: float,
    pct_change: float | None,
) -> KLine:
    return KLine(
        code=code,
        trade_date=trade_date,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1,
        amount=1.0,
        turnover_rate=None,
        pct_change=pct_change,
    )


async def test_bulk_insert_get_daily_chronological_and_pct_change(empty_sqlite_db):
    db = empty_sqlite_db
    async with db.session() as session:
        repo = KlineRepository(session)
        rows = [
            KLine(
                code="sh.t",
                trade_date=date(2024, 1, 2),
                open=10.0,
                high=10.5,
                low=9.8,
                close=10.2,
                volume=1000,
                amount=10000.0,
                turnover_rate=1.5,
                pct_change=0.5,
            ),
            KLine(
                code="sh.t",
                trade_date=date(2024, 1, 3),
                open=10.2,
                high=10.8,
                low=10.0,
                close=10.5,
                volume=1100,
                amount=11000.0,
                turnover_rate=1.6,
                pct_change=0.3,
            ),
        ]
        n = await repo.bulk_insert(rows)
        assert n == 2

    async with db.session() as session:
        repo = KlineRepository(session)
        out = await repo.get_daily(code="sh.t", limit=10)
    assert len(out) == 2
    assert [k.trade_date for k in out] == [date(2024, 1, 2), date(2024, 1, 3)]
    assert out[0].close == 10.2
    assert out[0].pct_change == pytest.approx(0.5)
    assert out[1].pct_change == pytest.approx(0.3)


async def test_bulk_insert_upsert_same_code_date_updates(empty_sqlite_db):
    db = empty_sqlite_db
    d = date(2024, 2, 1)
    async with db.session() as session:
        repo = KlineRepository(session)
        await repo.bulk_insert(
            [
                KLine(
                    code="sh.u",
                    trade_date=d,
                    open=1.0,
                    high=1.0,
                    low=1.0,
                    close=10.0,
                    volume=1,
                    amount=1.0,
                    turnover_rate=None,
                    pct_change=1.0,
                )
            ]
        )
    async with db.session() as session:
        repo = KlineRepository(session)
        await repo.bulk_insert(
            [
                KLine(
                    code="sh.u",
                    trade_date=d,
                    open=1.0,
                    high=1.0,
                    low=1.0,
                    close=99.0,
                    volume=2,
                    amount=2.0,
                    turnover_rate=None,
                    pct_change=9.0,
                )
            ]
        )
    async with db.session() as session:
        repo = KlineRepository(session)
        out = await repo.get_daily(code="sh.u", limit=5)
    assert len(out) == 1
    assert out[0].close == 99.0
    assert out[0].pct_change == pytest.approx(9.0)


async def test_get_daily_start_end_filter(empty_sqlite_db):
    db = empty_sqlite_db
    async with db.session() as session:
        repo = KlineRepository(session)
        await repo.bulk_insert(
            [
                KLine(
                    code="sh.v",
                    trade_date=date(2024, 3, i),
                    open=float(i),
                    high=float(i),
                    low=float(i),
                    close=float(i),
                    volume=1,
                    amount=1.0,
                    pct_change=None,
                )
                for i in range(1, 6)
            ]
        )
    async with db.session() as session:
        repo = KlineRepository(session)
        out = await repo.get_daily(
            code="sh.v",
            start_date=date(2024, 3, 2),
            end_date=date(2024, 3, 4),
            limit=50,
        )
    assert [k.trade_date for k in out] == [
        date(2024, 3, 2),
        date(2024, 3, 3),
        date(2024, 3, 4),
    ]


async def test_get_top_gainers_orders_desc_on_explicit_date(empty_sqlite_db):
    db = empty_sqlite_db
    d = date(2024, 5, 10)
    rows = [
        _k("sh.a", d, close=10.0, pct_change=1.0),
        _k("sh.b", d, close=11.0, pct_change=5.5),
        _k("sh.c", d, close=12.0, pct_change=2.0),
    ]
    async with db.session() as session:
        await KlineRepository(session).bulk_insert(rows)
    async with db.session() as session:
        top = await KlineRepository(session).get_top_gainers(trade_date=d, limit=10)
    assert [k.code for k in top] == ["sh.b", "sh.c", "sh.a"]
    assert [k.pct_change for k in top] == pytest.approx([5.5, 2.0, 1.0])


async def test_get_top_losers_orders_asc_most_negative_first(empty_sqlite_db):
    db = empty_sqlite_db
    d = date(2024, 5, 11)
    rows = [
        _k("sz.a", d, close=10.0, pct_change=-1.0),
        _k("sz.b", d, close=11.0, pct_change=-5.0),
        _k("sz.c", d, close=12.0, pct_change=-2.0),
    ]
    async with db.session() as session:
        await KlineRepository(session).bulk_insert(rows)
    async with db.session() as session:
        bot = await KlineRepository(session).get_top_losers(trade_date=d, limit=10)
    assert [k.code for k in bot] == ["sz.b", "sz.c", "sz.a"]
    assert [k.pct_change for k in bot] == pytest.approx([-5.0, -2.0, -1.0])


async def test_get_top_by_amount_orders_desc_on_explicit_date(empty_sqlite_db):
    db = empty_sqlite_db
    d = date(2024, 5, 20)
    from src.data.models import Market, StockInfo, StockType
    from src.data.storage import StockRepository

    async with db.session() as session:
        await StockRepository(session).bulk_upsert(
            [
                StockInfo(
                    code="sh.am1",
                    name="小",
                    market=Market.SH,
                    stock_type=StockType.COMMON,
                    is_trading=True,
                ),
                StockInfo(
                    code="sh.am2",
                    name="大",
                    market=Market.SH,
                    stock_type=StockType.COMMON,
                    is_trading=True,
                ),
            ]
        )
        await KlineRepository(session).bulk_insert(
            [
                _k("sh.am1", d, close=10.0, pct_change=0.1).model_copy(
                    update={"amount": 100.0}
                ),
                _k("sh.am2", d, close=11.0, pct_change=0.2).model_copy(
                    update={"amount": 999.0}
                ),
            ]
        )
    async with db.session() as session:
        top = await KlineRepository(session).get_top_by_amount(trade_date=d, limit=10)
    assert [k.code for k in top] == ["sh.am2", "sh.am1"]


async def test_get_top_by_amount_join_excludes_kline_without_stock_info(
    empty_sqlite_db,
):
    db = empty_sqlite_db
    d = date(2024, 5, 21)
    async with db.session() as session:
        await KlineRepository(session).bulk_insert(
            [
                _k("sh.orph", d, close=1.0, pct_change=0.0).model_copy(
                    update={"amount": 1e12}
                ),
            ]
        )
    async with db.session() as session:
        top = await KlineRepository(session).get_top_by_amount(trade_date=d, limit=5)
    assert top == []


async def test_get_top_gainers_none_date_uses_latest_trade_date_only(empty_sqlite_db):
    db = empty_sqlite_db
    async with db.session() as session:
        repo = KlineRepository(session)
        await repo.bulk_insert(
            [
                _k("sh.p1", date(2024, 6, 1), close=10.0, pct_change=9.0),
                _k("sh.p2", date(2024, 6, 2), close=10.0, pct_change=1.0),
                _k("sh.p3", date(2024, 6, 2), close=10.0, pct_change=3.0),
            ]
        )
    async with db.session() as session:
        top = await KlineRepository(session).get_top_gainers(trade_date=None, limit=10)
    assert [k.code for k in top] == ["sh.p3", "sh.p2"]
    assert all(k.trade_date == date(2024, 6, 2) for k in top)


async def test_get_latest_global_trade_date(empty_sqlite_db):
    db = empty_sqlite_db
    async with db.session() as session:
        repo = KlineRepository(session)
        await repo.bulk_insert(
            [
                _k("sh.z", date(2024, 7, 1), close=1.0, pct_change=0.1),
                _k("sh.z", date(2024, 7, 3), close=2.0, pct_change=0.2),
            ]
        )
    async with db.session() as session:
        mx = await KlineRepository(session).get_latest_global_trade_date()
    assert mx == date(2024, 7, 3)


def test_describe_database_write_target_includes_custom_sqlite_path(
    tmp_path, monkeypatch
):
    db_file = tmp_path / "custom.sqlite"
    monkeypatch.setenv("DATABASE_MODE", "sqlite")
    monkeypatch.setenv("DATABASE_SQLITE_PATH", str(db_file))
    get_settings.cache_clear()
    try:
        text = describe_database_write_target()
        assert "SQLite" in text
        assert "custom.sqlite" in text
    finally:
        get_settings.cache_clear()


async def test_get_latest_trade_dates_for_codes_empty_returns_empty_dict(
    empty_sqlite_db,
):
    async with empty_sqlite_db.session() as session:
        m = await KlineRepository(session).get_latest_trade_dates_for_codes([])
    assert m == {}


async def test_get_latest_trade_dates_for_codes_groups_by_code(empty_sqlite_db):
    db = empty_sqlite_db
    async with db.session() as session:
        repo = KlineRepository(session)
        await repo.bulk_insert(
            [
                _k("sh.la", date(2024, 8, 1), close=1.0, pct_change=0.1),
                _k("sh.la", date(2024, 8, 5), close=2.0, pct_change=0.2),
                _k("sh.lb", date(2024, 8, 3), close=3.0, pct_change=0.3),
            ]
        )
    async with db.session() as session:
        repo = KlineRepository(session)
        m = await repo.get_latest_trade_dates_for_codes(["sh.lb", "sh.la", "sh.missing"])
    assert m["sh.la"] == date(2024, 8, 5)
    assert m["sh.lb"] == date(2024, 8, 3)
    assert "sh.missing" not in m


async def test_get_latest_date_single_code(empty_sqlite_db):
    db = empty_sqlite_db
    async with db.session() as session:
        repo = KlineRepository(session)
        await repo.bulk_insert(
            [
                _k("sh.lc", date(2024, 9, 1), close=1.0, pct_change=None),
                _k("sh.lc", date(2024, 9, 10), close=2.0, pct_change=None),
            ]
        )
    async with db.session() as session:
        d = await KlineRepository(session).get_latest_date("sh.lc")
    assert d == date(2024, 9, 10)


async def test_get_daily_last_n_bars_per_code_matches_get_daily(empty_sqlite_db):
    db = empty_sqlite_db
    async with db.session() as session:
        repo = KlineRepository(session)
        await repo.bulk_insert(
            [
                _k("sh.pw", date(2024, 11, d), close=float(d), pct_change=0.1 * d)
                for d in range(1, 9)
            ]
        )
    end_d = date(2024, 11, 8)
    async with db.session() as session:
        repo = KlineRepository(session)
        single = await repo.get_daily(code="sh.pw", end_date=end_d, limit=4)
        multi = await repo.get_daily_last_n_bars_per_code(
            ["sh.pw"], end_d, max_bars=4
        )
    assert list(multi["sh.pw"]) == single
    assert [k.trade_date for k in single] == [
        date(2024, 11, 5),
        date(2024, 11, 6),
        date(2024, 11, 7),
        date(2024, 11, 8),
    ]


async def test_get_daily_last_n_bars_per_code_filters_end_date_and_orders(
    empty_sqlite_db,
):
    db = empty_sqlite_db
    async with db.session() as session:
        repo = KlineRepository(session)
        await repo.bulk_insert(
            [
                _k("sh.px", date(2024, 12, 1), close=1.0, pct_change=None),
                _k("sh.px", date(2024, 12, 10), close=2.0, pct_change=None),
                _k("sh.py", date(2024, 12, 1), close=10.0, pct_change=None),
                _k("sh.py", date(2024, 12, 5), close=11.0, pct_change=None),
            ]
        )
    end_d = date(2024, 12, 5)
    async with db.session() as session:
        repo = KlineRepository(session)
        m = await repo.get_daily_last_n_bars_per_code(
            ["sh.px", "sh.py"], end_d, max_bars=10
        )
    assert set(m.keys()) == {"sh.px", "sh.py"}
    assert [k.trade_date for k in m["sh.px"]] == [date(2024, 12, 1)]
    assert [k.trade_date for k in m["sh.py"]] == [
        date(2024, 12, 1),
        date(2024, 12, 5),
    ]


async def test_get_daily_last_n_bars_per_code_empty_codes(empty_sqlite_db):
    async with empty_sqlite_db.session() as session:
        m = await KlineRepository(session).get_daily_last_n_bars_per_code(
            [], date(2024, 1, 1), max_bars=5
        )
    assert m == {}


async def test_get_daily_last_n_bars_per_code_in_chunks_merge(
    empty_sqlite_db, monkeypatch
):
    monkeypatch.setattr("src.data.storage.repositories._KLINE_IN_CHUNK", 1)
    d = date(2024, 12, 20)
    async with empty_sqlite_db.session() as session:
        repo = KlineRepository(session)
        await repo.bulk_insert(
            [
                _k("sh.q1", d, close=1.0, pct_change=None),
                _k("sh.q2", d, close=2.0, pct_change=None),
                _k("sh.q3", d, close=3.0, pct_change=None),
            ]
        )
    async with empty_sqlite_db.session() as session:
        m = await KlineRepository(session).get_daily_last_n_bars_per_code(
            ["sh.q1", "sh.q2", "sh.q3"], d, max_bars=1
        )
    assert set(m) == {"sh.q1", "sh.q2", "sh.q3"}
    assert all(len(v) == 1 for v in m.values())


async def test_list_codes_on_trade_date_sorted_and_limit(empty_sqlite_db):
    db = empty_sqlite_db
    d = date(2024, 10, 15)
    async with db.session() as session:
        repo = KlineRepository(session)
        await repo.bulk_insert(
            [
                _k("sh.zz", d, close=1.0, pct_change=0.0),
                _k("sh.aa", d, close=1.0, pct_change=0.0),
                _k("sh.aa", date(2024, 9, 1), close=1.0, pct_change=0.0),
            ]
        )
    async with db.session() as session:
        repo = KlineRepository(session)
        all_c = await repo.list_codes_on_trade_date(d)
        assert all_c == ["sh.aa", "sh.zz"]
        one = await repo.list_codes_on_trade_date(d, max_codes=1)
        assert one == ["sh.aa"]
        unlimited = await repo.list_codes_on_trade_date(d, max_codes=0)
        assert unlimited == ["sh.aa", "sh.zz"]
    async with db.session() as session:
        empty = await KlineRepository(session).list_codes_on_trade_date(date(2020, 1, 1))
    assert empty == []
