"""Tests for src.ml.hyperopt.HyperOptRunner."""

from __future__ import annotations

import math

import pytest

from src.ml.hyperopt import HyperOptRunner, OptimizationResult, TrialRecord


# ---------------------------------------------------------------------------
# Init / validation
# ---------------------------------------------------------------------------


def test_init_rejects_invalid_direction():
    with pytest.raises(ValueError, match="direction"):
        HyperOptRunner(direction="bogus")  # type: ignore[arg-type]


def test_init_rejects_invalid_sampler():
    with pytest.raises(ValueError, match="sampler"):
        HyperOptRunner(sampler="bogus")  # type: ignore[arg-type]


def test_optimize_rejects_zero_trials():
    runner = HyperOptRunner(seed=42)
    with pytest.raises(ValueError, match="n_trials"):
        runner.optimize(lambda t: 0.0, n_trials=0)


# ---------------------------------------------------------------------------
# Maximize / minimize
# ---------------------------------------------------------------------------


def test_optimize_finds_maximum_of_quadratic():
    """f(x) = -(x - 3)^2 has max at x=3, value 0."""

    def objective(trial):
        x = trial.suggest_float("x", -10.0, 10.0)
        return -((x - 3.0) ** 2)

    runner = HyperOptRunner(direction="maximize", sampler="tpe", seed=42)
    result = runner.optimize(objective, n_trials=40)

    assert isinstance(result, OptimizationResult)
    assert result.direction == "maximize"
    assert result.n_complete == 40
    assert result.n_failed == 0
    assert result.n_trials == 40
    assert result.best_params["x"] == pytest.approx(3.0, abs=2.0)
    assert result.best_value <= 0.0
    assert result.best_value > -10.0


def test_optimize_finds_minimum_when_direction_minimize():
    """f(x) = (x - 5)^2 has min at x=5, value 0."""

    def objective(trial):
        x = trial.suggest_float("x", -10.0, 10.0)
        return (x - 5.0) ** 2

    runner = HyperOptRunner(direction="minimize", sampler="tpe", seed=7)
    result = runner.optimize(objective, n_trials=40)
    assert result.direction == "minimize"
    assert result.best_params["x"] == pytest.approx(5.0, abs=2.0)
    assert result.best_value >= 0.0


def test_optimize_with_int_and_categorical_params():
    """Suggest int + categorical."""

    def objective(trial):
        a = trial.suggest_int("a", 1, 10)
        choice = trial.suggest_categorical("choice", ["x", "y", "z"])
        # Best when a=10 and choice="z"
        bonus = {"x": 0, "y": 1, "z": 2}[choice]
        return float(a + bonus)

    runner = HyperOptRunner(direction="maximize", seed=1, sampler="random")
    result = runner.optimize(objective, n_trials=30)
    assert result.best_value <= 12.0
    assert result.best_value >= 1.0


# ---------------------------------------------------------------------------
# History / records
# ---------------------------------------------------------------------------


def test_history_length_matches_n_trials():
    def objective(trial):
        return trial.suggest_float("x", 0.0, 1.0)

    runner = HyperOptRunner(direction="maximize", seed=0)
    result = runner.optimize(objective, n_trials=15)
    assert len(result.history) == 15
    assert result.n_trials == 15
    for record in result.history:
        assert isinstance(record, TrialRecord)
        assert record.state in ("complete", "fail", "pruned")
        assert "x" in record.params


def test_failed_trials_counted_when_catch_enabled():
    """Objective that always raises -> all trials fail; should raise after."""
    def objective(trial):
        trial.suggest_float("x", 0.0, 1.0)
        raise RuntimeError("boom")

    runner = HyperOptRunner(direction="maximize", seed=0, catch_exceptions=True)
    with pytest.raises(RuntimeError, match="All trials failed"):
        runner.optimize(objective, n_trials=5)


def test_failed_trials_propagate_when_catch_disabled():
    """With catch_exceptions=False, the first error escapes immediately."""
    def objective(trial):
        trial.suggest_float("x", 0.0, 1.0)
        raise ValueError("explicit")

    runner = HyperOptRunner(direction="maximize", seed=0, catch_exceptions=False)
    with pytest.raises(ValueError, match="explicit"):
        runner.optimize(objective, n_trials=5)


def test_some_failures_are_tolerated():
    """Mix successful and failing trials; runner returns success result."""
    counter = {"n": 0}

    def objective(trial):
        counter["n"] += 1
        x = trial.suggest_float("x", 0.0, 1.0)
        if counter["n"] % 3 == 0:
            raise RuntimeError("intermittent")
        return x

    runner = HyperOptRunner(direction="maximize", seed=42, catch_exceptions=True)
    result = runner.optimize(objective, n_trials=12)
    assert result.n_complete > 0
    assert result.n_failed > 0
    assert result.n_complete + result.n_failed == result.n_trials


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def test_result_to_dict_is_json_serializable():
    import json

    def objective(trial):
        return trial.suggest_float("x", 0.0, 1.0)

    result = HyperOptRunner(seed=1).optimize(objective, n_trials=5)
    payload = result.to_dict()
    serialized = json.dumps(payload)
    parsed = json.loads(serialized)
    assert parsed["direction"] == "maximize"
    assert parsed["n_trials"] == 5
    assert "best_params" in parsed
    assert isinstance(parsed["history"], list)
    assert len(parsed["history"]) == 5


# ---------------------------------------------------------------------------
# Determinism via seed
# ---------------------------------------------------------------------------


def test_same_seed_yields_same_best_params():
    def objective(trial):
        x = trial.suggest_float("x", -5.0, 5.0)
        y = trial.suggest_float("y", -5.0, 5.0)
        return -(x ** 2 + y ** 2)

    r1 = HyperOptRunner(direction="maximize", sampler="random", seed=99).optimize(objective, n_trials=10)
    r2 = HyperOptRunner(direction="maximize", sampler="random", seed=99).optimize(objective, n_trials=10)
    assert r1.best_params == r2.best_params
    assert math.isclose(r1.best_value, r2.best_value)
