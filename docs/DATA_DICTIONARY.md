# 数据字典

本文档描述 Trading Buddy 系统中的数据库表结构和核心数据字段。

## 目录

1. [用户相关表](#用户相关表)
   - [user](#user)
   - [api_key](#api_key)
   - [password_reset_token](#password_reset_token)

2. [股票基础数据](#股票基础数据)
   - [stock_info](#stock_info)
   - [stock_sector](#stock_sector)
   - [sector_info](#sector_info)

3. [行情数据](#行情数据)
   - [daily_kline](#daily_kline)
   - [minute_kline](#minute_kline)
   - [index_data](#index_data)

4. [交易相关](#交易相关)
   - [paper_account](#paper_account)
   - [paper_position](#paper_position)
   - [paper_order](#paper_order)
   - [paper_lot](#paper_lot)

5. [日历与事件](#日历与事件)
   - [trading_calendar](#trading_calendar)
   - [policy_event](#policy_event)

6. [策略与回测](#策略与回测)
   - [backtest_run](#backtest_run)

7. [风控相关](#风控相关)
   - [risk_rule](#risk_rule)
   - [risk_event](#risk_event)

8. [审计日志](#审计日志)
   - [audit_log](#audit_log)

---

## 用户相关表

### user

用户表，存储系统用户信息。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 用户唯一标识 |
| username | VARCHAR(64) | NOT NULL UNIQUE | 用户名（字母、数字、下划线） |
| email | VARCHAR(128) | NULLABLE UNIQUE | 用户邮箱 |
| password_hash | VARCHAR(255) | NOT NULL | 密码哈希（bcrypt） |
| is_active | BOOLEAN | DEFAULT TRUE | 用户是否活跃 |
| role | VARCHAR(32) | NOT NULL DEFAULT 'user' | 用户角色（user/admin） |
| last_login_at | DATETIME | NULLABLE | 最后登录时间 |
| created_at | DATETIME | DEFAULT NOW() | 创建时间 |
| updated_at | DATETIME | DEFAULT NOW() ON UPDATE NOW() | 更新时间 |

### api_key

API Key 表，供程序化调用使用。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | Key 唯一标识 |
| user_id | INTEGER | NOT NULL FOREIGN KEY | 关联用户 ID |
| key_hash | VARCHAR(255) | NOT NULL | API Key 的 SHA256 哈希 |
| label | VARCHAR(64) | NOT NULL DEFAULT 'default' | Key 的描述标签 |
| last_used_at | DATETIME | NULLABLE | 最后使用时间 |
| created_at | DATETIME | DEFAULT NOW() | 创建时间 |

### password_reset_token

密码重置令牌表。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 令牌唯一标识 |
| user_id | INTEGER | NOT NULL FOREIGN KEY | 关联用户 ID |
| token | VARCHAR(255) | NOT NULL UNIQUE | 重置令牌（URL-safe base64） |
| used | BOOLEAN | DEFAULT FALSE | 是否已使用 |
| expires_at | DATETIME | NOT NULL | 过期时间（默认 24 小时） |
| created_at | DATETIME | DEFAULT NOW() | 创建时间 |

---

## 股票基础数据

### stock_info

股票信息表，存储股票基本资料。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| code | VARCHAR(16) | PRIMARY KEY | 股票代码（如 sh.600000） |
| name | VARCHAR(64) | NOT NULL | 股票名称 |
| market | VARCHAR(16) | NOT NULL | 市场（sh/sz） |
| stock_type | VARCHAR(16) | NOT NULL | 股票类型（stock/index/fund） |
| industry | VARCHAR(64) | NULLABLE | 行业分类 |
| list_date | DATE | NULLABLE | 上市日期 |
| status | VARCHAR(16) | NOT NULL DEFAULT 'normal' | 状态（normal/suspended/delisted） |
| created_at | DATETIME | DEFAULT NOW() | 创建时间 |
| updated_at | DATETIME | DEFAULT NOW() ON UPDATE NOW() | 更新时间 |

### stock_sector

股票行业映射表。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| code | VARCHAR(16) | PRIMARY KEY | 股票代码 |
| sector_code | VARCHAR(16) | NOT NULL | 行业代码 |
| sector_name | VARCHAR(64) | NOT NULL | 行业名称 |
| weight | FLOAT | NULLABLE | 行业权重 |
| created_at | DATETIME | DEFAULT NOW() | 创建时间 |

### sector_info

行业信息表。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| sector_code | VARCHAR(16) | PRIMARY KEY | 行业代码 |
| sector_name | VARCHAR(64) | NOT NULL | 行业名称 |
| parent_code | VARCHAR(16) | NULLABLE | 父行业代码（用于层级） |
| level | INTEGER | DEFAULT 1 | 行业层级 |
| created_at | DATETIME | DEFAULT NOW() | 创建时间 |

---

## 行情数据

### daily_kline

日 K 线数据表。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| code | VARCHAR(16) | NOT NULL | 股票代码 |
| trade_date | DATE | NOT NULL | 交易日期 |
| open | FLOAT | NOT NULL | 开盘价 |
| high | FLOAT | NOT NULL | 最高价 |
| low | FLOAT | NOT NULL | 最低价 |
| close | FLOAT | NOT NULL | 收盘价 |
| volume | BIGINT | NOT NULL | 成交量（股） |
| amount | FLOAT | NOT NULL | 成交额（元） |
| pct_change | FLOAT | NULLABLE | 涨跌幅（%） |
| turnover_rate | FLOAT | NULLABLE | 换手率（%） |
| pe_ttm | FLOAT | NULLABLE | 市盈率 TTM |
| pb | FLOAT | NULLABLE | 市净率 |
| dividend_yield | FLOAT | NULLABLE | 股息率 |
| created_at | DATETIME | DEFAULT NOW() | 创建时间 |

**索引**: `(code, trade_date)` UNIQUE, `(trade_date, amount)`

### minute_kline

分钟 K 线数据表。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| code | VARCHAR(16) | NOT NULL | 股票代码 |
| datetime | DATETIME | NOT NULL | 时间戳 |
| open | FLOAT | NOT NULL | 开盘价 |
| high | FLOAT | NOT NULL | 最高价 |
| low | FLOAT | NOT NULL | 最低价 |
| close | FLOAT | NOT NULL | 收盘价 |
| volume | BIGINT | NOT NULL | 成交量（股） |
| amount | FLOAT | NOT NULL | 成交额（元） |
| created_at | DATETIME | DEFAULT NOW() | 创建时间 |

**索引**: `(code, datetime)` UNIQUE

### index_data

指数数据表。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| code | VARCHAR(16) | NOT NULL | 指数代码 |
| trade_date | DATE | NOT NULL | 交易日期 |
| open | FLOAT | NOT NULL | 开盘点数 |
| high | FLOAT | NOT NULL | 最高点数 |
| low | FLOAT | NOT NULL | 最低点数 |
| close | FLOAT | NOT NULL | 收盘点数 |
| volume | BIGINT | NOT NULL | 成交量（股） |
| amount | FLOAT | NOT NULL | 成交额（元） |
| pct_change | FLOAT | NULLABLE | 涨跌幅（%） |
| pe | FLOAT | NULLABLE | 市盈率 |
| pb | FLOAT | NULLABLE | 市净率 |
| dividend_yield | FLOAT | NULLABLE | 股息率 |
| created_at | DATETIME | DEFAULT NOW() | 创建时间 |

**索引**: `(code, trade_date)` UNIQUE

---

## 交易相关

### paper_account

纸交易资金账户表。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 账户唯一标识 |
| user_id | INTEGER | NULLABLE FOREIGN KEY | 关联用户 ID（NULL 为系统默认） |
| label | VARCHAR(32) | NOT NULL DEFAULT 'default' | 账户标签 |
| name | VARCHAR(64) | NULLABLE | 账户名称 |
| cash | FLOAT | NOT NULL DEFAULT 1000000.0 | 可用现金（元） |
| initial_cash | FLOAT | NOT NULL DEFAULT 1000000.0 | 初始资金（元） |
| created_at | DATETIME | DEFAULT NOW() | 创建时间 |

**索引**: `(user_id, label)` UNIQUE

### paper_position

纸交易持仓表。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 持仓唯一标识 |
| account_id | INTEGER | NOT NULL FOREIGN KEY | 关联账户 ID |
| code | VARCHAR(16) | NOT NULL | 股票代码 |
| quantity | INTEGER | NOT NULL | 持仓数量（股） |
| avg_cost | FLOAT | NOT NULL | 平均成本（元） |
| current_price | FLOAT | NOT NULL | 当前价格（元） |
| buy_trade_date | DATE | NOT NULL | 买入日期 |
| created_at | DATETIME | DEFAULT NOW() | 创建时间 |

**索引**: `(account_id, code)` UNIQUE

### paper_order

纸交易委托订单表。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 订单唯一标识 |
| account_id | INTEGER | NOT NULL FOREIGN KEY | 关联账户 ID |
| code | VARCHAR(16) | NOT NULL | 股票代码 |
| side | VARCHAR(16) | NOT NULL | 买卖方向（buy/sell） |
| order_type | VARCHAR(16) | NOT NULL | 订单类型（market/limit） |
| price | FLOAT | NOT NULL | 委托价格（市价单为 0） |
| quantity | INTEGER | NOT NULL | 委托数量（股） |
| filled_quantity | INTEGER | NOT NULL DEFAULT 0 | 成交数量（股） |
| status | VARCHAR(16) | NOT NULL DEFAULT 'pending' | 订单状态（pending/filled/cancelled） |
| trade_date | DATE | NOT NULL | 交易日期 |
| created_at | DATETIME | DEFAULT NOW() | 创建时间 |

**索引**: `(account_id, trade_date)`

### paper_lot

纸交易成交批次表（记录每笔成交）。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 成交批次唯一标识 |
| order_id | INTEGER | NOT NULL FOREIGN KEY | 关联订单 ID |
| code | VARCHAR(16) | NOT NULL | 股票代码 |
| side | VARCHAR(16) | NOT NULL | 买卖方向 |
| price | FLOAT | NOT NULL | 成交价格 |
| quantity | INTEGER | NOT NULL | 成交数量 |
| trade_date | DATE | NOT NULL | 成交日期 |
| created_at | DATETIME | DEFAULT NOW() | 创建时间 |

---

## 日历与事件

### trading_calendar

交易日历表。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| trade_date | DATE | PRIMARY KEY | 交易日期 |
| exchange | VARCHAR(16) | NOT NULL | 交易所（SSE/SZSE） |
| is_trading_day | BOOLEAN | NOT NULL | 是否交易日 |
| holiday_name | VARCHAR(64) | NULLABLE | 节假日名称 |
| created_at | DATETIME | DEFAULT NOW() | 创建时间 |

### policy_event

政策事件表。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 事件唯一标识 |
| event_date | DATE | NOT NULL | 事件日期 |
| title | VARCHAR(255) | NOT NULL | 事件标题 |
| content | TEXT | NULLABLE | 事件内容 |
| impact_level | VARCHAR(16) | NULLABLE | 影响级别（high/medium/low） |
| related_codes | TEXT | NULLABLE | 相关股票代码（JSON 数组） |
| created_at | DATETIME | DEFAULT NOW() | 创建时间 |

---

## 策略与回测

### backtest_run

回测结果存档表。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 回测唯一标识 |
| kind | VARCHAR(32) | NOT NULL | 回测类型（ma_cross_single/buy_hold_single/ma_cross_scan） |
| strategy_id | VARCHAR(64) | NOT NULL | 策略 ID |
| strategy_version | VARCHAR(16) | NOT NULL DEFAULT '1' | 策略版本 |
| request_params | JSON | NOT NULL | 请求参数（JSON） |
| response_payload | JSON | NOT NULL | 响应结果（JSON） |
| summary | TEXT | NULLABLE | 摘要信息 |
| created_at | DATETIME | DEFAULT NOW() | 创建时间 |

---

## 风控相关

### risk_rule

风控规则表。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 规则唯一标识 |
| name | VARCHAR(64) | NOT NULL | 规则名称 |
| rule_type | VARCHAR(32) | NOT NULL | 规则类型（max_drawdown/daily_loss/position_limit等） |
| params | JSON | NOT NULL | 规则参数（JSON） |
| enabled | BOOLEAN | DEFAULT TRUE | 是否启用 |
| severity | VARCHAR(16) | NOT NULL DEFAULT 'medium' | 严重级别（low/medium/high/critical） |
| description | TEXT | NULLABLE | 规则描述 |
| created_at | DATETIME | DEFAULT NOW() | 创建时间 |
| updated_at | DATETIME | DEFAULT NOW() ON UPDATE NOW() | 更新时间 |

### risk_event

风险事件记录表。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 事件唯一标识 |
| rule_id | INTEGER | NOT NULL FOREIGN KEY | 关联规则 ID |
| rule_name | VARCHAR(64) | NOT NULL | 规则名称 |
| severity | VARCHAR(16) | NOT NULL | 严重级别 |
| code | VARCHAR(16) | NULLABLE | 相关股票代码 |
| message | TEXT | NOT NULL | 事件消息 |
| detail | JSON | NULLABLE | 详细信息（JSON） |
| status | VARCHAR(16) | NOT NULL DEFAULT 'active' | 状态（active/resolved） |
| created_at | DATETIME | DEFAULT NOW() | 创建时间 |

---

## 审计日志

### audit_log

审计日志表，记录系统重要操作。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 日志唯一标识 |
| user_id | INTEGER | NULLABLE FOREIGN KEY | 操作用户 ID |
| username | VARCHAR(64) | NULLABLE | 操作用户名 |
| action | VARCHAR(64) | NOT NULL | 操作类型（login/logout/register等） |
| resource_type | VARCHAR(64) | NULLABLE | 资源类型（user/order/position等） |
| resource_id | VARCHAR(64) | NULLABLE | 资源 ID |
| detail | JSON | NULLABLE | 操作详情（JSON） |
| ip_address | VARCHAR(45) | NULLABLE | 客户端 IP |
| user_agent | VARCHAR(255) | NULLABLE | 客户端 User-Agent |
| success | BOOLEAN | NOT NULL DEFAULT TRUE | 是否成功 |
| error_message | TEXT | NULLABLE | 错误信息 |
| created_at | DATETIME | DEFAULT NOW() | 创建时间 |

---

## 其他表

### watchlist

自选股分组表。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 分组唯一标识 |
| user_id | INTEGER | NOT NULL FOREIGN KEY | 关联用户 ID |
| name | VARCHAR(64) | NOT NULL | 分组名称 |
| is_default | BOOLEAN | DEFAULT FALSE | 是否默认分组 |
| created_at | DATETIME | DEFAULT NOW() | 创建时间 |

### watchlist_item

自选股明细表。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 明细唯一标识 |
| watchlist_id | INTEGER | NOT NULL FOREIGN KEY | 关联分组 ID |
| code | VARCHAR(16) | NOT NULL | 股票代码 |
| added_at | DATETIME | DEFAULT NOW() | 添加时间 |

---

## 数据类型说明

| 类型 | 说明 |
|------|------|
| INTEGER | 整数 |
| BIGINT | 大整数（用于成交量等） |
| FLOAT | 浮点数（用于价格、金额等） |
| VARCHAR(N) | 可变长度字符串 |
| TEXT | 长文本 |
| DATE | 日期（YYYY-MM-DD） |
| DATETIME | 日期时间（YYYY-MM-DD HH:MM:SS） |
| BOOLEAN | 布尔值（TRUE/FALSE） |
| JSON | JSON 对象 |

---

## 索引建议

根据业务查询模式，建议创建以下索引：

| 表名 | 索引字段 | 用途 |
|------|----------|------|
| daily_kline | (code, trade_date) | 按股票和日期查询 |
| daily_kline | (trade_date, amount) | 按日期排序查成交额 |
| minute_kline | (code, datetime) | 按股票和时间查询 |
| index_data | (code, trade_date) | 按指数和日期查询 |
| paper_position | (account_id, code) | 查账户持仓 |
| paper_order | (account_id, trade_date) | 查账户订单 |
| risk_event | (created_at) | 按时间查询风险事件 |
| audit_log | (user_id, created_at) | 查用户操作日志 |
