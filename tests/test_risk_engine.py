"""Unit tests for the risk engine and individual rules."""

from __future__ import annotations

import pytest

from src.risk.engine import RiskEngine
from src.risk.models import PortfolioState
from src.risk.rules.cash_ratio import CashRatioMinRule
from src.risk.rules.max_drawdown import MaxDrawdownRule
from src.risk.rules.position_limit import SinglePositionLimitRule


class TestMaxDrawdownRule:
    """Tests for MaxDrawdownRule."""

    def test_drawdown_at_limit_fails(self):
        """Equity 85, peak 100, limit -15% -> exactly at limit, should fail (<=)."""
        rule = MaxDrawdownRule(name="max_dd", params={"max_drawdown_pct": -0.15})
        state = PortfolioState(
            cash=0, total_equity=85, positions=[], peak_equity=100
        )
        result = rule.check(state)
        assert result.passed is False
        assert result.rule_type == "max_drawdown"

    def test_drawdown_beyond_limit_fails(self):
        """Equity 80, peak 100, limit -15% -> -20% drawdown, should fail."""
        rule = MaxDrawdownRule(name="max_dd", params={"max_drawdown_pct": -0.15})
        state = PortfolioState(
            cash=0, total_equity=80, positions=[], peak_equity=100
        )
        result = rule.check(state)
        assert result.passed is False
        assert "20.00%" in result.message
        assert "15.00%" in result.message
        assert result.context is not None
        assert result.context["current_drawdown"] == pytest.approx(-0.20)

    def test_drawdown_within_limit_passes(self):
        """Equity 90, peak 100, limit -15% -> -10% drawdown, should pass."""
        rule = MaxDrawdownRule(name="max_dd", params={"max_drawdown_pct": -0.15})
        state = PortfolioState(
            cash=0, total_equity=90, positions=[], peak_equity=100
        )
        result = rule.check(state)
        assert result.passed is True

    def test_zero_equity_passes(self):
        """Zero equity should pass to avoid division issues."""
        rule = MaxDrawdownRule(name="max_dd", params={"max_drawdown_pct": -0.15})
        state = PortfolioState(
            cash=0, total_equity=0, positions=[], peak_equity=100
        )
        result = rule.check(state)
        assert result.passed is True


class TestPositionLimitRule:
    """Tests for SinglePositionLimitRule."""

    def test_position_within_limit_passes(self):
        """Position 25%, limit 30% -> should pass."""
        rule = SinglePositionLimitRule(
            name="pos_limit", params={"max_weight_pct": 0.30}
        )
        state = PortfolioState(
            cash=0,
            total_equity=100,
            positions=[
                {"code": "sh.600000", "quantity": 100, "weight": 0.25}
            ],
        )
        result = rule.check(state)
        assert result.passed is True

    def test_position_over_limit_fails(self):
        """Position 35%, limit 30% -> should fail."""
        rule = SinglePositionLimitRule(
            name="pos_limit", params={"max_weight_pct": 0.30}
        )
        state = PortfolioState(
            cash=0,
            total_equity=100,
            positions=[
                {"code": "sh.600000", "quantity": 100, "weight": 0.35}
            ],
        )
        result = rule.check(state)
        assert result.passed is False
        assert "sh.600000" in result.message
        assert "35.0%" in result.message
        assert result.context is not None
        assert result.context["weight"] == pytest.approx(0.35)

    def test_multiple_positions_checks_each(self):
        """Multiple positions, one over limit -> should fail on first over-limit."""
        rule = SinglePositionLimitRule(
            name="pos_limit", params={"max_weight_pct": 0.30}
        )
        state = PortfolioState(
            cash=0,
            total_equity=100,
            positions=[
                {"code": "sh.600000", "quantity": 100, "weight": 0.20},
                {"code": "sz.000001", "quantity": 100, "weight": 0.35},
            ],
        )
        result = rule.check(state)
        assert result.passed is False
        assert "sz.000001" in result.message


