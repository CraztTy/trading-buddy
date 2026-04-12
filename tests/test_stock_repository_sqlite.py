"""StockRepository + SQLite（共用 conftest.empty_sqlite_db）。"""

from __future__ import annotations

from src.data.models import Market, StockInfo, StockType
from src.data.storage import StockRepository


def _stock(
    code: str,
    name: str,
    *,
    market: Market = Market.SH,
    industry: str | None = None,
    is_trading: bool = True,
    stock_type: StockType = StockType.COMMON,
) -> StockInfo:
    return StockInfo(
        code=code,
        name=name,
        market=market,
        stock_type=stock_type,
        industry=industry,
        sector_code=None,
        ipo_date=None,
        out_date=None,
        is_trading=is_trading,
    )


async def test_bulk_upsert_get_by_code_roundtrip(empty_sqlite_db):
    db = empty_sqlite_db
    async with db.session() as session:
        n = await StockRepository(session).bulk_upsert(
            [_stock("sh.x1", "测试甲", industry="银行")]
        )
        assert n == 1
    async with db.session() as session:
        s = await StockRepository(session).get_by_code("sh.x1")
    assert s is not None
    assert s.name == "测试甲"
    assert s.industry == "银行"
    assert s.market == Market.SH


async def test_get_by_code_unknown_returns_none(empty_sqlite_db):
    db = empty_sqlite_db
    async with db.session() as session:
        s = await StockRepository(session).get_by_code("sh.ghost")
    assert s is None


async def test_bulk_upsert_merge_updates_fields(empty_sqlite_db):
    db = empty_sqlite_db
    async with db.session() as session:
        r = StockRepository(session)
        await r.bulk_upsert([_stock("sh.x2", "旧名", industry="旧业")])
        await r.bulk_upsert([_stock("sh.x2", "新名", industry="新业")])
    async with db.session() as session:
        s = await StockRepository(session).get_by_code("sh.x2")
    assert s is not None
    assert s.name == "新名"
    assert s.industry == "新业"


async def test_get_name_map_fallback_to_code_when_name_empty(empty_sqlite_db):
    db = empty_sqlite_db
    async with db.session() as session:
        await StockRepository(session).bulk_upsert(
            [
                _stock("sh.n1", "有名字"),
                StockInfo(
                    code="sh.n2",
                    name="",
                    market=Market.SH,
                    stock_type=StockType.COMMON,
                    is_trading=True,
                ),
            ]
        )
    async with db.session() as session:
        m = await StockRepository(session).get_name_map(["sh.n1", "sh.n2", "sh.none"])
    assert m["sh.n1"] == "有名字"
    assert m["sh.n2"] == "sh.n2"
    assert "sh.none" not in m


async def test_get_name_map_empty_codes_returns_empty_dict(empty_sqlite_db):
    db = empty_sqlite_db
    async with db.session() as session:
        m = await StockRepository(session).get_name_map([])
    assert m == {}


async def test_get_all_codes_filters_by_market(empty_sqlite_db):
    db = empty_sqlite_db
    async with db.session() as session:
        r = StockRepository(session)
        await r.bulk_upsert(
            [
                _stock("sh.k1", "沪A", market=Market.SH),
                _stock("sz.k2", "深B", market=Market.SZ),
            ]
        )
    async with db.session() as session:
        r = StockRepository(session)
        sh_only = await r.get_all_codes(market="sh", is_trading=True)
        all_codes = await r.get_all_codes(market=None, is_trading=True)
    assert "sh.k1" in sh_only
    assert "sz.k2" not in sh_only
    assert "sh.k1" in all_codes and "sz.k2" in all_codes


async def test_get_all_codes_industry_prefix_and_market(empty_sqlite_db):
    db = empty_sqlite_db
    async with db.session() as session:
        r = StockRepository(session)
        await r.bulk_upsert(
            [
                _stock("sh.f1", "A", industry="新能源 整车", market=Market.SH),
                _stock("sz.f2", "B", industry="新能源材料", market=Market.SZ),
                _stock("sh.f3", "C", industry="银行", market=Market.SH),
            ]
        )
    async with db.session() as session:
        r = StockRepository(session)
        both = await r.get_all_codes(is_trading=True, industry="新能源")
        sh_only = await r.get_all_codes(
            market="sh", is_trading=True, industry="新能源"
        )
    assert set(both) == {"sh.f1", "sz.f2"}
    assert set(sh_only) == {"sh.f1"}


