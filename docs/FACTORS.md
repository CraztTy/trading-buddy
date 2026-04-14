# 因子包（阶段 B · 最小落地）

> 对照 **`docs/ROADMAP.md`** 阶段 B「因子与特征库（先薄后厚）」：当前为 **纯 Python 原语**，与 HTTP 解耦，便于 Notebook / 脚本与后续「因子预览 API」复用。

## 模块位置

- **`src/factors/primitives.py`**：**`rolling_*`**、**`rolling_zscore`**、**`ema`**、**`macd_dif_dea_hist`**（DIF/DEA/HIST，基于同一套递归 **EMA**）、**`kdj_k_d_j`**、**`cci`**、**`williams_r`**、**`mfi`**、**`obv`**、**`true_range`**（三列浮点 **TR**，与 **`kline_true_range`** 同式）、**`dmi_adx_wilder`**（Wilder **+DI/-DI/ADX**）、**`aroon`**（**Up / Down / Osc**）、**`donchian`**（**唐奇安通道**）、**`vwap_cumulative`** / **`vwap_rolling`**（**VWAP**）、**`rsi_wilder`**、**`atr_wilder`**、**`bollinger_bands`**、`pct_change_1`、`pct_change_n`、**`roc`**、**`trix`**、**`diff_n`**（序列须 **时间升序**）。
- **`src/factors/kline_series.py`**：**`kline_float_series(klines, column)`** — 从 **`KLine`** 列表抽取 **open / high / low / close / volume / amount** 浮点列；**`kline_true_range(klines)`** — 日 K **True Range** 序列（供 **ATR**；与 **`true_range(high,low,close)`** 数值一致）。
- **`src/factors/__init__.py`**：对外导出。

## 约定

- 窗口不足处返回 **`None`**（**`ema` 除外**：非空序列每根均为浮点；**`obv`** 亦每根为浮点、无窗口概念），与 pandas 风格一致，便于对齐时间索引。
- **`rsi_wilder`**：前 ``period`` 根（索引 ``0 … period-1``）为 ``None``，首根 RSI 在索引 ``period``（至少 ``period+1`` 根 K 线）。
- **`kdj_k_d_j`**：前 ``n-1`` 根（索引 ``0 … n-2``）为 ``None``；自索引 ``n-1`` 起 ``K``/``D``/``J`` 有值（与常见软件口径一致时须核对数据源对齐）。
- **`cci`**：前 ``period-1`` 根为 ``None``；窗口内典型价无离散（``MD≈0``）时为 ``None``。
- **`williams_r`**：前 ``period-1`` 根为 ``None``；窗口内 ``HH<=LL`` 时为 ``None``。
- **`mfi`**：前 ``period`` 根（索引 ``0 … period-1``）为 ``None``；窗口内无升跌分流的 ``RMF``（正负流均为 0）时为 ``None``。
- **`roc`**：与 **`pct_change_n`** 相同索引约定；前 ``period`` 根为 ``None``；基期价为 ``0`` 时为 ``None``。
- **`trix`**：索引 ``0`` 为 ``None``（无前一平滑值）；``i>=1`` 为 ``(e3[i]/e3[i-1]-1)*100``，其中 ``e3=EMA(EMA(EMA(close,span),span),span)``；``e3[i-1]==0`` 时为 ``None``。
- **`obv`**：与 ``close`` 等长、全为浮点；**无** ``None`` 填充（首根起即有定义）。
- **`atr_wilder`**（``period>1``）：索引 ``0 … period-2`` 为 ``None``，首根 ATR 在 ``period-1``（前 ``period`` 根 TR 的简单平均）；``period==1`` 时逐根等于 TR。
- **`dmi_adx_wilder`**：``period`` 须 **≥ 2**。``+DM``/``-DM`` 与 **TR** 经与 **ATR** 相同的 Wilder 平滑后得 **+DI/-DI**（``×100/TR``，``TR<=0`` 时为 ``None``）；**DX** 由两 DI 导出；首根 **ADX** 在索引 ``2*period-2``（前 ``period`` 根 **DX** 的简单平均），其后 Wilder 递推。索引 ``0`` 的 **+DI/-DI** 为 ``None``。
- **`aroon`**：``period`` 须 **≥ 2**；前 ``period-1`` 根 **Up/Down/Osc** 均为 ``None``；窗口内最高/最低并列时取 **距当日最近** 的一根计算 **bars_since**；**Osc = Up − Down**。
- **`donchian`**：``window`` 须 **≥ 1**；上轨 = ``rolling_max(high, window)``，下轨 = ``rolling_min(low, window)``，中轨 = ``(上轨+下轨)/2``（与 **rolling_*** 相同，前 ``window-1`` 根上/中/下轨均为 ``None``）。
- **VWAP**：典型价 ``TP=(high+low+close)/3``。**累计**（``vwap_cumulative``）：自序列**首根**起 ``sum(TP×V)/sum(V)``，每根均有值（累加成交量为 0 时该根为 ``None``）。**滚动**（``vwap_rolling``）：``window≥1``，前 ``window-1`` 根为 ``None``，其后为最近 ``window`` 根上的 ``sum(TP×V)/sum(V)``；``volume`` 须 **≥ 0**。
- 涨跌幅为 **简单收益 %**，非对数收益。
- **`rolling_std`** 使用窗口内 **总体方差**（除以窗口长度，非样本 `n-1`）；与常见「样本标准差」略有差异，研究脚本若要对齐 pandas 可在外层自行 `ddof=1` 重算。
- **振幅示例**（示意，非新原语）：对对齐后的 high/low 分别做 **`rolling_max`** / **`rolling_min`** 再组合（如 ``(mx - mn) / close``）需在脚本侧对齐索引与除零。

