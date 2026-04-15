#!/usr/bin/env python3
"""
Trading Buddy - 数据库初始化脚本
创建所有表结构（含 ``trade_calendar``）。

建表完成后**建议**尽快灌交易日历（Baostock，需网络），否则看板「交易日历」与
``check_daily_kline_quality.py`` 的交易日缺口 / B+D 门控无数据可依：

  python scripts/fetch_trade_calendar.py --start 2020-01-01 --end 2025-12-31

等价入口：``python scripts/fetch_data.py --mode calendar --source baostock``（见 ``--calendar-*``）。
日常拉数可在 ``--mode daily`` / ``all`` 时加 ``--with-calendar`` 顺带刷新尾部区间。
"""

import asyncio
import sys
import time
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(project_root))

from src.common import describe_database_write_target, get_logger
from src.data.storage import dispose_database, get_database


async def init_database():
    """初始化数据库"""
    logger = get_logger("init")
    
    from src.common import get_settings
    settings = get_settings()
    
    # 强制设置项目根目录
    settings.project_root = project_root
    
    logger.info(f"Initializing database (mode: {settings.database.mode})...")
    logger.info(f"写入目标: {describe_database_write_target()}")
    logger.info(f"Project root: {project_root}")
    
    # 确保数据目录存在
    if settings.database.mode == "sqlite":
        db_path = project_root / settings.database.db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"Database path: {db_path}")
    
    # 创建数据库连接
    db = get_database()

    t0 = time.perf_counter()
    try:
        # 创建所有表
        await db.create_tables()
        logger.info("Database tables created successfully")
        logger.info(
            "建议：灌交易日历 trade_calendar（Baostock）→ "
            "python scripts/fetch_trade_calendar.py --start 2020-01-01 --end 2025-12-31 "
            "或 fetch_data.py --mode calendar；详见 init_db 模块说明。"
        )

    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
    finally:
        logger.info(f"[timing] init_db {time.perf_counter() - t0:.1f}s")
        await dispose_database()


if __name__ == "__main__":
    asyncio.run(init_database())
