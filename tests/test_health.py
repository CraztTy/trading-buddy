"""API /health；依赖 lifespan 时可能因 Redis 等不可达而 skip。"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_health_json_shape():
    from fastapi.testclient import TestClient

    from src.api.main import app

    try:
        with TestClient(app) as client:
            r = client.get("/health")
    except Exception as e:
        pytest.skip(f"TestClient 启动失败（检查 .env / Redis）: {e}")

    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "healthy"
    assert "database_mode" in data
    assert "redis_enabled" in data

    rr = client.get("/health/ready")
    assert rr.status_code == 200, rr.text
    ready = rr.json()
    assert ready.get("status") == "ready"
    assert ready.get("database") == "ok"
