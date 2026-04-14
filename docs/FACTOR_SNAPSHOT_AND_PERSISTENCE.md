# 因子截面持久化（阶段 B →「厚」）— 设计小步

> **状态**：仅设计稿与命名约定；**不**引入新 ORM 表、**不**改现有 HTTP/CLI 行为。  
> **上游**：**[FACTORS.md](FACTORS.md)**「截面因子数据模型（草案）」、**`GET /api/factors/cross-section`**、**`scripts/export_factor_cross_section.py`**。  
> **下游**：拍板后再写 **`init_db` 迁移**、批处理入口或 **API 写入**。

---

## 1. 要解决的问题（「厚」想覆盖什么）

| 需求 | 薄层（当前）是否够用 | 「厚」层要补什么 |
|------|----------------------|------------------|
| 某日全市场 **ret / 价量** 可复算、可审计 | HTTP/CSV + `manifest` 可描述来源 | 历史多日、多版本并排查询；与回测/研究 JOIN |
| 与 **`daily_kline`** 血缘清晰 | 导出脚本从同一仓储读 | 落盘后仍能对齐 **`trade_date` / code** 与 **`ingest_run_id`** |
| 重建 / 回灌 | 重跑脚本即可 | 幂等键、部分重算、冷热分层（可选） |

---

## 2. 方案对比（库表 vs 文件）

| 维度 | **A — 库表 `factor_snapshot`（或分区表）** | **B — 仅文件（Parquet / 分区 CSV）+ `manifest`** | **C — 混合** |
|------|---------------------------------------------|--------------------------------------------------|--------------|
| **查询** | SQL 过滤 `as_of`、多因子列、与 `stock_info` JOIN 方便 | DuckDB/Polars/Spark 读 Parquet；或按日文件 grep | 热数据表 + 冷归档文件 |
| **运维** | 备份随 DB；索引与膨胀需规划 | 对象存储或 NFS；Git 外大文件 | 两套监控 |
| **版本与回滚** | `factor_set_id` / `ingested_at` 列或附表 | `manifest` 中 `git_commit` + 文件 SHA | 表记指针指向文件路径 |
| **与现有 CLI** | 新增 `ingest` 或扩展导出写库 | **`experiments/.../outputs/`** 已是 B 子集 | 先 B 后 A 迁移 |

**默认推荐（分阶段）**：先 **B 规范化**（目录 + `manifest` 字段补齐），再视查询压力决定是否上 **A**；**C** 适合日频全市场、年级别历史都进分析库的场景。

---

## 3. 分阶段路线（可合并 PR 的粒度）

1. **B0（已具备）**：**`export_factor_cross_section.py`** → CSV；**`GET /api/factors/cross-section`** 只读不落库。  
2. **B1（文档 + 约定）**：**`experiments/{id}/manifest.json`** 增加可选字段 **`factor_exports`**（见下 §5）；仍无新代码。  
3. **B2（仍可无 DB 表）**：脚本 **`--format parquet`** 或独立 **`export_factor_cross_section_parquet.py`**（依赖可选 `pyarrow`），输出与 CSV 同列语义。  
4. **A1（首次落库）**：单表 **`factor_cross_section_daily`**（命名可再议），列与 **FACTORS** 草案 + 当前 **`FactorCrossSectionRow`** 对齐；**`UNIQUE(as_of_trade_date, code, factor_set_id)`**；**`init_db` + repository upsert**；**无**对外写入 HTTP（仅内部 CLI/cron）。  
5. **A2（可选）**：只读 **`GET /api/factors/cross-section/snapshot?...`** 读表（与现算路径二选一或合并策略需另文）。

---

## 4. 若选 A：表形态草案（实现前评审）

**表名（工作名）**：`factor_cross_section_daily`（避免与泛化 `factor_snapshot` 多因子宽表混淆时可再拆表）。

| 列 | 类型 | 说明 |
|----|------|------|
| `as_of_trade_date` | `DATE` | 截面日，与 **`daily_kline.trade_date`** 一致 |
| `code` | `VARCHAR(32)` | **`sh.*` / `sz.*` / `bj.*`** |
| `factor_set_id` | `VARCHAR(64)` | 如 **`ret_close_20d_v1`**（**`period` + 列语义 + 版本`**） |
| `close`, `volume`, `amount` | 数值 | 与现 API 一致 |
| `turnover_rate`, `pct_change`, `ret_pct` | 可空浮点 | 与 **`null`** 语义一致 |
| `meta_bars` | `INT` | 参与计算的根数 |
| `ingested_at` | `DATETIME` | 写入时间（审计） |
| `source` | `VARCHAR(32)` | 如 **`compute_v1`** / **`reimport`** |

**索引**：**`PRIMARY KEY (as_of_trade_date, code, factor_set_id)`** 或 **唯一约束 + surrogate `id`**（按 MySQL/SQLite 习惯二选一）。二级索引：**`(as_of_trade_date)`**、**`(code, as_of_trade_date)`** 便于时间序列拉取。

**幂等**：同一 **`factor_set_id` + as_of + code`** 重复跑 **upsert** 覆盖或跳过（策略写进批处理说明）。

---

## 5. `manifest.json` 扩展（B1 即可文档化）

在 **[experiments/README.md](../experiments/README.md)** 示例上增加可选块：

```json
"factor_exports": [
  {
    "path": "outputs/cross_20240628.csv",
    "as_of_trade_date": "2024-06-28",
    "factor_set_id": "ret_close_20d_v1",
    "columns": ["as_of_trade_date", "code", "close", "volume", "ret_20d", "meta_bars"],
    "cli": "python scripts/export_factor_cross_section.py --as-of-date 2024-06-28 --period 20 -o outputs/cross_20240628.csv"
  }
]
```

与 **`data_fingerprint` / `api_openapi_sha256`** 并列，便于复现实验时核对因子层。

---

## 6. 待决问题（需产品 / 研究拍板后再写代码）

1. **时点**：截面是 **T 日收盘后** 还是 **T+1 开盘前** 再算？影响 **`as_of_trade_date`** 与回测 **`signal`** 对齐方式。  
2. **版本号**：**`factor_set_id`** 是否纳入 **OpenAPI / `__version__`** 或独立 **`factors_schema_version`**？  
3. **是否允许 HTTP 触发写库**：默认 **否**（仅 CLI/cron）；若将来要，需鉴权与配额。  
4. **宽表 vs 窄表**：多因子一表多列（宽） vs **键值行**（窄，`(factor_name, value)`）；首版建议 **宽表 + 固定 `factor_set_id`**，避免过早通用化。

---

## 7. 修订

| 日期 | 说明 |
|------|------|
| 2026-04-15 | 首版：方案对比、分阶段、表草案、`manifest` 扩展、待决问题。 |
