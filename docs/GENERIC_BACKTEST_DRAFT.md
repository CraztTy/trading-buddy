# 通用回测引擎 — 接口草案与迁移路径（路线图 backlog 第 4 项）

> 状态：**草案 + MVP+ 已落地**（内核抽取、同步 `POST`、`POST?async=1` + `GET …/jobs/{id}` + **`POST …/jobs/{id}/cancel`**、**`running` 超时回收**、请求体前向占位、`catalog` 的 `async_*`、**`scripts/verify_stack.py`** 含 **`--skip-db`** 与异步 smoke）；与 `GET /api/backtest/ma-cross*` **共存**。  
> 对照：`docs/ROADMAP.md` 阶段 C。

## 第一步（已实现）

- **内核**：`src/backtest/runner/ma_cross_executor.py` 的 **`execute_ma_cross_single`**；**`buy_hold`** 见 **`execute_buy_hold_single`**（`src/backtest/runner/buy_hold_executor.py`）+ **`run_buy_hold_backtest`** — 校验、拉 K、基准 K、**`assumptions`** 文案。
- **HTTP**：**`POST /api/backtest/run`**，请求体 `strategy_id` / `strategy_version` / `params`：`ma_cross` 时与 GET **`/api/backtest/ma-cross`** 查询参数同义，响应 **`result`**（`MaCrossBacktestResponse`）；**`buy_hold`** 时与 GET **`/api/backtest/buy-hold`** 同义（无 `fast`/`slow`），响应同为 **`result`**；`ma_cross_scan` 时与 GET `ma-cross/scan` 同义，响应 **`scan_result`**（`MaCrossScanResponse`）。均含 **`engine_version`**、**`assumptions`**。  
  演练示例（买入持有）：`{"strategy_id":"buy_hold","strategy_version":"1","params":{"code":"sh.000001","limit":500}}`。
  **异步（MVP）**：查询参数 **`async=1`**（或 **`async=true`**）时返回 **202** + **`job_id`** / **`status_path`**，由 **`GET /api/backtest/jobs/{job_id}`** 轮询；合法 **`status`** 含 **`pending` → `running` → `completed`**，失败为 **`failed`**，排队取消为 **`cancelled`**。**`POST /api/backtest/jobs/{job_id}/cancel`** 仅对 **`pending`** 生效。长时间滞留 **`running`** 时，**GET** 可按环境变量触发**回收为 `failed`**（见下文 **「API 契约：异步任务（job）」**）。响应体含 **`async_job_persistence`**（与 **`GET /api/backtest/catalog`** 同源）及可选 **`queued_at` / `started_at` / `finished_at`**（UTC、ISO-8601、``Z`` 后缀）。任务表在**进程内存**或 **Redis**（见上文 Redis 段）。默认不带 **`async`** 时仍为 **200 同步**。
