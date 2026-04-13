"""``scripts/export_factor_cross_section.py``：临时 SQLite 库上的集成行为。"""

from __future__ import annotations

import csv
import importlib.util
from argparse import Namespace
from datetime import date
from pathlib import Path

import pytest

from src.data.models import KLine
from src.data.storage import KlineRepository


def _k(
    code: str,
    trade_date: date,
    *,
    close: float,
    pct_change: float | None = None,
) -> KLine:
    return KLine(
        code=code,
        trade_date=trade_date,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=100,
        amount=1000.0,
        turnover_rate=1.5,
        pct_change=pct_change,
    )


def _load_export_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "export_factor_cross_section.py"
    spec = importlib.util.spec_from_file_location("_export_factor_cross_section", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _args(**overrides) -> Namespace:
    base = dict(
        as_of_date="2024-06-10",
        period=2,
        max_codes=5000,
        codes_file=None,
        max_concurrent=4,
        legacy_per_code_fetch=False,
        auto_legacy_fallback=False,
        output="-",
        dry_run=False,
    )
    base.update(overrides)
    return Namespace(**base)


async def test_export_cross_section_batch_csv_row(empty_sqlite_db, tmp_path):
    mod = _load_export_module()
    db = empty_sqlite_db
    async with db.session() as session:
        await KlineRepository(session).bulk_insert(
            [_k("sh.tz", date(2024, 6, d), close=float(d)) for d in range(1, 12)]
        )

    outp = tmp_path / "cross.csv"
    rc = await mod._async_main(_args(output=str(outp), max_codes=10, period=2))
    assert rc == 0
    text = outp.read_text(encoding="utf-8")
    rows = list(csv.DictReader(text.splitlines()))
    assert len(rows) == 1
    r = rows[0]
    assert r["code"] == "sh.tz"
    assert float(r["close"]) == pytest.approx(10.0)
    assert int(r["meta_bars"]) == 3
    assert float(r["ret_2d"]) == pytest.approx((10.0 / 8.0 - 1.0) * 100.0)


async def test_export_cross_section_dry_run(empty_sqlite_db, capsys):
    mod = _load_export_module()
    db = empty_sqlite_db
    async with db.session() as session:
        await KlineRepository(session).bulk_insert(
            [_k("sh.dr", date(2024, 7, 1), close=1.0), _k("sh.dr", date(2024, 7, 2), close=2.0)]
        )

    rc = await mod._async_main(
        _args(as_of_date="2024-07-02", dry_run=True, max_codes=10, period=1)
    )
    assert rc == 0
    err = capsys.readouterr().err
    assert "[dry-run]" in err
    assert "标的数 1" in err


async def test_export_cross_section_legacy_matches_batch(empty_sqlite_db, tmp_path):
    mod = _load_export_module()
    db = empty_sqlite_db
    async with db.session() as session:
        await KlineRepository(session).bulk_insert(
            [_k("sh.lg", date(2024, 8, d), close=float(d)) for d in range(1, 8)]
        )
    p_batch = tmp_path / "b.csv"
    p_legacy = tmp_path / "l.csv"
    assert await mod._async_main(
        _args(
            as_of_date="2024-08-07",
            period=3,
            output=str(p_batch),
            max_codes=20,
        )
    ) == 0
    assert await mod._async_main(
        _args(
            as_of_date="2024-08-07",
            period=3,
            output=str(p_legacy),
            max_codes=20,
            legacy_per_code_fetch=True,
            max_concurrent=2,
        )
    ) == 0
    assert p_batch.read_text(encoding="utf-8") == p_legacy.read_text(encoding="utf-8")


async def test_export_cross_section_auto_legacy_fallback(
    empty_sqlite_db, tmp_path, monkeypatch, capsys
):
    mod = _load_export_module()
    db = empty_sqlite_db
    async with db.session() as session:
        await KlineRepository(session).bulk_insert(
            [_k("sh.fb", date(2024, 9, d), close=float(d)) for d in range(1, 6)]
        )

    async def _boom(self, codes, end_date, *, max_bars):
        raise RuntimeError("simulated batch failure")

    monkeypatch.setattr(
        "src.data.storage.repositories.KlineRepository.get_daily_last_n_bars_per_code",
        _boom,
    )
    outp = tmp_path / "fb.csv"
    rc = await mod._async_main(
        _args(
            as_of_date="2024-09-05",
            period=2,
            output=str(outp),
            max_codes=10,
            auto_legacy_fallback=True,
        )
    )
    assert rc == 0
    err = capsys.readouterr().err
    assert "[warn]" in err
    assert "--auto-legacy-fallback" in err
    rows = list(csv.DictReader(outp.read_text(encoding="utf-8").splitlines()))
    assert len(rows) == 1
    assert rows[0]["code"] == "sh.fb"


async def test_export_cross_section_batch_failure_exit_1_without_fallback(
    empty_sqlite_db, tmp_path, monkeypatch
):
    mod = _load_export_module()
    db = empty_sqlite_db
    async with db.session() as session:
        await KlineRepository(session).bulk_insert(
            [_k("sh.b1", date(2024, 11, d), close=float(d)) for d in range(1, 6)]
        )

    async def _boom(self, codes, end_date, *, max_bars):
        raise RuntimeError("simulated batch failure")

    monkeypatch.setattr(
        "src.data.storage.repositories.KlineRepository.get_daily_last_n_bars_per_code",
        _boom,
    )
    outp = tmp_path / "fail.csv"
    rc = await mod._async_main(
        _args(
            as_of_date="2024-11-05",
            period=2,
            output=str(outp),
            max_codes=10,
            auto_legacy_fallback=False,
        )
    )
    assert rc == 1
    assert not outp.exists()


async def test_export_cross_section_codes_file_and_comments(
    empty_sqlite_db, tmp_path
):
    """``--codes-file`` 支持 ``#`` 注释；当日无 K 的 code 不产生行。"""
    mod = _load_export_module()
    codes_path = tmp_path / "pool.txt"
    codes_path.write_text(
        "sh.cf\n# trailing\nsh.cg\n",
        encoding="utf-8",
    )
    db = empty_sqlite_db
    async with db.session() as session:
        r = KlineRepository(session)
        await r.bulk_insert(
            [_k("sh.cf", date(2024, 10, d), close=float(d)) for d in range(1, 9)]
        )
        await r.bulk_insert(
            [_k("sh.cg", date(2024, 10, d), close=1.0) for d in range(1, 6)]
        )

    outp = tmp_path / "cf.csv"
    rc = await mod._async_main(
        _args(
            as_of_date="2024-10-08",
            period=2,
            codes_file=str(codes_path),
            output=str(outp),
        )
    )
    assert rc == 0
    rows = list(csv.DictReader(outp.read_text(encoding="utf-8").splitlines()))
    assert len(rows) == 1
    assert rows[0]["code"] == "sh.cf"


async def test_export_cross_section_codes_file_only_comments_exit_2(
    empty_sqlite_db, tmp_path
):
    mod = _load_export_module()
    p = tmp_path / "noop.txt"
    p.write_text("# x\n  \n", encoding="utf-8")
    rc = await mod._async_main(
        _args(
            codes_file=str(p),
            as_of_date="2024-01-01",
            output=str(tmp_path / "o.csv"),
        )
    )
    assert rc == 2