## 测试

- **`tests/test_factors_primitives.py`**、**`tests/test_factors_kline_series.py`**

## HTTP 只读预览

- **`GET /api/factors/cross-section`**：按 **`as_of_date`**（必填）从 **`daily_kline`** 枚举当日有 K 的 **`code`**（**`max_codes`** 默认 **100**、上限 **500**，升序截断，与导出脚本 **`--max-codes`** 一致），经 **`get_daily_last_n_bars_per_code`** 拉每标的最近 **`period+1`** 根（**`period`** 默认 **20**、**1～250**，与 **`pct_change_n`** 的 **N** 一致），在进程内用 **`compute_cross_section_row`** 生成行；响应 **`ret_pct`** 对应 CSV 列 **`ret_{period}d`**（脚本侧命名）。含 **`close` / `volume` / `amount` / `turnover_rate` / `pct_change` / `meta_bars`**；**`doc_ref`** 为 **`docs/FACTORS.md`**。该日无可用标的时 **400**；批量窗口查询失败时 **503**（正文提示 **`--legacy-per-code-fetch`** 等 CLI 退路）。OpenAPI 见 **`FactorCrossSectionResponse`**；刷新 **`docs/openapi.json`** 用 **`python scripts/export_openapi.py`**。
- **Vue 与截面快捷链**：**`frontend/src/composables/crossSectionOverviewLink.js`** 请求 **`GET /api/dashboard/overview`**，取 **`indices[0].date`** 作为 **`as_of_date`**，拼 **`period=20`**、**`max_codes=100`** 的 **`/api/factors/cross-section`** 完整 URL（与主要指数卡片同一交易日）；**`RankBoard`**（行情看板侧栏底部）与 **`FactorPreviewPanel`**（因子预览页眉第二行）共用，**新标签**打开 JSON。无指数 K 时仅文案提示、无链接。
- **`GET /api/factors/catalog`**：返回当前支持的 **`op`** 列表及 **`window` / `column` / `series_keys`** 约定，与 **`OpName`** 一一对应（供 UI 下拉、外部脚本发现；不落库）；**`window`** 取值 **`required` \| `optional` \| `unused`**，**`column`** 取值 **`ohlcv` \| `ignored`**；**`series_keys`** 为字符串列表，**每项去首尾空白后须非空**（与预览 JSON 中 **`series`** 的键名一致）。响应另含 **`preview_path`**（**`/api/factors/preview`**）、**`doc_ref`**（**`docs/FACTORS.md`**）。OpenAPI 中对应 **`FactorCatalogResponse`** / **`FactorOpCatalogEntry`**（见 **`docs/openapi.json`**，**`python scripts/export_openapi.py`** 刷新）；**`tests/test_openapi_contract.py`** 与栈探测 **`scripts/verify_stack.py`** 会断言上述顶层字段、条目字段，且 **`ops[].id`** 集合与 **`OpName`** 成员完全一致。
- Vue 看板 **「因子预览」** 页签在挂载时请求 **`/api/factors/catalog`** 填充算子下拉（失败时回退内置列表并提示）；预览仍走 **`/api/factors/preview`**，按 **`trade_dates`** 与 **`series`** 绘图（与全局当前标的联动，加载成功后同步 `currentCode`）。E2E 使用 **`frontend/e2e/fixtures/factor-catalog.json`**。增删算子后请在仓库根执行 **`python scripts/export_factor_catalog_fixture.py`**（UTF-8 写入，与 **`OpName`** 同步）；**`--dry-run`** 仅打印路径与条数。若同时改了回测 **`POST /run`** 注册策略，可改用 **`python scripts/export_all_e2e_catalogs.py`** 一次写因子与回测两份 E2E 固件。勿用 PowerShell **`>`** 重定向手写导出，否则易成 UTF-16 导致 Playwright 侧 **`JSON.parse`** 失败。
- **`GET /api/factors/preview`**：从库中拉日 K（`limit` 上限，**时间升序**），对 **`column`**（`open` / `high` / `low` / `close` / `volume` / `amount`）跑 **`op`**（`rolling_*`、`ema`、`pct_change_1`、`pct_change_n`、**`roc`**、**`trix`**、`diff_n`、**`rsi`**、**`atr`**、**`adx`**、**`aroon`**、**`donchian`**、**`vwap`**、**`bollinger`**、**`macd`**、**`kdj`**、**`cci`**、**`williams_r`**、**`mfi`**、**`obv`**）。
  - **统一 JSON 形态**：**`series: Record<string, (number|null)[]>`** — 所有算子只通过命名序列返回，**各数组与 `trade_dates` 等长**。
    - **单轨**（含 **`atr`**、**`vwap`**）：**`series: { "value": [...] }`**（与 `primitives` 一致；**`vwap` 滚动**前 ``window-1`` 根为 `null`；**`vwap` 累计**无窗口不足；其余算子窗口不足规则见各条；`ema` 无 `null` 亦为标量数组）。
    - **`op=bollinger`**：**`series: { "mid", "upper", "lower" }`**；**`meta: { "bb_k": <float> }`**（与查询参数 **`bb_k`** 一致）。**`rolling_*` / `ema` / `pct_change_*` / `diff_n` / `rsi` / `atr`** 等单轨算子 **`meta` 为 `null`**（或由序列化省略）。
    - **`op=macd`**：**`series: { "dif", "dea", "hist" }`**；**`meta: { "fast", "slow", "signal" }`** 与查询 **`macd_fast` / `macd_slow` / `macd_signal`**（默认 **12 / 26 / 9**）一致。须 **`macd_fast < macd_slow`**；**不使用** **`window`**（响应里 **`window` 为 `null`**）。对 **`column`** 抽取的价格序列计算（通常 **close**）。
    - **`op=adx`**：**`series: { "plus_di", "minus_di", "adx" }`**（与 **`dmi_adx_wilder()`** 一致）；**`meta: { "period": <int> }`** 与 **`window`** 相同。须传 **`window`** 作为 **period**（须 **≥ 2**，常见 **14**）。用 **high / low / close**；**`column` 忽略**。
    - **`op=aroon`**：**`series: { "aroon_up", "aroon_down", "aroon_osc" }`**（与 **`aroon()`** 一致）；**`meta: { "period": <int> }`** 与 **`window`** 相同。须传 **`window`** 作为 **period**（须 **≥ 2**，常见 **14**）。用 **high / low**；**`column` 忽略**。
    - **`op=donchian`**：**`series: { "dc_upper", "dc_mid", "dc_lower" }`**（与 **`donchian()`** 一致）；**`meta: { "period": <int> }`** 与 **`window`** 相同（通道宽度，须 **≥ 1**，常见 **20**）。用 **high / low**；**`column` 忽略**。
    - **`op=vwap`**：**`series: { "value": [...] }`**。**不传 `window`**：**`vwap_cumulative`**，**`meta: { "mode": "cumulative" }`**，响应 **`window` 为 `null`**（日线无分时数据时，表示**自本次拉取序列首根起**的累计 VWAP）。**传 `window=N`**：**`vwap_rolling`**，**`meta: { "mode": "rolling", "period": N }`**（``N≥1``）。用 **high / low / close / volume**；**`column` 忽略**。
    - **`op=kdj`**：**`series: { "k", "d", "j" }`**；**`meta: { "n", "m1", "m2" }`** 与 **`window`**（RSV 周期 **n**，须 **≥ 2**）及 **`kdj_m1` / `kdj_m2`**（默认 **3**，约 **1～30**）一致。用日 K **high / low / close**；**`column` 忽略**（可填 `close` 占位）。响应 **`window`** 等于 **n**（非 `null`）。
    - **`op=cci`**：**`series: { "value": [...] }`**（与 **`cci()`** 一致）；**`meta` 为 `null`**。须传 **`window`** 作为 **period**（须 **≥ 2**，常见 **14 / 20**）。用 **high / low / close** 算典型价；**`column` 忽略**。
    - **`op=williams_r`**：**`series: { "value": [...] }`**（与 **`williams_r()`** 一致）；**`meta` 为 `null`**。须传 **`window`** 作为 **period**（须 **≥ 2**，常见 **14**）。用 **high / low / close**；**`column` 忽略**。
    - **`op=mfi`**：**`series: { "value": [...] }`**（与 **`mfi()`** 一致）；**`meta` 为 `null`**。须传 **`window`** 作为 **period**（须 **≥ 2**，常见 **14**）。用 **high / low / close / volume**；**`column` 忽略**。
    - **`op=roc`**：**`series: { "value": [...] }`**（与 **`roc()`** 一致，即 N 期简单收益 **%**）；**`meta` 为 `null`**。须传 **`window`** 作为 **period**（须 **≥ 1**，常见 **10 / 12**）。按 **`column`** 抽取一列浮点序列（与 **`pct_change_n`** 相同用法）。
    - **`op=trix`**：**`series: { "value": [...] }`**（与 **`trix()`** 一致）；**`meta` 为 `null`**。须传 **`window`** 作为三重 **EMA** 的 **span**（须 **≥ 1**，常见 **14**）。按 **`column`** 抽取价格序列。
    - **`op=obv`**：**`series: { "value": [...] }`**（与 **`obv(close,volume)`** 一致，全浮点、无 `null`）；**`meta` 为 `null`**。**不传** **`window`**（响应 **`window` 为 `null`**）。用 **close + volume**；**`column` 忽略**。
  - **`op=atr`**：用 **high/low/close** 计算 **True Range** 再 **`atr_wilder`**；**`column` 参数忽略**（可填 `close` 占位）；结果仍在 **`series.value`**。
  - **`op=bollinger`**：须传 **`window`**；查询 **`bb_k`**（默认 `2`，约 `0.25`～`12`）：上下轨 = 中轨 ± **`bb_k` × rolling_std**。
  - **`response_format`**：`json`（默认）；**`csv`**：**UTF-8 BOM**（`Content-Disposition: attachment`），空值为空白单元格。**单轨**表头 **`trade_date,value`**（含 **vwap**）；**`bollinger`** 表头 **`trade_date,mid,upper,lower`**；**`macd`** 表头 **`trade_date,dif,dea,hist`**；**`kdj`** 表头 **`trade_date,k,d,j`**；**`adx`** 表头 **`trade_date,plus_di,minus_di,adx`**；**`aroon`** 表头 **`trade_date,aroon_up,aroon_down,aroon_osc`**；**`donchian`** 表头 **`trade_date,dc_upper,dc_mid,dc_lower`**。
  - **`rolling_*`**（含 **`rolling_zscore`**）、**`ema`**、**`pct_change_n`**、**`roc`**、**`trix`**、**`diff_n`**、**`rsi`**、**`atr`**、**`bollinger`**、**`kdj`**、**`cci`**、**`williams_r`**、**`mfi`**、**`adx`**、**`aroon`**、**`donchian`** 必须传 **`window`**（`kdj` / **`cci`** / **`williams_r`** / **`mfi`** / **`adx`** / **`aroon`** 的 **`window`** 须 **≥ 2**；**`donchian`** 的 **`window`** 须 **≥ 1**；`atr` / `rsi` 为 Wilder **period**；`ema` / **`trix`** 为 EMA **span**；`pct_change_n` / **`roc`** / `diff_n` 为 `n` 或 ROC **period**，须 **≥ 1**）；**`pct_change_1`**、**`macd`**、**`obv`**、**`vwap`（仅累计模式）** 可不传 **`window`**（**`vwap` 滚动**须传 **`window≥1`**；累计时响应 **`window` 为 `null`**）。
  - 可选 **`start_date` / `end_date`**（ISO 日期）；无数据时 **400**。
  - 另有 **`bars`**（序列长度）、**`limit`**、**`code` / `column` / `op` / `window`** 等元字段；后续新增多序列算子时继续往 **`series`** 填键即可，避免再引入并列顶层数组。

