"""
Trading Buddy - 实时行情API（限流 + 短缓存，减轻 baostock 压力）
"""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.data.models import RealtimeQuote
from src.data.sources import DataSourceFactory

from ..rate_limit import enforce_realtime_rate_limit
from ..realtime_cache import (
    cache_get,
    cache_set,
    cache_ttl,
    stable_key_batch,
    stable_key_quote,
)

router = APIRouter(dependencies=[Depends(enforce_realtime_rate_limit)])


def _quotes_json(quotes: list[RealtimeQuote]) -> str:
    return json.dumps(
        [q.model_dump(mode="json") for q in quotes],
        ensure_ascii=False,
    )


def _quotes_from_json(raw: str) -> list[RealtimeQuote]:
    data = json.loads(raw)
    return [RealtimeQuote.model_validate(x) for x in data]


async def _fetch_quotes_from_source(code_list: list[str]) -> list[RealtimeQuote]:
    source = DataSourceFactory.create("baostock")
    try:
        await source.connect()
        return await source.get_realtime_quote(code_list)
    finally:
        await source.disconnect()


@router.get("/quote")
async def get_realtime_quote(
    codes: Annotated[str, Query(description="股票代码，多个用逗号分隔")],
) -> list[RealtimeQuote]:
    """获取实时行情"""
    code_list = [c.strip() for c in codes.split(",") if c.strip()]

    if not code_list:
        return []

    code_list = [
        f"sh.{c}" if not c.startswith(("sh.", "sz.", "bj.")) else c
        for c in code_list
    ]

    ckey = stable_key_quote(code_list)
    ttl = cache_ttl()
    cached = await cache_get(ckey)
    if cached:
        return _quotes_from_json(cached)

    quotes = await _fetch_quotes_from_source(code_list)
    if quotes:
        await cache_set(ckey, _quotes_json(quotes), ttl)
    return quotes


@router.get("/batch")
async def get_batch_quotes(
    market: str = Query("all", description="市场: sh/sz/bj/all"),
    limit: int = Query(50, le=200, description="返回数量"),
) -> dict:
    """批量获取市场行情摘要（主要指数）"""
    indices = [
        "sh.000001",
        "sz.399001",
        "sz.399006",
        "sh.000300",
    ]

    ckey = stable_key_batch()
    ttl = cache_ttl()
    cached = await cache_get(ckey)
    if cached:
        return json.loads(cached)

    quotes = await _fetch_quotes_from_source(indices)
    payload = {
        "indices": [q.model_dump(mode="json") for q in quotes],
        "timestamp": quotes[0].update_time.isoformat() if quotes else None,
    }
    out = json.dumps(payload, ensure_ascii=False, default=str)
    await cache_set(ckey, out, ttl)
    return json.loads(out)
