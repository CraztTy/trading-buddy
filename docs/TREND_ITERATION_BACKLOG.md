# 个股趋势 v0 — 迭代任务拆分（落盘）

> **定位**：在**系统主体功能完整**（数据/API/Vue/回测/纸交易/自选等主链路可跑）前提下，以 **「个股趋势」** 为突破点，**小步迭代、可合并、可回滚**。  
> **与总路线图关系**：本文件是 **[ROADMAP.md](ROADMAP.md)** 阶段 **A→C** 在「趋势轨」上的**可执行子集**；舆情 / 外部热点（如预测市场）**不纳入本 backlog 的验收范围**，另轨标记 **`track:narrative`** / **`later`**，定义见 **[NARRATIVE_TRACK.md](NARRATIVE_TRACK.md)**。阶段 **B** 在路线图中的缺口与下一小步见 **[PHASE_B_GAP_AND_NEXT.md](PHASE_B_GAP_AND_NEXT.md)**。

---

## 当前进展（滚动更新）

| 束 | 状态 | 说明 |
|----|------|------|
| **A** | **A1–A3 已示例填表** | 池与参数见 **[TREND_V0_SPEC.md](TREND_V0_SPEC.md)**。**A3** 检查表示例 **run id `1` / `2`**（另可选 **`buy_hold_single`**）；重跑回填用 **`scripts/trend_v0_archive_baseline.py`**（`--in-process` / `--json-out`；默认含 buy_hold，**`--skip-buy-hold`** 仅 MA+scan）。 |
| **B** | **B1–B3 已落盘** | **B1/B2**：见 **[TREND_V0_SPEC.md](TREND_V0_SPEC.md)**「束 B」。**B3**：**[SLOW_QUERY_AND_INDEXES.md](SLOW_QUERY_AND_INDEXES.md)**（索引、场景、分页、`alter_daily_kline_*`）。 |
| **C** | **C1–C3 已落工具** | **C1** `trend_v0_signals.py`；**C2** `trend_v0_factors_preview.py`；**C3** `trend_v0_catalog_check.py`（同 **`verify_stack`** 三 catalog 契约；可选 HTTP）。细节见 **[TREND_V0_SPEC.md](TREND_V0_SPEC.md)**「束 C1–C3」。 |
| **D** | **D1–D4 工具** | **`trend_v0_backtest_compare.py`**：D1 **`buy-hold-repeat`**；D3 **`fee-sweep-buy-hold`**；**`--in-process`** 与 A3 脚本一致免 uvicorn；**`--start-date` / `--end-date`**（束 D4）。**A3 重填**：**`trend_v0_archive_baseline.py`**（`--json-out` / `--in-process`）。规格见 **[TREND_V0_SPEC.md](TREND_V0_SPEC.md)**「束 D」「A3」。 |
| **E** | **E1 + E2 文档** | **E1**：`scripts/trend_v0_paper_smoke.py`（池内门控 + 买 + T+1 卖探测）。**E2**：规格内「回测 vs 纸交易」偏差表；可选 wiki/Issue 填实例。 |

> **v0 工具链收口（2026-04）**：束 **A–E** 对应脚本与专文已齐；**README** 提供 **`scripts/trend_v0_*.py`** 一览表，**`docs/SLOW_QUERY_AND_INDEXES.md`** 覆盖 B3。后续迭代以 **趋势 v1**、痛点专项或 **ROADMAP** 其它轨为主，本 backlog 可冻结为小版本参照。

---

## 北极星（趋势轨验收一句话）

任意纳入 **趋势 v0 股票池** 的标的：  
**数据可信 → 趋势可定义 → 可回测/可扫描 → 可存档对比 → 纸交易口径可对齐 → 复盘有据可查**。

---

## 迭代守底线（每条 PR / 每次发版前尽量满足）

