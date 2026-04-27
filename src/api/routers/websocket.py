"""WebSocket 实时行情推送 — 订阅/取消订阅/广播。

连接流程:
    1. 前端: new WebSocket("ws://host/ws/quotes")
    2. 后端: accept 连接
    3. 前端发送: {"action": "subscribe", "codes": ["sh.600000", "sz.000001"]}
    4. 后端: 启动后台轮询，有变化时推送
    5. 前端发送: {"action": "unsubscribe", "codes": ["sh.600000"]}
    6. 后端: 停止对该标的的推送
    7. 连接断开: 后端自动清理所有订阅

消息格式:
    客户端 -> 服务端:
        {"action": "subscribe", "codes": ["sh.600000"]}
        {"action": "unsubscribe", "codes": ["sh.600000"]}
        {"action": "ping"}

    服务端 -> 客户端:
        {"type": "quote", "code": "sh.600000", "price": 10.55, ...}
        {"type": "pong"}
        {"type": "error", "message": "..."}
"""

from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.common import get_logger
from src.market_data import MarketDataManager

logger = get_logger("websocket_quotes")
router = APIRouter()

# 全局行情管理器（单例，延迟启动）
_md_manager: MarketDataManager | None = None


def _get_manager() -> MarketDataManager:
    """获取或创建全局行情管理器。"""
    global _md_manager
    if _md_manager is None:
        _md_manager = MarketDataManager()
    return _md_manager


@router.websocket("/quotes")
async def websocket_quotes(ws: WebSocket):
    """实时行情 WebSocket 连接。"""
    await ws.accept()
    mgr = _get_manager()

    # 确保管理器已启动
    if not mgr._running:
        await mgr.start()

    logger.info("websocket connected: %s", ws.client)

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            action = msg.get("action", "").strip().lower()

            if action == "subscribe":
                codes = msg.get("codes", [])
                if isinstance(codes, str):
                    codes = [codes]
                for code in codes:
                    if code and isinstance(code, str):
                        await mgr.subscribe(code, ws)
                await ws.send_json({
                    "type": "subscribed",
                    "codes": [c.strip().lower() for c in codes if c and isinstance(c, str)],
                })

            elif action == "unsubscribe":
                codes = msg.get("codes", [])
                if isinstance(codes, str):
                    codes = [codes]
                for code in codes:
                    if code and isinstance(code, str):
                        await mgr.unsubscribe(code, ws)
                await ws.send_json({
                    "type": "unsubscribed",
                    "codes": [c.strip().lower() for c in codes if c and isinstance(c, str)],
                })

            elif action == "ping":
                await ws.send_json({"type": "pong"})

            else:
                await ws.send_json({
                    "type": "error",
                    "message": f"Unknown action: {action}",
                })

    except WebSocketDisconnect:
        logger.info("websocket disconnected: %s", ws.client)
    except Exception as e:
        logger.warning("websocket error: %s", e)
    finally:
        # 清理该连接的所有订阅
        await mgr.unsubscribe_all(ws)
