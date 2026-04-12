"""回测 / 扫描结果存档。"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import BacktestRunModel

ALLOWED_KINDS = frozenset({"ma_cross_single", "ma_cross_scan"})
# request_params + response_payload 序列化后合计上限（避免撑爆 DB）
MAX_BACKTEST_RUN_TOTAL_BYTES = 2 * 1024 * 1024


def json_payload_bytes(obj: dict[str, Any]) -> int:
    return len(json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"))


def assert_run_payload_size(request_params: dict[str, Any], response_payload: dict[str, Any]) -> None:
    total = json_payload_bytes(request_params) + json_payload_bytes(response_payload)
    if total > MAX_BACKTEST_RUN_TOTAL_BYTES:
        raise ValueError(
            f"存档体积过大（约 {total} 字节），超过上限 {MAX_BACKTEST_RUN_TOTAL_BYTES}；"
            "可缩短扫描代码列表或减少 equity 采样后再试。"
        )


def build_summary(kind: str, response_payload: dict[str, Any]) -> str:
    if kind == "ma_cross_single":
        c = str(response_payload.get("code") or "?")
        fp = response_payload.get("fast_period")
        sp = response_payload.get("slow_period")
        tr = response_payload.get("total_return_pct")
        return f"{c} MA{fp}/{sp} 策略{tr}%"
    if kind == "ma_cross_scan":
        items = response_payload.get("items") or []
        fp = response_payload.get("fast_period")
        sp = response_payload.get("slow_period")
        ok = sum(1 for x in items if isinstance(x, dict) and not x.get("error"))
        return f"批量 {len(items)} 行（有效 {ok}）MA{fp}/{sp}"
    return (kind or "unknown")[:200]


class BacktestRunRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(
        self,
        *,
        kind: str,
        summary: str,
        request_params: dict[str, Any],
        response_payload: dict[str, Any],
    ) -> BacktestRunModel:
        row = BacktestRunModel(
            kind=kind,
            summary=summary[:512],
            request_params=request_params,
            response_payload=response_payload,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, run_id: int) -> BacktestRunModel | None:
        return await self._session.get(BacktestRunModel, run_id)

    async def count_all(self, *, kind: str | None = None, q: str | None = None) -> int:
        stmt = select(func.count()).select_from(BacktestRunModel)
        if kind is not None:
            stmt = stmt.where(BacktestRunModel.kind == kind)
        if q:
            stmt = stmt.where(BacktestRunModel.summary.contains(q))
        return int((await self._session.execute(stmt)).scalar_one())

    async def list_recent(
        self, limit: int, offset: int, *, kind: str | None = None, q: str | None = None
    ) -> list[BacktestRunModel]:
        stmt = select(BacktestRunModel).order_by(desc(BacktestRunModel.created_at), desc(BacktestRunModel.id))
        if kind is not None:
            stmt = stmt.where(BacktestRunModel.kind == kind)
        if q:
            stmt = stmt.where(BacktestRunModel.summary.contains(q))
        stmt = stmt.offset(offset).limit(limit)
        r = await self._session.execute(stmt)
        return list(r.scalars().all())

    async def delete_by_id(self, run_id: int) -> bool:
        row = await self.get(run_id)
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.flush()
        return True
