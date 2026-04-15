"""
Trading Buddy - 日志模块
使用 Loguru，提供高性能、结构化日志
"""

import sys
from pathlib import Path
from loguru import logger
from .config import get_settings


def _patcher_request_id(record: dict) -> None:
    """为每条日志注入 extra.request_id（HTTP 内为当前 X-Request-ID，否则 '-'）。"""
    from .request_context import request_id_ctx

    rid = request_id_ctx.get()
    record["extra"]["request_id"] = rid if rid else "-"


def setup_logger() -> None:
    """初始化日志配置"""
    settings = get_settings()

    # 移除默认处理器
    logger.remove()
    logger.configure(patcher=_patcher_request_id)

    use_json = settings.log.json_logs
    log_dir = settings.project_root / "logs"
    log_dir.mkdir(exist_ok=True)

    if use_json:
        # 每行一条 JSON（Loguru serialize），便于 Loki / ELK / 日志平台采集
        logger.add(
            sys.stdout,
            level=settings.log.level,
            serialize=True,
            colorize=False,
        )
        logger.add(
            log_dir / "trading_{time:YYYY-MM-DD}.log",
            rotation="00:00",
            retention="30 days",
            level=settings.log.level,
            encoding="utf-8",
            serialize=True,
        )
        logger.add(
            log_dir / "error_{time:YYYY-MM-DD}.log",
            rotation="00:00",
            retention="90 days",
            level="ERROR",
            encoding="utf-8",
            serialize=True,
        )
        return

    # 控制台输出（人类可读）
    logger.add(
        sys.stdout,
        format=settings.log.format,
        level=settings.log.level,
        colorize=True,
    )

    logger.add(
        log_dir / "trading_{time:YYYY-MM-DD}.log",
        rotation="00:00",  # 每天午夜轮转
        retention="30 days",  # 保留30天
        format=settings.log.format,
        level=settings.log.level,
        encoding="utf-8",
    )

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
