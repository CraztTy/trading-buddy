#!/usr/bin/env python3
"""
验证当前 .env：MySQL / Redis 是否按配置工作，并冒烟测试核心 API 路由。
用法（项目根目录）: python scripts/verify_stack.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


async def _mysql_counts() -> tuple[int, int]:
    from sqlalchemy import func, select

    from src.data.storage import dispose_database, get_database
    from src.data.storage.models import DailyKlineModel, StockInfoModel

    db = get_database()
    try:
        async with db.session() as session:
            ns = await session.scalar(select(func.count()).select_from(StockInfoModel))
            nk = await session.scalar(select(func.count()).select_from(DailyKlineModel))
            return int(ns or 0), int(nk or 0)
    finally:
        await dispose_database()


def _redis_probe() -> dict:
    from src.common import get_settings
    import redis

    s = get_settings()
    if not s.redis.enabled:
        return {"enabled": False, "ok": None, "sample_keys": 0}
    r = redis.Redis(
        host=s.redis.host,
        port=s.redis.port,
        db=s.redis.db,
        password=s.redis.password or None,
        decode_responses=True,
        socket_connect_timeout=5,
    )
    try:
        r.ping()
        sample = 0
        for _ in r.scan_iter(match="tb:stkname:*", count=200):
            sample += 1
            if sample >= 500:
                break
        return {"enabled": True, "ok": True, "sample_keys": sample, "host": s.redis.host}
    except Exception as e:
        return {"enabled": True, "ok": False, "error": str(e)}
    finally:
        r.close()


def _api_routes() -> list[tuple[str, int]]:
    from fastapi.testclient import TestClient

    from src.api.main import app

    out: list[tuple[str, int]] = []
    with TestClient(app) as client:
        for path in (
            "/health",
            "/health/ready",
            "/api/dashboard/overview",
            "/api/dashboard/gainers?limit=3",
            "/api/dashboard/losers?limit=3",
            "/api/stocks/list",
        ):
            r = client.get(path)
            out.append((path, r.status_code))
    return out


def main() -> int:
    from src.common import get_settings

    s = get_settings()
    print("=== 配置 ===")
    print(f"  DATABASE_MODE: {s.database.mode}")
    print(f"  MySQL 目标: {s.database.user}@{s.database.host}:{s.database.port}/{s.database.name}")
    print(f"  REDIS_ENABLED: {s.redis.enabled}")
    if s.redis.enabled:
        print(f"  Redis 目标: {s.redis.host}:{s.redis.port} db={s.redis.db}")

    if s.database.mode != "mysql":
        print("\n[FAIL] 期望 DATABASE_MODE=mysql，请检查 .env")
        return 1

    print("\n=== MySQL ===")
    try:
        ns, nk = asyncio.run(_mysql_counts())
        print(f"  stock_info 行数: {ns}")
        print(f"  daily_kline 行数: {nk}")
        print("  [OK] 已连上 MySQL 并完成计数")
    except Exception as e:
        print(f"  [FAIL] {e}")
        return 1

    print("\n=== Redis ===")
    rp = _redis_probe()
    if not rp["enabled"]:
        print("  [SKIP] REDIS_ENABLED=false，名称缓存仅走 DB 批量查询")
    elif rp.get("ok"):
        print(f"  PING 成功；tb:stkname:* 键数量约: {rp.get('sample_keys', 0)}")
        print("  [OK] Redis 可用")
    else:
        print(f"  [FAIL] {rp.get('error', rp)}")
        return 1

    print("\n=== API 冒烟 (TestClient) ===")
    try:
        for path, code in _api_routes():
            tag = "OK" if code == 200 else "FAIL"
            print(f"  [{tag}] {path} -> {code}")
            if code != 200:
                return 1
    except Exception as e:
        print(f"  [FAIL] {e}")
        return 1

    print("\n=== 汇总 ===")
    print("  MySQL: 使用中（仓储与看板数据）")
    if s.redis.enabled:
        print("  Redis: 已启用（股票名称缓存等依赖 app.state.redis）")
    else:
        print("  Redis: 未启用")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
