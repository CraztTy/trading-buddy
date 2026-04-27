# Trading Buddy — 产品路线图（对标北极星）

> **北极星**：打造全世界范围内体验与能力都顶尖的 **A 股量化交易系统**（数据、研究、回测、风控、执行与运维一体化，对真实资金与合规极端负责）。  
> 本文档为工程可执行的滚动计划；当前代码基线为 **Trading Buddy V1**（数据 + API + Vue + 最小回测 / 纸交易 / 自选 / 结果存档），后续迭代以本路线图排序与验收。

---

## 北极星定义（可验收，而非口号）

将「最好」落成六类指标；**每个里程碑须能对照其中至少一类**说明贡献。

**专项 backlog（个股趋势 v0）**：与阶段 A–C 对齐的可执行任务拆分见 **[TREND_ITERATION_BACKLOG.md](TREND_ITERATION_BACKLOG.md)**（小步迭代、守底线清单、束 A–E）。默认池、参数与基线存档步骤见 **[TREND_V0_SPEC.md](TREND_V0_SPEC.md)**。

| 维度 | 含义 |
|------|------|
| **正确性** | 行情 / 复权 / 停牌 / 除权除息口径一致；回测、纸交易与（未来）实盘撮合规则可对齐解释。 |
| **完备性** | 研究 → 回测 → 风控 → 仿真 → 实盘（可选）→ 归因与复盘，链路不断档。 |
| **可靠性** | 数据与任务可回放、可审计；API 与关键路径有测试、SLO、告警。 |
| **性能与成本** | 从单机到可水平扩展有清晰路径（缓存、分区、异步任务）。 |
| **安全与合规** | 密钥、权限、操作留痕；A 股交易规则与适当性边界在设计与文档中显式化。 |
| **研究效率** | 策略与参数可版本化、可复现、可对比；低摩擦接入因子与（可选）机器学习。 |

---

## 阶段划分（建议 12–24 个月滚动，按季度切里程碑）

### 阶段 A：地基加固（世界级前提）

**目标**：干净环境可复现；数据层可信到「敢用来做决策」。

- **数据管道**：增量更新、失败重试、幂等写入；关键表（`stock_info`、`daily_kline`、**`trade_calendar`**）数据质量检查（缺失率、重复、日期空洞、交易日历覆盖）。落地入口：**`python scripts/check_daily_kline_quality.py`**（**`--json`** 含全表 `trade_calendar` 摘要）、**`docs/DATA_AND_ADJUSTMENT.md`**、**`scripts/fetch_data.py`**（`--kline-retries`、**`--mode calendar`** / **`--with-calendar`** 等）。
- **复权与公司行为**：明确前复权 / 后复权 / 不复权策略与回测默认；中长期覆盖分红送转等（可先文档 + 技术债清单，再分步实现）。
- **多数据源抽象**：在现有数据源之上抽象 provider 接口，为付费源 / Level2 留切换点。
- **观测与运维**：结构化日志、健康检查；任务运行记录（耗时、行数）与简单告警钩子。

**产出物**：数据质量报告脚本、口径文档（**[DATA_AND_ADJUSTMENT.md](DATA_AND_ADJUSTMENT.md)**）、**[SLOW_QUERY_AND_INDEXES.md](SLOW_QUERY_AND_INDEXES.md)**（`daily_kline` 索引与热点查询）、CI 门禁（测试 + 前端构建 + E2E）、核心仓储与 HTTP 集成测覆盖。

---

### 阶段 B：研究层（找得到 Alpha）

**目标**：从「单策略 HTTP」进化为「可管理的研究资产」。

- **策略目录与契约**：策略 ID、参数 schema、版本、依赖数据清单；与 `kind` / 存档模型对齐。
- **因子与特征库（先薄后厚）**：统一时间索引、截面缓存约定；经典价量因子 + 单元测试打底。
- **研究工作流**：Notebook / 脚本与 API 对齐的「可复现实验包」（配置 + 数据快照哈希 + 结果哈希）。

**产出物**：策略注册表、最小因子包（见 **`docs/FACTORS.md`** 与 **`src/factors/`**）、实验复现说明（可放在本目录或 README 引用）。

