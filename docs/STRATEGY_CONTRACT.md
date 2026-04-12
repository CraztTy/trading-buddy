# 策略契约与开发者示例（Backlog #3）

> 与 **`GET /api/strategies/catalog`**、**`POST /api/strategies/signal`** 及回测结果存档字段 **`kind`**（`ma_cross_single` / `ma_cross_scan`）对齐说明。  
> 对照：`docs/ROADMAP.md` 近 90 天 backlog 第 3 条。

**看板入口**：Vue **策略回测** 页顶、单标的/批量切换栏下方有一行 **「策略目录 / 试算信号」**（按钮 **策略目录**、**试算信号**）；试算使用当前行情标的与下方快线/慢线/K 根数及可选日期区间，结果以 JSON 展示。

## Catalog

```http
GET /api/strategies/catalog
```

响应外壳为 **`StrategyCatalogResponse`**（仅键 **`strategies`**）；OpenAPI 见 **`docs/openapi.json`**。**`scripts/verify_stack.py`** 会断言每条含 **`strategy_contract_version`**（当前须为 **`1`**）、**`backtest_run.strategy_version`**（**`1`**）、**`id`** 与 **`backtest_run.strategy_id`** 一致、**`signal_params`**（对象）、**`backtest_archive_kinds`**（**`ma_cross`** 须按序为 **`['ma_cross_single','ma_cross_scan']`**；**`ma_cross_scan`** 须为 **`['ma_cross_scan']`**）、**`backtest_run.archive_kind`** 须为该条 **`backtest_archive_kinds`** 之一，及 **`backtest_run.params_schema`**（对象）；另含 **`title`** / **`description`**（人类可读；去首尾空白后须非空字符串）。每条策略含：

| 字段 | 含义 |
|------|------|
| **`id`** | 策略标识；与 **`POST /api/strategies/signal`** 的 `kind`（当前仅 `ma_cross`）、以及 **`POST /api/backtest/run`** 的 `strategy_id`（`ma_cross` / `ma_cross_scan`）对应关系见下表。 |
| **`title`** / **`description`** | 看板与栈探测用短文案；须为字符串且 **`.strip()` 后非空**（与 **`verify_stack`** / **`tests/test_openapi_contract.py`** 一致）。 |
| **`backtest_archive_kinds`** | 与该策略族相关的 **`POST /api/backtest/runs`** 的 **`kind`** 枚举子集，供列表筛选与工具映射。 |
| **`strategy_contract_version`** | 契约文档与 catalog 字段的滚动版本（整数串）。 |
| **`signal_params`** | **`POST /api/strategies/signal`** 中 `params` 的 JSON Schema 风格描述；**`ma_cross`** 含可调字段；**`ma_cross_scan`** 显式 **`maxProperties: 0`**（不提供试算 signal，见下文）。 |
| **`backtest_run`** | **`POST /api/backtest/run`** 信封：`strategy_id` / `strategy_version`、建议存档 **`archive_kind`**、以及内层 **`params`** 的 **`params_schema`**（与 `MaCrossRunParamsBody` / `MaCrossScanRunParamsBody` 校验一致）。 |

**`id` 与 HTTP 的对应**

| catalog `id` | `POST …/strategies/signal` 的 `kind` | `POST …/backtest/run` 的 `strategy_id` |
|--------------|--------------------------------------|----------------------------------------|
| `ma_cross` | `ma_cross` | `ma_cross` |
| `ma_cross_scan` | —（无批量 signal） | `ma_cross_scan` |

## 统一信号（JSON 模板）

与 **`GET /api/backtest/ma-cross/signal`** 语义一致，便于脚本与 CI 调用。

```http
POST /api/strategies/signal
Content-Type: application/json

{
  "code": "sh.000001",
  "kind": "ma_cross",
  "params": {
    "fast": 5,
    "slow": 20,
    "limit": 500
  }
}
```

**curl 示例**（API 默认 `http://127.0.0.1:8000`，按本机修改）：

```bash
curl -sS "http://127.0.0.1:8000/api/strategies/catalog" | head -c 2000

curl -sS -X POST "http://127.0.0.1:8000/api/strategies/signal" \
  -H "Content-Type: application/json" \
  -d "{\"code\":\"sh.000001\",\"kind\":\"ma_cross\",\"params\":{\"fast\":5,\"slow\":20,\"limit\":500}}"
```

成功时响应形如：`{"kind":"ma_cross","signal":{...}}`，其中 **`signal`** 与 GET `ma-cross/signal` 的 JSON 字段一致。

### 为何不能用 `kind=ma_cross_scan` 调 signal？

