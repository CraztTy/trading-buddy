# Trading Buddy 看板（Vue 3）

## 开发

仓库根（已装 Python 依赖与 **`frontend` node_modules**）可 **`npm run verify`** 跑 **pytest + `npm run build`**，与 CI 的 Python job + 前端构建阶段接近（不含 Playwright）。

先启动后端 API（默认 `http://127.0.0.1:8000`），再执行：

```bash
cd frontend
npm install
npm run dev
```

浏览器打开终端里提示的地址（一般为 `http://localhost:5173`）。请求通过 Vite 代理到 `/api`，无需改 CORS。探针路径 **`/health`**、**`/health/ready`** 同样代理到后端，供顶栏 **API 状态** 使用；`vite preview`（如 E2E）已共用该代理。

扩展请求封装见 **`src/composables/api.js`**：**`fetchJson`** 走 **`VITE_API_BASE`** 前缀（默认 **`/api`**）；**`fetchJsonAbs`** 用于同源根路径（如 **`/health*`**），默认 **`toast: false`**，避免与健康轮询叠 Toast。

生产环境若静态资源与 API 不同域，需在网关或 CDN 上为 **`/health*`** 配置与 **`VITE_API_BASE`** 同源的后端转发，否则顶栏会显示离线。

Nginx 示例（静态 `location /` + API 同主机不同路径时，把健康检查与 API 一并反代到后端 `127.0.0.1:8000`）：

```nginx
location /api/ {
  proxy_pass http://127.0.0.1:8000/api/;
  proxy_http_version 1.1;
  proxy_set_header Host $host;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  proxy_set_header X-Forwarded-Proto $scheme;
}
location /health {
  proxy_pass http://127.0.0.1:8000;
  proxy_http_version 1.1;
  proxy_set_header Host $host;
}
```

**策略回测**：侧栏进入后支持双均线「单标的」与「批量扫描」。与行情共用可选 **日期区间**、K 根数、手续费与滑点；**基准代码**（可选）会作为查询参数 `benchmark_code` 传给后端，用于 β / α 相对指数（如 `sh.000300`）回归，留空则相对标的自身日收益。详见仓库根目录 `README.md`「最小回测」。

修改代理目标：编辑 `.env.development` 里的 `VITE_PROXY_TARGET`。

## 生产构建

```bash
npm run build
```

产物在 `frontend/dist/`。若静态站点与 API 不同源，复制 `.env.production.example` 为 `.env.production` 并设置 `VITE_API_BASE`（例如 `https://你的域名:8000/api`）。

## E2E（Playwright）

**推荐（方式 B）**：终端一 **`npm run e2e:preview`**（**4173**，含 **`build`** + **`strictPort`**）；若 **`dist/`** 已新、只需起预览，用 **`npm run e2e:preview:only`**；仓库根亦可 **`npm run frontend:e2e:preview`** / **`npm run frontend:e2e:preview:only`**。终端二在 **`frontend/`** 跑下表命令。**`PLAYWRIGHT_EXECUTABLE_PATH`**（Chrome for Testing 的 **`chrome.exe`**）仍可在终端二先导出，会覆盖 channel 默认（见 **`playwright.config.js`**）。**Windows** 已 **`npx playwright install chromium`** 时 config 默认优先内置 Chromium。更细的说明见 **`FIRST_STEPS.md`** 与根目录 **`README.md`**「测试」。

| 命令 | 作用 |
|------|------|
| **`npm run e2e:preview`** | 终端一：`build` + **`vite preview :4173`** |
| **`npm run e2e:preview:only`** | 仅起 **4173**（不跑 **`build`**；需 **`dist/`** 已存在） |
| **`npm run preview`** | 普通 **`vite preview`**（**4173**，**无** E2E 的 **`--strictPort`** / 前置 **`build`**） |
| **`npm run test:e2e:smoke`** / **`:smoke:connected`** | 少量 spec 快速冒烟（**`main-nav-smoke`** + **`turnover-tab`**） |
| **`npm run test:e2e:connected`** | 终端二：方式 B，无头（内置 **`PLAYWRIGHT_BASE_URL`**，`preflight` 探测） |
| **`npm run test:e2e:connected:chromium`** / **`:chrome`** | 方式 B + 固定 **`PLAYWRIGHT_CHANNEL`** |
| **`npm run test:e2e:ui:connected`** | 方式 B，Playwright UI |
| **`npm run test:e2e:ui:connected:chromium`** / **`:chrome`** | 方式 B，UI + 固定 **`PLAYWRIGHT_CHANNEL`** |
| **`npm run test:e2e`** | 方式 A，无头（**`preflight`** 不探测；**`global-setup`** + **webServer** / **reuse**） |
| **`npm run test:e2e:ui`** | 方式 A，Playwright UI |
| **`npm run test:e2e:ui:chromium`** / **`:chrome`** | 方式 A，UI + 固定 channel |
| **`npm run test:e2e:chromium`** / **`:chrome`** | 方式 A + 固定 channel（无头） |

子集：上表除 **`e2e:preview`** 外，命令后均可加 **`-- e2e/某.spec.js`**（或其它 Playwright CLI 参数）。**`frontend` 已安装依赖时**，可在**仓库根**使用 **`npm run frontend:install`**、**`npm run frontend:preview`**、**`npm run frontend:e2e:smoke`** 等（根 **`package.json`**；Node **20+**）。传 Playwright 参数推荐 **`npm --prefix frontend run test:e2e:connected -- e2e/foo.spec.js`**；若坚持用 **`npm run frontend:…`**，需**多一层 `--`**（例：**`npm run frontend:e2e:smoke -- -- --list`**）。

新增用例切换顶栏主视图时，优先使用 **`App.vue`** 上 **`data-testid="main-nav-*"`** 与 **`e2e/fixtures/mainNavTestIds.js`** 中的 **`MAIN_NAV`**，避免 `getByRole({ name })` 与页面内其它含相同子串的按钮冲突。回测单标的区 **`运行回测`** / **`闭环 · 纸交易`** 分别对应 **`data-testid="backtest-run-submit"`**、**`backtest-open-paper`**（`BacktestPanel.vue`）。

## 技术栈

Vue 3、Vite 5、ECharts 5、`vue-echarts`。**`package.json`** 声明 **`license: MIT`**、**`engines.node: >=20`**（与仓库根 **`.nvmrc`** / CI 一致）。
