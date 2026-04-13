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
    ]
