# 趋势 v0 规格（束 A：可复现基线）

> 本文档落实 **[TREND_ITERATION_BACKLOG.md](TREND_ITERATION_BACKLOG.md)** 中 **A1、A2** 的默认选择，并给出 **A3（基线存档）** 的操作步骤与 **D1** 最小请求体。  
> **股票池文件**：仓库根目录 **[`config/trend_v0_pool.txt`](../config/trend_v0_pool.txt)**（可编辑；脚本 **`scripts/check_trend_v0_pool.py`** 用于快速检查池内日 K 是否存在）。  
> **脚本索引**：**[README.md](../README.md)** 中 **「个股趋势 v0 脚本」** 表；**索引与慢查询**（束 B3）：**[SLOW_QUERY_AND_INDEXES.md](SLOW_QUERY_AND_INDEXES.md)**。

---

## A1：趋势 v0 股票池（已锁定默认）

| 项 | 选择 |
|----|------|
| **主方案** | **固定代码列表**（便于复现与脚本检查） |
| **文件** | `config/trend_v0_pool.txt` |
| **备选** | 全市场子集 / 指数成分 / 自选：可在本文件「修订」中注明切换方式，列表文件仍建议保留为「当前扫描子集」 |

---

## A2：趋势 v0 规则（与 `ma_cross` / `ma_cross_scan` / `buy_hold` 对齐）

### 规则 1：双均线趋势（单标的回测）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `strategy_id` | `ma_cross` | 与 **`POST /api/backtest/run`** 一致 |
| `strategy_version` | `1` | 与 catalog 一致 |
| `code` | `sh.600519` | 默认用池内第一只，可改 |
| `fast` | `5` | 快线周期 |
| `slow` | `20` | 慢线周期 |
| `limit` | `500` | 日 K 根数上限 |
| `start_date` / `end_date` | `null` | 可选；不设则由内核与 `limit` 约束 |
| `commission_rate` | `0.00015` | 单边万分之 1.5（示例） |
| `slippage_rate` | `0.00005` | 单边万分之 0.5（示例） |
| `benchmark_code` | `null` 或 `sh.000300` | 可选；需库内有该代码日 K |

### 规则 2：双均线批量扫描（小池）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `strategy_id` | `ma_cross_scan` | |
| `codes` | 见下节「扫描用 codes 字符串」 | 逗号分隔，**长度 ≤ max_codes** |
| `fast` / `slow` / `limit` | 同规则 1 | |
| `max_codes` | `10` | 不超过池子行数时可改为与池一致 |
| `sort_by` | `total_return` | 与 GET scan 同义 |
| `max_concurrent` | `8` | MySQL 下并行拉 K |

**扫描用 `codes` 字符串**：将 `config/trend_v0_pool.txt` 中非注释行拼成一行逗号分隔（可只取前 `max_codes` 只）。

### 规则 3：买入持有（单标的回测，对照用）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `strategy_id` | `buy_hold` | 与 **`POST /api/backtest/run`** 一致 |
| `strategy_version` | `1` | 与 catalog 一致 |
| `code` | 与规则 1 同（池内第一只） | 无 `fast` / `slow` |
| `limit` / `start_date` / `end_date` / `commission_rate` / `slippage_rate` / `benchmark_code` | 同规则 1 | 窗口与费率与 MA 单标的对齐便于对照 |

---

## B1 / B2：池子数据质量检查与日常维护（前置条件）

### 池子日 K 覆盖检查（B1）

趋势 v0 要求池内每只标的都有**足够长度且足够新**的日 K，以及有效的 `change_pct`。推荐在首次拉数后和每次日常增量后执行：

```bash
# 基础检查：每只至少有 60 根日 K
python scripts/check_trend_v0_pool.py --min-bars 60

# 增强检查：同时检查 change_pct 缺失、以及最新 K 线是否超过 7 天（可能停牌/缺数据）
python scripts/check_trend_v0_pool.py \
  --min-bars 60 \
  --check-pct \
  --max-age-days 7 \
  --adjust-flag 3
```

**验收标准**：
- 池内全部通过 `min-bars` 检查
- `change_pct` 缺失比例可接受（理想为 0%，若数据源偶发缺失则记录上限）
- `max-age-days` 告警数量在可接受范围内（停牌属于正常市场行为，但需知情）

**全局质量补充**：可同时跑全表检查，关注重复键、非法 OHLC、负成交量、orphan 日 K：

