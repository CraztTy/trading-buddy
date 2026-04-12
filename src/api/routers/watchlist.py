"""自选股 API：默认分组，增删查。"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.data.storage import get_session
from src.data.storage.watchlist_repository import WatchlistRepository

router = APIRouter()

_CODE_RE = re.compile(r"^(sh|sz|bj)\.[\w.-]+$", re.I)


class WatchlistItemOut(BaseModel):
    code: str
    name: str | None = None
    created_at: str | None = None


class WatchlistItemsResponse(BaseModel):
    watchlist_id: int
    items: list[WatchlistItemOut]


class WatchlistAddRequest(BaseModel):
    code: str = Field(..., min_length=4, max_length=24, description="标的代码，如 sh.600000")


def _norm_code(raw: str) -> str:
    c = (raw or "").strip().lower()
    if not c:
        raise HTTPException(status_code=400, detail="code 不能为空")
    if not _CODE_RE.match(c):
        raise HTTPException(status_code=400, detail="code 格式须为 sh.|sz.|bj. 前缀")
    return c


@router.get("/items", response_model=WatchlistItemsResponse)
async def watchlist_items(session: AsyncSession = Depends(get_session)) -> WatchlistItemsResponse:
    repo = WatchlistRepository(session)
    wl = await repo.get_or_create_default_watchlist()
    rows = await repo.list_items(wl.id)
    items = [
        WatchlistItemOut(
            code=r.code,
            name=r.name,
            created_at=r.created_at.isoformat() if r.created_at else None,
        )
        for r in rows
    ]
    return WatchlistItemsResponse(watchlist_id=wl.id, items=items)


@router.post("/items", status_code=201)
async def watchlist_add_item(
    body: WatchlistAddRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    code = _norm_code(body.code)
    repo = WatchlistRepository(session)
    wl = await repo.get_or_create_default_watchlist()
    try:
        await repo.add_item(wl.id, code)
    except ValueError as e:
        msg = str(e)
        if "已在自选" in msg:
            raise HTTPException(status_code=409, detail=msg) from e
        raise HTTPException(status_code=400, detail=msg) from e
    return {"ok": True, "code": code}


@router.delete("/items/{code}", status_code=200)
async def watchlist_remove_item(
    code: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    c = _norm_code(code)
    repo = WatchlistRepository(session)
    wl = await repo.get_or_create_default_watchlist()
    n = await repo.remove_item(wl.id, c)
    if n == 0:
        raise HTTPException(status_code=404, detail="自选无此代码")
    return {"ok": True, "code": c}
