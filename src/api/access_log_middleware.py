"""可选 HTTP 访问日志（见 API_ACCESS_LOG）。"""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from src.common import get_logger

_access_logger = get_logger("http.access")


class AccessLogMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, ignore_prefixes: tuple[str, ...] = ()) -> None:
        super().__init__(app)
        self.ignore_prefixes = ignore_prefixes

    def _path_ignored(self, path: str) -> bool:
        return any(path.startswith(p) for p in self.ignore_prefixes)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if self._path_ignored(path):
            return await call_next(request)
        t0 = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        rid = getattr(request.state, "request_id", None) or "-"
        _access_logger.info(
            "{} {} -> {} {:.1f}ms id={}",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            rid,
        )
        return response
