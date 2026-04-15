"""SlowRequestWarningMiddleware：超过阈值打 WARN。"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from loguru import logger
from starlette.testclient import TestClient

from src.api.slow_request_middleware import SlowRequestWarningMiddleware


@pytest.fixture
def slow_warn_app():
    app = FastAPI()

    @app.get("/fast")
    async def fast():
        return {"ok": True}

    @app.get("/slow")
    async def slow():
        await asyncio.sleep(0.05)
        return {"ok": True}

    app.add_middleware(
        SlowRequestWarningMiddleware, threshold_ms=30, ignore_prefixes=()
    )
    return app


@pytest.fixture
def slow_warn_app_with_ignore():
    app = FastAPI()

    @app.get("/slow")
    async def slow():
        await asyncio.sleep(0.05)
        return {"ok": True}

    app.add_middleware(
        SlowRequestWarningMiddleware, threshold_ms=30, ignore_prefixes=("/slow",)
    )
    return app


def _capture_slow_warnings():
    msgs: list[str] = []

    def sink(message) -> None:
        line = str(message)
        if "slow_request" in line and "WARNING" in line:
            msgs.append(line)

    lid = logger.add(sink, level="WARNING")
    return msgs, lid


def test_slow_request_middleware_warns_on_slow_route(slow_warn_app):
    msgs, lid = _capture_slow_warnings()
    try:
        with TestClient(slow_warn_app) as client:
            r = client.get("/slow")
    finally:
        logger.remove(lid)
    assert r.status_code == 200
    assert msgs
    assert "slow_request" in msgs[0]


def test_slow_request_middleware_silent_on_fast_route(slow_warn_app):
    msgs, lid = _capture_slow_warnings()
    try:
        with TestClient(slow_warn_app) as client:
            r = client.get("/fast")
    finally:
        logger.remove(lid)
    assert r.status_code == 200
    assert not msgs


def test_slow_request_middleware_respects_ignore_prefix(slow_warn_app_with_ignore):
    msgs, lid = _capture_slow_warnings()
    try:
        with TestClient(slow_warn_app_with_ignore) as client:
            r = client.get("/slow")
    finally:
        logger.remove(lid)
    assert r.status_code == 200
    assert not msgs