| 项 | 命令或说明 |
|----|------------|
| 单元与 HTTP 集成测 | `python -m pytest -q` |
| OpenAPI 契约（若改路由/响应模型） | `python scripts/export_openapi.py` 后 `python -m pytest tests/test_openapi_contract.py` |
| 栈探活（有真库/Redis 时） | `python scripts/verify_stack.py`；仅 API 时可 `python scripts/verify_stack.py --skip-db` |
| 前端 | `frontend` 构建 + 既有 Playwright E2E（见 README **测试** 节） |
| 主路径 | `feed_dashboard` / `fetch_data`、API 启停、Vue 行情/列表/自选/回测入口不被本迭代破坏 |

---

## 束 A：趋势 v0 基线（以「定义」为主，代码改动尽量少）

**目标**：先有**可复现的池子 + 规则 + 基线存档**，再改实现。

| ID | 任务 | 产出 / Definition of Done |
|----|------|----------------------------|
| **A1** | 锁定 **趋势 v0 股票池** | 明确三选一为主：**全市场子集** / **指数成分** / **自选 N 只**；写明池子来源（列表筛选条件导出、或固定 code 列表文件路径）。 |
| **A2** | 锁定 **v0 趋势规则** | ≤2 条可执行规则（建议与现有 **双均线 `ma_cross`** 参数对齐）；表格化：`fast` / `slow` / `limit` / `start_date` & `end_date` / `commission_rate` / `slippage_rate` / 可选 `benchmark_code`。 |
| **A3** | 建立 **基线存档** | 用当前 UI 或 API 各跑 **1 次单标的** + **1 次小批量扫描**，写入 **`POST /api/backtest/runs`** 存档；记录两条 **run id** 与摘要字段，作为后续对比基准。操作步骤见 **[TREND_V0_SPEC.md](TREND_V0_SPEC.md)** 内「A3：基线存档」节。 |

**依赖**：无。建议 **Week 1** 完成 A1–A3（A1/A2 已由规格文件与池文件覆盖；A3 为人工 + API）。

---

## 束 B：数据与个股日 K（趋势地基）

**目标**：对 A1 池子敢说「日 K 决策可用」。

| ID | 任务 | 产出 / DoD |
|----|------|------------|
| **B1** | 池内标的 **日 K 覆盖**检查 | 缺 K、缺 `change_pct`、异常停牌比例在可接受阈值内；可复用 **`scripts/check_daily_kline_quality.py`**（含 `--gap-*` 等）并保留命令与结论片段。 |
| **B2** | **交易日历**与拉数节奏文档化 | 链到 **[FIRST_STEPS.md](../FIRST_STEPS.md)**、**[DATA_AND_ADJUSTMENT.md](DATA_AND_ADJUSTMENT.md)**；写清「池子更新 + 日更」推荐命令（如 `feed_dashboard --profile daily`）。 |
| **B3** | （可选）**慢查询 / 大表**清单 | 列表、排行、K 线批量场景：已知索引与分页策略；与 **`alter_daily_kline_*`** 类脚本对齐说明。 |

**依赖**：A1。建议 **Week 1–2**。

---

## 束 C：研究层 — 个股趋势「可调用」

**目标**：趋势从个人经验变成**可注册、可复现**的资产。

| ID | 任务 | 产出 / DoD |
|----|------|------------|
| **C1** | **信号**路径固化 | 对池内抽样，**`GET /api/backtest/ma-cross/signal`** 或 **`POST /api/strategies/signal`** 与 UI 一致；可选加脚本或最小集成测防回归。 |
| **C2** | **因子**与趋势结合 | 选 1～2 个价量趋势相关因子，走通 **`GET /api/factors/preview`**；结论与 **[FACTORS.md](FACTORS.md)** 一致。 |
| **C3** | **策略目录与存档契约** | **`GET /api/strategies/catalog`** / **`GET /api/backtest/catalog`** 与 `kind`、`archive_kind`、`strategy_version` 无漂移；**`verify_stack`** 与 **`tests/test_openapi_contract.py`** 保持绿。 |

**依赖**：A2、B1。建议 **Week 2–3**。

