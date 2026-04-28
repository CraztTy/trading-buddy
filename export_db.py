#!/usr/bin/env python3
"""导出 MySQL 数据库到 SQL 文件（连接参数与 .env / 环境变量一致，支持云库）"""

import os
import sys
from datetime import date, datetime
from pathlib import Path

import pymysql

project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

from src.common import get_settings


def export_database() -> None:
    s = get_settings()
    if s.database.mode != "mysql":
        raise SystemExit("当前为 SQLite 或非 MySQL 模式，请设置 DATABASE_MODE=mysql 后再导出")

    kw = {
        **s.database.mysql_connect_args(),
        "host": s.database.host,
        "port": s.database.port,
        "user": s.database.user,
        "password": s.database.password,
        "database": s.database.name,
        "charset": "utf8mb4",
    }
    conn = pymysql.connect(**kw)
    cursor = conn.cursor()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"backup_trading_{timestamp}.sql"
    filepath = os.path.join(os.getcwd(), filename)

    cursor.execute("SHOW TABLES")
    tables = [row[0] for row in cursor.fetchall()]

    print(f"正在导出 {len(tables)} 个表...")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"-- MySQL Backup: {s.database.name}\n")
        f.write(f"-- Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        for table in tables:
            print(f"  导出表: {table}")

            cursor.execute(f"SHOW CREATE TABLE `{table}`")
            create_stmt = cursor.fetchone()[1]
            f.write(f"-- Table: {table}\n")
            f.write(f"DROP TABLE IF EXISTS `{table}`;\n")
            f.write(f"{create_stmt};\n\n")

            cursor.execute(f"SELECT * FROM `{table}`")
            rows = cursor.fetchall()

            if rows:
                cursor.execute(f"SHOW COLUMNS FROM `{table}`")
                columns = [col[0] for col in cursor.fetchall()]

                for row in rows:
                    values = []
                    for val in row:
                        if val is None:
                            values.append("NULL")
                        elif isinstance(val, datetime):
                            values.append(f'"{val.strftime("%Y-%m-%d %H:%M:%S")}"')
                        elif isinstance(val, date):
                            values.append(f'"{val.strftime("%Y-%m-%d")}"')
                        elif isinstance(val, (int, float)):
                            values.append(str(val))
                        else:
                            val_str = str(val).replace("\\", "\\\\").replace('"', '\\"')
                            values.append(f'"{val_str}"')

                    cols = ",".join(f"`{c}`" for c in columns)
                    vals = ",".join(values)
                    f.write(f"INSERT INTO `{table}` ({cols}) VALUES ({vals});\n")

                print(f"    {len(rows):,} 条记录")

    conn.close()

    size = os.path.getsize(filepath)
    print(f"\n导出完成: {filepath}")
    print(f"文件大小: {size / 1024 / 1024:.2f} MB")


if __name__ == "__main__":
    export_database()