- **发现**：**`GET /api/backtest/catalog`** — 返回 **`engine_version`**、已注册 **`strategies`**（`strategy_id` / `strategy_version` / **`response_shape`** / **`archive_kind`**（与 **`POST /api/backtest/runs`**、**`GET …/runs?kind=`** 一致）/ 同义 **GET** 路径等），便于客户端与脚本对齐 **`POST /run`** 与存档筛选；并含 **`async_run_query_param`**（默认 **`async`**）、**`async_job_status_path_template`**（默认 **`/api/backtest/jobs/{job_id}`**）与 **`async_job_persistence`**（**`memory`** \| **`redis`**，与当前 API 实例行为一致）、**`async_job_queue_key`** / **`async_job_queue_depth`**（**`redis`** 时为列表键 **`tb:backtest:job:queue`** 与 **`LLEN`** 快照；**`memory`** 时为 `null`），供客户端发现异步轮询与持久化契约。Vue **策略回测** 顶栏会拉取并展示一行摘要（含上述异步提示）；**结果存档** 类型下拉由 catalog 驱动选项与映射说明。E2E 固件 **`frontend/e2e/fixtures/backtest-catalog.json`** 由 **`python scripts/export_backtest_catalog_fixture.py`**（**`--dry-run`** 仅打印）生成，须 UTF-8。与因子固件一并刷新时用 **`python scripts/export_all_e2e_catalogs.py`**。**OpenAPI** 全量见 **`docs/openapi.json`**（**`python scripts/export_openapi.py`**）；组件 **`BacktestStrategyCatalogEntry`** 将 **`archive_kind`** 标为必选字段，与 **`pytest tests/test_openapi_contract.py`** 快照断言一致。**`scripts/verify_stack.py`** 另校验 catalog 中 **`strategy_id`** 集合与 **`src.backtest.runner`** 内 **`POST /run`** 支持的 **`STRATEGY_ID_MA_CROSS` / `STRATEGY_ID_BUY_HOLD` / `STRATEGY_ID_MA_CROSS_SCAN`** 完全一致（无漏无多）。
- **栈契约（补充）**：**`scripts/verify_stack.py`** 对 **`GET /api/backtest/catalog`** 还校验 **`engine_version`** 与内核 **`ENGINE_VERSION`** 一致、**`post_run_path`**（**`/api/backtest/run`**）、**`doc_ref`**（**`docs/GENERIC_BACKTEST_DRAFT.md`**）、**`strategy_id`** 无重复、各策略条目含 **`strategy_version`**（当前须为 **`1`**）/ **`title`** / **`description`** / **`response_shape`** / **`get_equivalent_paths`**（列表内每项须为以 **`/`** 开头且去首尾空白后非空的字符串）；**`title`/`description`** 去首尾空白后须非空；且 **`ma_cross`** 须为 **`result`** + **`["/api/backtest/ma-cross"]`**，**`ma_cross_scan`** 须为 **`scan_result`** + **`["/api/backtest/ma-cross/scan"]`**，**`buy_hold`** 须为 **`result`** + **`["/api/backtest/buy-hold"]`**（顺序一致）。DB 行数统计失败且未传 **`--skip-db`** 时，脚本会打印 **`[HINT]`** 提示可重试 **`python scripts/verify_stack.py --skip-db`**。
- **兼容**：**`GET /api/backtest/ma-cross`**、**`GET /api/backtest/buy-hold`** 与 **`POST /run`** 同核（行为与错误码不变）。**Vue 策略回测** 单标的可选 **双均线 / 买入持有** 后「运行回测」，与批量「开始扫描」均走 **`POST /api/backtest/run`** 预览并再 **`POST /api/backtest/runs`** 存档（`request_params` 存完整 run 信封）；CSV 导出仍 **GET scan**；均线快照仍 **GET signal**（仅双均线模式展示）。

## 设计目标

- **多策略**：策略以注册 ID + 版本 + 参数 JSON 调用；与 `GET /api/strategies/catalog` 契约对齐。
- **多标的 / 组合**：支持目标权重或固定手数；再平衡频率（日 / 周）可配置。
- **一致规则**：费率、滑点、T+1、整手、停牌/涨跌停不可成交 — 与纸交易层共享 **规则引擎**（长期目标，先抽象接口再合代码）。