```bash
python scripts/check_daily_kline_quality.py --json
# 或带交易日历缺口抽样（需已灌 trade_calendar）
python scripts/check_daily_kline_quality.py --gap-sample 50 --gap-exchange cn
```

### 交易日历与日常增量节奏（B2）

**首次建库后必须执行**（Baostock 数据源）：

```bash
python scripts/fetch_trade_calendar.py --start 2020-01-01 --end 2025-12-31
```

**日常收盘后增量（推荐）**：刷新股票列表 + 指数/个股增量补数 + 顺带刷新日历尾部：

```bash
python scripts/feed_dashboard.py --profile daily --skip-init
```

等价于 `fetch_data.py` 的 `daily` 模式：

```bash
python scripts/fetch_data.py --mode daily --with-calendar
```

**池子专属日更**（若只关注 `config/trend_v0_pool.txt` 中的标的，可减少流量）：

```bash
python scripts/fetch_data.py \
  --mode klines \
  --codes $(paste -sd',' config/trend_v0_pool.txt) \
  --incremental \
  --with-calendar
```

> 说明：Windows PowerShell 中可用 `(Get-Content config/trend_v0_pool.txt) -join ','` 拼接代码串。

---

## A3：基线存档（需本机 API + 数据库已灌日 K）

### 步骤 1：单标的同步回测

在 API 已启动（默认 `http://127.0.0.1:8000`）时执行 **PowerShell**（将 `body.json` 存为临时文件以避免转义问题）：

`body-run-single.json`：

```json
{
  "strategy_id": "ma_cross",
  "strategy_version": "1",
  "params": {
    "code": "sh.600519",
    "fast": 5,
    "slow": 20,
    "limit": 500,
    "commission_rate": 0.00015,
    "slippage_rate": 0.00005
  }
}
```

```powershell
$base = "http://127.0.0.1:8000"
$r = Invoke-RestMethod -Uri "$base/api/backtest/run" -Method POST -ContentType "application/json" -InFile "body-run-single.json"
$r | ConvertTo-Json -Depth 12 | Out-File "baseline-single-response.json" -Encoding utf8
```

### 步骤 2：写入存档 `POST /api/backtest/runs`

`body-archive-single.json`（将上一步 **`$r` 整份**作为 `response_payload`，请求体与 **`POST /run`** 相同部分写入 `request_params`）：

```json
{
  "kind": "ma_cross_single",
  "request_params": {
    "strategy_id": "ma_cross",
    "strategy_version": "1",
    "params": {
      "code": "sh.600519",
      "fast": 5,
      "slow": 20,
      "limit": 500,
      "commission_rate": 0.00015,
      "slippage_rate": 0.00005
    }
  },
  "response_payload": {}
}
```

将 **`response_payload`** 替换为 **`baseline-single-response.json` 根对象**（与 `POST /run` 返回 JSON 一致）。

```powershell
Invoke-RestMethod -Uri "$base/api/backtest/runs" -Method POST -ContentType "application/json" -InFile "body-archive-single.json"
```

记录返回的 **`id`** 作为 **单标的基线 run id**。

### 步骤 3：小批量扫描 + 存档

构造 `body-run-scan.json`（`codes` 为池子前 10 只逗号拼接示例）：

```json
{
  "strategy_id": "ma_cross_scan",
  "strategy_version": "1",
  "params": {
    "codes": "sh.600519,sh.601318,sh.600036,sz.000001,sz.300750,sh.688981,sh.601012,sz.002594,sh.600900,sz.000333",
    "fast": 5,
    "slow": 20,
    "limit": 500,
    "commission_rate": 0.00015,
    "slippage_rate": 0.00005,
    "max_codes": 10,
    "sort_by": "total_return",
    "max_concurrent": 8
  }
}
```

同步 `POST /api/backtest/run` 后，用 **`kind`: `ma_cross_scan`** 与对应 **`request_params` / `response_payload`** 再 **`POST /api/backtest/runs`**，记录 **scan 基线 run id**。

### 步骤 4（可选对照）：同标的 `buy_hold` 单回测 + 存档

与规则 1 同一 **`code`**，请求体示例 `body-run-buy-hold.json`：

```json
{
  "strategy_id": "buy_hold",
  "strategy_version": "1",
  "params": {
    "code": "sh.600519",
    "limit": 500,
    "commission_rate": 0.00015,
    "slippage_rate": 0.00005
  }
}
```

