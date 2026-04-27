# Phase 1 迭代计划：认证 + 组合回测 + 风控 + 纸交易完善

> 目标：从单策略 MVP 进化为可内部上线使用的量化研究平台。  
> 总工期预估：8–10 周（8 个迭代，每个 1–1.5 周）。  
> 与 ROADMAP 对应：阶段 C（回测与仿真）+ 阶段 D（组合与风控）的前置部分 + 阶段 F（多用户）。

---

## 迭代拆分原则

1. **可独立交付**：每个迭代有明确入口、可测试、可合并。
2. **向后兼容**：已有 API / 前端页面不会被破坏（通过配置开关或新增路由实现）。
3. **复用现有架构**：沿用 `runner/executor` 模式、`catalog` 注册机制、`async job` 框架。
4. **先引擎后 UI**：先落地核心算法和 API，再配前端面板。

---

## 迭代 1：用户认证 MVP（~1 周）

**目标**：任何人无法随意访问你的数据和策略。后端 JWT 认证 + 前端登录能力，现有功能不受影响。

| 模块 | 任务 | 关键文件 |
|------|------|----------|
| 数据层 | 新增 `UserModel`（id, username, password_hash, is_active, created_at） | `src/data/storage/models.py` |
| 数据层 | 新增 `ApiKeyModel`（可选：支持 API Key 调用） | `src/data/storage/models.py` |
| 后端 | `POST /api/auth/register` 注册 | `src/api/routers/auth.py`（新建） |
| 后端 | `POST /api/auth/login` → 返回 JWT access token | `src/api/routers/auth.py` |
| 后端 | `get_current_user()` FastAPI Depend，未认证时 401 | `src/api/dependencies.py` |
| 后端 | `AUTH_REQUIRED` 配置开关（默认 `false`，向后兼容） | `src/common/config.py` |
| 后端 | 现有路由可选注入 `current_user`（先不强制，为迭代 2 做准备） | 所有 router |
| 前端 | `LoginModal.vue` 登录弹窗 + `AuthStore`（Pinia/Composable） | `frontend/src/components/LoginModal.vue` |
| 前端 | 请求自动带 `Authorization: Bearer <token>` | `frontend/src/composables/api.js` |
| 前端 | 未认证时拦截并弹出登录 | `frontend/src/App.vue` |
| 测试 | HTTP 测：注册、登录、401、token 刷新 | `tests/test_auth_api_http.py` |

**验收标准**：
- 开启 `AUTH_REQUIRED=true` 后，未带 token 访问任何 API 返回 401。
- 关闭 `AUTH_REQUIRED=false`（默认）时，一切行为与现在一致。
- 前端可注册、登录、登出，token 存 localStorage。

---

## 迭代 2：用户数据隔离（~0.5–1 周）

**目标**：纸交易、回测存档、自选按用户隔离，告别「全局 default 账户」。

| 模块 | 任务 | 关键文件 |
|------|------|----------|
| 数据层 | `PaperAccountModel` 加 `user_id: int`（FK → user.id） | `src/data/storage/models.py` |
| 数据层 | `BacktestRunModel` 加 `user_id: int` | `src/data/storage/models.py` |
| 数据层 | `WatchlistModel` 加 `user_id: int` | `src/data/storage/models.py` |
| 数据层 | 迁移：已有数据分配给一个默认系统用户 | `scripts/migrate_user_isolation.py` |
| 后端 | Paper API：所有操作限定当前 user | `src/api/routers/paper.py` |
| 后端 | Backtest archive API：GET /runs 只返回当前 user | `src/api/routers/backtest.py` |
| 后端 | Watchlist API：只操作当前 user 的分组 | `src/api/routers/watchlist.py` |
| 前端 | 顶栏展示当前用户名 + 登出按钮 | `frontend/src/App.vue` |
| 前端 | 切换用户时清空 sessionStorage 缓存 | `frontend/src/composables/` |
| 测试 | HTTP 测：用户 A 看不到用户 B 的纸交易和存档 | `tests/test_auth_isolation.py` |

