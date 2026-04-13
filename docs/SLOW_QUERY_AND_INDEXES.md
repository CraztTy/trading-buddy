# 慢查询与大表清单（束 B3）

> 落实 **[TREND_ITERATION_BACKLOG.md](TREND_ITERATION_BACKLOG.md)** 束 **B3**：列表 / 排行 / K 线批量场景的**已知索引**、**分页策略**，以及与补索引脚本 **`scripts/alter_daily_kline_trade_date_*.sql`** 的对齐说明。  
> **ORM 定义**：**[`src/data/storage/models.py`](../src/data/storage/models.py)**；**MySQL 建表基线**：**[`scripts/schema.sql`](../scripts/schema.sql)**（新建库以二者一致为准）。

---

## 1. 大表与增长

| 表 | 体量特征 | 典型风险 |
|----|----------|----------|
| **`daily_kline`** | 按「标的数 × 交易日」增长，全市场可达亿级行 | 缺 **`trade_date`** 或 **`code`** 过滤时全表扫描；按日排序 Top N 无合适索引时 filesort |
| **`stock_info`** | 约数千～数万行 | 行业 **`LIKE 'x%'`** 前缀过滤；**`ORDER BY code`** 分页 |
| **`trade_calendar`** | 按交易所 × 自然日，行数可控 | 按 **`exchange` + `calendar_date`** 点查与区间 |
| **`index_data`** | 指数日 K，通常远小于个股日 K | 按 **code + trade_date** 查询 |

---

## 2. `daily_kline` 索引与对应查询

**模型 / 基线索引**（名称以仓库为准）：

| 索引名 | 列 | 服务场景 |
|--------|-----|----------|
| **`uq_daily_kline_code_date`**（唯一） | **`(code, trade_date)`** | 去重 upsert；**`WHERE code = ?` 且按日排序/区间`** 时可被优化器用于「先缩到单标的历史」 |
| **`ix_daily_kline_trade_date_pct`** | **`(trade_date, change_pct)`** | 指定交易日 **涨跌幅榜**：`WHERE trade_date = ? AND change_pct IS NOT NULL ORDER BY change_pct DESC/ASC LIMIT N`（**[`KlineRepository.get_top_gainers` / `get_top_losers`](../src/data/storage/repositories.py)**） |
| **`ix_daily_kline_trade_date_amount`** | **`(trade_date, amount)`** | 指定交易日 **成交额榜**：`WHERE trade_date = ? … ORDER BY amount DESC LIMIT N`（**`get_top_by_amount`**）；看板 **GET `/api/dashboard/gainers|losers|turnover`** |
| **`code` 单列 index**（ORM `index=True`） | **`code`** | **`get_daily`**：`WHERE code = ?` + 可选 `trade_date` 范围 + **`ORDER BY trade_date DESC LIMIT n`**；单标的 K 线、回测、因子预览、纸交易定价 |

**`trade_date = NULL`（全表最新日）的涨跌幅榜**：实现上用 **`trade_date = (SELECT MAX(trade_date) FROM daily_kline)`** 子查询绑定单日，仍依赖 **`ix_daily_kline_trade_date_pct`** / **`amount`** 在**该日**上的排序。

### 已有库补索引（与 ORM 对齐）

若库是在增加 **`ix_daily_kline_trade_date_amount`** 之前创建的，成交额榜可能走次优计划，可执行：

| 引擎 | 脚本 |
|------|------|
| **MySQL** | **[`scripts/alter_daily_kline_trade_date_amount_index.sql`](../scripts/alter_daily_kline_trade_date_amount_index.sql)** — `ALTER TABLE … ADD INDEX ix_daily_kline_trade_date_amount (trade_date, amount);` 执行前 **`SHOW INDEX FROM daily_kline;`** 确认是否已存在 |
| **SQLite**（本地） | **[`scripts/alter_daily_kline_trade_date_amount_index_sqlite.sql`](../scripts/alter_daily_kline_trade_date_amount_index_sqlite.sql)** — `CREATE INDEX IF NOT EXISTS …` |

新建 MySQL 库直接使用 **`scripts/schema.sql`** 即可，一般**无需**再跑上述 ALTER。

---

## 3. API 场景 → 仓储路径（便于对慢请求下钻）

| 场景 | 路由或入口 | 数据访问要点 |
|------|-------------|--------------|
| 涨跌 / 成交额榜 | **`GET /api/dashboard/gainers`** 等 | 单日 + 排序 + **`LIMIT`**（默认 ≤50） |
| 单标的日 K | **`GET /api/klines/...`**、回测 **`ma_cross`**、因子 **`preview`** | **`get_daily(code, …, limit)`**：务必带 **`code`**；**`limit`** 有上限（如 250 / 5000） |
| 批量扫描 | **`GET/POST … ma_cross_scan`** | 多 **`code`** 并行/顺序拉 **`get_daily`**；总成本 ≈ **`max_codes` × 单次 K 线成本** |
| 股票列表分页 | **`GET /api/stocks/list`** | **`stock_info`**：**`ORDER BY code` + `LIMIT` + `OFFSET`**；**`offset` 超界由服务端钳制**（见 **`stocks.py`**） |
| 纸交易成交列表 | **`GET /api/paper/orders`** | 分页 **`limit`/`offset`**；账户维度 |
| 回测存档列表 | **`GET /api/backtest/runs`** | **`ORDER BY` 最近 + 分页** |

---

## 4. 分页与「深分页」注意

- **股票列表**：**`limit` ≤ 500**，大 **`offset`** 时 MySQL 仍要对 **`code` 排序结果跳过** 多行，属正常成本；导出「全表」应沿用前端/README 约定：**分页拉取合并**，而非单次超大 **`offset`**。
- **排行榜**：始终 **`trade_date` 固定单日 + 小 `limit`**，避免「全历史排序」。

---

## 5. 自检（MySQL）

在怀疑榜单纯慢时，可对典型语句做 **`EXPLAIN ANALYZE`**（MySQL 8.0.18+）或 **`EXPLAIN`**，确认是否命中 **`ix_daily_kline_trade_date_pct`** / **`ix_daily_kline_trade_date_amount`**（**`key`** / **`rows`** 合理、`Extra` 无大范围 `Using filesort` 跨全日历史）。

示例（替换日期）：

```sql
EXPLAIN SELECT * FROM daily_kline
WHERE trade_date = '2026-04-09' AND change_pct IS NOT NULL
ORDER BY change_pct DESC LIMIT 20;
```

---

## 6. 修订

| 日期 | 说明 |
|------|------|
| 2026-04-13 | 首版：B3 清单，与 **`alter_daily_kline_*`**、**`schema.sql`**、**`KlineRepository`** 对齐。 |
