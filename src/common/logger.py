"""
Trading Buddy - 日志模块
使用 Loguru，提供高性能、结构化日志
"""

import sys
from pathlib import Path
from loguru import logger
from .config import get_settings


def setup_logger() -> None:
    """初始化日志配置"""
    settings = get_settings()
    
    # 移除默认处理器
    logger.remove()
    
    # 控制台输出
    logger.add(
        sys.stdout,
        format=settings.log.format,
        level=settings.log.level,
        colorize=True,
    )
    
    # 文件输出 - 按日期分割
    log_dir = settings.project_root / "logs"
    log_dir.mkdir(exist_ok=True)
    
    logger.add(
        log_dir / "trading_{time:YYYY-MM-DD}.log",
        rotation="00:00",  # 每天午夜轮转
        retention="30 days",  # 保留30天
        format=settings.log.format,
        level=settings.log.level,
        encoding="utf-8",
    )
    
    # 错误日志单独记录
    logger.add(
        log_dir / "error_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="90 days",
        format=settings.log.format,
        level="ERROR",
        encoding="utf-8",
    )


def get_logger(name: str | None = None) -> logger:
    """获取日志记录器"""
    if name:
        return logger.bind(name=name)
    return logger
