"""ClickHouse 客户端 — 连接管理和基础查询。

依赖: pip install clickhouse-connect
用法:
    from src.data.clickhouse.client import get_ch_client
    client = get_ch_client()
    result = client.query("SELECT * FROM daily_kline LIMIT 10")
"""

from __future__ import annotations

from functools import lru_cache

import clickhouse_connect
from clickhouse_connect.driver.client import Client

from src.common import get_logger
from src.common.config import get_settings

logger = get_logger("clickhouse")

_ch_client: Client | None = None


def get_ch_client() -> Client | None:
    """获取 ClickHouse 客户端（单例，延迟初始化）。

    Returns:
        Client 实例，如果未启用则返回 None。
    """
    global _ch_client
    settings = get_settings().clickhouse

    if not settings.enabled:
        return None

    if _ch_client is None:
        try:
            _ch_client = clickhouse_connect.get_client(
                host=settings.host,
                port=settings.port,
                username=settings.user,
                password=settings.password,
                database=settings.database,
                settings={
                    "max_execution_time": 60,
                    "max_memory_usage": 4_000_000_000,  # 4GB
                },
            )
            logger.info(
                "clickhouse connected: %s:%s/%s",
                settings.host,
                settings.port,
                settings.database,
            )
        except Exception as e:
            logger.error("clickhouse connection failed: %s", e)
            return None

    return _ch_client


def close_ch_client() -> None:
    """关闭 ClickHouse 客户端。"""
    global _ch_client
    if _ch_client is not None:
        try:
            _ch_client.close()
            logger.info("clickhouse disconnected")
        except Exception as e:
            logger.warning("clickhouse close error: %s", e)
        _ch_client = None


def health_check() -> dict:
    """ClickHouse 健康检查。"""
    client = get_ch_client()
    if client is None:
        return {"status": "disabled"}
    try:
        result = client.query("SELECT 1")
        return {
            "status": "ok",
            "host": get_settings().clickhouse.host,
            "database": get_settings().clickhouse.database,
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}