## 截面因子数据模型（草案）

> **薄文档**：约定「某日全市场因子向量」的列名与主键，便于脚本 / Notebook 与后续批处理接口对齐；**只读 HTTP** 见上 **`GET /api/factors/cross-section`**（不落库）；专用 ORM 表或批量落盘仍属路线图。

- **持久化（阶段 B →「厚」）设计小步**：库表 vs Parquet/CSV、分阶段 **B0→A2**、**`manifest.factor_exports`** 与待决问题见 **[FACTOR_SNAPSHOT_AND_PERSISTENCE.md](FACTOR_SNAPSHOT_AND_PERSISTENCE.md)**（**实现前评审稿**，当前仓库无新表）。

- **`as_of_trade_date`**：截面所依据的**交易日**（`YYYY-MM-DD`）。使用 T 日收盘后因子还是 T+1 开盘前再算，须在 **`experiments/{id}/manifest.json`** 或流水线说明中写死，避免同一实验混用两种时点。
- **行主键**：**`(as_of_trade_date, code)`**；**`code`** 与 **`daily_kline` / 行情侧** 证券代码一致（如 **`sh.600000`**）。
- **因子列**：稳定英文蛇形名（示例占位 **`ret_20d`**、**`vol_ratio_20d`**）；值为 **`float | null`**（停牌、窗口不足等与预览 API 一致用 **`null`**）。
- **非因子辅助列**（可选）：若与因子同文件输出，建议前缀 **`meta_`**（如 **`meta_is_st`**），避免与 **`primitives`** 导出名撞车。
- **首版落地建议**：研究脚本可将截面 **CSV** 或 **Parquet** 写入 **`experiments/{experiment_id}/outputs/`**，在 **`manifest.json`** 记录文件名、列清单与 **`as_of_trade_date`**（可用 **`export_factor_cross_section.py --print-manifest-snippet`** 生成 **`factor_exports[]`** 片段）；与 **`GET /api/factors/preview`** 的单标的时间序列互补，而非替代。仓库提供 **`scripts/export_factor_cross_section.py`**（读 **`daily_kline`**，**`--output-format csv|parquet`**；列含 **`close`**、**`volume`**、**`amount`**、**`turnover_rate`**、**`pct_change`**（当日，可空）、**`ret_{N}d`**、**`meta_bars`**；**`factor_set_id`** 命名与 **`cross_section_factor_set_id()`** 一致，见 **`docs/FACTOR_SNAPSHOT_AND_PERSISTENCE.md`**）；标的枚举走 **`KlineRepository.list_codes_on_trade_date`**；各 code 最近 **N+1** 根 K 默认走 **`KlineRepository.get_daily_last_n_bars_per_code`**（**ROW_NUMBER**，**MySQL 8+** / **SQLite 3.25+**，大 **`IN`** 自动分块）；**`--legacy-per-code-fetch`** 强制逐 **`get_daily`**（**`--max-concurrent`**）；**`--auto-legacy-fallback`** 在批量窗口失败时自动切到同路径。**`--dry-run`** 仅打印条数。用法见脚本顶部 docstring。

## 后续（仍属路线图）

- 横截面因子、与 `daily_kline` 拉取层在回测/批处理中的深度衔接；上节 **「截面因子数据模型（草案）」** 为后续表结构或批处理 API 的命名锚点。
