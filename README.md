# Trading Buddy - 精简版量化交易系统 V1

> A股量化交易基础设施，聚焦数据层 + 可视化，为后续策略执行打基础。当前发布线：**1.2.2**（版本见 `src/common/__init__.py`、`CHANGELOG.md` 与 `GET /health` 的 `app_version`）。

长期目标与分阶段推进计划见 **[docs/ROADMAP.md](docs/ROADMAP.md)**（北极星、验收维度、阶段 A–F、并行轨道与近 90 天 backlog）。阶段 **B** 缺口与下一小步见 **[docs/PHASE_B_GAP_AND_NEXT.md](docs/PHASE_B_GAP_AND_NEXT.md)**；因子截面落库 / 文件持久化在动 **`init_db`** 之前见 **[docs/FACTOR_SNAPSHOT_AND_PERSISTENCE.md](docs/FACTOR_SNAPSHOT_AND_PERSISTENCE.md)**。**舆情 / 叙事** 平行轨见 **[docs/NARRATIVE_TRACK.md](docs/NARRATIVE_TRACK.md)**（**`track:narrative`**）。  
**个股趋势 v0 迭代任务拆分（可执行 backlog）**见 **[docs/TREND_ITERATION_BACKLOG.md](docs/TREND_ITERATION_BACKLOG.md)**；默认池与存档步骤见 **[docs/TREND_V0_SPEC.md](docs/TREND_V0_SPEC.md)**。  
**`daily_kline` 索引、排行/K 线热点与慢查询自检**见 **[docs/SLOW_QUERY_AND_INDEXES.md](docs/SLOW_QUERY_AND_INDEXES.md)**。验收用 **`scripts/trend_v0_*.py`** 一览见下节 **「个股趋势 v0 脚本」**。

## 技术栈

| 层级 | 技术选型 | 说明 |
|------|----------|------|
| 语言 | Python 3.10+ | 主流、库丰富 |
| API | FastAPI | 高性能、自动文档 `/docs` |
| 数据库 | SQLite（默认）/ MySQL 8.0 | 本地零配置或云上结构化存储 |
| 缓存 | Redis（可选） | 实时行情缓存 |
| 数据源 | baostock（免费） | A股数据、无需注册 |
| 看板 | Vue 3 + Vite + ECharts | 主看板在 `frontend/`；仓库内 `dashboard/index.html` 为旧版静态页备选 |

## 架构分层

```
┌─────────────────────────────────────────────────────────────┐
│                      看板层 (Dashboard)                       │
│              Vue 看板：K 线 / 指数 / 涨跌榜                    │
├─────────────────────────────────────────────────────────────┤
│                      API层 (API Service)                     │
│              FastAPI - 股票查询 / K线 / 实时行情               │
├─────────────────────────────────────────────────────────────┤
│                      缓存层 (Cache)                           │
│                    Redis - 实时数据（可选）                      │
├─────────────────────────────────────────────────────────────┤
│                      数据层 (Data Service)                     │
│           数据拉取 / 数据清洗 / 数据存储 / 历史数据              │
├─────────────────────────────────────────────────────────────┤
│                      数据源 (Data Sources)                    │
│                  baostock（免费）→ 未来升级付费                 │
└─────────────────────────────────────────────────────────────┘
```

## 预留扩展点（V2/V3）

- [ ] 券商API对接（实盘交易）
- [ ] 策略引擎（信号计算、回测）
- [ ] 消息队列（Kafka - 行情解耦）
- [ ] 时序数据库（ClickHouse - 历史K线）
- [ ] Level2行情（付费数据源）

## 快速开始

更细的步骤、云库与日常增量说明见 **[FIRST_STEPS.md](FIRST_STEPS.md)**。

