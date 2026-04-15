"""为每个请求分配 ``X-Request-ID``（可继承客户端 ``X-Request-ID`` / ``X-Correlation-ID``）。"""

from __future__ import annotations

import re
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from src.common.request_context import request_id_ctx

# 仅允许安全子集，避免响应头注入
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def _resolve_request_id(request: Request) -> str:
    raw = request.headers.get("x-request-id") or request.headers.get(
        "x-correlation-id"
    )
    if raw:
        s = raw.strip()
        if s and _REQUEST_ID_RE.fullmatch(s):
            return s[:128]
    return str(uuid.uuid4())


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = _resolve_request_id(request)
        request.state.request_id = rid
        token = request_id_ctx.set(rid)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            request_id_ctx.reset(token)
