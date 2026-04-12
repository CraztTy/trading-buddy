"""就绪探针 HTTP：/health/ready 依赖真实 get_database() 会话。"""

from __future__ import annotations


class _BadSessionCM:
    async def __aenter__(self):
        raise RuntimeError("db probe failed")

    async def __aexit__(self, exc_type, exc, tb):
        return None


class _BadDb:
    def session(self):
        return _BadSessionCM()


async def test_health_shallow_200(http_test_client):
    r = http_test_client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "healthy"
    assert "app_version" in body
    assert body["database_mode"] == "sqlite"
    assert body["redis_enabled"] is False


async def test_root_200(http_test_client):
    r = http_test_client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Trading Buddy API"
    assert body["status"] == "running"
    assert "version" in body


async def test_health_ready_200(http_test_client):
    r = http_test_client.get("/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert body["database"] == "ok"
    assert body["redis"] == "skipped"


async def test_health_ready_503_when_db_fails(http_test_client, monkeypatch):
    monkeypatch.setattr("src.api.main.get_database", lambda: _BadDb())

    r = http_test_client.get("/health/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "not_ready"
    assert body["database"] == "error"
    assert "database_error" in body


async def test_health_ready_redis_ping_ok(http_test_client, monkeypatch):
    """配置视为启用 Redis 时，使用 app.state 上的客户端参与就绪判断。"""
    import src.api.main as main_mod
    from src.common.config import get_settings

    real = get_settings()
    patched = real.model_copy(
        update={"redis": real.redis.model_copy(update={"enabled": True})}
    )
    monkeypatch.setattr(main_mod, "get_settings", lambda: patched)

    class FakeRedis:
        async def ping(self):
            return True

    app = http_test_client.app
    prev = getattr(app.state, "redis", None)
    app.state.redis = FakeRedis()
    try:
        r = http_test_client.get("/health/ready")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ready"
        assert body["database"] == "ok"
        assert body["redis"] == "ok"
    finally:
        app.state.redis = prev


async def test_health_ready_redis_uninitialized_503(http_test_client, monkeypatch):
    """Redis 在配置中启用但进程内无客户端时，就绪探针为 not_ready / 503。"""
    import src.api.main as main_mod
    from src.common.config import get_settings

    real = get_settings()
    patched = real.model_copy(
        update={"redis": real.redis.model_copy(update={"enabled": True})}
    )
    monkeypatch.setattr(main_mod, "get_settings", lambda: patched)
    monkeypatch.setattr(main_mod, "get_redis_client", lambda: None)

    app = http_test_client.app
    prev = getattr(app.state, "redis", None)
    if hasattr(app.state, "redis"):
        delattr(app.state, "redis")
    try:
        r = http_test_client.get("/health/ready")
        assert r.status_code == 503
        body = r.json()
        assert body["status"] == "not_ready"
        assert body["database"] == "ok"
        assert body["redis"] == "uninitialized"
        assert "redis_error" in body
    finally:
        if prev is not None:
            app.state.redis = prev


async def test_health_ready_redis_ping_error_503(http_test_client, monkeypatch):
    """Redis 已挂载但 PING 失败时，就绪探针为 not_ready / 503。"""
    import src.api.main as main_mod
    from src.common.config import get_settings

    real = get_settings()
    patched = real.model_copy(
        update={"redis": real.redis.model_copy(update={"enabled": True})}
    )
    monkeypatch.setattr(main_mod, "get_settings", lambda: patched)

    class FlakyRedis:
        async def ping(self):
            raise RuntimeError("ping refused")

    app = http_test_client.app
    prev = getattr(app.state, "redis", None)
    app.state.redis = FlakyRedis()
    try:
        r = http_test_client.get("/health/ready")
        assert r.status_code == 503
        body = r.json()
        assert body["status"] == "not_ready"
        assert body["database"] == "ok"
        assert body["redis"] == "error"
        assert "redis_error" in body
        assert "ping refused" in body["redis_error"]
    finally:
        app.state.redis = prev
