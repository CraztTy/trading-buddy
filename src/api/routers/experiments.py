"""实验追踪 API — 创建实验、记录运行、查询历史。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_user
from src.data.storage.database import get_session
from src.data.storage.models import ExperimentModel, ExperimentRunModel

router = APIRouter()


def _user_id_or_system(current_user: dict) -> int | None:
    uid = current_user.get("id", 0)
    return None if uid == 0 else uid


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ExperimentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    strategy_id: str = Field(..., min_length=1, max_length=64)
    description: str | None = Field(None, max_length=500)
    params_template: dict[str, Any] = Field(default_factory=dict)
    tags: str | None = Field(None, max_length=256)


class ExperimentItem(BaseModel):
    id: int
    name: str
    strategy_id: str
    description: str | None
    params_template: dict[str, Any]
    tags: str | None
    status: str
    created_at: str


class ExperimentRunCreate(BaseModel):
    experiment_id: int
    run_params: dict[str, Any] = Field(default_factory=dict)
    result_summary: dict[str, Any] = Field(default_factory=dict)
    status: str = Field("completed", pattern="^(completed|failed|running)$")
    duration_ms: int | None = None
    git_commit: str | None = None
    error_message: str | None = None


class ExperimentRunItem(BaseModel):
    id: int
    experiment_id: int
    run_params: dict[str, Any]
    result_summary: dict[str, Any]
    status: str
    duration_ms: int | None
    git_commit: str | None
    error_message: str | None
    created_at: str


class ExperimentListResponse(BaseModel):
    items: list[ExperimentItem]
    total: int
    limit: int
    offset: int


class ExperimentRunListResponse(BaseModel):
    items: list[ExperimentRunItem]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# Endpoints — Experiments
# ---------------------------------------------------------------------------


@router.post("/experiments", response_model=ExperimentItem, status_code=201)
async def create_experiment(
    body: ExperimentCreate,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> ExperimentItem:
    """创建实验定义。"""
    user_id = _user_id_or_system(current_user)
    row = ExperimentModel(
        user_id=user_id,
        name=body.name,
        strategy_id=body.strategy_id,
        description=body.description,
        params_template=body.params_template,
        tags=body.tags,
    )
    session.add(row)
    await session.flush()
    return _experiment_to_item(row)


@router.get("/experiments", response_model=ExperimentListResponse)
async def list_experiments(
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    strategy_id: str | None = Query(None),
) -> ExperimentListResponse:
    """列出实验。普通用户只能看自己的。"""
    user_id = _user_id_or_system(current_user)

    stmt = select(ExperimentModel)
    count_stmt = select(func.count()).select_from(ExperimentModel)

    if user_id is not None:
        stmt = stmt.where(ExperimentModel.user_id == user_id)
        count_stmt = count_stmt.where(ExperimentModel.user_id == user_id)
    if strategy_id:
        stmt = stmt.where(ExperimentModel.strategy_id == strategy_id)
        count_stmt = count_stmt.where(ExperimentModel.strategy_id == strategy_id)

    stmt = stmt.order_by(desc(ExperimentModel.created_at)).offset(offset).limit(limit)

    result = await session.execute(stmt)
    rows = result.scalars().all()
    total = (await session.execute(count_stmt)).scalar_one()

    return ExperimentListResponse(
        items=[_experiment_to_item(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/experiments/{exp_id}", response_model=ExperimentItem)
async def get_experiment(
    exp_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> ExperimentItem:
    """获取实验详情。"""
    user_id = _user_id_or_system(current_user)
    stmt = select(ExperimentModel).where(ExperimentModel.id == exp_id)
    if user_id is not None:
        stmt = stmt.where(ExperimentModel.user_id == user_id)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="实验不存在")
    return _experiment_to_item(row)


@router.delete("/experiments/{exp_id}", status_code=204)
async def delete_experiment(
    exp_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> Response:
    """删除实验及其运行记录。"""
    from sqlalchemy import delete

    user_id = _user_id_or_system(current_user)
    stmt = select(ExperimentModel).where(ExperimentModel.id == exp_id)
    if user_id is not None:
        stmt = stmt.where(ExperimentModel.user_id == user_id)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="实验不存在")

    # 级联删除运行记录
    await session.execute(
        delete(ExperimentRunModel).where(ExperimentRunModel.experiment_id == exp_id)
    )
    await session.delete(row)
    await session.flush()
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Endpoints — Experiment Runs
# ---------------------------------------------------------------------------


@router.post("/experiments/{exp_id}/runs", response_model=ExperimentRunItem, status_code=201)
async def create_experiment_run(
    exp_id: int,
    body: ExperimentRunCreate,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> ExperimentRunItem:
    """为实验记录一次运行。"""
    user_id = _user_id_or_system(current_user)

    # 验证实验存在且属于当前用户
    exp_stmt = select(ExperimentModel).where(ExperimentModel.id == exp_id)
    if user_id is not None:
        exp_stmt = exp_stmt.where(ExperimentModel.user_id == user_id)
    exp_result = await session.execute(exp_stmt)
    if exp_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="实验不存在")

    row = ExperimentRunModel(
        experiment_id=exp_id,
        run_params=body.run_params,
        result_summary=body.result_summary,
        status=body.status,
        duration_ms=body.duration_ms,
        git_commit=body.git_commit,
        error_message=body.error_message,
    )
    session.add(row)
    await session.flush()
    return _run_to_item(row)


@router.get("/experiments/{exp_id}/runs", response_model=ExperimentRunListResponse)
async def list_experiment_runs(
    exp_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ExperimentRunListResponse:
    """列出实验的运行记录。"""
    user_id = _user_id_or_system(current_user)

    # 验证实验存在且属于当前用户
    exp_stmt = select(ExperimentModel).where(ExperimentModel.id == exp_id)
    if user_id is not None:
        exp_stmt = exp_stmt.where(ExperimentModel.user_id == user_id)
    exp_result = await session.execute(exp_stmt)
    if exp_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="实验不存在")

    stmt = (
        select(ExperimentRunModel)
        .where(ExperimentRunModel.experiment_id == exp_id)
        .order_by(desc(ExperimentRunModel.created_at))
        .offset(offset)
        .limit(limit)
    )
    count_stmt = (
        select(func.count())
        .select_from(ExperimentRunModel)
        .where(ExperimentRunModel.experiment_id == exp_id)
    )

    result = await session.execute(stmt)
    rows = result.scalars().all()
    total = (await session.execute(count_stmt)).scalar_one()

    return ExperimentRunListResponse(
        items=[_run_to_item(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/experiments/{exp_id}/runs/{run_id}", response_model=ExperimentRunItem)
async def get_experiment_run(
    exp_id: int,
    run_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> ExperimentRunItem:
    """获取单次运行详情。"""
    user_id = _user_id_or_system(current_user)

    # 验证实验存在且属于当前用户
    exp_stmt = select(ExperimentModel).where(ExperimentModel.id == exp_id)
    if user_id is not None:
        exp_stmt = exp_stmt.where(ExperimentModel.user_id == user_id)
    exp_result = await session.execute(exp_stmt)
    if exp_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="实验不存在")

    stmt = select(ExperimentRunModel).where(
        ExperimentRunModel.id == run_id,
        ExperimentRunModel.experiment_id == exp_id,
    )
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="运行记录不存在")
    return _run_to_item(row)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _experiment_to_item(row: ExperimentModel) -> ExperimentItem:
    return ExperimentItem(
        id=row.id,
        name=row.name,
        strategy_id=row.strategy_id,
        description=row.description,
        params_template=dict(row.params_template or {}),
        tags=row.tags,
        status=row.status,
        created_at=row.created_at.isoformat() if row.created_at else "",
    )


def _run_to_item(row: ExperimentRunModel) -> ExperimentRunItem:
    return ExperimentRunItem(
        id=row.id,
        experiment_id=row.experiment_id,
        run_params=dict(row.run_params or {}),
        result_summary=dict(row.result_summary or {}),
        status=row.status,
        duration_ms=row.duration_ms,
        git_commit=row.git_commit,
        error_message=row.error_message,
        created_at=row.created_at.isoformat() if row.created_at else "",
    )
