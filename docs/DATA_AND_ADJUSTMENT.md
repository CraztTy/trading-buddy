# 数据口径与复权说明（阶段 A）

本文档对应 `docs/ROADMAP.md` 阶段 A「数据管道 + 复权与公司行为」的**当前事实、默认约定与已知局限**，便于回测与研究工作流对齐预期。

## 默认价格口径（V1 事实）

### Baostock 数据源

- 个股与指数日 K 均通过 `query_history_k_data_plus`，字段含 `open,high,low,close,volume,amount,pctChg`。
- **`adjustflag="3"`**：按 Baostock 约定为**不复权**（原始价量口径入库）。**非**前复权（`2`）或后复权（`1`）。
- 实现位置：`src/data/sources/baostock.py`（`get_daily_kline` / 指数路径复用同逻辑）。

### 其它 `DATA_SOURCE`

- 以各 `DataSource` 实现为准；更换数据源时**须在本节与 README 中写明复权与字段语义**。

### 存储与消费

- **日 K 主表**：`daily_kline`（`DailyKlineModel`），单套 OHLCV 序列，**不在库内维护多套复权档**。
- **双均线回测 / 信号 / 因子预览**：均直接读表内字段；**与「是否复权」一致取决于入库口径**（当前默认：Baostock 不复权）。
- **纸交易**：以最近可用日 K 收盘价等规则为准，见 API 与 `README.md`。

## 拉数：增量、幂等与重试

- **增量**：`scripts/fetch_data.py` 的 `--incremental` 或 `--mode daily`；按库内各 `code` 最新 `trade_date` 向前重叠 `--overlap-days` 自然日再拉，避免长假断档与尾部修正。
- **日常顺带刷交易日历**：`--mode daily` 或 `--mode all` 时加 **`--with-calendar`**（仅 **baostock** 生效）：在股票/指数/日 K 流程结束后，按 Baostock 推断的**最后交易日**为结束日，向前 **`--with-calendar-span-days`**（默认 **450** 自然日）灌 `trade_calendar`；分区键与分块同 **`--calendar-exchange`** / **`--calendar-chunk-days`**。非 baostock 时打日志跳过。
- **幂等写入**：`KlineRepository.bulk_insert` 对 `(code, trade_date)` 使用 **SQLite `ON CONFLICT DO UPDATE` / MySQL `ON DUPLICATE KEY UPDATE`**，同一区间重复拉取**覆盖**同键行，可安全重跑。
- **重试**：日 K 与指数拉取在**单次请求抛错**时按 `--kline-retries`（默认 3）与 `--kline-retry-backoff`（默认 0.5s，指数退避）重试；**数据源返回空列表**仍视为无数据（不重试），由日志与质量报告排查。

## 交易日历表 `trade_calendar`

- **初始化后**：执行 **`python scripts/init_db.py`** 建表后，**建议尽快**运行 **`fetch_trade_calendar.py`**（或 **`fetch_data.py --mode calendar`**）灌入日历；否则 **`trade_calendar` 为空**，看板状态、**`--gap-exchange`** 下的交易日缺口与 B+D 门控均无依据。
- **用途**：按自然日存储是否交易日，供质量脚本在「相邻两根日 K」之间统计**应存在的交易日个数**（与公历缺口互补）。**不替代**交易所官方公告；数据来自 Baostock `query_trade_dates`。
- **模型**：`TradingCalendarModel`（`exchange` + `calendar_date` 唯一，`is_trading_day`）。
- **默认分区键**：**`exchange='cn'`** — 与 Baostock A 股交易日查询口径一致（沪深北统一日历；若未来需分所，可增 `sh`/`sz` 等键并扩展灌数脚本）。
- **灌数**（项目根，需网络与 Baostock）：

```bash
python scripts/fetch_trade_calendar.py --start 2020-01-01 --end 2025-12-31
python scripts/fetch_trade_calendar.py --start 2024-01-01 --end 2024-06-30 --exchange cn --chunk-days 200
# 与统一拉数入口等价（须 DATA_SOURCE 或 --source 为 baostock）
python scripts/fetch_data.py --mode calendar --source baostock --calendar-start 2022-01-01 --calendar-end 2025-12-31
python scripts/fetch_data.py --mode calendar --calendar-end 2025-12-31
# 上条省略 --calendar-start 时，默认从结束日向前 --calendar-span-days（默认 730）自然日
# 定时任务「拉完行情顺带刷日历尾部」
python scripts/fetch_data.py --mode daily --with-calendar
python scripts/fetch_data.py --mode all --with-calendar --with-calendar-span-days 500
```

