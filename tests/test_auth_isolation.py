"""
用户数据隔离 HTTP 测试：
- User A 的纸交易、回测存档、自选股，User B 不可见。
- 系统用户（AUTH_REQUIRED=false）行为兼容。
"""

from __future__ import annotations

from datetime import date, timedelta

from src.data.models import KLine
from src.data.storage import KlineRepository


def _bar(code: str, d: date, close: float) -> KLine:
    o = close - 0.1
    return KLine(
        code=code,
        trade_date=d,
        open=o,
        high=close + 0.2,
        low=o - 0.1,
        close=close,
        volume=1000,
        amount=close * 1000,
        turnover_rate=None,
        pct_change=None,
    )


def _register_user(client, username: str, password: str = "secret123") -> dict:
    r = client.post("/api/auth/register", json={"username": username, "password": password})
    assert r.status_code == 201, f"register failed: {r.text}"
    return r.json()


def _login_user(client, username: str, password: str = "secret123") -> str:
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, f"login failed: {r.text}"
    return r.json()["access_token"]


# ---------------------------------------------------------------------------
# Paper trading isolation
# ---------------------------------------------------------------------------


async def test_paper_trade_isolated_between_users(http_test_client, empty_sqlite_db):
    """User A 下单后，User B 看不到 A 的持仓和订单。"""
    client = http_test_client
    code = "sh.iso1"
    base = date(2025, 6, 1)
    rows = [_bar(code, base + timedelta(days=i), 10.0) for i in range(5)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    # 创建两个用户
    _register_user(client, "papera")
    _register_user(client, "paperb")
    token_a = _login_user(client, "papera")
    token_b = _login_user(client, "paperb")

    # User A 买入
    r_buy = client.post(
        "/api/paper/orders",
        json={"code": code, "side": "buy", "quantity": 100},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert r_buy.status_code == 200

    # User A 能看到持仓
    st_a = client.get("/api/paper/state", headers={"Authorization": f"Bearer {token_a}"})
    assert st_a.status_code == 200
    assert len(st_a.json()["positions"]) == 1
    assert st_a.json()["positions"][0]["quantity"] == 100

    # User B 看不到持仓
    st_b = client.get("/api/paper/state", headers={"Authorization": f"Bearer {token_b}"})
    assert st_b.status_code == 200
    assert st_b.json()["positions"] == []
    assert st_b.json()["account"]["cash"] == 1_000_000.0

    # User B 的订单列表为空
    ord_b = client.get("/api/paper/orders", headers={"Authorization": f"Bearer {token_b}"})
    assert ord_b.json()["total"] == 0

    # User A 的订单列表有 1 条
    ord_a = client.get("/api/paper/orders", headers={"Authorization": f"Bearer {token_a}"})
    assert ord_a.json()["total"] == 1


async def test_paper_account_list_isolated(http_test_client, empty_sqlite_db):
    """User A 创建命名账户，User B 看不到。"""
    client = http_test_client
    _register_user(client, "acct_a")
    _register_user(client, "acct_b")
    token_a = _login_user(client, "acct_a")
    token_b = _login_user(client, "acct_b")

    # User A 创建命名账户
    r = client.post(
        "/api/paper/account/create",
        json={"label": "mystrategy", "initial_cash": 500000.0},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert r.status_code == 200

    # User A 能看到 mystrategy（default 是懒创建的，未访问过则不列出）
    lst_a = client.get("/api/paper/accounts", headers={"Authorization": f"Bearer {token_a}"})
    assert lst_a.status_code == 200
    labels_a = {a["label"] for a in lst_a.json()["items"]}
    assert labels_a == {"mystrategy"}

    # User B 无账户（未创建过）
    lst_b = client.get("/api/paper/accounts", headers={"Authorization": f"Bearer {token_b}"})
    assert lst_b.status_code == 200
    labels_b = {a["label"] for a in lst_b.json()["items"]}
    assert labels_b == set()


async def test_paper_reset_only_affects_current_user(http_test_client, empty_sqlite_db):
    """User A reset 不影响 User B 的账户。"""
    client = http_test_client
    code = "sh.isorst"
    base = date(2025, 6, 1)
    rows = [_bar(code, base + timedelta(days=i), 10.0) for i in range(5)]
    async with empty_sqlite_db.session() as session:
        await KlineRepository(session).bulk_insert(rows)

    _register_user(client, "rst_a")
    _register_user(client, "rst_b")
    token_a = _login_user(client, "rst_a")
    token_b = _login_user(client, "rst_b")

    # 两人都买入
    for tok in (token_a, token_b):
        r = client.post(
            "/api/paper/orders",
            json={"code": code, "side": "buy", "quantity": 100},
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 200

    # User A reset
    client.post(
        "/api/paper/account/reset",
        json={"account_label": "default"},
        headers={"Authorization": f"Bearer {token_a}"},
    )

    # User A 持仓清空
    st_a = client.get("/api/paper/state", headers={"Authorization": f"Bearer {token_a}"})
    assert st_a.json()["positions"] == []

    # User B 持仓仍在
    st_b = client.get("/api/paper/state", headers={"Authorization": f"Bearer {token_b}"})
    assert len(st_b.json()["positions"]) == 1


# ---------------------------------------------------------------------------
# Backtest archive isolation
# ---------------------------------------------------------------------------


def _single_payload():
    return {
        "kind": "ma_cross_single",
        "request_params": {"code": "sh.000001", "fast": 5, "slow": 20, "limit": 120},
        "response_payload": {
            "code": "sh.000001",
            "fast_period": 5,
            "slow_period": 20,
            "bars_used": 120,
            "total_return_pct": 1.5,
            "buy_hold_return_pct": 0.8,
            "equity_curve": [],
            "note": "test",
        },
    }


async def test_backtest_archive_isolated_between_users(http_test_client, empty_sqlite_db):
    """User A 保存回测存档，User B 看不到。"""
    client = http_test_client
    _register_user(client, "bta")
    _register_user(client, "btb")
    token_a = _login_user(client, "bta")
    token_b = _login_user(client, "btb")

    # User A 保存存档
    r = client.post(
        "/api/backtest/runs",
        json=_single_payload(),
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert r.status_code == 201
    run_id = r.json()["id"]

    # User A 能看到
    lst_a = client.get("/api/backtest/runs", headers={"Authorization": f"Bearer {token_a}"})
    assert lst_a.json()["total"] == 1
    assert lst_a.json()["items"][0]["id"] == run_id

    # User B 看不到
    lst_b = client.get("/api/backtest/runs", headers={"Authorization": f"Bearer {token_b}"})
    assert lst_b.json()["total"] == 0

    # User B 访问详情返回 404
    det_b = client.get(f"/api/backtest/runs/{run_id}", headers={"Authorization": f"Bearer {token_b}"})
    assert det_b.status_code == 404

    # User B 删除返回 404
    del_b = client.delete(f"/api/backtest/runs/{run_id}", headers={"Authorization": f"Bearer {token_b}"})
    assert del_b.status_code == 404

    # User A 访问详情成功
    det_a = client.get(f"/api/backtest/runs/{run_id}", headers={"Authorization": f"Bearer {token_a}"})
    assert det_a.status_code == 200


# ---------------------------------------------------------------------------
# Watchlist isolation
# ---------------------------------------------------------------------------


async def test_watchlist_isolated_between_users(http_test_client, empty_sqlite_db):
    """User A 添加自选股，User B 看不到。"""
    client = http_test_client
    _register_user(client, "wla")
    _register_user(client, "wlb")
    token_a = _login_user(client, "wla")
    token_b = _login_user(client, "wlb")

    # User A 添加
    r = client.post(
        "/api/watchlist/items",
        json={"code": "sh.600000"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert r.status_code == 201

    # User A 能看到
    lst_a = client.get("/api/watchlist/items", headers={"Authorization": f"Bearer {token_a}"})
    assert len(lst_a.json()["items"]) == 1
    assert lst_a.json()["items"][0]["code"] == "sh.600000"

    # User B 看不到
    lst_b = client.get("/api/watchlist/items", headers={"Authorization": f"Bearer {token_b}"})
    assert lst_b.json()["items"] == []

    # User B 删除返回 404
    del_b = client.delete("/api/watchlist/items/sh.600000", headers={"Authorization": f"Bearer {token_b}"})
    assert del_b.status_code == 404

    # User A 删除成功
    del_a = client.delete("/api/watchlist/items/sh.600000", headers={"Authorization": f"Bearer {token_a}"})
    assert del_a.status_code == 200


# ---------------------------------------------------------------------------
# System user backward compatibility
# ---------------------------------------------------------------------------


async def test_system_user_sees_legacy_data(http_test_client, empty_sqlite_db, monkeypatch):
    """AUTH_REQUIRED=false 时，无 token 的系统用户仍能看到 user_id=NULL 的旧数据。"""
    client = http_test_client
    # 确保 AUTH_REQUIRED=false（默认）
    monkeypatch.setenv("AUTH_REQUIRED", "false")
    from src.common.config import get_settings

    get_settings.cache_clear()

    # 系统用户（无 token）保存存档
    r = client.post("/api/backtest/runs", json=_single_payload())
    assert r.status_code == 201

    # 系统用户能查到
    lst = client.get("/api/backtest/runs")
    assert lst.json()["total"] == 1

    # 系统用户添加自选股
    r2 = client.post("/api/watchlist/items", json={"code": "sh.600001"})
    assert r2.status_code == 201
    wl = client.get("/api/watchlist/items")
    assert len(wl.json()["items"]) == 1

    # 系统用户纸交易状态
    st = client.get("/api/paper/state")
    assert st.status_code == 200
    assert st.json()["account"]["label"] == "default"