`POST /api/backtest/run` 成功后，用 **`kind`: `buy_hold_single`** 与对应 **`request_params` / `response_payload`** 再 **`POST /api/backtest/runs`**，记录 **buy_hold 基线 run id**。自动化脚本 **`scripts/trend_v0_archive_baseline.py`** 默认已包含本步；若仅需 MA 两步存档，加 **`--skip-buy-hold`**。

### A3 完成检查表（人工勾选）

| 检查项 | 记录 |
|--------|------|
| 单标的基线 **`POST /api/backtest/runs` 返回 id** | `id = 1` |
| 扫描基线 **`POST /api/backtest/runs` 返回 id** | `id = 2` |
| **`GET /api/backtest/runs?kind=ma_cross_single`** 能列出摘要 | ☑（已验证含 `id=1`） |
| **`GET /api/backtest/runs?kind=ma_cross_scan`** 能列出摘要 | ☑（已验证含 `id=2`） |
| **`buy_hold` 单标的存档 `POST /api/backtest/runs` 返回 id**（步骤 4） | （脚本输出 **`buy_hold_single_run_id`**） |
| **`GET /api/backtest/runs?kind=buy_hold_single`** 能列出摘要 | ☑ |

**说明**：上表前两行 id 为 **2026-04-13** 在已灌日 K 的 MySQL 上执行 **A3**（与上文物体一致：`sh.600519` 单标的；池内前 10 只扫描）后 **`POST /api/backtest/runs` 的响应**。若你本地库此前无存档，序号多为 **`1` / `2` / `3`**（MA 单、scan、buy_hold 各一条）；若已有历史存档，id 会顺延（例如 **`3` / `4` / `5`**）——请以你当时接口返回为准，并可在本行自行改写 id 作为团队基线。`buy_hold` 行在脚本默认三步跑通后回填 **`buy_hold_single_run_id`**。

**重新生成并回填 id**：在项目根执行 **`python scripts/trend_v0_archive_baseline.py`**（默认 **`--base-url http://127.0.0.1:8000`**，须已起 API）或 **`python scripts/trend_v0_archive_baseline.py --in-process`**（TestClient，无需 uvicorn）。可加 **`--json-out artifacts/trend_v0/a3_run_ids.json`** 落盘；将打印的 **`ma_cross_single_run_id` / `ma_cross_scan_run_id` / `buy_hold_single_run_id`** 抄回上表（后一项在默认模式下存在；**`--skip-buy-hold`** 时无 **`buy_hold_single_run_id`** 字段）。可选 **`--dry-run`**：仅打印请求体不写库。

---

## 束 B：数据门控与更新节奏

### B1：池子日 K 与全库质量

**池内条数（快速）**：

```powershell
cd <项目根>
python scripts\check_trend_v0_pool.py
python scripts\check_trend_v0_pool.py --pool config\my_pool.txt --min-bars 120
```

**全库日 K / 交易日历门控**（`scripts\check_daily_kline_quality.py`）示例：

```powershell
python scripts\check_daily_kline_quality.py --json
python scripts\check_daily_kline_quality.py --kline-only --gap-sample 20 --gap-top-k 5
```

无数据时先执行 **`python scripts\feed_dashboard.py --profile quick`**（或等价拉数），见 **[FIRST_STEPS.md](FIRST_STEPS.md)**。

### B2：交易日历与日常灌数

- 交易日历与字段说明：**[DATA_AND_ADJUSTMENT.md](DATA_AND_ADJUSTMENT.md)**  
- 从零跑通环境与灌数：**[FIRST_STEPS.md](FIRST_STEPS.md)**  
- 日更/增量拉数以团队约定为准；门禁脚本见上 **B1**。

### B3：慢查询 / 大表清单（索引与分页）

见专文 **[SLOW_QUERY_AND_INDEXES.md](SLOW_QUERY_AND_INDEXES.md)**：`daily_kline` / `stock_info` 热点、**`ix_daily_kline_trade_date_pct` / `ix_daily_kline_trade_date_amount`** 与看板排行、**`GET /api/stocks/list`** 深分页注意、**`alter_daily_kline_*`** 补索引脚本与 **`scripts/schema.sql`** 对齐说明。

---

## 束 C1：信号路径抽样（需 API 已启动）

