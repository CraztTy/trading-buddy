#!/usr/bin/env python3
"""
MySQL 生产环境迁移脚本：为 daily_kline 增加 adjust_flag 列并更新索引。
自动读取项目根目录 .env 中的 DATABASE_* 配置，无需手动输入连接串。

用法（项目根目录）：
  python scripts/migrate_mysql_adjust_flag.py

执行内容：
  1. ALTER TABLE daily_kline ADD adjust_flag VARCHAR(2) DEFAULT '3'
  2. UPDATE daily_kline SET adjust_flag='3' WHERE adjust_flag IS NULL OR adjust_flag=''
  3. 删除旧唯一索引 uk_code_date（若存在）
  4. 添加新唯一索引 uk_code_date_flag(code, trade_date, adjust_flag)
  5. 确认/补齐 ORM 期望的 ix_daily_kline_trade_date_pct / amount 索引
"""

from __future__ import annotations

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, inspect, text
from src.common.config import DatabaseSettings, _load_env_file


def main() -> None:
    _load_env_file()
    db_cfg = DatabaseSettings()
    if db_cfg.mode != "mysql":
        print(f"当前 DATABASE_MODE={db_cfg.mode}，本迁移仅适用于 mysql，已跳过。")
        return

    engine = create_engine(db_cfg.sync_url, connect_args=db_cfg.mysql_connect_args())
    conn = engine.connect()
    try:
        insp = inspect(engine)
        cols = {c["name"] for c in insp.get_columns("daily_kline")}
        indexes = {idx["name"] for idx in insp.get_indexes("daily_kline")}
        uqs = {
            uq["name"]
            for uq in (insp.get_unique_constraints("daily_kline") or [])
        }
        print(f"[info] 当前 daily_kline 列: {sorted(cols)}")
        print(f"[info] 当前索引: {sorted(indexes | uqs)}")

        # 1. 添加列
        if "adjust_flag" not in cols:
            print("[migrate] 添加列 daily_kline.adjust_flag ...")
            conn.execute(
                text(
                    "ALTER TABLE daily_kline "
                    "ADD COLUMN adjust_flag VARCHAR(2) NOT NULL DEFAULT '3' "
                    "COMMENT '复权类型: 1=后复权 2=前复权 3=不复权'"
                )
            )
            conn.commit()
            print("[ok] 列已添加")
        else:
            print("[skip] adjust_flag 列已存在")

        # 2. 回填旧数据
        print("[migrate] 回填 adjust_flag 为 NULL/空字符串的旧数据 ...")
        r = conn.execute(
            text(
                "UPDATE daily_kline SET adjust_flag = '3' "
                "WHERE adjust_flag IS NULL OR adjust_flag = ''"
            )
        )
        conn.commit()
        print(f"[ok] 回填行数: {r.rowcount}")

        # 3. 删除旧唯一索引（如果存在）
        # MySQL 中唯一约束通常表现为索引
        if "uk_code_date" in indexes or "uk_code_date" in uqs:
            print("[migrate] 删除旧唯一索引 uk_code_date ...")
            conn.execute(text("ALTER TABLE daily_kline DROP INDEX uk_code_date"))
            conn.commit()
            print("[ok] 旧索引已删除")
        else:
            print("[skip] 旧索引 uk_code_date 不存在")

        # 4. 添加新唯一索引
        if "uk_code_date_flag" not in indexes and "uk_code_date_flag" not in uqs:
            print("[migrate] 添加新唯一索引 uk_code_date_flag(code, trade_date, adjust_flag) ...")
            conn.execute(
                text(
                    "ALTER TABLE daily_kline "
                    "ADD UNIQUE KEY uk_code_date_flag (code, trade_date, adjust_flag)"
                )
            )
            conn.commit()
            print("[ok] 新索引已添加")
        else:
            print("[skip] 新索引 uk_code_date_flag 已存在")

        # 5. 补齐 ORM 期望的普通索引（ harmless 重复执行会被跳过）
        for idx_name, cols_def in (
            ("ix_daily_kline_trade_date_pct", "(trade_date, change_pct)"),
            ("ix_daily_kline_trade_date_amount", "(trade_date, amount)"),
        ):
            if idx_name not in indexes:
                print(f"[migrate] 添加索引 {idx_name} {cols_def} ...")
                conn.execute(
                    text(
                        f"ALTER TABLE daily_kline ADD INDEX {idx_name} {cols_def}"
                    )
                )
                conn.commit()
                print(f"[ok] 索引 {idx_name} 已添加")
            else:
                print(f"[skip] 索引 {idx_name} 已存在")

        print("\n[done] MySQL 迁移完成。建议随后运行:")
        print("  python scripts/check_trend_v0_pool.py --min-bars 60 --adjust-flag 3")
        print("  python scripts/verify_stack.py")
    except Exception as e:
        conn.rollback()
        print(f"\n[error] 迁移失败: {e}")
        raise SystemExit(1)
    finally:
        conn.close()
        engine.dispose()


if __name__ == "__main__":
    main()