```bash
# 1) 可选：仅本地 MySQL + Redis
docker-compose up -d

# 2) Python 依赖（云 MySQL 8 建议保留 requirements 中的 cryptography）
pip install -r requirements.txt

# 3) 根目录复制环境模板并编辑（勿提交 .env）
cp .env.example .env   # Windows: copy .env.example .env

# 4) 建表
python scripts/init_db.py
# 建表后建议灌交易日历（Baostock，需网络；看板 / 质量脚本的交易日缺口依赖 trade_calendar）
# python scripts/fetch_trade_calendar.py --start 2020-01-01 --end 2025-12-31
# 或: python scripts/fetch_data.py --mode calendar --source baostock

# 5) 灌数（推荐一键；详见 FIRST_STEPS；默认会灌 trade_calendar，无外网时加 --skip-calendar）
python scripts/feed_dashboard.py --profile quick

# 6) 启动 API
python -m uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
# 或（与 .env 中 API_HOST / API_PORT / API_DEBUG 一致）：python scripts/run_api.py

# 7) 另开终端：Vue 看板
cd frontend && npm install && npm run dev（可选：参考 `frontend/.env.example` 配置 `VITE_PROXY_TARGET` 等）
#    已在 frontend 装好依赖时，也可在仓库根执行：npm run frontend:dev（见根目录 package.json）
# 开发默认 http://localhost:5173 ，经 Vite 代理访问本机 API（生产环境 Nginx 反代 **`/api`** 与 **`/health*`** 示例见 **`frontend/README.md`**）
# 看板含「行情看板 / 股票列表 / 自选 / 因子预览 / 策略回测 / 纸交易」：指数卡片下方先请求 **`GET /api/data/trade-calendar/options`**（**`TRADE_CALENDAR_EXCHANGE_OPTIONS`** / **`TRADE_CALENDAR_DEFAULT_EXCHANGE`**）再拉 **`GET /api/data/trade-calendar/status`**（60s 轮询状态）；侧栏排行含涨幅 / 跌幅 / **成交额**（`dashboard/turnover`，可选日期）；股票列表页调用 stocks/list，点行可回到行情并切换标的；每行 **「复制」**、**「加自选」**；**「导出本页 CSV」** 导出当前页列表；**「导出全部」** 按当前筛选分页拉取合并（默认最多 1 万条，UTF-8 BOM）；若响应 offset 与请求不一致（服务端钳制）界面会提示。自选走 **`GET/POST/DELETE /api/watchlist/*`**（见下节 API 摘要）。同浏览器 **会话**内用 **sessionStorage** 记住主视图、当前标的、涨跌/成交额 Tab（刷新保留，关标签页后清除）。**纸交易**页走 **`GET /api/paper/state`**、**`GET /api/paper/orders`**（分页/可选 `code` 筛选）、**`POST /api/paper/orders`**、**`POST /api/paper/account/reset`**：默认百万虚拟资金，市价单按标的**最近日 K 收盘价**撮合；股数须 **100 整数倍**；**卖出 T+1**（`buy_trade_date` 早于定价日 K 线日，FIFO 批）。策略回测页可点 **「闭环 · 纸交易」** 带入当前标的
```

接口文档：http://127.0.0.1:8000/docs  
浅探活：`GET /health`；含 DB/Redis 探测：`GET /health/ready`。看板 **`GET /api/dashboard/turnover`**：最新（或 `trade_date`）交易日全市场**交易中**标的按**成交额**降序 Top，依赖 `stock_info` 与 `daily_kline` 索引；可选 `trade_date=YYYY-MM-DD`。  
股票：`GET /api/stocks/list` 代码列表（可选 `market`、`industry`、`stock_type`；**`limit`（1–500，默认 100）**、**`offset`** 分页；结果按 `code` 排序；**DB 层 `COUNT` + `LIMIT`/`OFFSET`**，不将全量 code 载入应用内存）。JSON 体为 **`items`**（`code` / `name` / `status`）、**`total`**（过滤后总数）、**`limit`**、**`offset`**（请求 `offset` 超界时服务端钳到**最后一页起点**并回显；末页条数可少于 **`limit`**）；**`/docs`** 中 **`StockListResponse`** 带示例 JSON。`GET /api/stocks/{code}` 详情；`GET /api/stocks/industry/{industry}` 按行业前缀返回 `StockInfo` 列表（`/docs` 见说明）。  
自选（MVP 单默认分组）：**`GET /api/watchlist/items`** 列出 `code` / `name`（左联 `stock_info`）/ `created_at`；**`POST /api/watchlist/items`** JSON `{"code":"sh.600000"}` 添加（重复 **409**；上限 500 只）；**`DELETE /api/watchlist/items/{code}`** 移除（不存在 **404**）。看板「股票列表」行内 **加自选 / 自选 ✓**，「自选」页集中管理；「策略回测」「纸交易」可从自选快捷填标的。  
因子原语只读预览：看板 **「因子预览」** 页 **`GET /api/factors/catalog`** 填算子下拉，**`GET /api/factors/preview`**（`code`、`column`、`op`、`window`、**`bb_k`**、**`macd_*`**、**`kdj_m1`/`kdj_m2`**、**`response_format=json|csv`** 等；JSON 体 **`series`**（单轨 **`value`**（含 **atr、cci、williams_r、mfi、roc、trix、obv** 等），**`adx`** 三轨 **`plus_di`/`minus_di`/`adx`**，**`aroon`** 三轨 **`aroon_up`/`aroon_down`/`aroon_osc`**，**`donchian`** 三轨 **`dc_upper`/`dc_mid`/`dc_lower`**，**`vwap`** 单轨 **`value`**（不传 **`window`** 为自首根累计，传 **`window`** 为滚动 N 根），布林带三轨，MACD **`dif`/`dea`/`hist`**，KDJ **`k`/`d`/`j`**）+ 可选 **`meta`**；与 **`docs/FACTORS.md`** 一致，不落库）。**`GET /api/factors/cross-section`** 在行情侧栏底部与因子页眉提供快捷链：**`as_of_date`** 取自 **`GET /api/dashboard/overview`** 首条指数 **`date`**，默认 **period=20**、**max_codes=100**（**`frontend/src/composables/crossSectionOverviewLink.js`**）。  
策略（V2 切片）：**`GET /api/strategies/catalog`** 列出已注册策略，含 **`signal_params`**（试算信号）、**`backtest_run`**（**`POST /api/backtest/run`** 的 `strategy_id` / `strategy_version`、建议存档 **`archive_kind`**、内层 **`params`** 的 JSON Schema）；**`POST /api/strategies/signal`** JSON `{"code","kind","params"}` 取最新信号（当前 **`kind=ma_cross`** 与 **`GET /api/backtest/ma-cross/signal`** 等价）。**`backtest_run.archive_kind`** 与 **`GET /api/backtest/catalog`** 各行 **`archive_kind`** 须一致（**`tests/test_strategies_api_http.py`** 与 **`scripts/verify_stack.py`** 防漂移）。契约全文与 curl 模板见 **`docs/STRATEGY_CONTRACT.md`**。  
回测结果存档（表 **`backtest_run`**，由 **`python scripts/init_db.py`** 创建）：**`POST /api/backtest/runs`** 提交 `kind`（`ma_cross_single` | `buy_hold_single` | `ma_cross_scan`）、`request_params`、`response_payload`（均为 JSON 对象；合计约 **2 MiB** 上限，超限 **413**），返回 **`id`** 与 **`summary`**；**`GET /api/backtest/runs`** 分页（`limit` 1–100、`offset`；看板可选每页 **10 / 30 / 50** 条、**上一页 / 下一页** 与 **跳转页码**；每页条数写入浏览器 **`localStorage`** 键 **`tb_backtest_runs_limit`**），可选 **`kind`** 只列某一类型，可选 **`q`**（最多 **120** 字符）按返回字段 **`summary`** 子串过滤（与 **`kind`** 组合为 AND）；**`GET /api/backtest/runs/{id}`** 取完整请求与响应；**`DELETE /api/backtest/runs/{id}`** 删除一条（**204**，不存在 **404**）。策略回测页在单标的（双均线或买入持有）或批量扫描成功后会自动 **POST** 存档，页底 **结果存档** 可按类型筛选、**摘要关键字** 搜索、刷新、点 **#id** 看详情、列表**勾选**（可不展开详情）**本页全选**后 **导出所选 ZIP**（内含 `backtest-runs/` 下多条 `backtest-run-{id}-{kind}.json`，单次最多 **50** 条）、**删除所选**（对每条 **DELETE**）、单条 **导出 JSON**、行内 **删除**。

## 项目结构

```
trading-buddy/
├── LICENSE                # MIT（与文末「License」一致）
├── package.json           # 可选：根目录 npm 脚本转发到 frontend/（无需在根 npm install；Node 20+）
├── .nvmrc                 # 可选：nvm/fnm 等使用 Node 20（与 Playwright CI 一致）
├── .python-version        # 可选：pyenv 等使用 Python 3.12（与 pytest CI job 一致）
├── .github/               # **workflows/ci.yml**（pytest + Playwright）、**dependabot.yml**（pip/npm 周更 PR）
├── .editorconfig          # 可选：EditorConfig（缩进、换行、尾空格等）
├── .gitattributes         # 可选：文本换行策略（如 ***.sh** 强制 LF）
├── scripts/stop_dev.ps1   # Windows：停 8000 / 5173–5175 / 4173 等监听进程
├── scripts/stop_dev.sh    # macOS/Linux：同上（需 lsof 或 fuser）
├── docker-compose.yml    # 可选：本地 MySQL + Redis
├── requirements.txt
├── .env.example           # 环境变量模板（勿写真实密码）
├── FIRST_STEPS.md         # 上手与发布流程
├── config/                # **trend_v0_pool.txt**（趋势 v0 默认股票池，可编辑）
├── docs/                  # **ROADMAP.md**；**PHASE_B_GAP_AND_NEXT.md**；**NARRATIVE_TRACK.md**；**TREND_ITERATION_BACKLOG.md**；**TREND_V0_SPEC.md**；**SLOW_QUERY_AND_INDEXES.md**；**DATA_AND_ADJUSTMENT.md**；**GENERIC_BACKTEST_DRAFT.md**；**STRATEGY_CONTRACT.md**；**FACTORS.md**
├── experiments/           # **README.md**：研究实验目录约定（可选子目录）
├── scripts/               # init_db、拉数、feed_dashboard、**verify_stack**、**run_backtest** / **scan_backtest**、**export_factor_cross_section**（截面 **ret_Nd** + 当日价量列 CSV；默认 **`get_daily_last_n_bars_per_code`**；**`--legacy-per-code-fetch`** / **`--auto-legacy-fallback`** 兼容老库，见 **FACTORS.md**）、**trend_v0_*.py**（见下表）、**export_openapi**（写 **`docs/openapi.json`**）、**export_all_e2e_catalogs**、**export_factor_catalog_fixture** / **export_backtest_catalog_fixture**、smoke_* 冒烟；**已有库补索引**：`alter_daily_kline_trade_date_amount_index.sql`（MySQL）、`alter_daily_kline_trade_date_amount_index_sqlite.sql`（SQLite）等
├── src/
│   ├── api/               # FastAPI 入口与 routers
│   ├── data/              # 数据源、存储、模型
│   ├── factors/           # 价量因子原语 + KLine（rolling_*、rolling_zscore、ema、macd、kdj、cci、williams_r、mfi、roc、trix、obv、adx/dmi_adx_wilder、aroon、donchian、vwap_cumulative/vwap_rolling、true_range、rsi_wilder、atr_wilder、bollinger、kline_true_range、pct_change_*、diff_n、kline_float_series）
│   └── common/            # 配置、日志、版本号；**`cli_iso_date.py`**（CLI 共用 **ISO 日期** / **起止顺序**）
├── frontend/              # Vue 3 看板（推荐）
├── dashboard/             # 旧版静态 HTML（可选）
└── tests/
```

### 研究实验目录（可选）

约定与 **`manifest` 建议字段**见 **`experiments/README.md`**（与 **[docs/PHASE_B_GAP_AND_NEXT.md](docs/PHASE_B_GAP_AND_NEXT.md)** 阶段 B §3 对齐）；大文件请放 **`artifacts/`**（已 **`.gitignore`**）。

### 个股趋势 v0 脚本（`scripts/trend_v0_*.py`）

均在仓库根执行；多数需 **API 已起**（`--in-process` 或 **`python -m uvicorn …`**）及 **日 K 已灌**。细节与束 A–E 对应关系见 **[docs/TREND_V0_SPEC.md](docs/TREND_V0_SPEC.md)**。  
含 **`--start-date` / `--end-date`** 时，**`trend_v0_archive_baseline`**、**`trend_v0_backtest_compare`**、**`run_backtest`**、**`scan_backtest`** 共用 **`src/common/cli_iso_date`**（**`parse_cli_iso_date`**、**`check_cli_date_order`**）。非法 ISO 或 **起止逆序** 时：**`trend_v0_*`** **退出码 1**；**`run_backtest` / `scan_backtest`** **退出码 2**。

| 脚本 | 作用 |
|------|------|
| **`scripts/check_trend_v0_pool.py`** | 池文件内各 code 是否有日 K（束 B 前置） |
| **`scripts/trend_v0_signals.py`** | 抽样 **`GET /api/backtest/ma-cross/signal`**（束 C1） |
| **`scripts/trend_v0_factors_preview.py`** | 抽样 **`GET /api/factors/preview`**（`roc`+`obv`，束 C2） |
| **`scripts/trend_v0_catalog_check.py`** | 三 catalog 契约（束 C3；默认同 **`verify_stack`** 段） |
| **`scripts/trend_v0_backtest_compare.py`** | 单标的/扫描可复现、**`--mode buy-hold-repeat`**、**`--in-process`**（TestClient，免 uvicorn）、导出、**`fee-sweep` / `fee-sweep-buy-hold`**、**`--start-date`/`--end-date`**（束 D） |
| **`scripts/trend_v0_archive_baseline.py`** | **A3**：`POST /run` → **`POST /api/backtest/runs`**（MA 单 + scan + 默认同标的 **buy_hold**；**`--skip-buy-hold`** 仅前两步），打印 run id |
| **`scripts/trend_v0_paper_smoke.py`** | 池内纸交易买 + T+1 卖探测（束 E1） |

## 环境变量（摘要）

根目录 `.env` 由 `src/common/config.py` 加载。与 **MySQL** 相关的常用键：

- `DATABASE_MODE`：`sqlite`（默认）或 `mysql`
- `DATABASE_SQLITE_PATH`（或别名 `DATABASE_DB_PATH`）：SQLite 时库文件路径，相对项目根或绝对路径；不设则 `data/trading.db`（单测可指向临时文件）。
- `DATABASE_HOST` / `DATABASE_PORT` / `DATABASE_USER` / `DATABASE_PASSWORD` / `DATABASE_NAME`
- 兼容别名：`DB_HOST`、`DB_PORT`、`DB_USER`、`DB_PASSWORD`、`DB_NAME`
- 云库：`DATABASE_CONNECT_TIMEOUT`、`DATABASE_SSL`

**Redis**：`REDIS_ENABLED`、`REDIS_HOST`、`REDIS_PORT`、`REDIS_PASSWORD`（可选）。

**其它**：`DATA_SOURCE`、`LOG_LEVEL`、`API_HOST`、`API_PORT`、`CORS_ORIGINS`（生产建议显式域名，逗号分隔）。

### API 与脚本可观测性（阶段 A）

键名与默认值以 **`.env.example`** 为准；以下为摘要。

- **探针**：`GET /health`（含 `pid`、`uptime_sec` 等浅层字段）、`GET /health/ready`（`probe_ms`、数据库与 Redis 状态）。
- **请求追踪**：所有响应带 **`X-Request-ID`**（可传请求头 **`X-Request-ID`** / **`X-Correlation-ID`**，字符集见 `.env.example`）；文本日志行尾默认有 **`rid=`**，`LOG_JSON=true` 时进入 JSON 的 `extra`。
- **`LOG_JSON=true`**：控制台与 `logs/*.log` 使用 Loguru 行级 JSON，便于 Loki/ELK。
- **访问日志**：`API_ACCESS_LOG=true` 写 **`http.access`**；**`API_ACCESS_LOG_IGNORE_PREFIXES`** 控制不记录的路径前缀（未配置时默认跳过 **`/health*`**；设为 **`none`** 则全部路径都记）。
- **慢请求 WARN**：**`API_SLOW_REQUEST_WARN_MS`**（毫秒，**`0`** 关闭）写 **`http.slow`**；**`API_SLOW_REQUEST_IGNORE_PREFIXES`** 与上类似（默认 **`/health`**；**`none`** 表示不忽略）。
- **脚本与运维**：**`scripts/stop_dev.ps1`**（Windows）、**`scripts/stop_dev.sh`**（macOS/Linux，**`lsof`** / **`fuser`**）结束 API **8000**、Vite **5173–5175**、preview **4173** 等监听；**`stop_dev.ps1`** 另清理常见 uvicorn 残留子进程；**`scripts/feed_dashboard.py`**、**`scripts/fetch_data.py`**、**`scripts/verify_stack.py`** 输出 **`[timing]`** 分段或总耗时；**`scripts/init_db.py`**、**`scripts/check_daily_kline_quality.py`**（后者耗时在 **stderr**，不破坏 **`--json`** 的 stdout）。

## 最小回测（双均线 · 批量 · 买入持有）

- **单标的 HTTP（双均线）**：`GET /api/backtest/ma-cross?code=sh.000001&fast=5&slow=20&limit=500`（脚本、书签、与 **`GET` 行为对齐** 的调试）；**Vue 看板「运行回测」** 在选 **双均线** 时与存档前试算走 **`POST /api/backtest/run`**（`strategy_id: ma_cross`，`params` 与 GET 查询同义，响应 **`result`**）。  
- **单标的 HTTP（买入持有）**：`GET /api/backtest/buy-hold?code=sh.600519&limit=500`（无 `fast`/`slow`）；**`POST /api/backtest/run`**（`strategy_id: buy_hold`，`params` 与 GET 查询同义，响应 **`result`** 与 MA 同形）；成功存档 **`kind=buy_hold_single`**。束 D 工具：**`scripts/trend_v0_backtest_compare.py`**（**`--mode buy-hold-repeat`**、**`fee-sweep-buy-hold`**、**`--in-process`**）、**`scripts/trend_v0_archive_baseline.py`**（默认同标的 **buy_hold** 存档）。辅助函数单测（无 DB）：**`tests/test_trend_v0_compare_helpers.py`**。  
  - **通用回测 MVP（同步）**：`POST /api/backtest/run` 在 **`ma_cross_scan`** 时 `params` 与下方批量扫描 GET 同义（`codes` / `max_codes` / `sort_by` / `max_concurrent` 等），响应 **`scan_result`**。单 / 批均含 **`engine_version`**、**`assumptions`**。与 **`GET ma-cross*`** **共用** `src/backtest/runner/` 内核。  
  - **通用回测 MVP（异步，可选）**：同一 JSON 体加查询参数 **`?async=1`** 或 **`?async=true`** 时返回 **202**，体含 **`job_id`**、**`status`**（`accepted`）、**`status_path`**（形如 **`/api/backtest/jobs/{job_id}`**）。轮询 **`GET /api/backtest/jobs/{job_id}`** 得 **`pending` → `running` → `completed`**（嵌套完整 **`result`**，与同步 200 同形）或 **`failed`** / **`cancelled`**（**`error`** 文案）；每轮响应含 **`async_job_persistence`**（与 **`GET /api/backtest/catalog`** 同源）及可选时间戳字段；未知或已淘汰的 **`job_id`** 为 **404**。**`POST /api/backtest/jobs/{job_id}/cancel`**：仅 **`pending`** 可 **200** 取消为 **`cancelled`**；非 pending **409**；无 job **404**。长时间滞留 **`running`** 时，**GET** 可按 **`BACKTEST_ASYNC_JOB_STUCK_SEC`**（见 **`.env.example`**，默认 1800，**`0`** 关闭）侧效应置 **`failed`**。状态机、**`result`** 与 HTTP 码表以 **`docs/openapi.json`** 为准，语义摘要见 **`docs/GENERIC_BACKTEST_DRAFT.md`** 中 **「API 契约：异步任务（job）」**。**`REDIS_ENABLED`** 且 **`BACKTEST_ASYNC_JOB_STORE=auto`**（默认）时，任务入 **Redis 列表队列**并写入 **Redis JSON**（**`GET /api/backtest/catalog`** 的 **`async_job_persistence`** 为 **`redis`**；键前缀 **`tb:backtest:job:`**，TTL 见 **`BACKTEST_ASYNC_JOB_TTL_SEC`**）；**`=memory`** 时始终进程内（重启丢失）；**`=redis`** 时强制 Redis，未连接则 **503**。不带 **`async`** 时仍为 **200** 同步。  
  - **通用回测 MVP（前向占位）**：请求体可选 **`universe` / `interval` / `start` / `end` / `initial_cash` / `commission` / `slippage`**（见 OpenAPI **`BacktestRunMvpRequest`** 说明）；当前 **不参与调度**，与 **`params`** 内费率字段独立；未知顶层键 **忽略**，便于客户端预发通用 JSON 骨架。  
  - `start_date`、`end_date`（可选，ISO 日期，含）：与 `limit` 一并约束取用的日 K；若二者均填且 `start_date` > `end_date` 则 400。  
  - `commission_rate`、`slippage_rate`：单边费率，在**持仓翻转日**各扣一次（与手续费同口径）；二者之和勿超过 `0.08`。  
  - **`benchmark_code`（可选）**：如 `sh.000300`。传入时，**underlying_beta** / **underlying_alpha_ann_pct** 为日策略收益对**基准日收益**（基准收盘价按标的交易日对齐，仅**前向填充**、无 bfill，避免前视）的 OLS（rf=0，α×252 年化到百分点）；响应字段 **`benchmark_code`** 回显小写代码。未传时上述两指标为对**标的自身**日收益回归。若请求了基准但库中无该代码日 K，返回 **400**。  
  - 其余返回：总收益、买入持有、**超额**、最大回撤、夏普 / **Sortino**、**Calmar**、年化与波动、**多头持仓段**统计（段数、**段胜率（按段首前一日累计权益加权）**、**段均收益 %**）、翻转次数、权益曲线采样点、`note` 字段含口径说明。
- **信号快照（无费率）**：`GET /api/backtest/ma-cross/signal?code=sh.000001&fast=5&slow=20&limit=500`  
  - 与单标的共用 `start_date` / `end_date` / `limit` 取 K；返回最近一根「快慢均线均已就绪」的 `as_of_date`、`position`（`long` \| `flat`）、`close`、`ma_fast`、`ma_slow`、`bars_used` 及口径 `note`（与回测均线定义一致）。K 不足或 `fast`≥`slow` 时 **400**。
- **批量扫描**：`GET /api/backtest/ma-cross/scan?codes=sh.000001,sh.000300&fast=5&slow=20&limit=500`（**`export=csv`** 等仍用此路由）；看板 **JSON 预览 / 存档前试算** 走 **`POST /api/backtest/run`**（`strategy_id: ma_cross_scan`，`params` 与 GET 查询同义，响应 **`scan_result`**）。  
  - `codes` 支持逗号或换行分隔，默认最多 **25** 只（`max_codes` 可调至 40）；无 K 线或回测失败的行带 `error` 并沉底。  
  - **`benchmark_code`（可选）**：与单标的相同；每只标的的 β/α 均相对同一基准序列（按各标的交易日对齐）。无基准 K 时 **400**。JSON 响应含 **`benchmark_code`**（未传则为 `null`）。  
  - `sort_by`：`total_return`（默认）| `excess_return` | `sharpe` | `buy_hold` | `ann_return` | `sortino` | `calmar` | `win_rate` | `avg_holding` | `underlying_beta` | `underlying_alpha`，按对应指标降序。  
  - `max_concurrent`（默认 8，上限 20）：**MySQL** 下并行拉各标日 K 的并发；**SQLite** 下为单会话顺序拉取，避免锁竞争。  
  - `export=csv`：返回 **UTF-8 BOM** CSV；首行 `#` 注释含 `fast/slow/limit/commission_rate/slippage_rate/sort_by`、可选 `start_date` / `end_date`、可选 **`benchmark_code=`**，便于 Excel 与复现。`export=json`（默认）。  
  - CLI：`python scripts/scan_backtest.py --codes "sh.000001,sh.000300" -o scan.csv`；可选 `--sort-by excess_return`、`--max-concurrent 12`、`--start-date` / `--end-date`（YYYY-MM-DD）、**`--benchmark-code sh.000300`**。  
  - JSON 响应含 `start_date` / `end_date` 回显（与请求一致，未传则为 `null`）。
- **Vue**：**策略回测** 内「单标的（双均线或买入持有）/ 批量扫描」；**共用**可选区间日、K 根数、**基准代码（β/α）**；手续费与滑点均为「万分之」；单 / 批 **运行与存档前试算** 默认 **`POST /api/backtest/run`**（同步 **200**）；可勾选 **「异步 job」** 走 **`POST …/run`** 加 catalog 的 **`async_run_query_param`**（默认 **`async=1`**）与 **`GET`** **`async_job_status_path_template`**（默认 **`/api/backtest/jobs/{job_id}`**）轮询，结果与同步同形后再 **POST /api/backtest/runs** 存档；异步排队未开始执行前可点 **「取消排队」**（**`POST …/jobs/{job_id}/cancel`**）。勾选状态写入浏览器 **`localStorage`** 键 **`tb_backtest_mvp_async`**（值为 **`1`** 表示开启），刷新后保留。单标的 **下载 JSON**、**自选 chip**、**均线信号一行**（仍 **`GET …/ma-cross/signal`**）；批量 **下载 CSV** 仍 **`GET …/ma-cross/scan?export=csv`**、**下载 JSON** 为扫描体、**填入主要指数**、**填入自选（最多 40）**；扫描结果摘要行会显示所选基准。
- **CLI**（读当前 `.env` 数据库）：

```bash
python scripts/run_backtest.py --code sh.000001 --fast 5 --slow 20 --limit 500
python scripts/run_backtest.py --code sh.000001 -o result.json
python scripts/run_backtest.py --code sh.000001 --commission-rate 0.00015 --slippage-rate 0.00005
python scripts/run_backtest.py --code sh.600519 --benchmark-code sh.000300 -o result_vs_hs300.json
python scripts/run_backtest.py --code sh.600519 --buy-hold --limit 500 --commission-rate 0.00015 --slippage-rate 0.00005 -o bh.json
python scripts/run_backtest.py --code sh.600519 --buy-hold --start-date 2023-01-01 --end-date 2024-06-30 --limit 500 -o bh_oos.json
python scripts/run_backtest.py --code sh.000001 --fast 5 --slow 20 --start-date 2024-01-01 --end-date 2024-12-31 --limit 300 -o ma_window.json
```

**`--start-date` / `--end-date`**（可选，**`YYYY-MM-DD`**，含端点）：与 **`GET/POST` 回测** 的 **`params.start_date` / `params.end_date`** 一致，经 **`KlineRepository.get_daily`** 取 K 后再跑内核。

**`--buy-hold`**：与 **`GET /api/backtest/buy-hold`** / **`POST …/run`**（`strategy_id: buy_hold`）同一内核（`run_buy_hold_backtest`），输出 JSON 与双均线脚本同形（含 **`equity_curve`**）。

逻辑说明（双均线）：快慢线均用**收盘**计算；信号在收盘确定后，**滞后一日**乘日收益，避免当根 K 线前视偏差。年化类指标均以样本内 `n-1` 个交易日为外推基准（非自然年）。基准对齐若无法在标的样本**首日**之前或当日形成有效收盘，会报错（需加长 `limit` 或放宽日期区间）。**买入持有**口径见响应 **`note`** 与 **`docs/GENERIC_BACKTEST_DRAFT.md`**。

## 数据质量与复权口径（阶段 A）

- **口径与拉数约定**（默认不复权、增量、幂等 upsert、重试参数）：**`docs/DATA_AND_ADJUSTMENT.md`**。
- **库表自检**：`python scripts/check_daily_kline_quality.py`（默认输出 `daily_kline` + `stock_info` + **`trade_calendar` 全表行数摘要**；**`--json`** 含 **`trade_calendar`** 节；**`--strict`** 在 orphan / 空名称等告警时非零退出；**`--kline-only`** 仅日 K；**`--gap-sample N`** / **`--gap-seed-offset`** / **`--gap-top-k`** / **`--gap-exchange cn|none`** / **`--gap-calendar-grace-days`** 做「抽样标的 + 公历缺口 + 可选交易日缺口（依赖 **`trade_calendar`**）」；**`--gap-exchange`** 非 none 且 **`--gap-sample>0`** 时启用 **B+D 门控**（日历非空且覆盖足够新，失败退出码 **3**），见 **`docs/DATA_AND_ADJUSTMENT.md`**）。**`python scripts/fetch_trade_calendar.py`** 从 Baostock 灌交易日历；**`scripts/fetch_data.py --mode calendar`**（**`--calendar-start`** / **`--calendar-end`** / **`--calendar-span-days`** 等）走同一灌数逻辑；**`--mode daily`** 或 **`all`** 可加 **`--with-calendar`** 在流程末尾按「最后交易日」向前 **`--with-calendar-span-days`**（默认 450 自然日）顺带刷新 **`trade_calendar`**（仅 baostock）。**`GET /api/data/trade-calendar/status`** 查看库内日历覆盖。**`scripts/fetch_data.py`** 另支持 **`--kline-retries`** / **`--kline-retry-backoff`**（单标的日 K / 指数请求抛错时重试）。

## 测试

```bash
python -m pytest -q
python -m pytest tests/test_trend_v0_compare_helpers.py -q   # trend_v0_backtest_compare 请求体/指纹，无 DB
python -m pytest tests/test_cli_iso_date_scripts.py tests/test_export_factor_cross_section.py tests/test_factors_cross_section.py -q   # 前：cli_iso_date + 多脚本 importlib；export_factor_cross_section（批量失败 exit 1、codes-file、dry-run、legacy / auto-fallback）；compute_cross_section_row 原语
```

Windows 上若未把 `pytest` 装成全局命令，请统一用 **`python -m pytest`**（与 CI 一致）。脚本 CLI 契约（不连库、不跑 Baostock）：**`tests/test_cli_fetch.py`**（含 **`feed_dashboard.py --dry-run`** 对步骤链与 **`--skip-calendar`** 的断言）。在仓库根（已 **`pip install -r requirements.txt`** 且 **`frontend`** 已 **`npm install`**）可一次跑 **Python 全量单测 + Vue 生产构建**：**`npm run verify`**；分项：**`npm run verify:pytest`**、**`npm run verify:frontend`**（见根 **`package.json`**）。Node 版本与 CI 对齐可参考根目录 **`.nvmrc`**（**20**）。

推送 / PR 至 **`main`** 或 **`master`** 时，GitHub Actions（`.github/workflows/ci.yml`）会安装 `requirements.txt` 并执行上述命令；**Python** 版本由 **`python-version-file: .python-version`** 读取，**Node**（Playwright job）由 **`node-version-file: .nvmrc`** 读取。另有一 job 在 **`frontend/`** 构建静态站、启动 **`vite preview`**（4173）后跑 **Playwright**（`e2e/*.spec.js`，`/api` 由浏览器侧 mock，不依赖后端）。仓库 **Actions** 页可手动 **`Run workflow`**（**`workflow_dispatch`**）重跑 CI。**Dependabot**（**`.github/dependabot.yml`**）按周检查 **`requirements.txt`** 与 **`frontend/package-lock.json`** 的更新并开 PR（可在仓库 **Settings → Code security** 中确认已启用）。

**前端 E2E（本机）**：**方式 A** 可单终端不设 **`PLAYWRIGHT_BASE_URL`**（见下）；**方式 B** 常在终端一 `cd frontend && npm run e2e:preview`（4173，内含 **`npm run build`**），终端二设 **`PLAYWRIGHT_BASE_URL`** 后跑用例。若你单独用 **`vite preview`**，改界面后请先 **`npm run build`** 再重开 preview，否则 E2E 仍跑旧 **`dist/`**（方式 A 下若 **4173** 已被占用，Playwright 会**复用**已有 preview，**更**要注意 **`dist/`** 是否已重建）。`cd frontend` 后 **`npm install`**；**macOS / Linux** 或 Windows 上显式 **`PLAYWRIGHT_CHANNEL=chromium`** 时，首次需 **`npx playwright install chromium`**。**Windows**：若已 **`npx playwright install chromium`**，**`npm run test:e2e`** 默认会走**内置 Chromium**（`playwright.config.js` 探测可执行文件）；未安装时仍走本机 **Google Chrome**。然后 **`npm run test:e2e`**（或 **`npm run test:e2e:chromium`** / **`npm run test:e2e:chrome`** 固定浏览器通道）。若已手动下载 **Chrome for Testing** 的 **`chrome-win64.zip`**：先解压到任意目录，在跑 E2E 的终端里将 **`PLAYWRIGHT_EXECUTABLE_PATH`** 设为 **`chrome.exe`** 的绝对路径（**优先于** channel 与内置 Chromium；`playwright.config.js` 会打 **`[playwright] using PLAYWRIGHT_EXECUTABLE_PATH=...`**）。部分压缩包解压后为 **`…\chrome-win64\chrome-win64\chrome.exe`**（多一层同名目录）。**`preflight`**：仅当 **`PLAYWRIGHT_BASE_URL`** 非空时探测该地址并打出 **`[e2e] 1 preview OK`**；未设时跳过探测（避免先于 **webServer** 连 **4173**）。随后 **`run-pw-heartbeat.cjs`** 约每 **20s** 打 **`[e2e] heartbeat …`**。若 **多次 heartbeat 仍没有** **`[playwright] config loaded`**，说明卡在 **Playwright CLI 启动**（常见于杀软扫 `node_modules`）；可另跑 **`npm run test:e2e:diag-import`** 看仅 `import('@playwright/test')` 要多少毫秒。用例含 **`e2e/turnover-tab.spec.js`**、**`e2e/stock-list.spec.js`**、**`e2e/watchlist-panel.spec.js`**、**`e2e/backtest-panel.spec.js`**（含异步取消排队）、**`e2e/factors-preview.spec.js`**、**`e2e/paper-trading.spec.js`**、**`e2e/main-nav-smoke.spec.js`**（主导航与行情地标；其余 spec 同套 **`installApiMocks`**）。**macOS / Linux 本机**或 **CI** 默认用 Playwright **自带 Chromium**；在任意系统要用系统 Chrome 时设 **`PLAYWRIGHT_CHANNEL=chrome`**（Windows 上也会覆盖上述「有内置则优先」）。要强制内置 Chromium：**`PLAYWRIGHT_CHANNEL=chromium`**（并 **`npx playwright install chromium`**）。误设 **`CI=true`** 时，可 **`Remove-Item Env:CI -ErrorAction SilentlyContinue`**。默认 **`http://127.0.0.1:4173`**，可用 **`PLAYWRIGHT_BASE_URL`** 覆盖。**未设 `PLAYWRIGHT_BASE_URL`** 而 **`npm run test:e2e`** / **`npx playwright test`** 时，会先 **`npm run build`**（`e2e/global-setup.cjs`）再由内置 **webServer** 起 **4173**（**CI** 外 **`reuseExistingServer: true`**：本机 **4173** 已有 **`vite preview`** 时会复用，不必先停端口）。

**方式 A（单终端）**：当前 shell **未**设置 **`PLAYWRIGHT_BASE_URL`**（或为空）时，**`preflight`** 不探测端口，**`npm run test:e2e`** 由 **webServer** 起 **4173** 或（非 **CI**）复用已监听的 **4173**；图形调试用 **`npm run test:e2e:ui`**；UI + 固定通道：**`npm run test:e2e:ui:chromium`** / **`:ui:chrome`**（均可加 **`-- e2e/某.spec.js`**）。若环境里**非空** **`PLAYWRIGHT_BASE_URL`** 而对应地址未起服务，**`preflight`** 会失败：可 **`Remove-Item Env:PLAYWRIGHT_BASE_URL -ErrorAction SilentlyContinue`** 后重试，或先起 preview 再跑（方式 B）。

**方式 B（双终端，推荐日常）**：终端一 **`cd frontend && npm run e2e:preview`**（或 **`npm run e2e:preview:only`**，在 **`dist/`** 已新时省一次 **`build`**）。终端二 **`cd frontend && npm run test:e2e:connected`**（脚本已设 **`PLAYWRIGHT_BASE_URL`**；**`preflight`** 探测、不启 webServer）。子集：**`npm run test:e2e:connected -- e2e/main-nav-smoke.spec.js`**。Playwright UI：**`npm run test:e2e:ui:connected`**；UI + 固定通道：**`npm run test:e2e:ui:connected:chromium`** / **`:ui:connected:chrome`**。方式 B 无头固定通道：**`npm run test:e2e:connected:chromium`** / **`:connected:chrome`**。方式 A 固定通道子集：**`npm run test:e2e:chromium -- e2e/main-nav-smoke.spec.js`**。可选：终端二先设 **`PLAYWRIGHT_EXECUTABLE_PATH`** 指向 **Chrome for Testing** 的 **`chrome.exe`**（与 **`frontend/.env.example`** 一致）。亦可手写 **`PLAYWRIGHT_BASE_URL`** 后 **`npm run test:e2e`**。命令一览表见 **`frontend/README.md`**「E2E」。在仓库根也可 **`npm run frontend:e2e:smoke`**、**`npm run frontend:e2e:connected`**、**`npm run frontend:e2e:chromium`** 等（须已 **`cd frontend && npm install`**）；完整别名见根目录 **`package.json`**。要把 **`--list`** 等参数交给 **Playwright**，在根目录用 **`npm run …`** 时需**多一层 `--`**（外层把参数交给内层 **`npm --prefix`**），例如 **`npm run frontend:e2e:smoke -- -- --list`**；更直观可写 **`npm --prefix frontend run test:e2e:smoke -- --list`**。

**E2E 顶栏主视图**：切换「行情看板 / 股票列表 / …」请用 **`App.vue`** 的 **`data-testid="main-nav-*"`** 与 **`frontend/e2e/fixtures/mainNavTestIds.js`** 的 **`MAIN_NAV`**（`page.getByTestId(MAIN_NAV.stocks)` 等），避免 `getByRole({ name })` 与页内其它按钮子串冲突；说明见 **`frontend/README.md`**「E2E」。

`pytest.ini` 已设置 **`testpaths = tests`**，只收集 `tests/` 下用例；含 `empty_sqlite_db` fixture 下的 **K 线 / 股票仓储** SQLite 集成测（`tests/test_*_repository_sqlite.py`），以及 **`http_test_client`**（`tests/conftest.py`）上的 **`tests/test_*_api_http.py`**（股票 / K 线 / 看板 / 回测 / **`/`**、**`/health`**、**`/health/ready`**，`TestClient` + `get_session` 依赖覆盖）。  
**手工 DB 冒烟**（需已配置 `.env` 并建表）：`python scripts/smoke_raw_sql.py`、`python scripts/smoke_kline_persist.py`；**栈探测**（DB 计数含 **`trade_calendar`** 总行数及 **按 exchange 分行数** + Redis + 核心 API `TestClient`，含 **`GET /openapi.json`**、**`/api/data/trade-calendar/options`**、**`status`**、**`GET /api/strategies/catalog`**；契约阶段校验因子 **`ops[].id`** 与 **`OpName`** 一致；**overview 首条指数有 `date` 时**烟囱 **`GET /api/factors/cross-section`**（否则 **[SKIP]**）；另含回测异步 **`GET /api/backtest/jobs/{未知 job_id}` → 404**、**`POST /api/backtest/jobs/{未知 job_id}/cancel` → 404**、**`POST /api/backtest/run?async=true` + 非法 `strategy_id` → 400**）：`python scripts/verify_stack.py`（catalog 形态断言实现于该脚本、**不迁入** **`src/`**，详见脚本顶部说明）；若 DB 尚未建全表（例如缺 **`trade_calendar`**），可用 **`python scripts/verify_stack.py --skip-db`** 跳过行数统计，仍跑 Redis、API 冒烟、catalog 与上述异步检查。支持 **`DATABASE_MODE=sqlite`** 与 **`mysql`**；在全部 GET 200 后会校验 **`/api/backtest/catalog`** 的 **`engine_version`**、**`post_run_path`**、**`doc_ref`**、**`async_run_query_param`**、**`async_job_status_path_template`**、**`strategy_id`** 去重与集合（相对 **`POST /api/backtest/run`** 的 **`STRATEGY_ID_*`**）、**`strategy_version='1'`**、**`response_shape`** / **`get_equivalent_paths`** 与内核同义 GET 约定、与 **`/api/strategies/catalog`** 的 **`archive_kind`**、**`strategy_contract_version` / `backtest_run.strategy_version`**（均为 **`1`**）、**`id`↔`backtest_run.strategy_id`**、**`signal_params`** / **`backtest_archive_kinds`**（**`ma_cross`** 与 **`ma_cross_scan`** 列表与契约一致）、**`backtest_run.archive_kind`** 属于该条 **`backtest_archive_kinds`**、**`params_schema`** 对齐；**`GET /api/strategies/catalog`** 与 **`GET /api/backtest/catalog`** 各条 **`title`/`description`** 去首尾空白后须非空，回测条目的 **`get_equivalent_paths`** 每项须为以 **`/`** 开头的非空白字符串；并校验 **`/api/factors/catalog`** 的 **`preview_path` / `doc_ref`**、**`ops`** 的 **`window`/`column`** 枚举、**`series_keys`** 每项非空白及 **`OpName`**。直连 MySQL 调试见 `scripts/smoke_mysql_direct.py`（内含硬编码 URL，勿提交敏感信息）。**OpenAPI**：改路由或 Pydantic 响应模型后执行 **`python scripts/export_openapi.py`** 刷新 **`docs/openapi.json`**；**`python -m pytest tests/test_openapi_contract.py`** 会对比该文件与运行时 schema（规范化 JSON），避免契约漂移。  
测试进程会设置 `TRADING_BUDDY_SKIP_DOTENV`（见 `tests/conftest.py`），**不读取** 仓库根目录 `.env`，避免本机云库配置影响 CI/本地单测。

**契约发现（只读）**：**`GET /api/strategies/catalog`**（**`StrategyCatalogResponse`**，OpenAPI 见 **`docs/openapi.json`**）、**`GET /api/backtest/catalog`**（`POST /api/backtest/run` 已注册策略；每条含 **`archive_kind`**，与 **`GET /api/backtest/runs?kind=`** 及策略 **`backtest_run.archive_kind`** 对齐；顶层另含 **`async_run_query_param`** / **`async_job_status_path_template`** / **`async_job_persistence`**；**Redis 异步**时再含 **`async_job_queue_key`**、**`async_job_queue_depth`**（**`LLEN`**））、**`GET /api/factors/catalog`**（因子预览 **`op`** 与 `window`/`column` 约定）；**`GET /api/factors/cross-section`**（**`verify_stack`** 在 **overview** 有指数 **`date`** 时烟囱，否则跳过）；栈探测 **`scripts/verify_stack.py`** 会请求上述路径（及 **overview** 等，见脚本说明）。改 **`OpName`** 或 **`POST /run`** 注册策略后，可在仓库根执行 **`python scripts/export_all_e2e_catalogs.py`** 一次刷新 **`frontend/e2e/fixtures/factor-catalog.json`** 与 **`backtest-catalog.json`**（**`--dry-run`** 仅打印；加 **`--with-openapi`** 可顺带 **`export_openapi.py`**）；亦可分别跑 **`export_factor_catalog_fixture`** / **`export_backtest_catalog_fixture`**（见 **`docs/FACTORS.md`**、**`docs/GENERIC_BACKTEST_DRAFT.md`**）。

## License

[MIT](LICENSE)（全文见仓库根目录 **`LICENSE`**）。
