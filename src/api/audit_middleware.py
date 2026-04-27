"""审计日志中间件 — 自动记录交易相关 API 请求。

记录范围：
- 纸交易：下单、重置账户、创建账户
- 回测：执行回测、保存存档、删除存档
- 风控：规则变更、试算
- 其他：登录、登出
"""

from __future__ import annotations

import json
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from src.common import get_logger
from src.data.storage import get_session
from src.data.storage.models import AuditLogModel

logger = get_logger("audit_middleware")

# 需要审计记录的路径前缀
_AUDIT_PATHS = {
    "/api/paper/orders": "paper_order",
    "/api/paper/account/reset": "paper_reset",
    "/api/paper/account/create": "paper_create",
    "/api/backtest/run": "backtest_run",
    "/api/backtest/runs": "backtest_archive",
    "/api/risk/rules": "risk_rule",
    "/api/risk/check": "risk_check",
    "/api/kill-switch/toggle": "kill_switch",
    "/api/auth/login": "auth_login",
    "/api/auth/register": "auth_register",
}

_MAX_DETAIL_SIZE = 4096
_MAX_BODY_SIZE = 2048


def _extract_action(path: str, method: str) -> str | None:
    """根据路径和方法提取 action 类型。"""
    for prefix, action in _AUDIT_PATHS.items():
        if path.startswith(prefix):
            # 区分 create/update/delete
            if method == "DELETE":
                return f"{action}_delete"
            if method == "PUT":
                return f"{action}_update"
            if method == "POST":
                return action
            return f"{action}_read"
    return None


def _safe_json(body: bytes) -> dict[str, Any] | None:
    """安全解析请求体 JSON。"""
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8", errors="replace"))
    except Exception:
        return None


def _extract_user_id(request: Request) -> int | None:
    """从 request.state 提取用户 ID。"""
    user = getattr(request.state, "current_user", None)
    if user and isinstance(user, dict):
        uid = user.get("id")
        return int(uid) if uid is not None else None
    return None


class AuditLogMiddleware(BaseHTTPMiddleware):
    """在响应后异步写入审计日志（不阻塞请求）。"""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        method = request.method
        action = _extract_action(path, method)

        if action is None:
            return await call_next(request)

        # 读取请求体（audit 用）
        body_bytes = b""
        if method in ("POST", "PUT", "PATCH"):
            body_bytes = await request.body()
            # 重新构造请求体供下游读取
            async def receive():
                return {"type": "http.request", "body": body_bytes}
            request._receive = receive

        body_json = _safe_json(body_bytes)
        # 脱敏：移除密码
        if body_json and isinstance(body_json, dict):
            body_json = {k: v for k, v in body_json.items() if "password" not in k.lower()}

        response = await call_next(request)

        # 响应后写入审计日志
        user_id = _extract_user_id(request)
        detail: dict[str, Any] = {
            "method": method,
            "path": path,
            "status_code": response.status_code,
        }
        if body_json:
            # 截断过大请求体
            detail["body"] = body_json if len(str(body_json)) <= _MAX_DETAIL_SIZE else {"_truncated": True}

        success = response.status_code < 400
        error_msg = None
        if not success:
            error_msg = f"HTTP {response.status_code}"

        await self._write_audit(
            action=action,
            resource_type=action.split("_")[0],
            resource_id=str(body_json.get("id", "")) if body_json else None,
            detail=detail,
            user_id=user_id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            success=success,
            error_message=error_msg,
        )
        return response

    async def _write_audit(
        self,
        action: str,
        resource_type: str,
        resource_id: str | None,
        detail: dict[str, Any],
        user_id: int | None,
        ip_address: str | None,
        user_agent: str | None,
        success: bool,
        error_message: str | None,
    ) -> None:
        try:
            from src.common.audit_log import log_audit
            from src.data.storage.database import get_database

            db = get_database()
            async with db.session() as session:
                await log_audit(
                    session=session,
                    action=action,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    detail=detail,
                    user_id=user_id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    success=success,
                    error_message=error_message,
                )
        except Exception as e:
            logger.warning("Audit log write failed: %s", e)
