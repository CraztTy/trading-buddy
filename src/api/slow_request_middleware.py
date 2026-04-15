"""单请求耗时超过阈值时打 WARN（见 API_SLOW_REQUEST_WARN_MS）。"""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from src.common import get_logger

_slow_logger = get_logger("http.slow")


class SlowRequestWarningMiddleware(BaseHTTPMiddleware):
    """``threshold_ms`` ≤ 0 时不应注册本中间件。"""

    def __init__(
        self,
        app,
        *,
        threshold_ms: int,
        ignore_prefixes: tuple[str, ...] = (),
    ) -> None:
        super().__init__(app)
        self.threshold_ms = threshold_ms
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
        if elapsed_ms >= self.threshold_ms:
            rid = getattr(request.state, "request_id", None) or "-"
            _slow_logger.warning(
                "slow_request {} {} -> {} {:.1f}ms (threshold {}ms) id={}",
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
                self.threshold_ms,
                rid,
            )
        return response
