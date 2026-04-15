"""LogSettings：LOG_JSON 等环境键。"""

from __future__ import annotations

import pytest

from src.common.config import LogSettings


def test_log_settings_json_logs_default() -> None:
    s = LogSettings()
    assert s.json_logs is False


@pytest.mark.parametrize("raw", ("true", "True", "1", "yes", "on"))
def test_log_settings_json_logs_truthy(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    monkeypatch.setenv("LOG_JSON", raw)
    assert LogSettings().json_logs is True


def test_log_settings_json_logs_explicit_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_JSON", "true")
    s = LogSettings(json_logs=False)
    assert s.json_logs is False