- **HTTP**：`GET /api/data/trade-calendar/options` 返回看板下拉的 **`exchanges`**（`value` / `label`）与 **`default_exchange`**，列表来自环境变量 **`TRADE_CALENDAR_EXCHANGE_OPTIONS`**（逗号分隔，默认 `cn`）与 **`TRADE_CALENDAR_DEFAULT_EXCHANGE`**（须为列表中一项，否则取首项）。`GET /api/data/trade-calendar/status?exchange=…` 返回 `row_count`、`date_min`、`date_max`（无数据时后两者为 `null`）。
- **幂等**：`TradeCalendarRepository.bulk_upsert_days` 对 `(exchange, calendar_date)` upsert，可重复跑同一区间。

## 已知局限（技术债）

- 未系统化落地：**分红送转、配股、拆并股** 事件表与多档复权因子；未与回测 PnL、税费、成本完全分离建模。
- 下一步（路线图）：事件表 + **复权策略枚举**（不复权 / 前复权 / 后复权）+ 回测入口参数，与多数据源对齐。

## 质量自检

运行（项目根，需可连库的 `.env`）：

```bash
python scripts/check_daily_kline_quality.py
python scripts/check_daily_kline_quality.py --json
python scripts/check_daily_kline_quality.py --gap-sample 50 --gap-seed-offset 0 --gap-top-k 15
python scripts/fetch_trade_calendar.py --start 2022-01-01 --end 2025-12-31
```

报告包含：

- **`daily_kline`**：行数、distinct 标的、全局 `trade_date` 范围、最新交易日行数、仅 1 根 K 的标的数、**重复 `(code, trade_date)` 组**、**非法 OHLC 行**、**负成交量行**、**orphan 日 K**（`code` 不在 `stock_info`）、`stock_info` 侧无 K 线的标的数等。
- **`stock_info`**（默认一并输出）：行数、**空 `name` 行**、交易中但缺 `list_date` 行数等。
- **`trade_calendar`**（**`--json`** 与文本模式均有）：全表 **`total_row_count`**、**`distinct_exchange_count`**、**`by_exchange`**（各 `exchange` 的 `row_count`，升序）；与 `calendar_gap_sample` 里按抽样 exchange 统计的口径互补。
- **`calendar_gap_sample`**（`--gap-sample N` 且 **N>0** 时）：在 `distinct code` **按 code 升序**取子序列（先 `offset`=`--gap-seed-offset` 再 `limit N`），对每只抽样标的取有序 `trade_date`。
  - **公历**：相邻 `trade_date` 的 **间隔天数减 1** → **max_interior_gap_calendar_days**（周末/长假未区分）。
  - **交易日**（`--gap-exchange cn` 默认；`none`/`off` 关闭）：若 `trade_calendar` 在对应 `exchange` 下**有数据**，则对相邻两根日 K 的开区间 `(d_prev, d_next)` 统计其中 **`is_trading_day=true`** 的条数，再在样本内取 **max_missing_trading_sessions** 及 Top 列表；**无表数据时不算交易日缺口**（可先跑 `fetch_trade_calendar.py`）。停牌、未灌 K 仍会表现为「中间缺交易日」。

退出码：

- **0**：无「硬错误」（无重复键、无非法 OHLC、无负成交量）。
- **2**：存在重复 `(code, trade_date)`、非法 OHLC 或负成交量。
- **3**：**交易日历门控（B+D）**：`--gap-sample>0` 且 **`--gap-exchange`** 非 `none`/`off` 时，`trade_calendar` 无数据，或 **`trading_calendar_date_max`** 早于 `min(日K全局 trade_date_max, 今天)` 减 **`--gap-calendar-grace-days`**（默认 7 自然日）。与 **`--gap-exchange none`** 时跳过。
- **1**：仅当传入 **`--strict`** 时，因 orphan 日 K、空名称或 `stock_info` 尚无日 K 的标的等告警而失败（优先级低于 2、3）。

仅检查日 K 表：`--kline-only`。

## 与路线图的对照

| 路线图条目 | 当前状态 |
|------------|----------|
| 关键表质量检查 | `daily_kline` / `stock_info` / `trade_calendar` 报告与脚本；`--gap-sample` / `--gap-exchange` |
| 增量 / 幂等 | `fetch_data` 增量窗口 + 仓储 upsert |
| 拉数重试 | `fetch_data` `--kline-retries` / `--kline-retry-backoff` |
| 复权多档 / 公司行为 | 未做；默认不复权见上文 |