**验收标准**：
- 用户 A 的纸交易持仓、回测存档、自选对用户 B 不可见。
- 未开启认证时（默认），使用默认系统用户，行为不变。

---

## 迭代 3：组合回测引擎核心（~1.5–2 周）

**目标**：支持多资产、权重分配、再平衡的组合级回测。这是从「单票思维」到「组合思维」的关键一步。

| 模块 | 任务 | 关键文件 |
|------|------|----------|
| 数据层 | `PortfolioBacktestResult` dataclass（组合收益曲线、持仓序列、权重变化） | `src/backtest/portfolio/`（新建目录） |
| 引擎 | `run_portfolio_backtest()` 核心算法 | `src/backtest/portfolio/engine.py` |
| 引擎 | 权重方案：等权 / 市值加权 / 自定义权重 | `src/backtest/portfolio/weights.py` |
| 引擎 | 再平衡：日频 / 周频 / 月频（按 trade_calendar） | `src/backtest/portfolio/rebalance.py` |
| 引擎 | 组合收益计算：加权平均日收益 → 累积权益曲线 | `src/backtest/portfolio/engine.py` |
| 引擎 | 组合指标：组合夏普、组合回撤、组合波动、换手率 | `src/backtest/portfolio/metrics.py` |
| 引擎 | 复用现有策略 signal：每只标的独立跑 signal，再按权重合成组合仓位 | `src/backtest/portfolio/engine.py` |
| 规则 | 组合层面费率、滑点（与单策略一致） | 复用现有 cost model |
| 测试 | 单元测：等权组合收益 = 各标的收益算术平均 | `tests/test_portfolio_engine.py` |
| 测试 | 单元测：周频再平衡权重重置 | `tests/test_portfolio_rebalance.py` |

**设计要点**：
- 输入：`codes`（标的列表）、`strategy_id`（信号策略，如 `ma_cross`）、`weights`（权重方案）、`rebalance_freq`（`daily`/`weekly`/`monthly`）、通用参数（limit, dates, commission, slippage）。
- 每只标的独立跑 signal 序列，得到每日目标仓位（0/1 或连续权重）。
- 组合日收益 = Σ(标的日收益 × 标的权重)。
- 再平衡日按目标权重重新调整，记录换手率。

**验收标准**：
- `run_portfolio_backtest(codes=["sh.000001", "sh.000300"], weights="equal", rebalance="monthly")` 返回组合权益曲线。
- 等权组合的收益与手动算术平均一致（单元测验证）。

---

## 迭代 4：组合回测 API + 前端集成（~1–1.5 周）

**目标**：用户可以在看板上配置组合并运行回测，看到组合级结果。

| 模块 | 任务 | 关键文件 |
|------|------|----------|
| 后端 | `portfolio_equal_weight`、`portfolio_value_weight` 注册为 strategy_id | `src/backtest/runner/portfolio_executor.py` |
| 后端 | `execute_portfolio_backtest()` 遵循 executor 模式 | `src/backtest/runner/portfolio_executor.py` |
| 后端 | `POST /api/backtest/run` 支持 portfolio 策略 | `src/api/routers/backtest.py` |
| 后端 | catalog 注册 portfolio 条目 | `src/strategies/catalog.py`、`src/api/routers/backtest.py` |
| 前端 | 组合回测配置面板（标的输入、权重选择、再平衡频率） | `BacktestPanel.vue` 新增组合 tab |
| 前端 | 组合结果展示：权重变化表、组合 vs 基准权益曲线 | `BacktestPanel.vue` |
| 前端 | 组合指标卡片（组合收益、夏普、回撤、换手率） | `BacktestPanel.vue` |
| 前端 | 与单策略回测结果对比（可选） | `BacktestPanel.vue` |
| 测试 | HTTP 测：组合回测 200 + 结果格式断言 | `tests/test_backtest_api_http.py` |
| 测试 | E2E：组合回测全流程 | Playwright |
| 文档 | 更新 `docs/GENERIC_BACKTEST_DRAFT.md` 和 `STRATEGY_CONTRACT.md` | docs/ |