批量扫描是**多标的截面**，没有与单票 **`ma-cross/signal`** 同构的「当前一根 K 上的 long/flat」输出。若误传 **`kind=ma_cross_scan`**，**`POST /api/strategies/signal`** 返回 **400**，正文中说明应改用 **`kind=ma_cross`** 或 **GET** signal。Catalog 中 **`ma_cross_scan.signal_params`** 使用 **`maxProperties: 0`** 与 **`additionalProperties: false`**，供静态检查与文档生成器识别「无 params 形状」。

## 与存档的关系

- 单标的回测成功后存档 **`kind=ma_cross_single`**；批量扫描 **`kind=ma_cross_scan`**。  
- Catalog 中 **`ma_cross`** 的 **`backtest_archive_kinds`** 列出上述两种，便于工具链把「策略 id」映射到历史存档筛选。

### `GET /api/backtest/catalog` 与 **`archive_kind`**

**`GET /api/backtest/catalog`** 中每条已注册 **`POST /api/backtest/run`** 策略的 **`archive_kind`** 与本节存档 **`kind`** 一致（例如 **`ma_cross`** → **`ma_cross_single`**，**`ma_cross_scan`** → **`ma_cross_scan`**），并与 **`GET /api/strategies/catalog`** 各条 **`backtest_run.archive_kind`** 对齐。看板 **策略回测** 页用该字段生成「存档类型」筛选选项与 **`GET /api/backtest/runs?kind=`** 的映射说明；新增 **`POST /run`** 策略时须在 **`_backtest_engine_catalog_payload`**（及策略 catalog）中同步 **`archive_kind`**，并刷新 E2E 固件（见 **`docs/GENERIC_BACKTEST_DRAFT.md`**）。

## 通用回测 MVP（与 GET ma-cross 同核）

```http
POST /api/backtest/run
Content-Type: application/json

{
  "strategy_id": "ma_cross",
  "strategy_version": "1",
  "params": {
    "code": "sh.000001",
    "fast": 5,
    "slow": 20,
    "limit": 500
  }
}
```

响应含 **`engine_version`**、**`assumptions`**、**`result`**（与 `GET /api/backtest/ma-cross` 相同字段）、**`scan_result`**（单标的时为 `null`）。详见 **`docs/GENERIC_BACKTEST_DRAFT.md`**。内层 **`params`** 的形状以 catalog 同条目的 **`backtest_run.params_schema`** 为准。

### 批量扫描（与 GET ma-cross/scan 同核）

```http
POST /api/backtest/run
Content-Type: application/json

{
  "strategy_id": "ma_cross_scan",
  "strategy_version": "1",
  "params": {
    "codes": "sh.600519,sz.000001",
    "fast": 5,
    "slow": 20,
    "limit": 500,
    "max_codes": 25,
    "sort_by": "total_return",
    "max_concurrent": 8
  }
}
```

成功时 **`scan_result`** 与 GET **`/api/backtest/ma-cross/scan`** 的 JSON 体一致；**`result`** 为 `null`。**`params`** 以 catalog **`ma_cross_scan`** 的 **`backtest_run.params_schema`** 为准。

## 存档 `request_params` 约定（看板与脚本）

- **推荐**：`request_params` 存 **`POST /api/backtest/run` 完整 JSON**（含 `strategy_id`、`strategy_version`、`params`），便于复现与审计；**`response_payload`** 仍为单次 API 结果体（单标的：`MaCrossBacktestResponse`；批量：`MaCrossScanResponse` 与 `scan_result` 一致）。  
- **历史数据**：可能为扁平 GET 查询参数；解析时应兼容两种形状。

## 契约版本与变更日志

策略条目上的 **`strategy_contract_version`** 为**字符串**，与本文档本节对齐；破坏性变更时递增并在此记录摘要。

### `strategy_contract_version` = `1`

| 日期（约） | 说明 |
|------------|------|
| 2026-04 | 初版：`signal_params`（`ma_cross`）、**`backtest_run`**（`params_schema` + **`archive_kind`**）、**`backtest_archive_kinds`**；**`POST /api/backtest/run`** 与 catalog 对齐。 |
| 2026-04 | **`ma_cross_scan.signal_params`** 明确 **`maxProperties: 0`**；**`POST /api/strategies/signal`** 对 **`kind=ma_cross_scan`** 返回专用 **400** 说明。 |

## 修订

新增策略 `id` 时：更新 `src/strategies/catalog.py`、补充本文件示例，并增加 `tests/test_strategies_api_http.py` 与 `tests/test_backtest_api_http.py`（`/run`）断言；有行为变更时更新上表与本节 **`strategy_contract_version`**（若递增则在 catalog 中同步改字符串）。
