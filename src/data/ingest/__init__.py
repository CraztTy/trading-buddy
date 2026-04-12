"""可复用的数据灌数逻辑（脚本、定时任务、API 后台任务）。"""

from .trade_calendar_baostock import ingest_trade_calendar_from_baostock

__all__ = ["ingest_trade_calendar_from_baostock"]