---

## 束 D：回测与对比（盈利能力主战场）

**目标**：迭代「规则」时有**数字可对打**。

| ID | 任务 | 产出 / DoD |
|----|------|------------|
| **D1** | **单标的**回测最小 JSON 模板 | 文档化一条 **`POST /api/backtest/run`**（`strategy_id: ma_cross`）可复制粘贴；同参重复跑结果一致（含 `engine_version`）。 |
| **D2** | **小批量扫描**规范 | 固定 `max_codes`、`sort_by`、导出 **`export=csv`** 或 JSON 的命名约定；两次迭代间 diff 可读。 |
| **D3** | **费率敏感性** | 同一规则至少 2～3 档费率；结果进存档或表格，能回答「净利是否被费率吃掉」。 |
| **D4** | （进阶）**样本外**一小段 | 不参与调参的日期区间只跑一次主版本；结论写入存档摘要或独立小节。 |

**依赖**：A3、C1。建议 **Week 3–4**。

---

## 束 E：纸交易与口径对齐

**目标**：回测数字与「像真钱」**可解释对齐**。

| ID | 任务 | 产出 / DoD |
|----|------|------------|
| **E1** | 纸交易 **仅趋势 v0 标的** | 与 README 纸交易规则（整手、T+1、定价用最近日 K 等）一致；记录下单与拒单原因。 |
| **E2** | **回测 vs 纸交易**对照 | 同一窗口、同一规则：差异表 + 已知允许偏差说明（文档或 issue 模板一页）。 |

**依赖**：D1、E1 前需 A2 费率与规则冻结。建议 **Week 4–5**。

---

## 建议周节奏（可随人力调整）

| 周次 | 交付重点 |
|------|----------|
| **Week 1** | A1–A3 + B1 |
| **Week 2** | B2 + C1 |
| **Week 3** | D1 + D2 |
| **Week 4** | D3 + E1 |
| **Week 5+** | C2、C3、B3、D4 按痛点插入；稳定后切「趋势 v1」或并行舆情轨 |

---

## Issue / PR 标签建议

| Label | 含义 |
|-------|------|
| `track:trend` | 本 backlog 范围内 |
| `track:narrative` | 舆情 / 外部热点，**本阶段不验收**；范围与分期见 **[NARRATIVE_TRACK.md](NARRATIVE_TRACK.md)** |
| `type:data` / `type:api` / `type:ui` / `type:docs` | 便于拆分审查 |

---

## 修订记录

| 日期 | 说明 |
|------|------|
| 2026-04-11 | 首版落盘，与 ROADMAP 阶段 A–C 对齐。 |
| 2026-04-11 | 推进束 A：新增 **TREND_V0_SPEC.md**、**config/trend_v0_pool.txt**、**scripts/check_trend_v0_pool.py**；backlog 增加「当前进展」。 |
| 2026-04-13 | 束 D：`trend_v0_backtest_compare.py` + 规格「束 D」+ **`artifacts/trend_v0/`** 入 **`.gitignore`**。 |
| 2026-04-13 | 束 E：`trend_v0_paper_smoke.py` + 规格「束 E」偏差表。 |
| 2026-04-13 | A3：规格检查表填入基线 **run id**（`1` / `2`）。 |
| 2026-04-13 | D4 日期参数 + **`trend_v0_archive_baseline.py`**；backlog **D** 行更新。 |
| 2026-04-13 | B3：**[SLOW_QUERY_AND_INDEXES.md](SLOW_QUERY_AND_INDEXES.md)**；backlog **B** 行更新。 |
| 2026-04-13 | README 增加 **SLOW_QUERY** 链、**trend_v0_*** 一览表；ROADMAP 阶段 A 产出物链至慢查询文档；本文件 **v0 收口** 说明。 |
| 2026-04-13 | **NARRATIVE_TRACK.md**、**PHASE_B_GAP_AND_NEXT.md**；文首与标签表链至舆情轨与阶段 B 缺口。 |