async def test_get_all_codes_stock_type_star(empty_sqlite_db):
    db = empty_sqlite_db
    async with db.session() as session:
        r = StockRepository(session)
        await r.bulk_upsert(
            [
                _stock("sh.st1", "科创", stock_type=StockType.STAR),
                _stock("sh.cm1", "主板", stock_type=StockType.COMMON),
            ]
        )
    async with db.session() as session:
        r = StockRepository(session)
        stars = await r.get_all_codes(is_trading=True, stock_type="star")
        bogus = await r.get_all_codes(is_trading=True, stock_type="not-a-type")
    assert set(stars) == {"sh.st1"}
    assert {"sh.st1", "sh.cm1"}.issubset(set(bogus))


async def test_get_by_industry_returns_all_matching_rows(empty_sqlite_db):
    db = empty_sqlite_db
    async with db.session() as session:
        r = StockRepository(session)
        await r.bulk_upsert(
            [
                _stock("sh.i1", "甲", industry="半导体"),
                _stock("sh.i2", "乙", industry="半导体"),
                _stock("sh.i3", "丙", industry="银行"),
            ]
        )
    async with db.session() as session:
        rows = await StockRepository(session).get_by_industry("半导体")
    codes = {s.code for s in rows}
    assert codes == {"sh.i1", "sh.i2"}
    assert len(rows) == 2
    assert all(s.industry == "半导体" for s in rows)
    assert {s.name for s in rows} == {"甲", "乙"}


async def test_get_by_industry_no_match_returns_empty_list(empty_sqlite_db):
    db = empty_sqlite_db
    async with db.session() as session:
        await StockRepository(session).bulk_upsert(
            [_stock("sh.i4", "丁", industry="保险")]
        )
    async with db.session() as session:
        rows = await StockRepository(session).get_by_industry("不存在的行业")
    assert rows == []


async def test_get_by_industry_prefix_matches_longer_label(empty_sqlite_db):
    db = empty_sqlite_db
    async with db.session() as session:
        await StockRepository(session).bulk_upsert(
            [_stock("sh.i5", "戊", industry="新能源 整车")]
        )
    async with db.session() as session:
        prefix = await StockRepository(session).get_by_industry("新能源")
        full = await StockRepository(session).get_by_industry("新能源 整车")
    assert len(prefix) == 1 and prefix[0].code == "sh.i5"
    assert len(full) == 1 and full[0].code == "sh.i5"


async def test_get_by_industry_whitespace_only_returns_empty(empty_sqlite_db):
    db = empty_sqlite_db
    async with db.session() as session:
        await StockRepository(session).bulk_upsert(
            [_stock("sh.i6", "己", industry="保险")]
        )
    async with db.session() as session:
        rows = await StockRepository(session).get_by_industry("   ")
    assert rows == []


async def test_get_by_industry_escapes_sql_wildcards_in_key(empty_sqlite_db):
    """用户输入含 % 时不应误当 LIKE 通配符。"""
    db = empty_sqlite_db
    async with db.session() as session:
        await StockRepository(session).bulk_upsert(
            [
                _stock("sh.w1", "A", industry="100%增长"),
                _stock("sh.w2", "B", industry="100x增长"),
            ]
        )
    async with db.session() as session:
        rows = await StockRepository(session).get_by_industry("100%")
    codes = {s.code for s in rows}
    assert codes == {"sh.w1"}


async def test_count_stock_codes_and_list_page_matches_get_all_slice(empty_sqlite_db):
    db = empty_sqlite_db
    async with db.session() as session:
        r = StockRepository(session)
        await r.bulk_upsert(
            [
                _stock(f"sh.dbpg{i}", f"名{i}", industry="DB分页测")
                for i in range(5)
            ]
        )
    async with db.session() as session:
        r = StockRepository(session)
        full = await r.get_all_codes(is_trading=True, industry="DB分页测")
        n = await r.count_stock_codes(is_trading=True, industry="DB分页测")
        p0 = await r.list_stock_codes_page(2, 0, is_trading=True, industry="DB分页测")
        p1 = await r.list_stock_codes_page(2, 2, is_trading=True, industry="DB分页测")
    assert n == len(full) == 5
    assert p0 == full[:2]
    assert p1 == full[2:4]
