"""pytest 入口：须在首次 import src.* 之前生效。"""

from __future__ import annotations

import os

import pytest_asyncio

os.environ["TRADING_BUDDY_SKIP_DOTENV"] = "1"


@pytest_asyncio.fixture
async def empty_sqlite_db(tmp_path, monkeypatch):
    """独立 SQLite 文件 + 全表结构；每用例 `tmp_path` 不同，互不污染。"""
    from src.common.config import get_settings
    from src.data.storage import dispose_database, get_database

    monkeypatch.setenv("DATABASE_MODE", "sqlite")
    monkeypatch.setenv("DATABASE_SQLITE_PATH", str(tmp_path / "pytest_isolated.db"))
    get_settings.cache_clear()
    await dispose_database()
    db = get_database()
    await db.create_tables()
    yield db
    await dispose_database()
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def http_test_client(empty_sqlite_db):
    """FastAPI TestClient，`get_session` 绑定到当前用例的临时库。"""
    from fastapi.testclient import TestClient

    from src.api.main import app
    from src.data.storage import get_session

    db = empty_sqlite_db

    async def override_get_session():
        async for session in db.get_session():
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