**对照与缺口（阶段 B）**：已落地与「尚未代码化」的下一小步见 **[PHASE_B_GAP_AND_NEXT.md](PHASE_B_GAP_AND_NEXT.md)**。舆情 / 叙事平行轨见 **[NARRATIVE_TRACK.md](NARRATIVE_TRACK.md)**（**`track:narrative`**，与阶段 B 验收独立）。

---

### 阶段 C：回测与仿真（信得过数字）

**目标**：回测在统计与工程上经得起质疑。

- **通用回测引擎**：多策略、多标的、组合权重、再平衡频率；与现有双均线回测**渐进迁移**而非一次性推翻。**组合回测已落地**：`portfolio_equal_weight` / `portfolio_value_weight`（等权/市值加权、日/周/月频再平衡、风控前置检查），见 `src/backtest/portfolio/`、`src/backtest/runner/portfolio_executor.py`。
- **交易成本模型**：滑点、冲击（参数化起步）、涨跌停不可成交、停牌；与 A 股规则（T+1、整手等）一致化（与纸交易共享规则引擎）。
- **验证方法论**：样本外、滚动窗口、走步分析（walk-forward）；防前视、防幸存者偏差的 checklist。

**产出物**：回测报告模板（指标 + 假设 + 数据区间）、与纸交易对齐的回归测试集；草案见 **[GENERIC_BACKTEST_DRAFT.md](GENERIC_BACKTEST_DRAFT.md)**（演进中）。

---

### 阶段 D：组合与风控（亏得起、睡得着）

**目标**：从单票思维到组合思维。

- **组合状态机**：目标权重、约束（单票上限、行业暴露、现金比例等）。**风控引擎已落地**：`src/risk/engine.py` + `src/risk/rules/`（max_drawdown、single_position_limit、sector_exposure_limit、daily_loss_limit、cash_ratio_min），默认规则集 `src/risk/defaults.py`。
- **风险指标**：回撤、波动、集中度；压力场景（指数大跌、流动性枯竭参数化）。
- **事前 / 事中风控**：下单前检查、拒单原因可解释；与审计日志打通。**已集成**：组合回测执行前调用 `RiskEngine.check_all_passed()` 拦截违规配置；纸交易 `POST /api/paper/orders` 下单前风控检查。

**产出物**：风控规则配置格式、拒单与告警事件模型。`tests/test_risk_engine.py`、`tests/test_portfolio_backtest_api_http.py`。

---

### 阶段 E：执行层（能把单子下到券商）

**目标**：小资金真实环境可控试点。

- **券商适配层**：统一订单 / 成交 / 持仓模型；先 1 家主流接口 MVP，再第二家验证抽象。
- **仿真与实盘一致性**：同一套规则引擎驱动纸交易与实盘（差异仅在撮合与延迟）。
- **运营工具**：对账、手工干预、紧急平仓（权限分级）。

**产出物**：仿真–实盘一致性矩阵、对账脚本、上线 Runbook。

---

### 阶段 F：产品化与世界级体验

**目标**：专业用户愿意每天用。

- **看板与研究 UI**：大规模列表性能、图表交互、策略 / 实验对比视图；多用户与权限（若需要）。
- **协作（机构向可选）**：审计、策略审批流。

**产出物**：性能预算（首屏、大表）、核心用户旅程 E2E。

---

## 并行轨道（全程不中断）

| 轨道 | 内容 |
|------|------|
| **测试与质量** | 契约测试、回归集、性能基线；大改动前跑基准。 |
| **安全** | 密钥管理、最小权限、依赖与供应链扫描。 |
| **合规与披露** | 用户协议、风险提示、日志留存策略；不做违规荐股自动化。 |
| **文档** | 「口径一页纸」+ API 与数据字典与代码同步更新。 |
| **舆情 / 叙事（可选）** | 标签 **`track:narrative`**；边界与分期见 **[NARRATIVE_TRACK.md](NARRATIVE_TRACK.md)**；与「趋势轨」验收分离。 |

---

## 最近 90 天建议 backlog（可据此开 issue）

1. **门禁固定**：全量 `pytest`、前端 `npm run build`、`Playwright` 为合并前例行；新 API 必带 HTTP 测。  
2. **数据质量**：日 K 缺失 / 重复检测脚本；文档化默认复权策略与已知局限。  
3. **策略契约**：完善策略目录与统一信号接口，与回测 `kind`、结果存档对齐；开发者示例或最小 UI 可选。  
4. **通用回测**：接口草案与迁移路径书面化，再动大重构。  