## 建议 HTTP 形态（草案）

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/backtest/run` | 请求体：`strategy_id`, `strategy_version`, `params`, `universe`（代码列表或表达式占位）, `interval`, `start`, `end`, `initial_cash`, `commission`, `slippage` |
| `GET` | `/api/backtest/jobs/{job_id}` | 异步任务状态轮询；**200** 为 **`BacktestRunJobStatusResponse`**；**404** 无此 job；可对陈旧 **`running`** 侧效应置 **`failed`**（契约见下节） |
| `POST` | `/api/backtest/jobs/{job_id}/cancel` | 仅 **`pending`** → **`cancelled`**：**200**；**404** 无 job；**409** 非 pending（契约见下节） |
| `GET` | `/api/backtest/runs` | 与现有结果存档对齐；`kind` 扩展为策略运行类型或统一为 `generic_v1` + 子类型字段 |

**响应**：在现有 MA 回测指标集合上扩展 `positions` / `trades` 可选块、**假设说明** `assumptions[]`（数据区间、复权口径、撮合模型版本）。

## API 契约：异步任务（job）

> 权威模式定义以 **`docs/openapi.json`**（`python scripts/export_openapi.py`）为准；本节为客户端可依赖的**语义契约**摘要。

### `status` 与响应字段

| `status` | 终端态 | `finished_at` | `result` | `error` |
|----------|--------|-----------------|----------|---------|
| `pending` | 否 | 多为 `null` | `null` | 多为 `null` |
| `running` | 否 | `null` | `null` | 多为 `null` |
| `completed` | 是 | 非空（UTC `Z`） | 与同步 **`POST /run`** 成功体同形（**`BacktestRunMvpResponse`**） | 多为 `null` |
| `failed` | 是 | 非空 | `null` | 人类可读失败说明 |
| `cancelled` | 是 | 非空 | `null` | 短文案（如 `cancelled`），供展示 |

**`GET /api/backtest/jobs/{job_id}`** 成功时响应模型为 **`BacktestRunJobStatusResponse`**：必含 **`job_id`**、**`status`**、**`async_job_persistence`**（与 **`GET /api/backtest/catalog`** 的 **`async_job_persistence`** 同源，取值 **`memory` \| `redis`**），时间戳 **`queued_at` / `started_at` / `finished_at`** 为可空字符串（约定 UTC、ISO-8601、**`Z`** 后缀）。

### `GET /api/backtest/jobs/{job_id}`

| HTTP | 条件 | 客户端行为 |
|------|------|------------|
| **200** | 记录存在 | 按 **`status`** 决定是否继续轮询；**`completed`** / **`failed`** / **`cancelled`** 为可停轮询的终态 |
| **404** | 无此 **`job_id`** 或记录已淘汰（如 Redis TTL） | 勿再假定 job 存在 |

**陈旧 `running` 回收（GET 侧效应，契约）**

- 当 **`status === "running"`**、**`started_at`** 可被服务端解析为 UTC，且 **`started_at` < (当前 UTC 时刻 − `BACKTEST_ASYNC_JOB_STUCK_SEC` 秒)** 时，**本次 GET 的响应**可将任务更新为 **`failed`**，写入 **`finished_at`** 与 **`error`**（语义：执行长时间未结束，按超时策略回收；具体文案以实现/OpenAPI 描述为准）。
- 环境变量 **`BACKTEST_ASYNC_JOB_STUCK_SEC`**：默认 **1800**；**`≤ 0`** 时**关闭**该回收逻辑（**`running`** 保持至自然结束或进程丢失）。
- **竞态说明（契约层）**：回收与 worker 写完终态可能并发；客户端**以最后一次 GET 返回的 `status` 与 `result` 为准**，不假定「先 409/先回收」与 worker 写 **`completed`** 的绝对先后顺序。

### `POST /api/backtest/jobs/{job_id}/cancel`

| HTTP | 条件 | 响应体要点 |
|------|------|------------|
| **200** | 取消前 **`status === "pending"`** | **`BacktestJobCancelResponse`**：**`job_id`** + **`status: "cancelled"`**（固定枚举） |
| **404** | 无此 job / 已淘汰 | 统一错误体 |
| **409** | **`running`**、已终态等（非 **`pending`**） | 统一错误体；语义：**仅 pending 可取消** |

**Redis 队列**：已入队任务仍可能被 worker **`BRPOP`** 取出；若在执行前记录已为 **`cancelled`**，worker **不得**再将其标为 **`completed`**。客户端对 **`running`** 不应依赖取消成功，应轮询终态或依赖上文 **GET 回收**（若配置开启）。

### 与 `catalog` 的交叉引用

客户端应通过 **`GET /api/backtest/catalog`** 读取 **`async_job_status_path_template`**、**`async_run_query_param`**、**`async_job_persistence`**、**`async_job_queue_key`** / **`async_job_queue_depth`**（**`redis`** 时非空），与本文 **GET/POST job** 路径及轮询策略对齐；**不改变**上表 HTTP 状态码与 **`status`** 枚举。

## 迁移路径（渐进）

1. **不改现有路由**：继续提供 `ma-cross` / `ma-cross/scan` / **`buy-hold`**。
2. **抽取内核**：单标的 **`execute_ma_cross_single`**、**`execute_buy_hold_single`**；批量 **`execute_ma_cross_scan`** / **`ma_cross_scan_items`** / **`parse_scan_codes`**（`src/backtest/runner/ma_cross_scan_executor.py`）；`src/backtest/scan.py` 仅保留 CSV 并从 runner 再导出供 CLI。**本地脚本**：**`scripts/run_backtest.py`** 默认双均线；**`--buy-hold`** 调用 **`run_buy_hold_backtest`**（与 **`POST /api/backtest/run`** 的 **`buy_hold`** 分支同源，读 **`.env`** 数据库）；**`--start-date` / `--end-date`**（**`YYYY-MM-DD`**）与 **`params`** 同义，见根目录 **`README.md`**。
3. **统一存档**：`backtest_run.kind` 增加通用类型或 `request_params.strategy_id` 必填，便于列表筛选与复现。
4. **纸交易对齐**：规则校验从纸交易模块 import 同一模块，避免两套逻辑漂移。

## MVP 第二步（建议 backlog，小步可验收）

与上文「建议 HTTP 形态」对齐的**下一批**工作，不改变已发布的 **`POST /api/backtest/run`** 成功语义，优先可测、可文档化项：

- **请求体前向字段（可选，已落地）**：**`BacktestRunMvpRequest`** 已含 **`universe` / `interval` / `start` / `end` / `initial_cash` / `commission` / `slippage`** 可选占位字段，OpenAPI 中标注 **MVP 不参与调度**；**`model_config.extra = "ignore"`** 忽略未知键。调度仍以 **`strategy_id` + `params`** 为准。
- **异步任务形态（已落地 MVP）**：**`POST /run?async=1`** 返回 **202** + **`job_id`** / **`status_path`**；**`GET /api/backtest/jobs/{job_id}`** 轮询 **`pending` / `running` / `completed` / `failed` / `cancelled`**；**`POST …/jobs/{job_id}/cancel`** 与 **`BACKTEST_ASYNC_JOB_STUCK_SEC`** 行为见上文 **「API 契约：异步任务（job）」**。当 **`REDIS_ENABLED`** 且 **`BACKTEST_ASYNC_JOB_STORE`** 为 **`auto`**（默认）时，任务入 **Redis 列表队列**（键 **`tb:backtest:job:queue`**）且状态写入 **Redis JSON**（键 **`tb:backtest:job:{job_id}`**，TTL 见 **`BACKTEST_ASYNC_JOB_TTL_SEC`**，默认 7 天），API 进程重启后仍可轮询（须在队列消费完成前保持 Redis 可用）。**`BACKTEST_ASYNC_JOB_STORE=memory`** 时始终用进程内表（重启清空）；**`=redis`** 时强制 Redis，未连接则 **503**。**`GET /api/backtest/catalog`** 的 **`async_job_persistence`** 为 **`memory`** 或 **`redis`**，与当前实例行为一致。默认不带 **`async`** 仍为 **200 同步**。
- **第三套策略注册清单**：新 `strategy_id` 时同步 **`src/backtest/runner`** 常量、**`_backtest_engine_catalog_payload`**、**`GET /api/strategies/catalog`**、**`scripts/verify_stack.py`**、**`export_backtest_catalog_fixture.py`** / **`tests/test_openapi_contract.py`**（与仓库内既有 catalog 契约流程一致）。

**新策略接入检查清单（复制勾选）**

1. **`src/backtest/runner`**：注册 **`STRATEGY_ID_*`**，实现 **`execute_*`** 并在 **`POST /api/backtest/run`** 分支接线。  
2. **`GET /api/backtest/catalog`**：在 **`_backtest_engine_catalog_payload`**（或等价）增加条目：**`strategy_id` / `strategy_version` / `response_shape` / `archive_kind` / `get_equivalent_paths`**，**`title`/`description`** 非空。  
3. **`GET /api/strategies/catalog`**：**`src/strategies/catalog.py`** 增加 **`id`** 与 **`backtest_run`**（**`strategy_id`**、**`archive_kind`** 与上一步 **`archive_kind`** 一致）、**`backtest_archive_kinds`**、**`signal_params`**（无试算则 **`maxProperties: 0`**）。  
4. **单测**：**`tests/test_backtest_api_http.py`**（**`POST /run`**）、**`tests/test_strategies_api_http.py`**（**`archive_kind`** 与 engine catalog 对齐已有用例）、**`tests/test_openapi_contract.py`**；必要时 **`tests/test_verify_stack_catalog_shape.py`**。  
5. **文档与固件**：**`docs/GENERIC_BACKTEST_DRAFT.md`** / **`docs/STRATEGY_CONTRACT.md`**；**`python scripts/export_openapi.py`**；**`python scripts/export_backtest_catalog_fixture.py`**（或 **`export_all_e2e_catalogs.py`**）刷新 **`frontend/e2e/fixtures/backtest-catalog.json`**。  
6. **异步行为**：若该策略支持 **`?async=1`**，确认 **Redis** 与 **memory** 路径下 worker 与 **`cancelled` / 回收** 语义仍成立（见上文 **API 契约：异步任务**）。
- **指标与假设扩展**：在 **`assumptions`** 与响应 JSON 上增加版本号或可选块（如 `positions`）时， bump **`ENGINE_VERSION`** 并更新本文件与 **`verify_stack`** 断言。

## 非目标（本阶段不做）

- 高频 tick 级撮合、Level2 订单簿仿真。
- 全自动参数寻优服务化（可在脚本层先做，不进 MVP API）。

## 修订

| 日期 | 说明 |
|------|------|
| 2026-04-10 | 「迁移路径」§2：**`scripts/run_backtest.py`** **`--buy-hold`**、**`--start-date` / `--end-date`**（与 **`params`** 同义）及 **`README.md`** 链。 |

实施通用回测 MVP 时更新本草案并链接 OpenAPI 示例。
