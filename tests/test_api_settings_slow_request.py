"""APISettings.slow_request_warn_ms（API_SLOW_REQUEST_WARN_MS）。"""

from __future__ import annotations

import pytest

from src.common.config import APISettings


def test_slow_request_warn_ms_default() -> None:
    assert APISettings().slow_request_warn_ms == 0


@pytest.mark.parametrize("raw,expected", (("100", 100), ("0", 0), (" 500 ", 500)))
def test_slow_request_warn_ms_from_env(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: int
) -> None:
    monkeypatch.setenv("API_SLOW_REQUEST_WARN_MS", raw)
    assert APISettings().slow_request_warn_ms == expected


def test_slow_request_warn_ms_caps_at_one_hour(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_SLOW_REQUEST_WARN_MS", "999999999")
    assert APISettings().slow_request_warn_ms == 3_600_000


def test_slow_request_warn_ms_invalid_env_falls_back_to_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("API_SLOW_REQUEST_WARN_MS", "not-int")
    assert APISettings().slow_request_warn_ms == 0


def test_slow_request_warn_ms_explicit_overrides_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("API_SLOW_REQUEST_WARN_MS", "5000")
    s = APISettings(slow_request_warn_ms=100)
    assert s.slow_request_warn_ms == 100


def test_slow_request_ignore_prefixes_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("API_SLOW_REQUEST_IGNORE_PREFIXES", raising=False)
    assert APISettings().slow_request_ignore_prefixes == ("/health",)


def test_slow_request_ignore_prefixes_none_disables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_SLOW_REQUEST_IGNORE_PREFIXES", "none")
    assert APISettings().slow_request_ignore_prefixes == ()


def test_slow_request_ignore_prefixes_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_SLOW_REQUEST_IGNORE_PREFIXES", "health, /docs/")
    s = APISettings()
    assert s.slow_request_ignore_prefixes == ("/health", "/docs/")


def test_slow_request_ignore_prefixes_explicit_overrides_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("API_SLOW_REQUEST_IGNORE_PREFIXES", "/x")
    s = APISettings(slow_request_ignore_prefixes=("/y",))
    assert s.slow_request_ignore_prefixes == ("/y",)