**验收标准**：
- 前端「组合回测」tab 可选标的、选权重方案、选再平衡频率、运行回测。
- 结果展示组合权益曲线、权重饼图（最新一期）、组合指标。
- 走 `POST /api/backtest/run` 统一入口，支持 `?async=1`。

---

## 迭代 5：风控规则引擎（~1–1.5 周）

**目标**：建立可配置、可扩展的风控规则引擎，拦截违规操作。

| 模块 | 任务 | 关键文件 |
|------|------|----------|
| 数据层 | `RiskRuleModel`（id, user_id, rule_type, params_json, enabled, scope） | `src/data/storage/models.py` |
| 数据层 | `RiskEventModel`（id, user_id, rule_id, event_type, detail, created_at） | `src/data/storage/models.py` |
| 引擎 | `RiskEngine` 类：`check(rules, portfolio_state) -> RiskCheckResult` | `src/risk/engine.py`（新建目录） |
| 引擎 | 规则实现：max_drawdown（最大回撤止损） | `src/risk/rules/max_drawdown.py` |
| 引擎 | 规则实现：single_position_limit（单票仓位上限 %） | `src/risk/rules/position_limit.py` |
| 引擎 | 规则实现：sector_exposure_limit（行业暴露上限） | `src/risk/rules/sector_exposure.py` |
| 引擎 | 规则实现：daily_loss_limit（单日亏损限额） | `src/risk/rules/daily_loss.py` |
| 引擎 | 规则实现：cash_ratio_min（最小现金比例） | `src/risk/rules/cash_ratio.py` |
| 后端 | `GET /api/risk/rules` 列出当前用户规则 | `src/api/routers/risk.py`（新建） |
| 后端 | `POST /api/risk/rules` 创建/更新规则 | `src/api/routers/risk.py` |
| 后端 | `POST /api/risk/check` 试算风控（传入组合状态） | `src/api/routers/risk.py` |
| 前端 | 风控规则配置面板（开关 + 参数输入） | `frontend/src/components/RiskPanel.vue`（新建） |
| 测试 | 单元测：各规则边界条件 | `tests/test_risk_*.py` |
| 测试 | HTTP 测：规则 CRUD + check 接口 | `tests/test_risk_api_http.py` |

**验收标准**：
- 用户可配置「单票不超过 30%」、「现金不低于 10%」等规则。
- `POST /api/risk/check` 传入组合状态，返回通过/不通过及原因。
- 规则引擎可独立运行，不依赖任何特定策略。

---

## 迭代 6：组合风控 + 纸交易风控集成（~1 周）

**目标**：风控从「可配置」变成「真拦截」。

| 模块 | 任务 | 关键文件 |
|------|------|----------|
| 后端 | 组合回测执行前调用风控引擎，违规则返回 400 + 原因列表 | `src/backtest/runner/portfolio_executor.py` |
| 后端 | 纸交易 `POST /api/paper/orders` 下单前调用风控检查 | `src/api/routers/paper.py` |
| 后端 | 风控不通过时记录 `RiskEvent` | `src/api/routers/paper.py` |
| 后端 | `GET /api/risk/events` 分页查询风控事件 | `src/api/routers/risk.py` |
| 前端 | 下单时风控拦截弹窗（显示不通过原因） | `PaperTradingPanel.vue` |
| 前端 | 风控事件列表页（历史拒单/告警） | `RiskPanel.vue` |
| 前端 | 组合回测时若风控不通过，展示原因而非静默失败 | `BacktestPanel.vue` |
| 测试 | HTTP 测：风控拦截下单 400 | `tests/test_risk_integration.py` |
| 测试 | HTTP 测：风控拦截组合回测 | `tests/test_portfolio_risk.py` |

**验收标准**：
- 纸交易下单时若触发风控（如单票超限），返回 400 并显示具体原因。
- 组合回测配置若违反风控规则，直接拒绝运行并说明原因。
- 所有风控事件可审计（who/what/when/why）。