对池内前 N 只依次请求 **`GET /api/backtest/ma-cross/signal`**，校验 HTTP 200 与响应字段（与 UI 同源接口）。

```powershell
cd <项目根>
# 先启动后端，例如 uvicorn ...
python scripts\trend_v0_signals.py
python scripts\trend_v0_signals.py --base-url http://127.0.0.1:8000 --sample 3
```

---

## 束 C2：因子预览（价量趋势，需 API）

与 **[FACTORS.md](FACTORS.md)** 中 **`GET /api/factors/preview`** 约定一致，v0 先固定 **2 个**与趋势研究常见相关的算子：

| 算子 | 参数 | 含义（见 FACTORS.md） |
|------|------|------------------------|
| **`roc`** | `column=close`，`window=12` | N 期简单收益 **%**（动量） |
| **`obv`** | `column=close`（占位），不传 `window` | 能量潮，**close + volume**，全序列有值 |

抽样脚本对池内前 N 只各请求上述 2 次，校验 HTTP 200、**`bars`** 与 **`trade_dates`** 等长、**`series`** 形状正确。

```powershell
cd <项目根>
python scripts\trend_v0_factors_preview.py
python scripts\trend_v0_factors_preview.py --sample 5 --limit 500
```

算子发现与字段约定以 **`GET /api/factors/catalog`** 为准；原语语义以 **[FACTORS.md](FACTORS.md)** 为准。

---

## 束 C3：三 catalog 契约（策略 / 回测 / 因子）

与 **`scripts/verify_stack.py`** 中 **`_verify_api_catalog_contracts()`** 一致，校验：

- **`GET /api/strategies/catalog`**：`ma_cross` / `ma_cross_scan` / `buy_hold`、`strategy_contract_version`、`backtest_run` / `archive_kind` / `backtest_archive_kinds` 等形态；
- **`GET /api/backtest/catalog`**：`engine_version`、`archive_kind` 与策略 catalog 对齐、`POST /run` 支持的 `strategy_id` 集合等；
- **`GET /api/factors/catalog`**：顶层 `preview_path` / `doc_ref`、`ops` 形态及 **OpName** 集合。

```powershell
cd <项目根>
# 进程内（无需 uvicorn，与 CI 同源）
python scripts\trend_v0_catalog_check.py
# 对已启动的 API 做 HTTP 校验（远程 persistence 与本地 .env 可不一致，脚本按响应体自洽校验）
python scripts\trend_v0_catalog_check.py --http-base-url http://127.0.0.1:8000
```

全栈探活仍用 **`python scripts\verify_stack.py`**（含 DB/Redis 与其它冒烟）。OpenAPI 契约用 **`python -m pytest tests\test_openapi_contract.py -q`**（改路由/模型后先 **`python scripts\export_openapi.py`**）。

---

## 束 D：回测与对比（工具 + 约定）

脚本：**`scripts/trend_v0_backtest_compare.py`**（HTTP 需本机或其它地址已起 API + 库内日 K；**`--in-process`** 走 TestClient，与当前仓库代码一致，无需占用 **8000**）。本地导出目录 **`artifacts/trend_v0/`**（已 **`.gitignore`**，不入库）。

### D1：单标的最小 JSON 与可复现

**`POST /api/backtest/run`** 最小体与 **A3** 中 **`body-run-single.json`** 一致（`strategy_id: ma_cross`、`strategy_version: 1`、`params` 含 `code` / `fast` / `slow` / `limit` / 费率）。**`buy_hold`** 对照体见 **A3 步骤 4** 的 **`body-run-buy-hold.json`**。

**同参重复跑**：下列命令对同一请求体连续 POST **至少 2 次**，断言 **`engine_version`** 与核心指标（`total_return_pct`、`max_drawdown_pct`、`sharpe_ratio`、`bars_used`、`signal_changes`）指纹一致（**`buy_hold`** 与 **`ma_cross`** 响应同为 `result` 单标形状，故共用指纹逻辑）：

```powershell
python scripts\trend_v0_backtest_compare.py --base-url http://127.0.0.1:8000 --mode single-repeat
python scripts\trend_v0_backtest_compare.py --mode single-repeat --code sh.600519 --repeat 3
python scripts\trend_v0_backtest_compare.py --mode buy-hold-repeat --code sh.600519 --repeat 3
python scripts\trend_v0_backtest_compare.py --in-process --mode buy-hold-repeat --code sh.600519 --repeat 3
```

