# 路线图阶段 B：对照现状与「尚未代码化」的下一小步

> 对照 **[ROADMAP.md](ROADMAP.md)** 阶段 **B：研究层** 三条 bullets 与「产出物」；**舆情 / 叙事** 见独立文档 **[NARRATIVE_TRACK.md](NARRATIVE_TRACK.md)**（**`track:narrative`**）。

---

## 1. 策略目录与契约

| 路线图表述 | 仓库现状 | 缺口 | 建议下一小步 |
|------------|----------|------|----------------|
| 策略 ID、schema、版本、依赖数据；与 `kind`/存档对齐 | **`GET /api/strategies/catalog`**、**`GET /api/backtest/catalog`**、**`POST /api/backtest/run`**、存档 **`POST /api/backtest/runs`**；**[STRATEGY_CONTRACT.md](STRATEGY_CONTRACT.md)** | ~~第二套真实策略~~ **`buy_hold`** 已注册（`POST /run` + **`buy_hold_single`** 存档 + 看板单标的切换）；后续可再扩 **`example_*`** 演示策略 | 新策略仍按 **`GENERIC_BACKTEST_DRAFT.md`** 检查清单同步 runner / catalog / `verify_stack` / E2E 固件 |

---

## 2. 因子与特征库（先薄后厚）

| 路线图表述 | 仓库现状 | 缺口 | 建议下一小步 |
|------------|----------|------|----------------|
| 统一时间索引、截面缓存；经典价量因子 + 测试 | **`src/factors/primitives.py`**、**`kline_series`**、**`cross_section.compute_cross_section_row`**；**`GET /api/factors/preview`**、**`GET /api/factors/catalog`**、**`GET /api/factors/cross-section`**；**`scripts/export_factor_cross_section.py`**；Vue **`crossSectionOverviewLink.js`**；**`verify_stack`** overview 填日烟囱；**[FACTORS.md](FACTORS.md)**（HTTP + 截面草案）；**`tests/test_factors_*.py`**、**`test_export_factor_cross_section`**、**`test_factors_api_http`**（截面 HTTP） | **缓存层**（Redis/本地）、**截面落库/批处理写入**（库表 vs Parquet，见下设计稿）、与流水线深度绑定 | **厚之前**：先读 **[FACTOR_SNAPSHOT_AND_PERSISTENCE.md](FACTOR_SNAPSHOT_AND_PERSISTENCE.md)**（方案对比、**B0→A2** 分阶段、表草案、**`manifest.factor_exports`**、待决问题）；**厚**：在评审稿上定 **A / B / C** 与 **`factor_set_id`** 规则后再动 **`init_db`** 与写入路径；**薄**增量照旧：Notebook / **HTTP** / CLI → **`experiments/.../outputs/`** |

---

## 3. 研究工作流（当前基本未代码化）

| 路线图表述 | 仓库现状 | 缺口 | 建议下一小步 |
|------------|----------|------|----------------|
| Notebook/脚本与 API 对齐的「可复现实验包」：配置 + 数据快照哈希 + 结果哈希 | 各 **`scripts/trend_v0_*.py`**、**`verify_stack`** 等可复现；**`trend_v0_backtest_compare.py`** 已支持 **`--in-process`**、**`buy-hold-repeat`**、**`fee-sweep-buy-hold`**；**`trend_v0_archive_baseline.py`** 默认含 **buy_hold** 存档（**`--skip-buy-hold`** 可关）。仍**无**统一实验包格式 | **无** `manifest`、**无** 官方目录约定、**无** 结果与数据版本绑定规范 | **仅文档**：目录布局见仓库 **`experiments/README.md`**（**`experiments/{experiment_id}/`**、`config`、`manifest` 建议字段、`outputs/`）；与 **`POST /api/backtest/runs`** 的 `request_params` 可互拷。首版不要求 CI 校验 |

---

## 4. 产出物对照（ROADMAP 原文）

阶段 B **产出物**：策略注册表、最小因子包、实验复现说明。

| 产出物 | 对应文档/代码 |
|--------|----------------|
| 策略注册表 | **OpenAPI** + **`STRATEGY_CONTRACT.md`** + 双 **catalog** |
| 最小因子包 | **`FACTORS.md`** + **`src/factors/`** |
| 实验复现说明 | 仓库根 **`experiments/README.md`**（目录布局与 **`manifest` 建议字段**）；与 **§3** 表「建议下一小步」一致，**仍无**强制 CI 与机器可读校验 |

---

## 5. 修订

| 日期 | 说明 |
|------|------|
| 2026-04-13 | 首版：阶段 B 三条对照 + 下一小步建议。 |
| 2026-04-10 | §3「仓库现状」补充 **trend_v0** 脚本 **`--in-process`** / **buy_hold** 相关 mode；CI 侧见 **`tests/test_trend_v0_compare_helpers.py`**（无 DB 指纹、请求体、**`_HttpxApiBridge`** URL 拼接断言）。**README**「最小回测 / 测试」链至 **buy_hold** 与上述单测。 |
| 2026-04-10 | 新增 **`experiments/README.md`**（约定 **`experiments/{id}/`**）；**§4** 产出物「实验复现说明」改为部分落地；**`tests/test_cli_iso_date_scripts.py`**（原 **`test_run_backtest_parse.py`**）覆盖 **`cli_iso_date`** 与相关 CLI 顶层加载。 |
| 2026-04-13 | **§2 / 实验目录**：**`FACTORS.md`** 截面草案；**`experiments/README.md`**；**`export_factor_cross_section.py`**（**`--dry-run`**、**`get_daily_last_n_bars_per_code`**、**`--legacy-per-code-fetch`** / **`--auto-legacy-fallback`**、**`--max-concurrent`**）；**`KlineRepository.list_codes_on_trade_date`**、**`get_daily_last_n_bars_per_code`**；根 **README** / **`FIRST_STEPS`**；**`tests/test_kline_repository_sqlite.py`**、**`tests/test_export_factor_cross_section.py`**。 |
| 2026-04-14 | **§2**：**`GET /api/factors/cross-section`**、**`compute_cross_section_row`**、Vue 快捷链、**`verify_stack`** 截面烟囱、**`tests/test_factors_cross_section.py`**；**§2 表**「仓库现状 / 缺口」与上述对齐。 |
| 2026-04-15 | **§2「厚」前设计**：新增 **[FACTOR_SNAPSHOT_AND_PERSISTENCE.md](FACTOR_SNAPSHOT_AND_PERSISTENCE.md)**；**§2 表**「建议下一小步」链至该文。 |
| 2026-04-16 | **B2 薄落地**：**`export_factor_cross_section.py`** 支持 **Parquet**、**`--print-manifest-snippet`**；**`cross_section_factor_set_id`**；**`pyarrow`** 依赖。 |