---

## 迭代 7：头寸管理与纸交易增强（~1 周）

**目标**：告别「全仓进出」，支持科学的头寸分配。

| 模块 | 任务 | 关键文件 |
|------|------|----------|
| 引擎 | 头寸规模算法：fixed_amount（固定金额每票） | `src/backtest/position_sizing.py` |
| 引擎 | 头寸规模算法：equal_weight（等权分配） | `src/backtest/position_sizing.py` |
| 引擎 | 头寸规模算法：volatility_target（目标波动率分配） | `src/backtest/position_sizing.py` |
| 引擎 | 头寸规模算法：risk_parity（风险平价，简化版） | `src/backtest/position_sizing.py` |
| 后端 | 组合回测支持 `position_sizing` 参数 | `src/backtest/runner/portfolio_executor.py` |
| 后端 | 纸交易账户支持 `initial_cash` 自定义（不再是固定 1M） | `src/api/routers/paper.py` |
| 后端 | 纸交易支持多账户（创建、切换、删除） | `src/api/routers/paper.py` |
| 数据层 | `PaperAccountModel` 支持自定义 `initial_cash` 和 `name` | `src/data/storage/models.py` |
| 前端 | 头寸方案选择器（等权/固定金额/目标波动） | `BacktestPanel.vue` |
| 前端 | 纸交易账户管理（创建、切换、重置） | `PaperTradingPanel.vue` |
| 测试 | 单元测：volatility_target 分配公式 | `tests/test_position_sizing.py` |

**验收标准**：
- 组合回测可选「等权」「固定金额每票」「目标波动率 10%」三种头寸方案。
- 纸交易可创建多个虚拟账户，各有独立资金和持仓。
- 纸交易初始资金可配置。

---

## 迭代 8：整合验收（~0.5–1 周）

**目标**：Phase 1 完整功能走通，无阻塞 Bug。

| 模块 | 任务 |
|------|------|
| 测试 | E2E：登录 → 配置组合回测 → 运行 → 查看结果 → 纸交易下单（全流程） |
| 测试 | 性能：组合回测 20 只标的、500 根 K 线、月频再平衡 < 3 秒 |
| 测试 | 回归：所有已有单策略回测、批量扫描、纸交易不受影响 |
| 文档 | 更新 `docs/STRATEGY_CONTRACT.md`（portfolio 策略契约） |
| 文档 | 更新 `docs/GENERIC_BACKTEST_DRAFT.md`（组合回测扩展） |
| 文档 | 更新 `docs/ROADMAP.md`（标记阶段 C/D 进度） |
| 文档 | 更新 `README.md`（新增组合回测和风控说明） |
| DevOps | `scripts/verify_stack.py` 通过 |
| DevOps | OpenAPI 导出并断言无漂移 |
| DevOps | E2E fixture 刷新（`export_all_e2e_catalogs.py`） |

**验收标准**：
- `pytest -q` 全绿。
- `npm run build` 通过。
- Playwright E2E 全绿。
- `scripts/verify_stack.py` 通过。

---

## 迭代依赖图

```
迭代 1（认证） ──→ 迭代 2（数据隔离）
     │                    │
     │                    ↓
     │              迭代 6（风控集成） ←── 迭代 5（风控引擎）
     │                    ↑
     │              迭代 7（头寸+纸交易增强）
     │
     ↓
迭代 3（组合引擎） ──→ 迭代 4（组合 API+前端）
```

**可并行**：
- 迭代 1、迭代 3、迭代 5 可并行启动（互不依赖）。
- 迭代 2 依赖 1；迭代 4 依赖 3；迭代 6 依赖 2+5；迭代 7 依赖 2。

**最短路径**（并行开发）：
- Week 1：迭代 1 + 迭代 3 + 迭代 5 同时启动
- Week 2：迭代 2 + 迭代 4 + 迭代 6 准备
- Week 3：迭代 4 完成
- Week 4：迭代 6 + 迭代 7
- Week 5：迭代 8 验收

