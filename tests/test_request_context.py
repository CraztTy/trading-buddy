"""request_id ContextVar（与 RequestIdMiddleware / 日志 patcher 配合）。"""

from __future__ import annotations

from src.common.request_context import request_id_ctx


def test_request_id_ctx_default_is_none() -> None:
    assert request_id_ctx.get() is None


def test_request_id_ctx_set_reset() -> None:
    token = request_id_ctx.set("rid-1")
    try:
        assert request_id_ctx.get() == "rid-1"
    finally:
        request_id_ctx.reset(token)
    assert request_id_ctx.get() is None
