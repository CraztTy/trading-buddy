"""HTTP 请求级上下文（供日志 patcher 等读取）。"""

from __future__ import annotations

from contextvars import ContextVar

# 由 RequestIdMiddleware 在请求生命周期内 set/reset；无请求时为 unset
request_id_ctx: ContextVar[str | None] = ContextVar("tb_request_id", default=None)
