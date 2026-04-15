"""APISettings.access_log（API_ACCESS_LOG）。"""

from __future__ import annotations

import pytest

from src.common.config import APISettings


def test_api_access_log_default() -> None:
    assert APISettings().access_log is False


@pytest.mark.parametrize("raw", ("true", "1", "yes", "on"))
def test_api_access_log_truthy(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    monkeypatch.setenv("API_ACCESS_LOG", raw)
    assert APISettings().access_log is True


def test_api_access_log_explicit_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_ACCESS_LOG", "true")
    s = APISettings(access_log=False)
    assert s.access_log is False


def test_access_log_ignore_prefixes_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("API_ACCESS_LOG_IGNORE_PREFIXES", raising=False)
    assert APISettings().access_log_ignore_prefixes == ("/health",)


def test_access_log_ignore_prefixes_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_ACCESS_LOG_IGNORE_PREFIXES", "none")
    assert APISettings().access_log_ignore_prefixes == ()


def test_access_log_ignore_prefixes_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_ACCESS_LOG_IGNORE_PREFIXES", "health, /api/x")
    assert APISettings().access_log_ignore_prefixes == ("/health", "/api/x")


def test_access_log_ignore_prefixes_explicit_overrides_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("API_ACCESS_LOG_IGNORE_PREFIXES", "/z")
    s = APISettings(access_log_ignore_prefixes=("/y",))
    assert s.access_log_ignore_prefixes == ("/y",)
