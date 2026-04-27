"""
认证 API HTTP 测试：注册、登录、获取当前用户、无 token 免登
"""

from __future__ import annotations

import pytest


async def test_register_success(http_test_client, empty_sqlite_db):
    r = http_test_client.post(
        "/api/auth/register",
        json={"username": "testuser", "password": "secret123"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["id"] == 1
    assert body["username"] == "testuser"


async def test_register_duplicate_username_409(http_test_client, empty_sqlite_db):
    http_test_client.post(
        "/api/auth/register",
        json={"username": "dupuser", "password": "secret123"},
    )
    r = http_test_client.post(
        "/api/auth/register",
        json={"username": "dupuser", "password": "anotherpass"},
    )
    assert r.status_code == 409
    assert "已存在" in r.json().get("detail", "")


async def test_login_success(http_test_client, empty_sqlite_db):
    http_test_client.post(
        "/api/auth/register",
        json={"username": "loginuser", "password": "mypassword"},
    )
    r = http_test_client.post(
        "/api/auth/login",
        json={"username": "loginuser", "password": "mypassword"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert body["username"] == "loginuser"


async def test_login_wrong_password_401(http_test_client, empty_sqlite_db):
    http_test_client.post(
        "/api/auth/register",
        json={"username": "wrongpass", "password": "correctpass"},
    )
    r = http_test_client.post(
        "/api/auth/login",
        json={"username": "wrongpass", "password": "badpass"},
    )
    assert r.status_code == 401


async def test_me_with_valid_token(http_test_client, empty_sqlite_db):
    http_test_client.post(
        "/api/auth/register",
        json={"username": "meuser", "password": "mypassword"},
    )
    login_r = http_test_client.post(
        "/api/auth/login",
        json={"username": "meuser", "password": "mypassword"},
    )
    token = login_r.json()["access_token"]

    r = http_test_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == 1
    assert body["username"] == "meuser"
    assert body["is_active"] is True


async def test_me_without_token_auth_required_false(http_test_client, empty_sqlite_db, monkeypatch):
    """AUTH_REQUIRED=false（默认）时，无 token 应返回系统用户 id=0。"""
    # 确保 AUTH_REQUIRED 为 false
    monkeypatch.setenv("AUTH_REQUIRED", "false")
    from src.common.config import get_settings

    get_settings.cache_clear()

    r = http_test_client.get("/api/auth/me")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == 0
    assert body["username"] == "system"
    assert body["is_active"] is True


async def test_me_without_token_auth_required_true_401(http_test_client, empty_sqlite_db, monkeypatch):
    """AUTH_REQUIRED=true 时，无 token 应返回 401。"""
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    from src.common.config import get_settings

    get_settings.cache_clear()

    r = http_test_client.get("/api/auth/me")
    assert r.status_code == 401


async def test_register_username_too_short(http_test_client, empty_sqlite_db):
    r = http_test_client.post(
        "/api/auth/register",
        json={"username": "ab", "password": "secret123"},
    )
    assert r.status_code == 422


async def test_register_password_too_short(http_test_client, empty_sqlite_db):
    r = http_test_client.post(
        "/api/auth/register",
        json={"username": "validuser", "password": "12345"},
    )
    assert r.status_code == 422


async def test_register_username_invalid_chars(http_test_client, empty_sqlite_db):
    r = http_test_client.post(
        "/api/auth/register",
        json={"username": "user-name!", "password": "secret123"},
    )
    assert r.status_code == 422