### D2：小批量扫描与导出命名

固定 **`sort_by=total_return`**、**`max_codes`** 与池子前 N 只（与 **A2 规则 2** 一致），便于两次运行之间 diff。

| 产物 | 来源 | 文件名约定（`--out-dir` 下） |
|------|------|------------------------------|
| 扫描 JSON | **`POST /api/backtest/run`**（`ma_cross_scan`） | `scan_{YYYYMMDDTHHMMSS}_sort-{sort_by}_max{N}_POST.json` |
| 扫描 CSV | **`GET /api/backtest/ma-cross/scan`**，`export=csv` | 同上时间戳：`..._GET.csv` |

```powershell
python scripts\trend_v0_backtest_compare.py --mode scan-snapshot --max-codes 10 --out-dir artifacts\trend_v0
python scripts\trend_v0_backtest_compare.py --mode scan-repeat --max-codes 10
```

第二行：**同参**连续扫描 2 次，校验逐 `code` 的 `total_return_pct` 与 `sort_by` 一致（与 GET JSON 对齐逻辑在脚本内：`POST` 为 `scan_result` 包装，GET 为扁平体）。

### D3：费率敏感性（三档）

对池内默认第一只 **`commission_rate`** ∈ **`0`**、**`0.00015`**、**`0.001`**（**`slippage_rate` 固定**，与命令行 `--slippage-rate` 一致），打印 Markdown 表（`total_return_pct`、`max_drawdown_pct`、`sharpe_ratio`、`annualized_return_pct`），用于判断净利是否被费率显著吃掉。

- **`--mode fee-sweep`**：**`ma_cross`** 单标的（使用 **`--fast` / `--slow`**）。
- **`--mode fee-sweep-buy-hold`**：**`buy_hold`** 单标的（无 fast/slow，**`--limit`** 仍生效）。

```powershell
python scripts\trend_v0_backtest_compare.py --mode fee-sweep
python scripts\trend_v0_backtest_compare.py --mode fee-sweep --code sh.601318
python scripts\trend_v0_backtest_compare.py --in-process --mode fee-sweep-buy-hold --code sh.600519
```

### D4：样本外 / 固定日期窗口（与调参主窗口分离）

1. **在 `params` 中写入** **`start_date`**、**`end_date`**（ISO **`YYYY-MM-DD`**，含端点），与 **`POST /api/backtest/run`**、**`GET /api/backtest/ma-cross/scan`** 一致。**CLI**：**`trend_v0_archive_baseline.py`**、**`trend_v0_backtest_compare.py`** 在发请求前用 **`src/common/cli_iso_date`**（**`parse_cli_iso_date`**、**`check_cli_date_order`**）；**`start_date` > `end_date`** 时 **退出码 1**。  
2. **可复现检查**：对同一窗口连跑 2 次（**`--mode single-repeat`**、**`buy-hold-repeat`** 或 **`scan-repeat`**），指纹应一致；**`buy_hold`** 费率扫档用 **`--mode fee-sweep-buy-hold`**。以上均可加 **`--in-process`** 免独立 uvicorn。  
3. **存档**：该窗口跑通后，用 **`python scripts/trend_v0_archive_baseline.py --start-date … --end-date …`**（或手工 **`POST /api/backtest/runs`**）写入存档，摘要中注明「样本外 / OOS」以免与全样本基线混淆。可选：将 **`a3_oos_run_ids.json`** 与 **`request_params`** 摘要写入 **`experiments/{experiment_id}/manifest.json`**（约定见 **`experiments/README.md`**）。本地 CLI 同窗口试算：**`scripts/run_backtest.py`** 支持 **`--start-date` / `--end-date`**（与 **`params`** 同义）。

```powershell
python scripts\trend_v0_backtest_compare.py --mode single-repeat --start-date 2023-01-01 --end-date 2024-06-30
python scripts\trend_v0_backtest_compare.py --mode scan-snapshot --start-date 2023-01-01 --end-date 2024-06-30 --max-codes 10
python scripts\trend_v0_archive_baseline.py --in-process --start-date 2023-01-01 --end-date 2024-06-30 --json-out artifacts\trend_v0\a3_oos_run_ids.json
python scripts\run_backtest.py --code sh.600519 --buy-hold --start-date 2023-01-01 --end-date 2024-06-30 --limit 500 -o artifacts\trend_v0\bh_oos_cli.json
```

