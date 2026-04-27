"""Risk management API router."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_user
from src.data.storage.database import get_session
from src.data.storage.models import RiskRuleModel
from src.risk.defaults import DEFAULT_RULE_CONFIGS, build_engine_from_configs
from src.risk.engine import RiskEngine
from src.risk.models import PortfolioState, RiskCheckResult
from src.risk.rules import RULE_REGISTRY
from sqlalchemy import select

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic request/response models
# ---------------------------------------------------------------------------


class RiskRuleCreate(BaseModel):
    """Create a risk rule configuration."""

    rule_type: str = Field(..., description="Rule type key from RULE_REGISTRY")
    name: str = Field(..., description="Display name for the rule")
    params: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class RiskRuleUpdate(BaseModel):
    """Update a risk rule configuration."""

    name: str | None = None
    params: dict[str, Any] | None = None
    enabled: bool | None = None


class PositionInput(BaseModel):
    """Position entry for risk check request."""

    code: str
    quantity: float = 0.0
    avg_price: float = 0.0
    market_value: float = 0.0
    weight: float = 0.0
    sector: str | None = None


class RiskCheckRequest(BaseModel):
    """Portfolio state for risk checking."""

    cash: float
    total_equity: float
    positions: list[PositionInput] = Field(default_factory=list)
    trade_date: date | None = None
    daily_pnl: float = 0.0
    peak_equity: float = 0.0


class RiskCheckResultItem(BaseModel):
    """Single risk check result for API response."""

    passed: bool
    rule_type: str
    rule_name: str
    message: str
    severity: str
    context: dict[str, Any] | None = None


class RiskCheckResponse(BaseModel):
    """Risk check API response."""

    all_passed: bool
    results: list[RiskCheckResultItem]
    errors: list[str]


class RiskRuleItem(BaseModel):
    """Risk rule configuration item."""

    id: int | None = None
    rule_type: str
    name: str
    params: dict[str, Any]
    enabled: bool


def _user_id_or_system(current_user: dict) -> int | None:
    """将系统用户（id=0）映射为 None，以便与 user_id=NULL 的旧数据兼容。"""
    uid = current_user.get("id", 0)
    return None if uid == 0 else uid


def _result_to_item(r: RiskCheckResult) -> RiskCheckResultItem:
    return RiskCheckResultItem(
        passed=r.passed,
        rule_type=r.rule_type,
        rule_name=r.rule_name,
        message=r.message,
        severity=r.severity,
        context=r.context,
    )


def _rule_to_dict(rule: RiskRuleModel) -> dict[str, Any]:
    return {
        "id": rule.id,
        "rule_type": rule.rule_type,
        "name": rule.name,
        "params": rule.params,
        "enabled": rule.enabled,
    }


async def _ensure_default_rules(
    session: AsyncSession, user_id: int | None
) -> None:
    """若用户无规则，则插入默认规则（幂等）。"""
    stmt = select(RiskRuleModel).where(RiskRuleModel.user_id == user_id)
    result = await session.execute(stmt)
    existing = result.scalars().all()
    if existing:
        return
    for cfg in DEFAULT_RULE_CONFIGS:
        rule = RiskRuleModel(
            user_id=user_id,
            rule_type=cfg["rule_type"],
            name=cfg["name"],
            params=cfg.get("params", {}),
            scope=cfg.get("scope", "all"),
            enabled=cfg.get("enabled", True),
        )
        session.add(rule)
    await session.flush()


async def _get_user_rules(
    session: AsyncSession, user_id: int | None
) -> list[RiskRuleModel]:
    """获取用户的所有风控规则（不存在时自动初始化默认规则）。"""
    await _ensure_default_rules(session, user_id)
    stmt = select(RiskRuleModel).where(RiskRuleModel.user_id == user_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/rules")
async def list_risk_rules(
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """List available risk rule types and user's rule configurations."""
    user_id = _user_id_or_system(current_user)
    rules = await _get_user_rules(session, user_id)
    return {
        "rules": [_rule_to_dict(r) for r in rules],
        "available_types": list(RULE_REGISTRY.keys()),
    }


