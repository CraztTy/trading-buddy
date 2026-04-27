"""Kill Switch API — 全局紧急停止控制。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.dependencies import get_current_user, require_admin
from src.common.kill_switch import is_killed, set_killed

router = APIRouter()


class KillSwitchStatus(BaseModel):
    """Kill switch 当前状态。"""

    killed: bool
    message: str


class KillSwitchToggle(BaseModel):
    """切换 kill switch 请求体。"""

    killed: bool


@router.get("/status", response_model=KillSwitchStatus)
async def kill_switch_status() -> KillSwitchStatus:
    """获取当前 kill switch 状态。"""
    killed = await is_killed()
    return KillSwitchStatus(
        killed=killed,
        message="交易与回测服务暂停" if killed else "服务正常运行",
    )


@router.post("/toggle", response_model=KillSwitchStatus)
async def kill_switch_toggle(
    body: KillSwitchToggle,
    current_user: dict = Depends(require_admin),
) -> KillSwitchStatus:
    """切换 kill switch 状态。需要认证。"""
    await set_killed(body.killed)
    return KillSwitchStatus(
        killed=body.killed,
        message="交易与回测服务已暂停" if body.killed else "服务已恢复",
    )
