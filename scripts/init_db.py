#!/usr/bin/env python3
"""
Trading Buddy - 数据库初始化脚本
创建所有表结构
"""

import sys
import asyncio
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
    
    try:
        # 创建所有表
        await db.create_tables()
        logger.info("Database tables created successfully")
        
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
    finally:
        await dispose_database()


if __name__ == "__main__":
    asyncio.run(init_database())
