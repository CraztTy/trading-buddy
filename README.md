# Trading Buddy - 精简版量化交易系统 V1

> A股量化交易基础设施，聚焦数据层 + 可视化，为后续策略执行打基础

## 技术栈

| 层级 | 技术选型 | 说明 |
|------|----------|------|
| 语言 | Python 3.10+ | 主流、库丰富 |
| API框架 | FastAPI | 高性能、自动文档 |
| 数据库 | MySQL 8.0 | 稳定、结构化存储 |
| 缓存 | Redis | 实时行情缓存 |
| 数据源 | baostock（免费） | A股数据、无需注册 |
| 前端看板 | ECharts | 轻量、K线图支持好 |

## 架构分层

```
┌─────────────────────────────────────────────────────────────┐
│                      看板层 (Dashboard)                       │
│              ECharts K线图 / 板块行情 / 涨跌榜                 │
├─────────────────────────────────────────────────────────────┤
│                      API层 (API Service)                     │
│              FastAPI - 股票查询 / K线 / 实时行情               │
├─────────────────────────────────────────────────────────────┤
│                      缓存层 (Cache)                           │
│                    Redis - 实时数据 / 会话                     │
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

```bash
# 1. 启动基础设施
docker-compose up -d

# 2. 安装依赖
pip install -r requirements.txt

# 3. 初始化数据库
python scripts/init_db.py

# 4. 拉取初始数据
python scripts/fetch_data.py

# 5. 启动API服务
uvicorn src.api.main:app --reload

# 6. 打开看板
# 浏览器访问 http://localhost:8000
```

## 项目结构

```
trading-buddy/
├── configs/              # 配置文件
│   └── settings.py       # Pydantic Settings
├── docker-compose.yml    # 基础设施
├── requirements.txt      # Python依赖
├── scripts/              # 工具脚本
│   ├── init_db.py        # 数据库初始化
│   └── fetch_data.py     # 数据拉取
├── src/                  # 源代码
│   ├── api/              # API层
│   │   ├── main.py       # FastAPI入口
│   │   └── routers/       # 路由模块
│   ├── data/             # 数据层
│   │   ├── sources/      # 数据源适配器
│   │   ├── storage/      # 存储逻辑
│   │   └── models/       # 数据模型
│   └── common/           # 公共模块
│       ├── config.py     # 配置
│       └── logger.py     # 日志
├── dashboard/            # 前端看板
│   └── index.html        # K线看板
├── tests/                # 测试
└── README.md
```

## 环境变量

```env
# .env 文件
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=trading

REDIS_HOST=localhost
REDIS_PORT=6379

DATA_SOURCE=baostock
LOG_LEVEL=INFO
```

## License

MIT