**保守串行**：8–10 周。

---

## 与 ROADMAP 阶段的对照

| Phase 1 迭代 | ROADMAP 阶段 | 说明 |
|-------------|-------------|------|
| 迭代 1–2 | F（产品化·多用户） | 提前做，为后续所有功能打基础 |
| 迭代 3–4 | C（回测与仿真） | 通用回测引擎的「组合」扩展 |
| 迭代 5–6 | D（组合与风控） | 风控规则引擎 + 事前拦截 |
| 迭代 7 | C/D 交叉 | 头寸管理是回测与风控的交汇点 |
| 迭代 8 | 并行轨道（测试） | 回归 + E2E + 文档 |

---

## 迭代状态汇总（2026-04-22）

| 迭代 | 状态 | 关键交付物 |
|------|------|-----------|
| 迭代 1：用户认证 MVP | **已完成** | `src/api/routers/auth.py`（JWT）、`tests/test_auth_api_http.py`、`AUTH_REQUIRED` 开关 |
| 迭代 2：用户数据隔离 | **已完成** | `user_id` 字段（PaperAccount/BacktestRun/Watchlist）、`tests/test_auth_isolation.py` |
| 迭代 3：组合回测引擎核心 | **已完成** | `src/backtest/portfolio/`（engine/metrics/rebalance/weights）、`tests/test_portfolio_engine.py` |
| 迭代 4：组合回测 API + 前端 | **已完成** | `POST /api/backtest/run` 支持 `portfolio_equal_weight`/`portfolio_value_weight`、`BacktestPanel.vue` 组合 tab |
| 迭代 5：风控规则引擎 | **已完成** | `src/risk/engine.py`、`src/risk/rules/`（max_drawdown/position_limit/sector_exposure/daily_loss/cash_ratio）、`tests/test_risk_engine.py` |
| 迭代 6：组合风控 + 纸交易风控集成 | **已完成** | 组合回测执行前风控检查、纸交易下单前风控拦截、`tests/test_portfolio_backtest_api_http.py` |
| 迭代 7：头寸管理与纸交易增强 | **已完成** | `src/backtest/position_sizing.py`（equal/fixed_amount/volatility_target）、组合回测 `position_sizing_method`/`position_sizing_params` 参数、`BacktestPanel.vue` 头寸方案选择器、纸交易 API `account_label` 支持（state/orders/reset）、`PaperTradingPanel.vue` 账户切换与 label 传递 |
| 迭代 8：整合验收 | **已完成** | `pytest -q` 全绿（640 passed）、`npm run build` 通过、OpenAPI 重新导出、`docs/ROADMAP.md` 与 `PHASE1_ITERATION_PLAN.md` 更新 |

---

## 风险与应对

| 风险 | 影响 | 应对 |
|------|------|------|
| 组合回测引擎性能差（标的太多） | 高 | 迭代 3 中先对 20 只标的有性能基线；超过则用采样或并行 |
| 风控规则与纸交易规则冲突 | 中 | 迭代 6 中明确规则优先级文档；先纸交易规则、再风控规则 |
| 前端改动太大导致回归失败 | 中 | 每个迭代保持 `npm run build` 通过；新增 tab/面板不破坏现有布局 |
| 数据迁移（user_id）出错 | 高 | 迭代 2 中先做 SQLite 本地测试；MySQL 环境再验证；保留回滚脚本 |
| 多用户后并发问题（纸交易） | 中 | 迭代 2 中 `PaperRepository` 所有查询加 `user_id` 过滤；利用数据库隔离 |

---

## 修订

| 日期 | 说明 |
|------|------|
| 2026-04-22 | 初版：Phase 1 八迭代拆分，与 ROADMAP 阶段 C/D/F 对齐。 |
| 2026-04-22 | 迭代 1–6 完成交付：认证、用户隔离、组合回测引擎、组合回测 API/前端、风控引擎、风控集成。新增 `tests/test_portfolio_backtest_api_http.py`、`tests/test_portfolio_performance.py`。 |
