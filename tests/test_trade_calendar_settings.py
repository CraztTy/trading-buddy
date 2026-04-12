"""TRADE_CALENDAR_* 配置解析。"""

from __future__ import annotations

import pytest

from src.common.config import TradeCalendarSettings, get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_trade_calendar_default_options(monkeypatch):
    monkeypatch.delenv("TRADE_CALENDAR_EXCHANGE_OPTIONS", raising=False)
    monkeypatch.delenv("TRADE_CALENDAR_DEFAULT_EXCHANGE", raising=False)
    tc = TradeCalendarSettings()
    assert tc.exchange_option_values() == ["cn"]
    assert tc.resolved_default_exchange() == "cn"


def test_trade_calendar_csv_and_default(monkeypatch):
    monkeypatch.setenv("TRADE_CALENDAR_EXCHANGE_OPTIONS", "cn, hk ,us,cn")
    monkeypatch.setenv("TRADE_CALENDAR_DEFAULT_EXCHANGE", "us")
    tc = TradeCalendarSettings()
    assert tc.exchange_option_values() == ["cn", "hk", "us"]
    assert tc.resolved_default_exchange() == "us"


def test_trade_calendar_default_falls_back_to_first(monkeypatch):
    monkeypatch.setenv("TRADE_CALENDAR_EXCHANGE_OPTIONS", "hk,us")
    monkeypatch.setenv("TRADE_CALENDAR_DEFAULT_EXCHANGE", "xx")
    tc = TradeCalendarSettings()
    assert tc.resolved_default_exchange() == "hk"


def test_trade_calendar_empty_csv_becomes_cn(monkeypatch):
    monkeypatch.setenv("TRADE_CALENDAR_EXCHANGE_OPTIONS", ",,,")
    tc = TradeCalendarSettings()
    assert tc.exchange_option_values() == ["cn"]
