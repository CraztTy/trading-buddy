"""超参优化运行器 — Optuna 包装，提供统一的 ``optimize`` 接口。

用法::

    from src.ml.hyperopt import HyperOptRunner

    def objective(trial):
        window = trial.suggest_int("window", 5, 60)
        threshold = trial.suggest_float("threshold", 0.0, 0.05)
        # 跑回测、返回评分（如夏普比率）
        return run_strategy(window=window, threshold=threshold)

    runner = HyperOptRunner(direction="maximize", sampler="tpe", seed=42)
    result = runner.optimize(objective, n_trials=50)
    # result.best_params, result.best_value, result.history

设计要点：
- 不依赖 Optuna 的状态对象暴露给上层；`HyperOptRunner` 只返回简单 dataclass，便于 JSON 序列化。
- ``timeout_sec`` 与 ``n_trials`` 任一触达即停。
- 默认使用 TPE 采样器（Tree-structured Parzen Estimator），适合中等维度连续 / 类别参数空间。
- ``catch_exceptions``：默认捕获 objective 中的所有异常作为失败 trial（不终止整轮）。

延迟导入 Optuna：仅在 ``optimize`` 调用时载入，避免冷启 / 测试环境缺包阻塞。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from src.common import get_logger

logger = get_logger("hyperopt_runner")

Direction = Literal["maximize", "minimize"]
SamplerName = Literal["tpe", "random", "cmaes"]


@dataclass(frozen=True)
class TrialRecord:
    """单次 trial 的结果（精简、可 JSON 化）。"""

    number: int
    value: float | None
    params: dict[str, Any]
    state: str  # "complete" | "fail" | "pruned"


@dataclass(frozen=True)
class OptimizationResult:
    """优化完成后返回的统一结果对象。"""

    best_value: float
    best_params: dict[str, Any]
    best_trial_number: int
    n_trials: int
    n_complete: int
    n_failed: int
    direction: Direction
    history: tuple[TrialRecord, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "best_value": self.best_value,
            "best_params": dict(self.best_params),
            "best_trial_number": self.best_trial_number,
            "n_trials": self.n_trials,
            "n_complete": self.n_complete,
            "n_failed": self.n_failed,
            "direction": self.direction,
            "history": [
                {
                    "number": t.number,
                    "value": t.value,
                    "params": dict(t.params),
                    "state": t.state,
                }
                for t in self.history
            ],
        }


class HyperOptRunner:
    """Optuna 包装 — 单次 ``optimize(objective, n_trials)`` 即得 ``OptimizationResult``。"""

    def __init__(
        self,
        direction: Direction = "maximize",
        sampler: SamplerName = "tpe",
        seed: int | None = None,
        catch_exceptions: bool = True,
        study_name: str | None = None,
        storage: str | None = None,
    ) -> None:
        if direction not in ("maximize", "minimize"):
            raise ValueError(f"direction must be 'maximize' or 'minimize', got {direction!r}")
        if sampler not in ("tpe", "random", "cmaes"):
            raise ValueError(f"sampler must be 'tpe' | 'random' | 'cmaes', got {sampler!r}")
        self.direction: Direction = direction
        self.sampler_name: SamplerName = sampler
        self.seed = seed
        self.catch_exceptions = catch_exceptions
        self.study_name = study_name
        self.storage = storage

    def optimize(
        self,
        objective: Callable[[Any], float],
        n_trials: int = 50,
        timeout_sec: float | None = None,
        show_progress: bool = False,
    ) -> OptimizationResult:
        """执行优化，返回统一结果。

        Args:
            objective: ``(trial) -> float``；调用 ``trial.suggest_*`` 定义搜索空间。
            n_trials: 最大试验数。
            timeout_sec: 总超时（秒）；与 ``n_trials`` 任一触达即停。
            show_progress: 是否显示 Optuna 自带进度条。
        """
        if n_trials < 1:
            raise ValueError(f"n_trials must be >= 1, got {n_trials}")

        try:
            import optuna
            from optuna.samplers import CmaEsSampler, RandomSampler, TPESampler
        except ImportError as exc:
            raise RuntimeError(
                "optuna is required for HyperOptRunner; install via `pip install optuna`"
            ) from exc

        sampler_obj: Any
        if self.sampler_name == "tpe":
            sampler_obj = TPESampler(seed=self.seed)
        elif self.sampler_name == "random":
            sampler_obj = RandomSampler(seed=self.seed)
        else:  # cmaes
            sampler_obj = CmaEsSampler(seed=self.seed)

        # 静默 Optuna 自身的 INFO 日志（避免污染应用日志）
        optuna.logging.set_verbosity(optuna.logging.WARNING)

        study = optuna.create_study(
            direction=self.direction,
            sampler=sampler_obj,
            study_name=self.study_name,
            storage=self.storage,
            load_if_exists=bool(self.storage),
        )

        catch_types: tuple = (Exception,) if self.catch_exceptions else ()

        study.optimize(
            objective,
            n_trials=n_trials,
            timeout=timeout_sec,
            catch=catch_types,
            show_progress_bar=show_progress,
        )

        history = tuple(
            TrialRecord(
                number=t.number,
                value=float(t.value) if t.value is not None else None,
                params=dict(t.params),
                state=str(t.state.name).lower(),
            )
            for t in study.trials
        )

        n_complete = sum(1 for t in history if t.state == "complete")
        n_failed = sum(1 for t in history if t.state in ("fail", "pruned"))

        if n_complete == 0:
            raise RuntimeError(
                "All trials failed; no best parameters available. Check objective for errors."
            )

        return OptimizationResult(
            best_value=float(study.best_value),
            best_params=dict(study.best_params),
            best_trial_number=int(study.best_trial.number),
            n_trials=len(history),
            n_complete=n_complete,
            n_failed=n_failed,
            direction=self.direction,
            history=history,
        )