class TestCashRatioRule:
    """Tests for CashRatioMinRule."""

    def test_cash_above_minimum_passes(self):
        """Cash 15%, limit 10% -> should pass."""
        rule = CashRatioMinRule(name="cash_min", params={"min_cash_pct": 0.10})
        state = PortfolioState(cash=15, total_equity=100, positions=[])
        result = rule.check(state)
        assert result.passed is True

    def test_cash_below_minimum_fails(self):
        """Cash 5%, limit 10% -> should fail."""
        rule = CashRatioMinRule(name="cash_min", params={"min_cash_pct": 0.10})
        state = PortfolioState(cash=5, total_equity=100, positions=[])
        result = rule.check(state)
        assert result.passed is False
        assert "5.0%" in result.message
        assert "10.0%" in result.message
        assert result.context is not None
        assert result.context["cash_ratio"] == pytest.approx(0.05)

    def test_zero_equity_passes(self):
        """Zero equity should pass to avoid division issues."""
        rule = CashRatioMinRule(name="cash_min", params={"min_cash_pct": 0.10})
        state = PortfolioState(cash=0, total_equity=0, positions=[])
        result = rule.check(state)
        assert result.passed is True


class TestRiskEngine:
    """Tests for RiskEngine with multiple rules."""

    def test_engine_with_all_passing_rules(self):
        """All rules pass -> all_passed True, no errors."""
        engine = RiskEngine()
        engine.register(
            MaxDrawdownRule(name="dd", params={"max_drawdown_pct": -0.15})
        )
        engine.register(
            SinglePositionLimitRule(name="pos", params={"max_weight_pct": 0.30})
        )
        engine.register(
            CashRatioMinRule(name="cash", params={"min_cash_pct": 0.10})
        )

        state = PortfolioState(
            cash=20,
            total_equity=100,
            positions=[{"code": "sh.600000", "weight": 0.20}],
            peak_equity=100,
        )
        results = engine.check(state)
        all_passed, errors = engine.check_all_passed(state)

        assert all_passed is True
        assert len(errors) == 0
        assert len(results) == 3
        for r in results:
            assert r.passed is True

    def test_engine_with_some_failing_rules(self):
        """Some rules fail -> all_passed False, errors populated."""
        engine = RiskEngine()
        engine.register(
            MaxDrawdownRule(name="dd", params={"max_drawdown_pct": -0.15})
        )
        engine.register(
            SinglePositionLimitRule(name="pos", params={"max_weight_pct": 0.30})
        )
        engine.register(
            CashRatioMinRule(name="cash", params={"min_cash_pct": 0.10})
        )

        # cash too low (5%), position too high (35%), drawdown OK
        state = PortfolioState(
            cash=5,
            total_equity=100,
            positions=[{"code": "sh.600000", "weight": 0.35}],
            peak_equity=100,
        )
        results = engine.check(state)
        all_passed, errors = engine.check_all_passed(state)

        assert all_passed is False
        assert len(errors) == 2
        assert any("仓位" in e for e in errors)
        assert any("现金比例" in e for e in errors)

        passed_count = sum(1 for r in results if r.passed)
        failed_count = sum(1 for r in results if not r.passed)
        assert passed_count == 1
        assert failed_count == 2

    def test_disabled_rule_not_checked(self):
        """Disabled rules should not be evaluated."""
        engine = RiskEngine()
        engine.register(
            MaxDrawdownRule(name="dd", params={"max_drawdown_pct": -0.15})
        )
        engine.register(
            SinglePositionLimitRule(
                name="pos", params={"max_weight_pct": 0.30}, enabled=False
            )
        )

        state = PortfolioState(
            cash=0,
            total_equity=100,
            positions=[{"code": "sh.600000", "weight": 0.35}],
            peak_equity=100,
        )
        results = engine.check(state)

        assert len(results) == 1
        assert results[0].passed is True
        assert results[0].rule_type == "max_drawdown"
