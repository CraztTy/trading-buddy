"""AccessLogMiddleware：忽略前缀不记 INFO。"""

from __future__ import annotations

from fastapi import FastAPI
from loguru import logger
from starlette.testclient import TestClient

from src.api.access_log_middleware import AccessLogMiddleware


def _capture_access_info():
    lines: list[str] = []

    def sink(message) -> None:
        line = str(message)
        if "http.access" in line or "GET " in line:
            if "GET " in line and "ms id=" in line:
                lines.append(line)

    lid = logger.add(sink, level="INFO")
    return lines, lid


def test_access_log_middleware_skips_ignored_prefix():
    app = FastAPI()

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/api/x")
    def api_x():
        return {"ok": True}

    app.add_middleware(AccessLogMiddleware, ignore_prefixes=("/health",))
    lines, lid = _capture_access_info()
    try:
        with TestClient(app) as client:
            assert client.get("/health").status_code == 200
            assert client.get("/api/x").status_code == 200
    finally:
        logger.remove(lid)
    assert len(lines) == 1
    assert "/api/x" in lines[0]
    assert "/health" not in lines[0]
