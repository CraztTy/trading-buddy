# Trading Buddy - 快速上手

## 环境要求

- Python 3.10+
- Docker Desktop
- 8GB+ RAM 推荐

## 第一步：启动基础设施

```bash
cd C:\Users\Administrator\Desktop\trading-buddy

# 启动 MySQL 和 Redis
docker-compose up -d
```

等待 30 秒让服务完全启动。

## 第二步：安装依赖

```bash
# 创建虚拟环境（推荐）
python -m venv venv
.\venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

## 第三步：初始化数据库

```bash
python scripts/init_db.py
```

看到 `Database initialized successfully` 即成功。

## 第四步：拉取初始数据

```bash
# 拉取股票列表
python scripts/fetch_data.py --mode stocks

# 拉取日K线数据（需要几分钟）
python scripts/fetch_data.py --mode klines --days 365
```

## 第五步：启动 API 服务

```bash
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

## 第六步：打开看板

直接在浏览器打开：
```
C:\Users\Administrator\Desktop\trading-buddy\dashboard\index.html
```

或者用 Live Server 打开。

## 验证是否正常运行

访问 API 文档：http://localhost:8000/docs

试试这些接口：
- `GET /api/dashboard/overview` - 查看指数行情
- `GET /api/klines/analysis/sh.000001` - 查看上证指数K线

## 常见问题

**Q: docker-compose 启动失败？**
```bash
# 检查 Docker 是否运行
docker ps

# 查看日志
docker-compose logs mysql
```

**Q: pip 安装依赖失败？**
```bash
# 使用国内镜像
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

**Q: baostock 数据拉取很慢？**
正常，首次需要拉取几千只股票的数据，耐心等待。

## 每日使用流程

```bash
# 每天收盘后（16:00后）运行更新
python scripts/fetch_data.py --mode klines --days 5
```

## 下一步

V1 功能已就绪：
- [x] 股票列表查询
- [x] 日K线数据
- [x] 实时行情
- [x] 简单看板

V2 规划中：
- [ ] 策略模板解析
- [ ] 信号计算引擎
- [ ] 回测模块
- [ ] 券商API对接
