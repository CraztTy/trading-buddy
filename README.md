# Trading Buddy - 精简版量化交易系统 V1

> A股量化交易基础设施，聚焦数据层 + 可视化，为后续策略执行打基础。当前发布线：**1.0.1**（版本见 `src/common/__init__.py` 与 `GET /health` 的 `app_version`）。

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

# 5) 灌数（推荐一键；详见 FIRST_STEPS）
python scripts/feed_dashboard.py --profile quick

# 6) 启动 API
python -m uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

# 7) 另开终端：Vue 看板
cd frontend && npm install && npm run dev
# 开发默认 http://localhost:5173 ，经 Vite 代理访问本机 API
```

接口文档：http://127.0.0.1:8000/docs  
浅探活：`GET /health`；含 DB/Redis 探测：`GET /health/ready`。

## 项目结构

```
trading-buddy/
├── docker-compose.yml    # 可选：本地 MySQL + Redis
├── requirements.txt
├── .env.example           # 环境变量模板（勿写真实密码）
├── FIRST_STEPS.md         # 上手与发布流程
├── scripts/               # init_db、拉数、feed_dashboard、verify_stack 等
├── src/
│   ├── api/               # FastAPI 入口与 routers
│   ├── data/              # 数据源、存储、模型
│   └── common/            # 配置、日志、版本号
├── frontend/              # Vue 3 看板（推荐）
├── dashboard/             # 旧版静态 HTML（可选）
└── tests/
```

## 环境变量（摘要）

根目录 `.env` 由 `src/common/config.py` 加载。与 **MySQL** 相关的常用键：

- `DATABASE_MODE`：`sqlite`（默认）或 `mysql`
- `DATABASE_HOST` / `DATABASE_PORT` / `DATABASE_USER` / `DATABASE_PASSWORD` / `DATABASE_NAME`
- 兼容别名：`DB_HOST`、`DB_PORT`、`DB_USER`、`DB_PASSWORD`、`DB_NAME`
- 云库：`DATABASE_CONNECT_TIMEOUT`、`DATABASE_SSL`

**Redis**：`REDIS_ENABLED`、`REDIS_HOST`、`REDIS_PORT`、`REDIS_PASSWORD`（可选）。

**其它**：`DATA_SOURCE`、`LOG_LEVEL`、`API_HOST`、`API_PORT`、`CORS_ORIGINS`（生产建议显式域名，逗号分隔）。

## 最小回测（双均线）

- **单标的 HTTP**：`GET /api/backtest/ma-cross?code=sh.000001&fast=5&slow=20&limit=500`  
  - `start_date`、`end_date`（可选，ISO 日期，含）：与 `limit` 一并约束取用的日 K；若二者均填且 `start_date` > `end_date` 则 400。  
  - `commission_rate`、`slippage_rate`：单边费率，在**持仓翻转日**各扣一次（与手续费同口径）；二者之和勿超过 `0.08`。  
  - 返回总收益、买入持有、**超额收益**（策略 − 买入持有）、最大回撤、夏普（252 日年化）、翻转次数、权益曲线采样点。
- **批量扫描**：`GET /api/backtest/ma-cross/scan?codes=sh.000001,sh.000300&fast=5&slow=20&limit=500`  
  - `codes` 支持逗号或换行分隔，默认最多 **25** 只（`max_codes` 可调至 40）；无 K 线或回测失败的行带 `error` 并沉底。  
  - `sort_by`：`total_return`（默认）| `excess_return` | `sharpe` | `buy_hold`，按对应指标降序。  
  - `max_concurrent`（默认 8，上限 20）：**MySQL** 下并行拉各标日 K 的并发；**SQLite** 下为单会话顺序拉取，避免锁竞争。  
  - `export=csv`：返回 **UTF-8 BOM** CSV（首行为参数注释，含 `sort_by`），便于 Excel；`export=json`（默认）。  
  - CLI：`python scripts/scan_backtest.py --codes "sh.000001,sh.000300" -o scan.csv`；可选 `--sort-by excess_return`、`--max-concurrent 12`、`--start-date` / `--end-date`（YYYY-MM-DD）。  
  - JSON 响应含 `start_date` / `end_date` 回显（与请求一致，未传则为 `null`）。
- **Vue**：**策略回测** 内「单标的 / 批量扫描」；**共用**可选区间日与 K 根数；手续费与滑点均为「万分之」；单标的 **下载 JSON**；批量 **下载 CSV / JSON**、**填入主要指数**。
- **CLI**（读当前 `.env` 数据库）：

```bash
python scripts/run_backtest.py --code sh.000001 --fast 5 --slow 20 --limit 500
python scripts/run_backtest.py --code sh.000001 -o result.json
python scripts/run_backtest.py --code sh.000001 --commission-rate 0.00015 --slippage-rate 0.00005
```

逻辑说明：快慢线均用**收盘**计算；信号在收盘确定后，**滞后一日**乘日收益，避免当根 K 线前视偏差。

## 测试

```bash
python -m pytest tests -q
```

测试进程会设置 `TRADING_BUDDY_SKIP_DOTENV`，**不读取** 仓库根目录 `.env`，避免本机云库配置影响 CI/本地单测。

## License

MIT