### Backlog 状态（对照上节四条）

| # | 项 | 状态 | 说明 |
|---|----|------|------|
| 1 | 门禁固定 | **已完成** | `.github/workflows/ci.yml`：`python -m pytest -q` 全量 + `frontend` 下 `npm run build` 与 **Playwright**（`npm run test:e2e`）；新 API 须有 `tests/test_*_api_http.py` 类单测；**`tests/test_cli_fetch.py`** 含 **`feed_dashboard --dry-run`** 步骤链契约。本地流程见根目录 `README.md`「测试」。 |
| 2 | 数据质量 | **已完成（MVP）** | 脚本 + 库内报告 + **`docs/DATA_AND_ADJUSTMENT.md`**（含 **stock_info 中尚无日 K 的标的数**）；按交易日历的「空洞率」、全市场缺失率等为增强项，另排期。 |
| 3 | 策略契约 | **已完成（MVP）** | Catalog 含 **`backtest_run`**（与 **`POST /api/backtest/run`** 的 `params_schema` / **`archive_kind`** 对齐）、**`signal_params`**、**`backtest_archive_kinds`**；**`backtest_run.archive_kind`** 与 **`GET /api/backtest/catalog`** 逐条一致（**`tests/test_strategies_api_http.py`**）；统一信号 **`POST /api/strategies/signal`** 已接 HTTP 测（含 **`ma_cross_scan`** **400**）。开发者说明与双 Catalog 表见 **`docs/STRATEGY_CONTRACT.md`**；看板 **策略回测** 顶栏 **策略目录 / 试算信号** 已加。 |
| 4 | 通用回测 | **已完成（MVP+）** | **`docs/GENERIC_BACKTEST_DRAFT.md`**（含 **API 契约：异步 job**、**新策略接入检查清单**）；**`POST /api/backtest/run`**（`ma_cross` / **`buy_hold`** / `ma_cross_scan` / **`portfolio_equal_weight`** / **`portfolio_value_weight`**）+ **`?async=1`**、**`GET /api/backtest/jobs/{job_id}`**、**`POST …/jobs/{id}/cancel`**（**`pending`**）、**`BACKTEST_ASYNC_JOB_STUCK_SEC`** 下 **GET 回收陈旧 `running`→`failed`**；**Redis 启用**时默认 **Redis 列表队列 + JSON 任务记录**（**`BACKTEST_ASYNC_JOB_STORE`** / **`BACKTEST_ASYNC_JOB_TTL_SEC`**）；请求体**前向占位**；**`GET /api/backtest/catalog`** 含 **`async_*`** 与 **`async_job_persistence`**；**`src/backtest/runner/`**、**`async_job_backend.py`**；Vue **策略回测**（单标的策略与存档 **`buy_hold_single`**、**组合回测 tab**）；**`scripts/verify_stack.py`**（含 cancel 404 冒烟）；**`tests/test_openapi_contract.py`** 断言 **OpenAPI** 含 **`POST …/jobs/{job_id}/cancel`**。 |

### 当前进度（随迭代更新）