日期须有日 K 覆盖；若 400「无可用日 K」或窗口过短，请改区间或先 **`feed_dashboard` / `fetch_data`**。

---

## 束 E：纸交易与回测口径（工具 + 对照说明）

纸交易规则以 **[README.md](../README.md)**（行情看板一节）与 **`GET /api/paper/*`** 为准：**整手 100 股**、**卖出 T+1**（`buy_trade_date` 早于定价日 K 的交易日）、**市价撮合价 = 最近一根日 K 收盘价**；MVP **不显式扣减佣金/滑点**（与回测 `commission_rate` / `slippage_rate` 不同）。

### E1：仅池内标的 + 下单与拒单记录

脚本 **`scripts/trend_v0_paper_smoke.py`**：

- 下单前校验 **`code`** 属于 **`config/trend_v0_pool.txt`**（不在池内则 **退出码 1**、不发起 HTTP）。
- 默认：池内前 `--sample` 只各 **买** 一手 → 对第一只尝试 **卖** 一手，预期 **HTTP 400**（T+1 文案，记入终端输出）。
- **`--reset`**：调用 **`POST /api/paper/account/reset`**，仅用于开发/自测。

```powershell
python scripts\trend_v0_paper_smoke.py --base-url http://127.0.0.1:8000
python scripts\trend_v0_paper_smoke.py --reset --sample 1 --base-url http://127.0.0.1:8000
python scripts\trend_v0_paper_smoke.py --code sh.600519 --skip-sell-probe
```

### E2：回测 vs 纸交易（允许偏差一览）

| 维度 | 回测 `ma_cross`（`POST /api/backtest/run`） | 纸交易 MVP（`POST /api/paper/orders`） |
|------|---------------------------------------------|----------------------------------------|
| 定价 | 按日序列规则与信号逐 bar | 仅 **最近一根日 K 收盘价** 一次性成交 |
| 佣金 / 滑点 | `params` 内费率参与净值 | **无**单独费率字段；成交额 = 价 × 量 |
| 持仓 / 可卖 | 回测内部仓位逻辑 | **T+1** + FIFO  lot；见拒单文案 |
| 目标用途 | 历史绩效、扫描对比 | 流程演练、与看板闭环 |

同一窗口、同一标的若要数值对齐：应以回测权益曲线为准；纸交易结果解释需带 **上表偏差**。差异表模板可贴在 Issue / 团队 wiki（本规格不强制表格存档路径）。

---

## 修订

| 日期 | 说明 |
|------|------|
| 2026-04-10 | A2–A3 / C3 / D1–D4：**`buy_hold`**、**`trend_v0_*`**、**`--in-process`**、**`fee-sweep-buy-hold`**；D4 链 **`experiments/README.md`**、**`run_backtest.py --start-date/--end-date`**；**`FIRST_STEPS.md`** 无 DB 单测与实验目录指针。CI：**`tests/test_trend_v0_compare_helpers.py`**、**`tests/test_cli_iso_date_scripts.py`**。 |
| 2026-04-11 | 首版；同日增补束 B（池检 + 全库质量 + 文档链）、束 C1（`scripts/trend_v0_signals.py`）。 |
| 2026-04-11 | 束 C2：`scripts/trend_v0_factors_preview.py`（`roc` + `obv`）与上表。 |
| 2026-04-11 | 束 C3：`scripts/trend_v0_catalog_check.py` 与上表。 |
| 2026-04-13 | 束 D：`scripts/trend_v0_backtest_compare.py`、导出目录约定、D4 占位。 |
| 2026-04-13 | 束 E：`scripts/trend_v0_paper_smoke.py`、E2 偏差表。 |
| 2026-04-13 | A3 检查表填入示例 **run id**（`1` / `2`）及列表验证说明。 |
| 2026-04-13 | D4：`trend_v0_backtest_compare.py` 支持 `--start-date` / `--end-date`；新增 **`scripts/trend_v0_archive_baseline.py`**；A3 节链至存档脚本。 |
| 2026-04-13 | 束 B3：**[SLOW_QUERY_AND_INDEXES.md](SLOW_QUERY_AND_INDEXES.md)**；本页「束 B」增加 B3 链。 |
| 2026-04-13 | 文首增加 README 脚本表、**SLOW_QUERY** 链。 |
