#!/usr/bin/env python3
"""
MySQL 模式冒烟测试：建表 + 可选 mock 写入少量数据。
使用前设置 DATABASE_MODE=mysql 及 DB_* / DATABASE_*（或项目根目录 .env）。

PowerShell 示例:
  $env:DATABASE_MODE="mysql"
  $env:DB_HOST="127.0.0.1"
  $env:DB_USER="root"
  $env:DB_PASSWORD="你的密码"
  $env:DB_NAME="trading"
  python scripts/smoke_mysql.py
  python scripts/smoke_mysql.py --fetch-mock
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(project_root))


async def main(fetch_mock: bool) -> None:
    from sqlalchemy import text

    from src.common import get_logger, get_settings
    from src.data.storage import dispose_database, get_database

    log = get_logger("smoke_mysql")
    s = get_settings()
    if s.database.mode != "mysql":
        raise SystemExit(
            f"当前 database.mode={s.database.mode!r}，请设置 DATABASE_MODE=mysql 后再运行"
        )

    log.info("MySQL 目标: %s@%s:%s/%s" % (s.database.user, s.database.host, s.database.port, s.database.name))

    db = get_database()
    try:
        try:
            await db.create_tables()
            log.info("create_tables 成功")
            async with db.session() as session:
                await session.execute(text("SELECT 1"))
            log.info("SELECT 1 成功")
        except Exception as e:
            log.error(
                "无法连接或初始化 MySQL。请确认: 1) mysqld 已启动且端口正确 "
                "2) 已执行 CREATE DATABASE %s; 3) 用户有建表权限 4) DB_HOST/DB_PASSWORD 等环境变量正确。详情: %s",
                s.database.name,
                e,
            )
            raise SystemExit(1) from e
    finally:
        await dispose_database()

    if fetch_mock:
        cmd = [
            sys.executable,
            str(project_root / "scripts" / "fetch_data.py"),
            "--source",
            "mock",
            "--mode",
            "all",
            "--limit",
            "2",
            "--days",
            "5",
            "--index-days",
            "30",
        ]
        log.info("运行: %s", " ".join(cmd))
        r = subprocess.run(cmd, cwd=str(project_root))
        raise SystemExit(r.returncode)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--fetch-mock",
        action="store_true",
        help="建表后再跑一小段 mock 拉数",
    )
    args = ap.parse_args()
    asyncio.run(main(args.fetch_mock))
