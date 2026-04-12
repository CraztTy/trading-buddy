# Trading Buddy 看板（Vue 3）

## 开发

先启动后端 API（默认 `http://127.0.0.1:8000`），再执行：

```bash
cd frontend
npm install
npm run dev
```

浏览器打开终端里提示的地址（一般为 `http://localhost:5173`）。请求通过 Vite 代理到 `/api`，无需改 CORS。

**策略回测**：侧栏进入后支持双均线「单标的」与「批量扫描」。与行情共用可选 **日期区间**、K 根数、手续费与滑点；**基准代码**（可选）会作为查询参数 `benchmark_code` 传给后端，用于 β / α 相对指数（如 `sh.000300`）回归，留空则相对标的自身日收益。详见仓库根目录 `README.md`「最小回测」。

修改代理目标：编辑 `.env.development` 里的 `VITE_PROXY_TARGET`。

## 生产构建

```bash
npm run build
```

产物在 `frontend/dist/`。若静态站点与 API 不同源，复制 `.env.production.example` 为 `.env.production` 并设置 `VITE_API_BASE`（例如 `https://你的域名:8000/api`）。

## 技术栈

Vue 3、Vite 5、ECharts 5、`vue-echarts`。
