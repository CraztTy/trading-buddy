#!/usr/bin/env python3
"""
迁移脚本：为迭代 2/5/6 新增的 user_id 字段补充 MySQL 表结构。
检查并添加缺失的列，兼容已存在的情况（幂等）。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from src.common.config import get_settings
from src.data.storage.database import Database


# (表名, 列名, 列定义)
MIGRATIONS = [
    ("watchlist", "user_id", "INT NULL DEFAULT NULL"),
    ("paper_account", "user_id", "INT NULL DEFAULT NULL"),
    ("paper_account", "name", "VARCHAR(64) NULL DEFAULT NULL"),
    ("backtest_run", "user_id", "INT NULL DEFAULT NULL"),
    ("risk_rule", "user_id", "INT NULL DEFAULT NULL"),
    ("risk_event", "user_id", "INT NULL DEFAULT NULL"),
]


async def main() -> None:
    settings = get_settings()
    if settings.database.mode != "mysql":
        print("当前数据库模式不是 MySQL，无需迁移。")
        return

    db = Database()
    async with db._engine.connect() as conn:
        for table, column, definition in MIGRATIONS:
            # 检查列是否已存在
            check_sql = text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = DATABASE() AND table_name = :table AND column_name = :column"
            )
            result = await conn.execute(check_sql, {"table": table, "column": column})
            exists = result.scalar() is not None

            if exists:
                print(f"  [SKIP] {table}.{column} 已存在")
                continue

            alter_sql = text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            await conn.execute(alter_sql)
            print(f"  [OK] {table}.{column} 添加成功")

        await conn.commit()

    print("迁移完成。")


if __name__ == "__main__":
    asyncio.run(main())
