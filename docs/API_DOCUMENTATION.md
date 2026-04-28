# API 接口文档

本文档描述 Trading Buddy 系统的 REST API 接口。

> **注意**: 完整的交互式 API 文档可在启动服务后访问 `http://localhost:8000/docs`。

## 目录

1. [基础信息](#基础信息)
2. [认证接口](#认证接口)
3. [健康检查](#健康检查)
4. [股票数据](#股票数据)
5. [行情数据](#行情数据)
6. [看板数据](#看板数据)
7. [因子数据](#因子数据)
8. [策略与回测](#策略与回测)
9. [纸交易](#纸交易)
10. [自选股](#自选股)
11. [风控接口](#风控接口)
12. [审计日志](#审计日志)

---

## 基础信息

### 基础路径

所有 API 端点均以 `/api` 开头。

### 请求格式

- 所有请求体均为 JSON 格式
- 所有响应体均为 JSON 格式

### 认证

- 部分接口需要认证，在请求头中携带 `Authorization: Bearer <token>`
- 未认证请求会返回 401 状态码

### 响应结构

```json
{
  "items": [],
  "total": 0,
  "limit": 100,
  "offset": 0
}
```

### 错误响应

```json
{
  "detail": "错误描述"
}
```

---

## 认证接口

### 注册

**POST** `/api/auth/register`

注册新用户。

**请求体**:
```json
{
  "username": "string (3-32位，字母/数字/下划线)",
  "password": "string (至少6位)",
  "email": "string (可选，邮箱格式)"
}
```

**成功响应** (201):
```json
{
  "id": 1,
  "username": "testuser",
  "email": "test@example.com"
}
```

### 登录

**POST** `/api/auth/login`

用户登录，获取 JWT 令牌。

**请求体**:
```json
{
  "username": "string",
  "password": "string"
}
```

**成功响应** (200):
```json
{
  "access_token": "string",
  "refresh_token": "string",
  "token_type": "bearer",
  "username": "string",
  "expires_in": 86400
}
```

### 刷新令牌

**POST** `/api/auth/refresh`

使用刷新令牌获取新的访问令牌。

**请求体**:
```json
{
  "refresh_token": "string"
}
```

**成功响应** (200):
```json
{
  "access_token": "string",
  "refresh_token": "string",
  "token_type": "bearer",
  "username": "string",
  "expires_in": 86400
}
```

### 登出

**POST** `/api/auth/logout`

用户登出，将当前令牌加入黑名单。

**请求头**: `Authorization: Bearer <token>`

**成功响应** (200):
```json
{
  "message": "登出成功"
}
```

### 获取当前用户

**GET** `/api/auth/me`

获取当前登录用户信息。

**请求头**: `Authorization: Bearer <token>`

**成功响应** (200):
```json
{
  "id": 1,
  "username": "testuser",
  "email": "test@example.com",
  "is_active": true,
  "role": "user",
  "created_at": "2024-01-01T00:00:00"
}
```

### 修改密码

**POST** `/api/auth/password/change`

修改当前用户密码。

**请求头**: `Authorization: Bearer <token>`

**请求体**:
```json
{
  "old_password": "string",
  "new_password": "string (至少6位)"
}
```

**成功响应** (200):
```json
{
  "message": "密码修改成功"
}
```

### 请求密码重置

**POST** `/api/auth/password/reset-request`

请求密码重置链接。

**请求体**:
```json
{
  "email": "string"
}
```

**成功响应** (200):
```json
{
  "message": "如果该邮箱已注册，重置链接将发送到您的邮箱"
}
```

### 确认密码重置

**POST** `/api/auth/password/reset-confirm`

使用令牌重置密码。

**请求体**:
```json
{
  "token": "string",
  "new_password": "string (至少6位)"
}
```

**成功响应** (200):
```json
{
  "message": "密码重置成功"
}
```

### 列出所有用户 (Admin)

**GET** `/api/auth/users`

列出所有用户（管理员专用）。

**请求头**: `Authorization: Bearer <admin_token>`

**成功响应** (200):
```json
[
  {
    "id": 1,
    "username": "admin",
    "email": "admin@example.com",
    "is_active": true,
    "role": "admin",
    "last_login_at": "2024-01-01T00:00:00",
    "created_at": "2024-01-01T00:00:00"
  }
]
```

### 创建用户 (Admin)

**POST** `/api/auth/users`

管理员创建新用户。

**请求头**: `Authorization: Bearer <admin_token>`

**请求体**:
```json
{
  "username": "string",
  "password": "string",
  "email": "string (可选)",
  "role": "string (user/admin，默认user)",
  "is_active": true
}
```

**成功响应** (201):
```json
{
  "id": 2,
  "username": "newuser",
  "email": null,
  "is_active": true,
  "role": "user",
  "last_login_at": null,
  "created_at": "2024-01-01T00:00:00"
}
```

### 修改用户角色 (Admin)

**PUT** `/api/auth/users/{user_id}/role`

修改用户角色或状态（管理员专用）。

**请求头**: `Authorization: Bearer <admin_token>`

**请求体**:
```json
{
  "role": "string (user/admin)",
  "is_active": true (可选)
}
```

**成功响应** (200):
```json
{
  "id": 2,
  "username": "newuser",
  "email": null,
  "is_active": true,
  "role": "admin",
  "last_login_at": null,
  "created_at": "2024-01-01T00:00:00"
}
```

### 删除用户 (Admin)

**DELETE** `/api/auth/users/{user_id}`

删除用户（管理员专用）。

**请求头**: `Authorization: Bearer <admin_token>`

**成功响应** (204): 无内容

---

## 健康检查

### 基础健康检查

**GET** `/health`

基础健康检查，返回服务状态。

**成功响应** (200):
```json
{
  "status": "healthy",
  "pid": 1234,
  "uptime_sec": 3600,
  "app_version": "1.2.2"
}
```

### 就绪检查

**GET** `/health/ready`

完整就绪检查，包括数据库和 Redis 连接状态。

**成功响应** (200):
```json
{
  "status": "ready",
  "probe_ms": 15,
  "database": "connected",
  "redis": "connected"
}
```

---

## 股票数据

### 股票列表

**GET** `/api/stocks/list`

获取股票列表，支持分页和筛选。

**查询参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| market | string | 市场筛选（sh/sz） |
| industry | string | 行业筛选 |
| stock_type | string | 类型筛选（stock/index/fund） |
| limit | int | 每页数量（1-500，默认100） |
| offset | int | 偏移量（默认0） |

**成功响应** (200):
```json
{
  "items": [
    {
      "code": "sh.600000",
      "name": "浦发银行",
      "status": "normal"
    }
  ],
  "total": 1000,
  "limit": 100,
  "offset": 0
}
```

### 股票详情

**GET** `/api/stocks/{code}`

获取单个股票的详细信息。

**路径参数**: `code` - 股票代码

**成功响应** (200):
```json
{
  "code": "sh.600000",
  "name": "浦发银行",
  "market": "sh",
  "stock_type": "stock",
  "industry": "银行",
  "list_date": "1999-11-10",
  "status": "normal",
  "created_at": "2024-01-01T00:00:00"
}
```

### 按行业查询

**GET** `/api/stocks/industry/{industry}`

按行业前缀查询股票列表。

**路径参数**: `industry` - 行业名称

**成功响应** (200):
```json
[
  {
    "code": "sh.600000",
    "name": "浦发银行",
    "industry": "银行"
  }
]
```

---

## 行情数据

### 日 K 线

**GET** `/api/kline/daily/{code}`

获取股票日 K 线数据。

**路径参数**: `code` - 股票代码

**查询参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| limit | int | 返回条数（默认100） |
| start_date | string | 开始日期（YYYY-MM-DD） |
| end_date | string | 结束日期（YYYY-MM-DD） |

**成功响应** (200):
```json
[
  {
    "code": "sh.600000",
    "trade_date": "2024-01-01",
    "open": 8.5,
    "high": 8.7,
    "low": 8.3,
    "close": 8.6,
    "volume": 10000000,
    "amount": 86000000.0,
    "pct_change": 1.2
  }
]
```

### 分钟 K 线

**GET** `/api/kline/minute/{code}`

获取股票分钟 K 线数据。

**路径参数**: `code` - 股票代码

**查询参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| limit | int | 返回条数（默认100） |

**成功响应** (200):
```json
[
  {
    "code": "sh.600000",
    "datetime": "2024-01-01 09:30:00",
    "open": 8.5,
    "high": 8.6,
    "low": 8.4,
    "close": 8.55,
    "volume": 100000,
    "amount": 855000.0
  }
]
```

---

## 看板数据

### 概览数据

**GET** `/api/dashboard/overview`

获取看板概览数据（指数行情等）。

**成功响应** (200):
```json
[
  {
    "code": "sh.000001",
    "name": "上证指数",
    "close": 3000.0,
    "pct_change": 0.5,
    "date": "2024-01-01"
  }
]
```

### 成交额排行

**GET** `/api/dashboard/turnover`

获取按成交额排序的股票列表。

**查询参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| trade_date | string | 交易日期（YYYY-MM-DD，默认最新） |
| limit | int | 返回条数（默认50） |

**成功响应** (200):
```json
[
  {
    "code": "sh.600000",
    "name": "浦发银行",
    "amount": 100000000.0,
    "close": 8.6,
    "pct_change": 1.2
  }
]
```

---

## 因子数据

### 因子目录

**GET** `/api/factors/catalog`

获取可用因子列表。

**成功响应** (200):
```json
[
  {
    "id": "ma",
    "name": "移动平均线",
    "description": "简单移动平均线",
    "params": {
      "column": ["close"],
      "window": [5, 10, 20, 60]
    }
  }
]
```

### 因子预览

**GET** `/api/factors/preview`

预览因子计算结果。

**查询参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| code | string | 股票代码 |
| column | string | 计算列（open/high/low/close） |
| op | string | 算子类型（ma/ema/macd/kdj等） |
| window | int | 窗口大小 |
| response_format | string | 响应格式（json/csv，默认json） |

**成功响应** (200):
```json
{
  "series": {
    "value": [8.5, 8.6, 8.7]
  },
  "meta": {
    "code": "sh.600000",
    "op": "ma",
    "window": 5
  }
}
```

### 因子截面

**GET** `/api/factors/cross-section`

获取因子截面数据。

**查询参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| as_of_date | string | 日期（YYYY-MM-DD） |
| column | string | 计算列 |
| op | string | 算子类型 |
| window | int | 窗口大小 |
| max_codes | int | 最大股票数量（默认100） |

**成功响应** (200):
```json
{
  "as_of_date": "2024-01-01",
  "factor_name": "ma_5",
  "data": [
    {"code": "sh.600000", "value": 8.5},
    {"code": "sh.600001", "value": 9.2}
  ]
}
```

---

## 策略与回测

### 策略目录

**GET** `/api/strategies/catalog`

获取已注册策略列表。

**成功响应** (200):
```json
[
  {
    "id": "ma_cross",
    "title": "双均线策略",
    "description": "基于快慢均线交叉的策略",
    "signal_params": {...},
    "backtest_run": {...}
  }
]
```

### 回测目录

**GET** `/api/backtest/catalog`

获取回测配置目录。

**成功响应** (200):
```json
[
  {
    "strategy_id": "ma_cross",
    "strategy_version": "1",
    "title": "双均线",
    "description": "双均线交叉策略",
    "response_shape": "single",
    "get_equivalent_paths": ["/api/backtest/ma-cross"]
  }
]
```

### 双均线回测

**GET** `/api/backtest/ma-cross`

执行双均线策略回测（GET 方式，用于调试）。

**查询参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| code | string | 股票代码 |
| fast | int | 快线周期（默认5） |
| slow | int | 慢线周期（默认20） |
| limit | int | K线数量（默认500） |
| start_date | string | 开始日期（可选） |
| end_date | string | 结束日期（可选） |
| commission_rate | float | 手续费率（默认0） |
| slippage_rate | float | 滑点率（默认0） |
| benchmark_code | string | 基准代码（可选） |

**成功响应** (200):
```json
{
  "code": "sh.600000",
  "engine_version": "1",
  "assumptions": {...},
  "total_return": 0.25,
  "buy_hold_return": 0.15,
  "excess_return": 0.10,
  "max_drawdown": 0.15,
  "sharpe_ratio": 1.5,
  "sortino_ratio": 2.0,
  "calmar_ratio": 1.67,
  "equity_curve": [...],
  "note": "口径说明..."
}
```

### 买入持有回测

**GET** `/api/backtest/buy-hold`

执行买入持有回测。

**查询参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| code | string | 股票代码 |
| limit | int | K线数量（默认500） |
| start_date | string | 开始日期（可选） |
| end_date | string | 结束日期（可选） |
| commission_rate | float | 手续费率（默认0） |
| slippage_rate | float | 滑点率（默认0） |
| benchmark_code | string | 基准代码（可选） |

**成功响应** (200):
```json
{
  "code": "sh.600000",
  "engine_version": "1",
  "total_return": 0.15,
  "equity_curve": [...],
  "note": "口径说明..."
}
```

### 双均线批量扫描

**GET** `/api/backtest/ma-cross/scan`

批量执行双均线策略回测。

**查询参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| codes | string | 股票代码列表（逗号分隔） |
| fast | int | 快线周期（默认5） |
| slow | int | 慢线周期（默认20） |
| limit | int | K线数量（默认500） |
| sort_by | string | 排序字段（默认total_return） |
| max_concurrent | int | 最大并发数（默认8） |
| export | string | 导出格式（json/csv，默认json） |
| benchmark_code | string | 基准代码（可选） |

**成功响应** (200):
```json
{
  "results": [
    {"code": "sh.600000", "total_return": 0.25, "sharpe": 1.5},
    {"code": "sh.600001", "total_return": 0.18, "sharpe": 1.2}
  ],
  "benchmark_code": "sh.000300"
}
```

### 通用回测接口

**POST** `/api/backtest/run`

通用回测执行接口（同步/异步）。

**请求体**:
```json
{
  "strategy_id": "ma_cross",
  "strategy_version": "1",
  "params": {
    "code": "sh.600000",
    "fast": 5,
    "slow": 20,
    "limit": 500
  },
  "universe": "string (可选)",
  "interval": "daily",
  "start": "2024-01-01",
  "end": "2024-12-31",
  "initial_cash": 1000000.0,
  "commission": 0.00015,
  "slippage": 0.00005
}
```

**成功响应** (200 同步):
```json
{
  "result": {...}
}
```

**成功响应** (202 异步):
```json
{
  "job_id": "abc123",
  "status": "accepted",
  "status_path": "/api/backtest/jobs/abc123"
}
```

### 查询异步任务状态

**GET** `/api/backtest/jobs/{job_id}`

查询异步回测任务状态。

**路径参数**: `job_id` - 任务 ID

**成功响应** (200):
```json
{
  "job_id": "abc123",
  "status": "completed",
  "result": {...}
}
```

### 取消异步任务

**POST** `/api/backtest/jobs/{job_id}/cancel`

取消待执行的异步任务。

**路径参数**: `job_id` - 任务 ID

**成功响应** (200):
```json
{
  "job_id": "abc123",
  "status": "cancelled"
}
```

### 获取信号

**GET** `/api/backtest/ma-cross/signal`

获取最新双均线信号。

**查询参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| code | string | 股票代码 |
| fast | int | 快线周期 |
| slow | int | 慢线周期 |
| limit | int | K线数量 |

**成功响应** (200):
```json
{
  "code": "sh.600000",
  "as_of_date": "2024-01-01",
  "position": "long",
  "close": 8.6,
  "ma_fast": 8.5,
  "ma_slow": 8.3,
  "bars_used": 20,
  "note": "口径说明..."
}
```

### 回测结果存档列表

**GET** `/api/backtest/runs`

获取已存档的回测结果列表。

**查询参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| limit | int | 每页数量（1-100，默认20） |
| offset | int | 偏移量 |
| kind | string | 回测类型筛选 |
| q | string | 摘要关键字搜索 |

**成功响应** (200):
```json
{
  "items": [
    {
      "id": 1,
      "kind": "ma_cross_single",
      "strategy_id": "ma_cross",
      "summary": "sh.600000 双均线回测",
      "created_at": "2024-01-01T00:00:00"
    }
  ],
  "total": 100,
  "limit": 20,
  "offset": 0
}
```

### 获取回测详情

**GET** `/api/backtest/runs/{id}`

获取单个回测结果详情。

**路径参数**: `id` - 回测 ID

**成功响应** (200):
```json
{
  "id": 1,
  "kind": "ma_cross_single",
  "strategy_id": "ma_cross",
  "strategy_version": "1",
  "request_params": {...},
  "response_payload": {...},
  "summary": "sh.600000 双均线回测",
  "created_at": "2024-01-01T00:00:00"
}
```

### 存档回测结果

**POST** `/api/backtest/runs`

存档回测结果。

**请求体**:
```json
{
  "kind": "ma_cross_single",
  "strategy_id": "ma_cross",
  "strategy_version": "1",
  "request_params": {...},
  "response_payload": {...},
  "summary": "摘要信息"
}
```

**成功响应** (201):
```json
{
  "id": 1,
  "summary": "摘要信息"
}
```

### 删除回测结果

**DELETE** `/api/backtest/runs/{id}`

删除存档的回测结果。

**路径参数**: `id` - 回测 ID

**成功响应** (204): 无内容

---

## 纸交易

### 获取账户状态

**GET** `/api/paper/state`

获取纸交易账户状态。

**请求头**: `Authorization: Bearer <token>`（可选）

**成功响应** (200):
```json
{
  "cash": 500000.0,
  "market_value": 500000.0,
  "total_assets": 1000000.0,
  "initial_cash": 1000000.0,
  "positions": [
    {
      "code": "sh.600000",
      "name": "浦发银行",
      "quantity": 10000,
      "avg_cost": 8.5,
      "current_price": 8.6,
      "market_value": 86000.0,
      "profit": 1000.0,
      "profit_pct": 1.18
    }
  ]
}
```

### 下单

**POST** `/api/paper/orders`

提交纸交易订单。

**请求头**: `Authorization: Bearer <token>`（可选）

**请求体**:
```json
{
  "code": "sh.600000",
  "side": "buy",
  "order_type": "market",
  "quantity": 1000
}
```

**成功响应** (200):
```json
{
  "id": 1,
  "code": "sh.600000",
  "side": "buy",
  "order_type": "market",
  "price": 8.6,
  "quantity": 1000,
  "filled_quantity": 1000,
  "status": "filled",
  "trade_date": "2024-01-01"
}
```

### 获取订单列表

**GET** `/api/paper/orders`

获取订单列表。

**请求头**: `Authorization: Bearer <token>`（可选）

**查询参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| limit | int | 每页数量（默认20） |
| offset | int | 偏移量 |
| code | string | 股票代码筛选 |

**成功响应** (200):
```json
{
  "items": [
    {
      "id": 1,
      "code": "sh.600000",
      "side": "buy",
      "order_type": "market",
      "price": 8.6,
      "quantity": 1000,
      "filled_quantity": 1000,
      "status": "filled",
      "trade_date": "2024-01-01"
    }
  ],
  "total": 10,
  "limit": 20,
  "offset": 0
}
```

### 重置账户

**POST** `/api/paper/account/reset`

重置纸交易账户（恢复初始资金，清空持仓）。

**请求头**: `Authorization: Bearer <token>`（可选）

**请求体**:
```json
{
  "cash": 1000000.0 (可选，默认重置为初始资金)
}
```

**成功响应** (200):
```json
{
  "message": "账户已重置",
  "cash": 1000000.0
}
```

---

## 自选股

### 获取自选列表

**GET** `/api/watchlist/items`

获取当前用户的自选股列表。

**请求头**: `Authorization: Bearer <token>`（可选）

**成功响应** (200):
```json
[
  {
    "code": "sh.600000",
    "name": "浦发银行",
    "created_at": "2024-01-01T00:00:00"
  }
]
```

### 添加自选

**POST** `/api/watchlist/items`

添加股票到自选。

**请求头**: `Authorization: Bearer <token>`（可选）

**请求体**:
```json
{
  "code": "sh.600000"
}
```

**成功响应** (201):
```json
{
  "code": "sh.600000",
  "name": "浦发银行",
  "created_at": "2024-01-01T00:00:00"
}
```

### 删除自选

**DELETE** `/api/watchlist/items/{code}`

从自选中移除股票。

**请求头**: `Authorization: Bearer <token>`（可选）

**路径参数**: `code` - 股票代码

**成功响应** (204): 无内容

---

## 风控接口

### 获取风控规则

**GET** `/api/risk/rules`

获取风控规则列表。

**请求头**: `Authorization: Bearer <token>`

**成功响应** (200):
```json
[
  {
    "id": 1,
    "name": "最大回撤限制",
    "rule_type": "max_drawdown",
    "params": {"max_drawdown": 0.2},
    "enabled": true,
    "severity": "high",
    "description": "限制账户最大回撤不超过20%"
  }
]
```

### 创建风控规则

**POST** `/api/risk/rules`

创建新的风控规则。

**请求头**: `Authorization: Bearer <token>`（需 admin）

**请求体**:
```json
{
  "name": "最大回撤限制",
  "rule_type": "max_drawdown",
  "params": {"max_drawdown": 0.2},
  "enabled": true,
  "severity": "high",
  "description": "限制账户最大回撤不超过20%"
}
```

**成功响应** (201):
```json
{
  "id": 1,
  "name": "最大回撤限制",
  "rule_type": "max_drawdown",
  "params": {"max_drawdown": 0.2},
  "enabled": true,
  "severity": "high",
  "description": "限制账户最大回撤不超过20%"
}
```

### 获取风险事件

**GET** `/api/risk/events`

获取风险事件列表。

**请求头**: `Authorization: Bearer <token>`

**查询参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| limit | int | 每页数量（默认20） |
| offset | int | 偏移量 |
| severity | string | 严重级别筛选 |

**成功响应** (200):
```json
{
  "items": [
    {
      "id": 1,
      "rule_id": 1,
      "rule_name": "最大回撤限制",
      "severity": "high",
      "code": "sh.600000",
      "message": "账户回撤超过20%",
      "detail": {...},
      "status": "active",
      "created_at": "2024-01-01T00:00:00"
    }
  ],
  "total": 10,
  "limit": 20,
  "offset": 0
}
```

### 处理风险事件

**POST** `/api/risk/events/{event_id}/resolve`

标记风险事件已处理。

**请求头**: `Authorization: Bearer <token>`（需 admin）

**路径参数**: `event_id` - 事件 ID

**成功响应** (200):
```json
{
  "id": 1,
  "status": "resolved"
}
```

---

## 审计日志

### 获取审计日志

**GET** `/api/audit/logs`

获取审计日志（管理员专用）。

**请求头**: `Authorization: Bearer <admin_token>`

**查询参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| limit | int | 每页数量（默认20） |
| offset | int | 偏移量 |
| user_id | int | 用户 ID 筛选 |
| action | string | 操作类型筛选 |
| start_time | string | 开始时间 |
| end_time | string | 结束时间 |

**成功响应** (200):
```json
{
  "items": [
    {
      "id": 1,
      "user_id": 1,
      "username": "admin",
      "action": "login",
      "resource_type": "user",
      "resource_id": "1",
      "detail": {...},
      "ip_address": "127.0.0.1",
      "success": true,
      "created_at": "2024-01-01T00:00:00"
    }
  ],
  "total": 100,
  "limit": 20,
  "offset": 0
}
```
