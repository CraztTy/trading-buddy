# Xtquant (QMT / 迅投) 实盘接入指南

Trading Buddy 支持通过 **xtquant** SDK 接入 **QMT / miniQMT**（迅投量化交易平台）执行 A 股实盘交易。

---

## 前置条件

| 项目 | 要求 |
|------|------|
| **操作系统** | Windows 10/11 64位（QMT 仅支持 Windows） |
| **QMT 客户端** | 已安装 miniQMT 或 QMT 交易端（通过券商申请） |
| **资金门槛** | 通常需要 10 万+ 资产（具体咨询券商） |
| **Python** | 3.8 - 3.11（xtquant 兼容性最佳） |
| **xtquant 包** | 已安装：`pip install xtquant` |

---

## 安装 xtquant

### 方式一：pip 安装（推荐）

```bash
pip install xtquant
```

### 方式二：从 QMT 目录复制

如果 pip 安装失败，从 QMT 安装目录复制：

```bash
# 找到 QMT 安装目录下的 xtquant 包
# 例如: C:\\国金QMT交易端\\bin.x64\\Lib\\site-packages\\xtquant
# 复制到当前 Python 环境的 site-packages 目录
xcopy "C:\\国金QMT交易端\\bin.x64\\Lib\\site-packages\\xtquant" "%PYTHONPATH%\\Lib\\site-packages\\xtquant" /E /I
```

---

## 配置环境变量

在项目根目录的 `.env` 文件中添加：

```env
# Broker 适配器配置
BROKER_ADAPTER=xtquant

# QMT / miniQMT 路径（必须是 miniQMT 的 userdata_mini 目录）
XTQUANT_QMT_PATH=C:\\国金QMT交易端\\userdata_mini

# 资金账号（QMT 登录的账号）
XTQUANT_ACCOUNT_ID=12345678

# 会话 ID（每个策略实例须唯一，范围 100000-999999）
XTQUANT_SESSION_ID=123456
```

---

## QMT 客户端准备

### 1. 启动 miniQMT

1. 打开 QMT 交易端
2. 切换到 **极简模式** 或 **独立交易**
3. 使用资金账号登录
4. 保持客户端运行（不要关闭）

### 2. 确认 miniQMT 路径

miniQMT 的 userdata 路径通常在：

```
C:\\Users\\<用户名>\\.xd_quant\\userdata_mini
# 或
C:\\国金QMT交易端\\userdata_mini
```

确认目录下有 `strategy` 和 `datadir` 子目录。

---

## 验证连接

### 通过 API 健康检查

```bash
# 启动 Trading Buddy API
cd trading-buddy
python scripts/run_api.py

# 另开终端测试健康检查
curl "http://localhost:8000/api/broker/health?adapter_type=xtquant"
```

期望返回：

```json
{
  "adapter": "xtquant",
  "status": "ok",
  "account_id": "12345678",
  "qmt_path": "C:\\国金QMT交易端\\userdata_mini",
  "session_id": 123456,
  "balance": {
    "cash": 100000.0,
    "total_equity": 150000.0
  }
}
```

### 查询资金和持仓

```bash
# 查询资金
curl "http://localhost:8000/api/broker/balance?adapter_type=xtquant"

# 查询持仓
curl "http://localhost:8000/api/broker/positions?adapter_type=xtquant"
```

---

## 下单示例

### 市价买入

```bash
curl -X POST "http://localhost:8000/api/broker/orders" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "sh.600000",
    "side": "buy",
    "quantity": 100,
    "order_type": "market",
    "adapter_type": "xtquant"
  }'
```

### 限价卖出

```bash
curl -X POST "http://localhost:8000/api/broker/orders" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "sz.000001",
    "side": "sell",
    "quantity": 200,
    "order_type": "limit",
    "limit_price": 15.88,
    "adapter_type": "xtquant"
  }'
```

### 撤单

```bash
curl -X DELETE "http://localhost:8000/api/broker/orders/12345?adapter_type=xtquant"
```

### 查询订单状态

```bash
curl "http://localhost:8000/api/broker/orders/12345?adapter_type=xtquant"
```

---

## 适配器切换

### 纸交易 vs 实盘

| 场景 | adapter_type | 说明 |
|------|-------------|------|
| 回测/研究 | `paper` | 默认，使用日K收盘价撮合 |
| 实盘交易 | `xtquant` | 真实资金，通过 QMT 下单 |

可以在请求中动态切换：

```bash
# 纸交易（默认）
curl "http://localhost:8000/api/broker/balance"

# 实盘
curl "http://localhost:8000/api/broker/balance?adapter_type=xtquant"
```

---

## 常见问题

### Q: 连接失败，返回 "xtquant 未安装"

A: 确保在当前 Python 环境中安装了 xtquant：

```bash
python -c "from xtquant import xtdata; print('ok')"
```

如果报错，重新安装或从 QMT 目录复制。

### Q: 连接失败，返回 "xtquant 连接失败"

A: 
1. 确认 QMT/miniQMT 客户端已启动并登录
2. 确认 `XTQUANT_QMT_PATH` 指向的是 `userdata_mini` 目录
3. 确认账号已开通 API 交易权限
4. 检查防火墙是否拦截了本地 TCP 连接

### Q: 下单返回 "拒单"

A:
1. 确认账户有足够资金（买入）或足够持仓（卖出）
2. 确认不在涨跌停状态
3. 确认交易时间（A 股 9:30-11:30, 13:00-15:00）
4. 确认数量为 100 的整数倍

### Q: 持仓查询返回空列表

A: 
1. 确认账号有持仓
2. 确认 `XTQUANT_ACCOUNT_ID` 正确
3. 检查 QMT 客户端是否已同步数据

### Q: 订单状态不同步

A: 当前 MVP 实现采用"下单后返回 SUBMITTED，通过 get_order 轮询查状态"策略。订单状态更新可能有 1-3 秒延迟。未来版本将接入 xtquant 回调推送机制。

---

## 风险提示

**实盘交易有风险，使用 xtquant 适配器前请确认：**

1. **充分测试**：先在纸交易中验证策略逻辑
2. **小资金试水**：首次实盘使用极小仓位
3. **Kill Switch**：熟悉 `POST /api/kill-switch/trigger` 紧急停止功能
4. **日志审计**：所有订单操作会记录到审计日志
5. **网络稳定**：确保服务器网络稳定，避免断线导致订单状态丢失

**Trading Buddy 不对实盘交易盈亏负责。**

---

## 技术细节

### 同步 API → 异步包装

xtquant 的 Python API 是同步阻塞的，所有调用都通过 `asyncio.to_thread()` 包装为异步，避免阻塞 FastAPI 事件循环。

### 代码格式转换

Trading Buddy 内部统一使用 `"sh.600000"` 格式，与 xtquant 交互时自动转换为 `"600000.SH"`。

### 订单状态映射

| xtquant 状态码 | 含义 | 映射状态 |
|---------------|------|----------|
| 48 | 未报 | PENDING |
| 49 | 待报 | PENDING |
| 50 | 已报 | SUBMITTED |
| 55 | 部分成交 | PARTIAL_FILLED |
| 56 | 全部成交 | FILLED |
| 54 | 已撤 | CANCELLED |
| 52 | 已失败 | REJECTED |

---

## 参考链接

- [xtquant 官方文档](http://dict.thinktrader.net/nativeApi/xttrader.html)
- [miniQMT 使用指南](https://miniqmt.com/)
- [QMT 常见问题](https://qmt.hxquant.com/?id=11)
