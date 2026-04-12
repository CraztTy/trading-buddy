"""交易日历门控 B+D（纯 dict 逻辑）。"""

from __future__ import annotations

from datetime import date

from src.data.quality.trade_calendar_gate import evaluate_trade_calendar_gate


def _rk(trade_date_max: str | None) -> dict:
    return {"trade_date_max": trade_date_max}


def _rg(
    *,
    enabled: bool,
    gap_exchange: str | None,
    row_count: int,
    date_max: str | None,
) -> dict:
    return {
        "enabled": enabled,
        "gap_exchange": gap_exchange,
        "trading_calendar_row_count": row_count,
        "trading_calendar_date_max": date_max,
    }


def test_gate_skipped_when_gap_exchange_none():
    ok, msgs = evaluate_trade_calendar_gate(
        _rk("2026-04-01"),
        _rg(enabled=True, gap_exchange=None, row_count=0, date_max=None),
        grace_days=7,
        today=date(2026, 4, 11),
    )
    assert ok and msgs == []


def test_gate_skipped_when_sample_disabled():
    ok, msgs = evaluate_trade_calendar_gate(
        _rk("2026-04-01"),
        _rg(enabled=False, gap_exchange="cn", row_count=0, date_max=None),
        grace_days=7,
        today=date(2026, 4, 11),
    )
    assert ok and msgs == []


def test_gate_fails_when_no_calendar_rows():
    ok, msgs = evaluate_trade_calendar_gate(
        _rk("2026-04-10"),
        _rg(enabled=True, gap_exchange="cn", row_count=0, date_max=None),
        grace_days=7,
        today=date(2026, 4, 11),
    )
    assert not ok
    assert any("无行数" in m for m in msgs)


def test_gate_fails_when_date_max_stale():
    ok, msgs = evaluate_trade_calendar_gate(
        _rk("2026-04-10"),
        _rg(enabled=True, gap_exchange="cn", row_count=100, date_max="2026-03-01"),
        grace_days=7,
        today=date(2026, 4, 11),
    )
    assert not ok
    assert any("早于要求下界" in m for m in msgs)


def test_gate_ok_when_calendar_covers():
    ok, msgs = evaluate_trade_calendar_gate(
        _rk("2026-04-10"),
        _rg(enabled=True, gap_exchange="cn", row_count=100, date_max="2026-04-09"),
        grace_days=7,
        today=date(2026, 4, 11),
    )
    assert ok and msgs == []


def test_gate_reference_caps_future_kline_max():
    """日 K max 晚于 today 时参考日取 today。"""
    ok, msgs = evaluate_trade_calendar_gate(
        _rk("2030-01-01"),
        _rg(enabled=True, gap_exchange="cn", row_count=10, date_max="2026-04-10"),
        grace_days=7,
        today=date(2026, 4, 11),
    )
    assert ok and msgs == []