| Backlog 项 | 交付物 |
|-------------|--------|
| 1 门禁 | **`.github/workflows/ci.yml`**（`python -m pytest -q`）；**`tests/test_cli_fetch.py`**（`feed_dashboard --dry-run` 等）；本地：`README.md`「测试」 |
| 2 数据质量 | `scripts/check_daily_kline_quality.py`；`src/data/quality/daily_kline.py`（重复键、orphan、`codes_with_single_bar`、**`stock_info_codes_without_kline`**、最新交易日覆盖等）；**`docs/DATA_AND_ADJUSTMENT.md`** |
| 3 策略契约（MVP） | **`docs/STRATEGY_CONTRACT.md`**（含双 Catalog **`archive_kind`** 表）；`BacktestPanel.vue` 顶 **策略目录 / 试算信号**；`GET /api/strategies/catalog` 与 **`GET /api/backtest/catalog`** **`archive_kind`** 对齐单测；`POST /api/strategies/signal` + HTTP 测 |
| 4 通用回测（MVP+） | **`docs/GENERIC_BACKTEST_DRAFT.md`**；**`POST /api/backtest/run`**（同步 / **`?async=1`** + **`GET …/jobs/{id}`** + **`POST …/cancel`** + **`BACKTEST_ASYNC_JOB_STUCK_SEC`** 回收）；**`src/backtest/async_job_backend.py`**（Redis 队列 **`tb:backtest:job:queue`** + 记录 **`tb:backtest:job:{id}`**；**`BACKTEST_ASYNC_JOB_STORE`** / **`BACKTEST_ASYNC_JOB_TTL_SEC`**）；**`BacktestRunMvpRequest`** 前向占位；**`GET /api/backtest/catalog`**（**`async_job_persistence`** 等）；**`src/backtest/runner/`**；Vue；E2E **`backtest-catalog.json`** / **`installApiMocks`** 异步 pending 窗口；**`scripts/verify_stack.py`**；固件 **`export_backtest_catalog_fixture.py`** |
| 4+ 组合回测 | `src/backtest/portfolio/`（engine/metrics/rebalance/weights）、`src/backtest/runner/portfolio_executor.py`；`POST /api/backtest/run` 支持 `portfolio_equal_weight`/`portfolio_value_weight`；`BacktestPanel.vue` 组合 tab；`tests/test_portfolio_backtest_api_http.py`、`tests/test_portfolio_engine.py`、`tests/test_portfolio_performance.py` |
| 5+ 风控引擎 | `src/risk/engine.py`、`src/risk/rules/`（max_drawdown/position_limit/sector_exposure/daily_loss/cash_ratio）、`src/risk/defaults.py`；组合回测执行前 `RiskEngine.check_all_passed()` 拦截、纸交易下单前风控检查；`tests/test_risk_engine.py` |
| 7+ 头寸管理 | `src/backtest/position_sizing.py`（equal/fixed_amount/volatility_target）；组合回测支持 `position_sizing_method`/`position_sizing_params`；`BacktestPanel.vue` 头寸方案选择器；`tests/test_position_sizing.py` |
| 7+ 纸交易增强 | 纸交易 API `account_label` 参数（state/orders/reset）；`PaperTradingPanel.vue` 账户切换与多账户支持 |
| B 因子（起步） | **`src/factors/`**（**`rolling_*`** / **`rolling_zscore`** / **`ema`** / **`macd_dif_dea_hist`** / **`kdj_k_d_j`** / **`cci`** / **`williams_r`** / **`mfi`** / **`roc`** / **`trix`** / **`obv`** / **`dmi_adx_wilder`** / **`aroon`** / **`donchian`** / **`vwap_cumulative`** / **`vwap_rolling`** / **`true_range`** / **`rsi_wilder`** / **`atr_wilder`** / **`bollinger_bands`** + **`kline_true_range`** / `pct_change_*` / **`diff_n`**；**`kline_float_series`**）；**`GET /api/factors/catalog`**（算子发现）；**`docs/FACTORS.md`**；**`tests/test_factors_*.py`** |

---

## 执行约定

- **每季度**明确一个主战场（例如 Q1 数据质量 + 复权设计，Q2 通用回测 MVP）。  
- **每个 PR** 建议附带：测试或脚本证据、OpenAPI / README 必要增量、以及本文件「六类指标」中受益项的一句话说明。  

---

## 修订

本路线图随版本滚动更新；重大方向变更应更新本文件并保留简短变更说明（可写在 git commit message 与 release note）。

- **2026-04-13**：阶段 A「产出物」补充 **[SLOW_QUERY_AND_INDEXES.md](SLOW_QUERY_AND_INDEXES.md)**（`daily_kline` 索引与热点查询清单）。
- **2026-04-13**：阶段 B 链 **[PHASE_B_GAP_AND_NEXT.md](PHASE_B_GAP_AND_NEXT.md)**；并行轨增加 **舆情/叙事** 行；新增 **[NARRATIVE_TRACK.md](NARRATIVE_TRACK.md)**。
- **2026-04-22**：阶段 C 标注组合回测已落地（`portfolio_equal_weight` / `portfolio_value_weight`）；阶段 D 标注风控引擎已落地（`src/risk/engine.py` + 规则集 + 集成）。新增 `tests/test_portfolio_backtest_api_http.py`、`tests/test_portfolio_performance.py`。
- **2026-04-23**：Phase 1 迭代 7–8 完成。头寸管理（`position_sizing.py`：equal/fixed_amount/volatility_target）+ 纸交易多账户（`account_label`）+ 组合回测风控预检查修复 + `pytest` 640 全绿 + `npm run build` 通过 + OpenAPI 更新。
