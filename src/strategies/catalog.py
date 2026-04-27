"""
已注册策略元数据（供看板 / OpenAPI 发现能力边界）。
"""

from __future__ import annotations

from typing import Any


def list_strategy_catalog() -> list[dict[str, Any]]:
    """稳定顺序的轻量目录；字段保持 JSON 友好。"""
    return [
        {
            "id": "ma_cross",
            "title": "双均线（日线收盘）",
            "description": (
                "快慢均线收盘比较；信号滞后一日用于回测。"
                "统一信号接口与 GET /api/backtest/ma-cross/signal 等价。"
            ),
            # 与 POST /api/backtest/runs 存档字段 kind 对齐（单标的 / 批量扫描）
            "backtest_archive_kinds": ["ma_cross_single", "ma_cross_scan"],
            "strategy_contract_version": "1",
            "signal_params": {
                "type": "object",
                "properties": {
                    "fast": {"type": "integer", "minimum": 1, "maximum": 120, "default": 5},
                    "slow": {"type": "integer", "minimum": 2, "maximum": 500, "default": 20},
                    "limit": {"type": "integer", "minimum": 30, "maximum": 5000, "default": 500},
                    "start_date": {"type": "string", "format": "date", "nullable": True},
                    "end_date": {"type": "string", "format": "date", "nullable": True},
                },
                "required": [],
            },
            # 与 POST /api/backtest/run 对齐（见 docs/STRATEGY_CONTRACT.md）
            "backtest_run": {
                "strategy_id": "ma_cross",
                "strategy_version": "1",
                "archive_kind": "ma_cross_single",
                "description": (
                    "Vue 看板单标的「运行回测」与此契约一致；存档 POST /api/backtest/runs 时 "
                    "kind 取 archive_kind，request_params 建议存完整 run 信封。"
                ),
                "params_schema": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 64,
                            "description": "标的代码，如 sh.000001",
                        },
                        "fast": {"type": "integer", "minimum": 1, "maximum": 120, "default": 5},
                        "slow": {"type": "integer", "minimum": 2, "maximum": 500, "default": 20},
                        "limit": {"type": "integer", "minimum": 30, "maximum": 5000, "default": 500},
                        "start_date": {"type": "string", "format": "date", "nullable": True},
                        "end_date": {"type": "string", "format": "date", "nullable": True},
                        "commission_rate": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 0.05,
                            "default": 0,
                            "description": "单边手续费率；与 slippage_rate 之和勿超过 0.08",
                        },
                        "slippage_rate": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 0.05,
                            "default": 0,
                        },
                        "benchmark_code": {
                            "type": "string",
                            "nullable": True,
                            "maxLength": 64,
                            "description": "可选；β/α 相对该基准日收益",
                        },
                    },
                    "required": ["code"],
                },
            },
        },
        {
            "id": "ma_cross_scan",
            "title": "双均线批量扫描（日线）",
            "description": (
                "多标的并行拉 K 后逐只双均线回测并排序；与 GET /api/backtest/ma-cross/scan 及 "
                "POST /api/backtest/run（strategy_id=ma_cross_scan）等价。"
            ),
            "backtest_archive_kinds": ["ma_cross_scan"],
            "strategy_contract_version": "1",
            "signal_params": {
                "type": "object",
                "description": (
                    "不提供 POST /api/strategies/signal：批量无单一「当前持仓」语义。"
                    "请对单代码使用 catalog 条目 ma_cross（kind=ma_cross）或 "
                    "GET /api/backtest/ma-cross/signal。"
                ),
                "properties": {},
                "required": [],
                "maxProperties": 0,
                "additionalProperties": False,
            },
            "backtest_run": {
                "strategy_id": "ma_cross_scan",
                "strategy_version": "1",
                "archive_kind": "ma_cross_scan",
                "description": (
                    "Vue 看板批量「开始扫描」与此契约一致；与 GET ma-cross/scan 查询参数同义。"
                ),
                "params_schema": {
                    "type": "object",
                    "properties": {
                        "codes": {
                            "type": "string",
                            "minLength": 1,
                            "description": "逗号、换行或分号分隔的标的列表",
                        },
                        "fast": {"type": "integer", "minimum": 1, "maximum": 120, "default": 5},
                        "slow": {"type": "integer", "minimum": 2, "maximum": 500, "default": 20},
                        "limit": {"type": "integer", "minimum": 30, "maximum": 5000, "default": 500},
                        "start_date": {"type": "string", "format": "date", "nullable": True},
                        "end_date": {"type": "string", "format": "date", "nullable": True},
                        "commission_rate": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 0.05,
                            "default": 0,
                        },
                        "slippage_rate": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 0.05,
                            "default": 0,
                        },
                        "max_codes": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 40,
                            "default": 25,
                            "description": "解析 codes 后最多参与扫描的只数",
                        },
                        "sort_by": {
                            "type": "string",
                            "default": "total_return",
                            "description": (
                                "total_return | excess_return | sharpe | buy_hold | ann_return | "
                                "sortino | calmar | win_rate | avg_holding | underlying_beta | underlying_alpha"
                            ),
                        },
                        "max_concurrent": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 20,
                            "default": 8,
                        },
                        "benchmark_code": {"type": "string", "nullable": True, "maxLength": 64},
                    },
                    "required": ["codes"],
                },
            },
        },
        {
            "id": "limit_up_pullback",
            "title": "涨停回调 · 单标的",
            "description": (
                "涨停回调策略单标的历史回测；"
                "与 POST /api/backtest/run（strategy_id=limit_up_pullback）及 "
                "GET /api/backtest/limit-up-pullback 等价。"
            ),
            "backtest_archive_kinds": ["limit_up_pullback_single"],
            "strategy_contract_version": "1",
            "signal_params": {
                "type": "object",
                "description": "不提供单标 signal；请使用回测 GET/POST 或选股 POST /api/strategies/limit-up-pullback/scan。",
                "properties": {},
                "required": [],
                "maxProperties": 0,
                "additionalProperties": False,
            },
            "backtest_run": {
                "strategy_id": "limit_up_pullback",
                "strategy_version": "1",
                "archive_kind": "limit_up_pullback_single",
                "description": "涨停回调策略单标回测参数。",
                "params_schema": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "minLength": 1, "maxLength": 64},
                        "limit": {"type": "integer", "minimum": 30, "maximum": 5000, "default": 500},
                        "start_date": {"type": "string", "format": "date", "nullable": True},
                        "end_date": {"type": "string", "format": "date", "nullable": True},
                        "commission_rate": {"type": "number", "minimum": 0, "maximum": 0.05, "default": 0},
                        "slippage_rate": {"type": "number", "minimum": 0, "maximum": 0.05, "default": 0},
                        "benchmark_code": {"type": "string", "nullable": True, "maxLength": 64},
                        "pullback_days": {"type": "integer", "minimum": 1, "maximum": 60, "default": 10},
                        "entry_type": {
                            "type": "string",
                            "enum": ["aggressive", "neutral", "conservative"],
                            "default": "neutral",
                        },
                        "volume_shrink_ratio": {"type": "number", "minimum": 0.1, "maximum": 1.0, "default": 0.5},
                        "max_hold_days": {"type": "integer", "minimum": 0, "maximum": 120, "default": 0},
                        "time_stop_days": {"type": "integer", "minimum": 0, "maximum": 120, "default": 0},
                        "time_stop_pct": {"type": "number", "minimum": -0.5, "maximum": 0.5, "default": 0.0},
                        "market_index_code": {"type": "string", "nullable": True, "maxLength": 64, "description": "大盘指数代码（如 sh.000001），传入后启用大盘过滤"},
                        "require_market_bull": {"type": "boolean", "default": False},
                        "market_strict": {"type": "boolean", "default": False},
                    },
                    "required": ["code"],
                },
            },
            "optimize": {
                "endpoint": "POST /api/backtest/limit-up-pullback/optimize",
                "description": "参数网格优化扫描，返回 Top-N 最优参数组合。",
                "params_schema": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "minLength": 1, "maxLength": 64},
                        "limit": {"type": "integer", "minimum": 30, "maximum": 5000, "default": 500},
                        "start_date": {"type": "string", "format": "date", "nullable": True},
                        "end_date": {"type": "string", "format": "date", "nullable": True},
                        "commission_rate": {"type": "number", "minimum": 0, "maximum": 0.05, "default": 0},
                        "slippage_rate": {"type": "number", "minimum": 0, "maximum": 0.05, "default": 0},
                        "benchmark_code": {"type": "string", "nullable": True, "maxLength": 64},
                        "entry_types": {"type": "array", "items": {"type": "string", "enum": ["aggressive", "neutral", "conservative"]}, "default": ["neutral"]},
                        "pullback_days_min": {"type": "integer", "minimum": 1, "maximum": 60, "default": 5},
                        "pullback_days_max": {"type": "integer", "minimum": 1, "maximum": 60, "default": 15},
                        "pullback_days_step": {"type": "integer", "minimum": 1, "maximum": 10, "default": 1},
                        "volume_shrink_ratios": {"type": "array", "items": {"type": "number"}, "default": [0.5]},
                        "max_hold_days_list": {"type": "array", "items": {"type": "integer"}, "default": [0]},
                        "time_stop_days_list": {"type": "array", "items": {"type": "integer"}, "default": [0]},
                        "time_stop_pcts": {"type": "array", "items": {"type": "number"}, "default": [0.0]},
                        "ma_strict_values": {"type": "array", "items": {"type": "boolean"}, "default": [False]},
                        "max_combinations": {"type": "integer", "minimum": 1, "maximum": 500, "default": 100},
                        "sort_by": {"type": "string", "default": "sharpe"},
                        "top_n": {"type": "integer", "minimum": 1, "maximum": 100, "default": 10},
                    },
                    "required": ["code"],
                },
            },
        },
        {
            "id": "limit_up_pullback_scan",
            "title": "涨停回调 · 批量扫描",
            "description": (
                "涨停回调策略批量扫描回测；"
                "与 POST /api/backtest/run（strategy_id=limit_up_pullback_scan）及 "
                "GET /api/backtest/limit-up-pullback/scan 等价。"
            ),
            "backtest_archive_kinds": ["limit_up_pullback_scan"],
            "strategy_contract_version": "1",
            "signal_params": {
                "type": "object",
                "description": "不提供批量 signal；请使用扫描 GET/POST 或选股 POST /api/strategies/limit-up-pullback/scan。",
                "properties": {},
                "required": [],
                "maxProperties": 0,
                "additionalProperties": False,
            },
            "backtest_run": {
                "strategy_id": "limit_up_pullback_scan",
                "strategy_version": "1",
                "archive_kind": "limit_up_pullback_scan",
                "description": "涨停回调策略批量扫描回测参数。",
                "params_schema": {
                    "type": "object",
                    "properties": {
                        "codes": {"type": "string", "minLength": 1, "description": "逗号或换行分隔的标的列表"},
                        "limit": {"type": "integer", "minimum": 30, "maximum": 5000, "default": 500},
                        "start_date": {"type": "string", "format": "date", "nullable": True},
                        "end_date": {"type": "string", "format": "date", "nullable": True},
                        "commission_rate": {"type": "number", "minimum": 0, "maximum": 0.05, "default": 0},
                        "slippage_rate": {"type": "number", "minimum": 0, "maximum": 0.05, "default": 0},
                        "max_codes": {"type": "integer", "minimum": 1, "maximum": 40, "default": 25},
                        "sort_by": {"type": "string", "default": "total_return"},
                        "max_concurrent": {"type": "integer", "minimum": 1, "maximum": 20, "default": 8},
                        "benchmark_code": {"type": "string", "nullable": True, "maxLength": 64},
                        "pullback_days": {"type": "integer", "minimum": 1, "maximum": 60, "default": 10},
                        "entry_type": {
                            "type": "string",
                            "enum": ["aggressive", "neutral", "conservative"],
                            "default": "neutral",
                        },
                        "volume_shrink_ratio": {"type": "number", "minimum": 0.1, "maximum": 1.0, "default": 0.5},
                        "max_hold_days": {"type": "integer", "minimum": 0, "maximum": 120, "default": 0},
                        "time_stop_days": {"type": "integer", "minimum": 0, "maximum": 120, "default": 0},
                        "time_stop_pct": {"type": "number", "minimum": -0.5, "maximum": 0.5, "default": 0.0},
                        "market_index_code": {"type": "string", "nullable": True, "maxLength": 64, "description": "大盘指数代码（如 sh.000001），传入后启用大盘过滤"},
                        "require_market_bull": {"type": "boolean", "default": False},
                        "market_strict": {"type": "boolean", "default": False},
                    },
                    "required": ["codes"],
                },
            },
        },
        {
            "id": "buy_hold",
            "title": "买入持有（日线收盘）",
            "description": (
                "全样本做多；与 GET /api/backtest/buy-hold 及 POST /api/backtest/run（strategy_id=buy_hold）等价；"
                "无独立 signal 端点。"
            ),
            "backtest_archive_kinds": ["buy_hold_single"],
            "strategy_contract_version": "1",
            "signal_params": {
                "type": "object",
                "description": "不提供 POST /api/strategies/signal；请使用回测 GET/POST。",
                "properties": {},
                "required": [],
                "maxProperties": 0,
                "additionalProperties": False,
            },
            "backtest_run": {
                "strategy_id": "buy_hold",
                "strategy_version": "1",
                "archive_kind": "buy_hold_single",
                "description": (
                    "params：code, limit, start_date, end_date, commission_rate, slippage_rate, benchmark_code；"
                    "无 fast/slow。"
                ),
                "params_schema": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 64,
                            "description": "标的代码，如 sh.000001",
                        },
                        "limit": {"type": "integer", "minimum": 30, "maximum": 5000, "default": 500},
                        "start_date": {"type": "string", "format": "date", "nullable": True},
                        "end_date": {"type": "string", "format": "date", "nullable": True},
                        "commission_rate": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 0.05,
                            "default": 0,
                            "description": "单边手续费率；与 slippage_rate 之和勿超过 0.08",
                        },
                        "slippage_rate": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 0.05,
                            "default": 0,
                        },
                        "benchmark_code": {
                            "type": "string",
                            "nullable": True,
                            "maxLength": 64,
                            "description": "可选；β/α 相对该基准日收益",
                        },
                    },
                    "required": ["code"],
                },
            },
        },
        {
            "id": "portfolio_equal_weight",
            "title": "组合回测 · 等权",
            "description": (
                "多标的组合回测，等权分配，支持日/周/月频再平衡；"
                "与 POST /api/backtest/run（strategy_id=portfolio_equal_weight）等价。"
            ),
            "backtest_archive_kinds": ["portfolio_equal_weight"],
            "strategy_contract_version": "1",
            "signal_params": {
                "type": "object",
                "description": "不提供组合 signal；请使用回测 POST /run。",
                "properties": {},
                "required": [],
                "maxProperties": 0,
                "additionalProperties": False,
            },
            "backtest_run": {
                "strategy_id": "portfolio_equal_weight",
                "strategy_version": "1",
                "archive_kind": "portfolio_equal_weight",
                "description": "组合回测等权分配参数。",
                "params_schema": {
                    "type": "object",
                    "properties": {
                        "codes": {"type": "string", "minLength": 1, "description": "逗号或换行分隔的标的列表"},
                        "limit": {"type": "integer", "minimum": 30, "maximum": 5000, "default": 500},
                        "start_date": {"type": "string", "format": "date", "nullable": True},
                        "end_date": {"type": "string", "format": "date", "nullable": True},
                        "commission_rate": {"type": "number", "minimum": 0, "maximum": 0.05, "default": 0},
                        "slippage_rate": {"type": "number", "minimum": 0, "maximum": 0.05, "default": 0},
                        "max_codes": {"type": "integer", "minimum": 1, "maximum": 40, "default": 25},
                        "benchmark_code": {"type": "string", "nullable": True, "maxLength": 64},
                        "strategy_for_signal": {"type": "string", "default": "ma_cross", "enum": ["ma_cross", "buy_hold"]},
                        "weights_scheme": {"type": "string", "default": "equal", "enum": ["equal", "value"]},
                        "rebalance_freq": {"type": "string", "default": "monthly", "enum": ["daily", "weekly", "monthly"]},
                        "fast": {"type": "integer", "minimum": 1, "maximum": 120, "default": 5},
                        "slow": {"type": "integer", "minimum": 2, "maximum": 500, "default": 20},
                        "max_concurrent": {"type": "integer", "minimum": 1, "maximum": 20, "default": 8},
                    },
                    "required": ["codes"],
                },
            },
        },
        {
            "id": "portfolio_value_weight",
            "title": "组合回测 · 市值加权",
            "description": (
                "多标的组合回测，市值加权分配，支持日/周/月频再平衡；"
                "与 POST /api/backtest/run（strategy_id=portfolio_value_weight）等价。"
            ),
            "backtest_archive_kinds": ["portfolio_value_weight"],
            "strategy_contract_version": "1",
            "signal_params": {
                "type": "object",
                "description": "不提供组合 signal；请使用回测 POST /run。",
                "properties": {},
                "required": [],
                "maxProperties": 0,
                "additionalProperties": False,
            },
            "backtest_run": {
                "strategy_id": "portfolio_value_weight",
                "strategy_version": "1",
                "archive_kind": "portfolio_value_weight",
                "description": "组合回测市值加权分配参数。",
                "params_schema": {
                    "type": "object",
                    "properties": {
                        "codes": {"type": "string", "minLength": 1, "description": "逗号或换行分隔的标的列表"},
                        "limit": {"type": "integer", "minimum": 30, "maximum": 5000, "default": 500},
                        "start_date": {"type": "string", "format": "date", "nullable": True},
                        "end_date": {"type": "string", "format": "date", "nullable": True},
                        "commission_rate": {"type": "number", "minimum": 0, "maximum": 0.05, "default": 0},
                        "slippage_rate": {"type": "number", "minimum": 0, "maximum": 0.05, "default": 0},
                        "max_codes": {"type": "integer", "minimum": 1, "maximum": 40, "default": 25},
                        "benchmark_code": {"type": "string", "nullable": True, "maxLength": 64},
                        "strategy_for_signal": {"type": "string", "default": "ma_cross", "enum": ["ma_cross", "buy_hold"]},
                        "weights_scheme": {"type": "string", "default": "value", "enum": ["equal", "value"]},
                        "rebalance_freq": {"type": "string", "default": "monthly", "enum": ["daily", "weekly", "monthly"]},
                        "fast": {"type": "integer", "minimum": 1, "maximum": 120, "default": 5},
                        "slow": {"type": "integer", "minimum": 2, "maximum": 500, "default": 20},
                        "max_concurrent": {"type": "integer", "minimum": 1, "maximum": 20, "default": 8},
                    },
                    "required": ["codes"],
                },
            },
        },
    ]