@router.post("/rules")
async def create_risk_rule(
    body: RiskRuleCreate,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Create a risk rule configuration."""
    if body.rule_type not in RULE_REGISTRY:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown rule_type: {body.rule_type}",
        )
    user_id = _user_id_or_system(current_user)
    rule = RiskRuleModel(
        user_id=user_id,
        rule_type=body.rule_type,
        name=body.name,
        params=body.params,
        enabled=body.enabled,
    )
    session.add(rule)
    await session.flush()
    return _rule_to_dict(rule)


@router.put("/rules/{rule_id}")
async def update_risk_rule(
    rule_id: int,
    body: RiskRuleUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Update a risk rule configuration."""
    user_id = _user_id_or_system(current_user)
    stmt = select(RiskRuleModel).where(
        RiskRuleModel.id == rule_id,
        RiskRuleModel.user_id == user_id,
    )
    result = await session.execute(stmt)
    rule = result.scalar_one_or_none()
    if rule is None:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")
    if body.name is not None:
        rule.name = body.name
    if body.params is not None:
        rule.params = body.params
    if body.enabled is not None:
        rule.enabled = body.enabled
    await session.flush()
    return _rule_to_dict(rule)


@router.delete("/rules/{rule_id}")
async def delete_risk_rule(
    rule_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Delete a risk rule configuration."""
    user_id = _user_id_or_system(current_user)
    stmt = select(RiskRuleModel).where(
        RiskRuleModel.id == rule_id,
        RiskRuleModel.user_id == user_id,
    )
    result = await session.execute(stmt)
    rule = result.scalar_one_or_none()
    if rule is None:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")
    await session.delete(rule)
    await session.flush()
    return {"deleted": rule_id}


@router.post("/check")
async def check_risk(
    body: RiskCheckRequest,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> RiskCheckResponse:
    """Accept portfolio state and run all registered risk rules."""
    state = PortfolioState(
        cash=body.cash,
        total_equity=body.total_equity,
        positions=[p.model_dump() for p in body.positions],
        trade_date=body.trade_date,
        daily_pnl=body.daily_pnl,
        peak_equity=body.peak_equity,
    )

    user_id = _user_id_or_system(current_user)
    rules = await _get_user_rules(session, user_id)
    configs = [_rule_to_dict(r) for r in rules]

    engine = build_engine_from_configs(configs)
    results = engine.check(state)
    all_passed, errors = engine.check_all_passed(state)

    return RiskCheckResponse(
        all_passed=all_passed,
        results=[_result_to_item(r) for r in results],
        errors=errors,
    )


# ---------------------------------------------------------------------------
# VaR / CVaR
# ---------------------------------------------------------------------------


class VarRequest(BaseModel):
    """VaR 计算请求。"""

    positions: list[PositionInput] = Field(default_factory=list)
    total_equity: float
    lookback_days: int = Field(252, ge=30, le=1000, description="历史回看天数")
    adjust_flag: str = Field("3", description="复权类型: 1=后复权 2=前复权 3=不复权")


class VarResponse(BaseModel):
    """VaR 计算结果。"""

    var_95: float = Field(description="95% 置信度 VaR（日收益率，负数=损失）")
    var_99: float = Field(description="99% 置信度 VaR")
    cvar_95: float = Field(description="95% 置信度 CVaR")
    cvar_99: float = Field(description="99% 置信度 CVaR")
    lookback_days: int = Field(description="实际使用的历史天数")
    data_quality: dict[str, Any] = Field(default_factory=dict)


@router.post("/var", response_model=VarResponse)
async def calculate_var(
    body: VarRequest,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> VarResponse:
    """历史模拟法计算组合 VaR / CVaR。

    取各持仓标的最近 N 天日 K 线，计算组合日收益率分布，
    按置信度分位数得到 VaR，阈值以下平均得到 CVaR。
    """
    from src.data.storage import KlineRepository
    from src.risk.var_calculator import calculate_var_historical

    if not body.positions:
        return VarResponse(
            var_95=0.0, var_99=0.0, cvar_95=0.0, cvar_99=0.0,
            lookback_days=0, data_quality={},
        )

    repo = KlineRepository(session)
    codes = [p.code for p in body.positions]

    # 批量获取各标的最近 N+1 根 K 线（多一根用于计算收益率）
    from datetime import date

    end_date = date.today()
    klines_map = await repo.get_daily_last_n_bars_per_code(
        codes=codes,
        end_date=end_date,
        max_bars=body.lookback_days + 1,
        adjust_flag=body.adjust_flag,
    )

    positions_dicts = [
        {
            "code": p.code,
            "market_value": p.market_value,
        }
        for p in body.positions
    ]

    result = calculate_var_historical(
        positions=positions_dicts,
        klines_map=klines_map,
        lookback_days=body.lookback_days,
        total_equity=body.total_equity,
    )

    return VarResponse(
        var_95=result.var_95,
        var_99=result.var_99,
        cvar_95=result.cvar_95,
        cvar_99=result.cvar_99,
        lookback_days=result.lookback_days,
        data_quality=result.data_quality,
    )


# ---------------------------------------------------------------------------
# 实时风控状态
# ---------------------------------------------------------------------------


class RealtimeRiskStateResponse(BaseModel):
    """实时风控状态响应。"""

    last_update: float | None = Field(description="上次更新时间戳")
    positions_count: int = Field(description="监控持仓数")
    monitored_codes: list[str] = Field(default_factory=list)
    drawdowns: dict[str, Any] = Field(default_factory=dict)
    daily_changes: dict[str, Any] = Field(default_factory=dict)
    var_result: dict[str, Any] | None = Field(None, description="VaR 计算结果")
    stress_active: bool = Field(False, description="压力场景是否激活")
    alerts: list[dict[str, Any]] = Field(default_factory=list)
    snapshot_count: int = Field(0, description="市场快照数")


@router.get("/realtime", response_model=RealtimeRiskStateResponse)
async def get_realtime_risk_state() -> RealtimeRiskStateResponse:
    """获取实时风控监控状态（盘中持续更新的风险指标）。"""
    from src.api.main import app

    consumers = getattr(app.state, "event_consumers", [])
    for consumer in consumers:
        if consumer.name == "risk_monitor":
            state = consumer.get_risk_state()
            return RealtimeRiskStateResponse(
                last_update=state.get("last_update"),
                positions_count=state.get("positions_count", 0),
                monitored_codes=state.get("monitored_codes", []),
                drawdowns=state.get("drawdowns", {}),
                daily_changes=state.get("daily_changes", {}),
                var_result=state.get("var_result"),
                stress_active=state.get("stress_active", False),
                alerts=state.get("alerts", []),
                snapshot_count=state.get("snapshot_count", 0),
            )

    # 消费者未启动时返回空状态
    return RealtimeRiskStateResponse()
