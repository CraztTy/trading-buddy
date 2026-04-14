# experiments/（研究实验目录约定）

与 **[docs/PHASE_B_GAP_AND_NEXT.md](../docs/PHASE_B_GAP_AND_NEXT.md)** §3「研究工作流」对齐：**本目录不入 CI 产物校验**；内容可为本地草稿、与 **`POST /api/backtest/runs`** 互拷的 `request_params` 等。

## 建议布局

```text
experiments/{experiment_id}/
  config.yaml          # 或 config.json：标的池、策略、窗口、费率等
  manifest.json        # 建议字段：git_commit、data_fingerprint、api_openapi_sha256（或导出时间）、params 摘要
  outputs/             # 图表、导出 JSON、日志片段（大文件可 .gitignore 子路径）
```

- **`experiment_id`**：小写英文 + 数字 + 连字符，如 `oos-2023-ma-vs-bh`。
- **`manifest.json`** 可与 **`scripts/trend_v0_archive_baseline.py --json-out`** 产出的 run id 并排记录，便于对照 **A3 检查表**（见 **[docs/TREND_V0_SPEC.md](../docs/TREND_V0_SPEC.md)**）。
- 大体积产物请放在 **`artifacts/`**（已根 **`.gitignore`**）或本实验目录 **`outputs/`**（根 **`.gitignore`** 已忽略 **`experiments/**/outputs/`**）；若需版本管理小样本可另建 **`samples/`** 并纳入 Git。

首版**不强制**仓库内必须有子目录；需要时按上表新建即可。

**实现提示**：**`scripts/run_backtest.py`**、**`scripts/scan_backtest.py`**、**`scripts/trend_v0_archive_baseline.py`**、**`scripts/trend_v0_backtest_compare.py`** 共用 **`src/common/cli_iso_date.py`** 的 **`parse_cli_iso_date`**、**`check_cli_date_order`**（非法 **`YYYY-MM-DD`** 在写库 / 请求前即失败；**`start_date` > `end_date`** 时 **run_backtest** / **scan** **退出码 2**，**trend_v0** 两脚本 **退出码 1**）。**CI（无 DB）**：**`tests/test_cli_iso_date_scripts.py`** 覆盖上述日期解析与四条脚本的 **`importlib` 顶层加载**。

**截面因子命名锚点**（只读 **HTTP**：**`GET /api/factors/cross-section`**，不落库；批处理写入仍自定）：**[docs/FACTORS.md](../docs/FACTORS.md)**「截面因子数据模型（草案）」与 **HTTP 只读预览** 节。Vue 看板在行情侧栏 / 因子页眉可链到该接口（**`as_of_date`** 来自 **overview** 指数日，见 **`frontend/src/composables/crossSectionOverviewLink.js`**）；栈探测 **`python scripts/verify_stack.py`** 在 **overview** 有 **`date`** 时烟囱同一路径（否则 **[SKIP]**）。**CSV / Parquet 导出（需 DB）**：**`python scripts/export_factor_cross_section.py --as-of-date YYYY-MM-DD -o experiments/<id>/outputs/cross.csv`** 或 **`--output-format parquet -o …/cross.parquet`**（默认 **`get_daily_last_n_bars_per_code`**；Parquet 依赖 **`pyarrow`**；老库 **`--legacy-per-code-fetch`** 或 **`--auto-legacy-fallback`**）；**`--print-manifest-snippet`** 打印 **`manifest.factor_exports[]`** JSON 片段到 stderr；**`--dry-run`** 仅统计当日标的列表不写文件（详见脚本 docstring）。

**「厚」之前的设计约定**：截面若落盘或将来进库，与 **`manifest.json`** 的衔接见 **[docs/FACTOR_SNAPSHOT_AND_PERSISTENCE.md](../docs/FACTOR_SNAPSHOT_AND_PERSISTENCE.md)**（可选 **`factor_exports`** 块、**`factor_set_id`**、分阶段 **B0→A2**）。

## `manifest.json` 示例（可复制改字段）

下列值为占位；**`a3_run_ids`** 可与 **`python scripts/trend_v0_archive_baseline.py --json-out …`** 输出合并或互链。

```json
{
  "experiment_id": "oos-2023-ma-vs-bh",
  "description": "样本外窗口 2023-01-01 — 2024-06-30；MA vs buy_hold",
  "git_commit": "abc1234",
  "recorded_at_utc": "2026-04-10T12:00:00Z",
  "data_fingerprint": "optional: e.g. daily_kline max(trade_date) per pool",
  "api_openapi_sha256": "optional",
  "a3_run_ids": {
    "ma_cross_single_run_id": null,
    "ma_cross_scan_run_id": null,
    "buy_hold_single_run_id": null
  },
  "cli": {
    "trend_v0_archive_baseline": "python scripts/trend_v0_archive_baseline.py --in-process --start-date 2023-01-01 --end-date 2024-06-30 --json-out artifacts/trend_v0/a3_oos_run_ids.json"
  },
  "factor_exports": []
}
```

可选 **`factor_exports`**：非空时为对象数组，字段见 **[docs/FACTOR_SNAPSHOT_AND_PERSISTENCE.md](../docs/FACTOR_SNAPSHOT_AND_PERSISTENCE.md)** §5；用于记录 **`export_factor_cross_section.py`** 等产物的路径、**`as_of_trade_date`**、**`factor_set_id`** 与列清单。
