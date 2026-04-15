# Trading Buddy - 快速上手

## 环境要求

- Python **3.10+** 可运行本仓库（**`requirements.txt`**）；**CI** 与根 **`.python-version`** 当前固定 **3.12**（**`python-version-file`**）。**pyenv** 可 **`pyenv local`** 读 **`.python-version`** 与 CI 对齐。**Playwright** job 的 Node 由 **`.nvmrc`**（**`node-version-file`**）指定。
- Node.js **20+**（Vue / Vite；**E2E** 与 **`.nvmrc`**、根 **`package.json` `engines`** 一致）
- 数据库：**本地 SQLite 即可**；若用云 **MySQL / Redis**，复制 `.env.example` 为项目根目录 `.env` 并按说明填写（Docker 非必须）
- 8GB+ RAM 推荐

## 第一步：安装 Python 依赖

```powershell
cd C:\Users\Administrator\Desktop\trading-buddy
# 若你的路径不同，请改为本仓库根目录

# 创建虚拟环境（推荐）
python -m venv venv
.\venv\Scripts\activate

pip install -r requirements.txt
```

## 第二步：初始化数据库

```powershell
python scripts\init_db.py
```

日志中出现表创建成功即可。使用 **云 MySQL** 时先在 `.env` 中设置 `DATABASE_MODE=mysql` 及 `DATABASE_*`（或兼容别名 `DB_*`），并确保库已创建。

**建表后建议**：灌 **`trade_calendar`**（交易日历），否则看板「交易日历」区块与 `check_daily_kline_quality.py` 的交易日缺口 / B+D 门控没有日历数据。需 **Baostock** 与网络，在项目根执行例如：

```powershell
python scripts\fetch_trade_calendar.py --start 2020-01-01 --end 2025-12-31
```

等价：`python scripts\fetch_data.py --mode calendar --source baostock`（可用 `--calendar-start` / `--calendar-end` 等）。日常增量拉数可加 **`--with-calendar`**（`fetch_data.py` 的 `daily` / `all`）顺带刷新日历尾部。

### 云库「表齐 + verify_stack」验收（可选）

若 **`python scripts\verify_stack.py`** 报错 **`trade_calendar` 表不存在**（或 MySQL 其它缺表）：先 **`python scripts\init_db.py`**，再按上一段灌 **`trade_calendar`**，然后**不加** **`--skip-db`** 重跑 **`verify_stack.py`**，应打印 **`stock_info` / `daily_kline` / `trade_calendar`** 行数，且 Redis、API 冒烟、catalog 契约、**因子截面**（**`GET /api/factors/cross-section`**，依赖 **overview** 首条指数 **`date`**；无指数数据时为 **`[SKIP]`**）与回测异步冒烟均为 **`[OK]`**（或截面为 **`[SKIP]`**）。若库表未齐又需先验 API，可临时 **`python scripts\verify_stack.py --skip-db`**。

## 第三步：拉取初始数据

### 方式 A：一键喂数（推荐，云库 / 本地库通用）

在项目根目录配置好 `.env` 后执行（**首次**会依次：**建表 → 股票列表 → 指数 K 线 → 部分股票日 K → 交易日历 `trade_calendar`（Baostock）**；不需要或无外网时加 **`--skip-calendar`**）：

```powershell
# 默认 standard：约 90 天日 K、最多 120 只股票，指数约 730 天
python scripts\feed_dashboard.py

# 更快验证看板
python scripts\feed_dashboard.py --profile quick

# 全市场日 K（极慢，慎用）
python scripts\feed_dashboard.py --profile full

# 表已建好则跳过 init
python scripts\feed_dashboard.py --skip-init

# 只看将执行哪些命令
python scripts\feed_dashboard.py --dry-run
```

**日常增量**（收盘后、定时任务推荐，按库中最新交易日补数，省时间省流量；默认会在同次命令中带 **`--with-calendar`** 顺带刷新日历尾部，仅 Baostock 生效；不需要时加 **`--skip-calendar`**）：

```powershell
python scripts\feed_dashboard.py --profile daily --skip-init
```

数据源默认读 `.env` 的 `DATA_SOURCE`；可加强制参数，例如  
`python scripts\feed_dashboard.py --source baostock`。

说明：**脚本可以替你写好流程，但必须在你本机运行**（需要你的网络访问 baostock、你的云库账号权限）；别人无法代替你连上你的云数据库执行写入。

### 方式 B：分步拉取（与 `fetch_data.py` 一致）

```powershell
# 数据源由 .env 中 DATA_SOURCE 决定，也可用 --source 覆盖
python scripts\fetch_data.py --source baostock --mode stocks

# 全市场 K 线较慢，建议先小批量验证
python scripts\fetch_data.py --source baostock --mode klines --days 30 --limit 50

# 主要指数（看板概览用）
python scripts\fetch_data.py --source baostock --mode indices

# 等价于「日常增量」的一条龙（股票表 + 指数 + 全市场日 K，增量逻辑）
python scripts\fetch_data.py --mode daily
```

需要**仅对日 K / 指数**做增量时，可加 `--incremental` 与 `--overlap-days`（详见 `python scripts\fetch_data.py --help`）。

本地联调可改用 `--source mock --limit 5` 快速灌入模拟数据。

## 第四步：启动 API

**方式 1（与文档一致，适合开发热重载）：**

```powershell
python -m uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

**方式 2（与 `.env` 一致，读取 `API_HOST` / `API_PORT` / `API_DEBUG`）：**

```powershell
python scripts\run_api.py
```

保持此终端运行。接口文档：http://127.0.0.1:8000/docs  

生产前端若与 API 不同域，可在 `.env` 中配置 `CORS_ORIGINS`（逗号分隔源，或 `*`，见 `.env.example`）。

可选：`LOG_JSON`、`API_ACCESS_LOG`、`API_SLOW_REQUEST_WARN_MS`、路径忽略前缀与 **`X-Request-ID`** 等见 **README**「API 与脚本可观测性」与 **`.env.example`**。本机停 API/Vite/preview 常用端口：**Windows** **`pwsh -File scripts\stop_dev.ps1`**；**macOS/Linux** **`bash scripts/stop_dev.sh`**（依赖 **`lsof`**，或 Linux 上可选 **`fuser`**）。Vue 依赖也可在仓库根执行 **`npm run frontend:install`**；起生产构建预览（**`vite.config` 默认 4173**）：**`npm run frontend:preview`**（与 **`e2e:preview`** 不同：后者含 **`npm run build`** 且 **`--strictPort`**）。

## 第五步：安装并启动 Vue 看板

**新开一个终端**（API 仍在运行）：

```powershell
cd C:\Users\Administrator\Desktop\trading-buddy\frontend
npm install
npm run dev
# 或已在仓库根：npm run frontend:install 后 npm run frontend:dev
```

终端会打印本地地址，一般为 **http://localhost:5173**。开发模式下 **`/api`** 与 **`/health*`** 会通过 Vite **代理**到 `http://127.0.0.1:8000`（可在 `frontend/.env.development` 里改 `VITE_PROXY_TARGET`）；顶栏 API 状态依赖后者。

更多说明见 `frontend/README.md`（含生产构建 `npm run build`、`VITE_API_BASE`，以及 Nginx 反代 **`/api`** 与 **`/health*`** 示例）。**`frontend` 已 `npm install` 后**，也可在**仓库根**执行 **`npm run frontend:dev`**（见根目录 **`package.json`**；无需在根目录 **`npm install`**）。

## 验证是否正常运行

- 浏览器打开 Vue 看板（上一步的 `npm run dev` 地址）；侧栏 **策略回测** 为单标的（**双均线** 或 **买入持有**）/ 批量扫描（可选日期区间、手续费、**基准代码** 用于 β/α）。
- 或访问 API：http://127.0.0.1:8000/docs  
  - `GET /api/dashboard/overview` — 指数概览  
  - `GET /api/klines/analysis/sh.000001` — 上证指数 K 线分析（路径以实际路由为准，可在 Docs 中查看）  
  - `GET /api/backtest/ma-cross` / `GET /api/backtest/ma-cross/scan` — 双均线单标的 / 批量扫描（详见根目录 `README.md`「最小回测」）  
  - `GET /api/backtest/buy-hold` — 买入持有单标的（无 `fast`/`slow`；与 `POST /api/backtest/run` 的 `strategy_id=buy_hold` 同核）

**健康与就绪（运维 / 负载均衡）：**

- `GET /health` — 仅返回配置摘要（`database_mode`、`redis_enabled`），**不连库**
- `GET /health/ready` — 执行数据库 `SELECT 1`；若启用 Redis 则 `PING`，失败时 **503**

**一键自检（需已配置 `.env`，会连数据库（`mysql` / `sqlite`）/ Redis 并冒烟若干路由）：**

```powershell
cd C:\Users\Administrator\Desktop\trading-buddy
python scripts\verify_stack.py
```

**截面因子 CSV（可选，需 `daily_kline` 已入库）：** 与 **`docs/FACTORS.md`** 草案一致；默认 **`KlineRepository.get_daily_last_n_bars_per_code`**（**ROW_NUMBER**，需 **MySQL 8+** / **SQLite 3.25+**）；老库加 **`--legacy-per-code-fetch`**（并调 **`--max-concurrent`**），或先试默认批量并加 **`--auto-legacy-fallback`**。写入 **`experiments\<实验>\outputs\`** 时根 **`.gitignore`** 已忽略 **`experiments/**/outputs/`**。

```powershell
cd C:\Users\Administrator\Desktop\trading-buddy
python scripts\export_factor_cross_section.py --as-of-date 2024-06-28 --dry-run
```

**`--dry-run`** 只统计当日有 K 的标的数；去掉后加 **`-o`** 写 CSV（列含 **`close`**、**`volume`**、**`amount`**、**`turnover_rate`**、**`pct_change`**、**`ret_{N}d`** 等）。详见脚本顶部注释与 **`experiments/README.md`**。

**截面 HTTP（只读 JSON）：** **`GET /api/factors/cross-section`** 见 **`docs/FACTORS.md`**。启动 Vue 看板后，「行情看板」涨跌侧栏底部与「因子预览」页眉可新标签打开该接口（**`as_of_date`** 由 **`GET /api/dashboard/overview`** 首条指数 **`date`** 填入；默认 **period=20**、**max_codes=100**；实现 **`frontend/src/composables/crossSectionOverviewLink.js`**）。若计划落盘或将来进库，先读 **`docs/FACTOR_SNAPSHOT_AND_PERSISTENCE.md`**（阶段 B「厚」前评审稿）。

自动化测试（不跑真实拉数）：

提交前快速自检（仓库根，需已 **`pip install -r requirements.txt`** 且 **`frontend`** 已 **`npm install`**）：**`npm run verify`**（**`pytest -q`** + **`frontend` `vite build`**）。**Dependabot** 按周扫 **`requirements.txt`** 与 **`frontend/package-lock.json`**（**`.github/dependabot.yml`**；需在 GitHub 仓库启用 **Dependabot version updates**）。

```powershell
python -m pytest -q
python -m pytest tests/test_trend_v0_compare_helpers.py tests/test_cli_iso_date_scripts.py tests/test_export_factor_cross_section.py tests/test_factors_cross_section.py -q
```

（`pytest.ini` 限定只跑 `tests/`；**`tests/test_cli_fetch.py`** 含 **`feed_dashboard.py --dry-run`** 等对一键喂数步骤的契约断言，不连库；**`test_trend_v0_compare_helpers`**、**`test_cli_iso_date_scripts`** 无 DB——后者覆盖 **`src/common/cli_iso_date`** 及 **`run_backtest` / `scan_backtest` / 两条 `trend_v0_*`**、**`export_factor_cross_section`** 脚本的顶层加载；**`tests/test_export_factor_cross_section.py`** 在临时 SQLite 上验 **`export_factor_cross_section`** 批量 CSV、**`--codes-file`**（含 **`#`** 注释）、**`--dry-run`**、**legacy**、**`--auto-legacy-fallback`**，以及批量失败且未 fallback 时 **退出码 1**。**`tests/test_factors_cross_section.py`** 验 **`compute_cross_section_row`** 与 **`pct_change_n`** 末点一致。手工 DB 冒烟见 `scripts/smoke_*.py` 与根 `README.md`「测试」。**研究实验目录约定**见 **`experiments/README.md`**；CLI 日期与区间校验见 **`README.md`**「个股趋势 v0 脚本」段。）

**前端 Playwright（主视图导航、涨跌/成交额、股票列表、回测等；请求由 E2E mock，不依赖后端 API）：** 另需 Node 20+。`cd frontend` 后 `npm ci`。常用命令也可在**仓库根**执行 **`npm run frontend:e2e:smoke`**、**`npm run frontend:e2e:connected`**、**`npm run frontend:e2e:chromium`** 等（见根 **`package.json`**）。要向 Playwright 传 **`--list`** 等参数：用 **`npm --prefix frontend run test:e2e:smoke -- --list`**，或在根 **`npm run frontend:e2e:smoke -- -- --list`**（多一层 **`--`**）。

- **推荐（日常，方式 B）**：终端一 **`npm run e2e:preview`**（4173，每次含 **`npm run build`**，避免跑旧 **`dist/`**）；若刚跑过 **`npm run build`** 只想起预览，可用 **`npm run e2e:preview:only`**（不重跑 **`build`**）；终端二 **`cd`** 到 **`frontend`** 后执行 **`npm run test:e2e:connected`**（脚本固定 **`PLAYWRIGHT_BASE_URL=http://127.0.0.1:4173`**，`preflight` 会探测 preview）。跑子集示例：**`npm run test:e2e:connected -- e2e/main-nav-smoke.spec.js`**。调试 UI 模式：**`npm run test:e2e:ui:connected`**（可选 **`-- e2e/某.spec.js`**）；固定通道：**`npm run test:e2e:ui:connected:chromium`** / **`:chrome`**。方式 A 下 UI + 通道：**`npm run test:e2e:ui:chromium`** / **`:chrome`**。需要 **Chrome for Testing** 时，在终端二先设 **`PLAYWRIGHT_EXECUTABLE_PATH`** 再执行同一命令即可。等价写法：手动 **`$env:PLAYWRIGHT_BASE_URL='http://127.0.0.1:4173'`** 后 **`npm run test:e2e`**。
- **方式 A（单终端）**：不设 **`PLAYWRIGHT_BASE_URL`**（或设为空）时 **`preflight`** **不**探测端口；随后 **`npm run build`**（`global-setup`）并由 **`playwright.config.js`** 内置 **webServer** 起 **4173**；若本机 **4173 已被** **`vite preview`** 占用，**`reuseExistingServer`**（非 CI）会复用该进程（**`dist/`** 若过期请重启 preview）。跑用例：**`npm run test:e2e`**；Playwright UI：**`npm run test:e2e:ui`**（可选 **`-- e2e/某.spec.js`**）。若环境里**误**留了非空的 **`PLAYWRIGHT_BASE_URL`** 却未起对应服务，**`preflight`** 会失败：PowerShell 可 **`Remove-Item Env:PLAYWRIGHT_BASE_URL -ErrorAction SilentlyContinue`** 后重试，或改用方式 B。

- **主导航（编写 E2E）**：顶栏视图按钮带 **`data-testid="main-nav-*"`**；用例中请 **`import { MAIN_NAV } from "./fixtures/mainNavTestIds.js"`** 并 **`page.getByTestId(MAIN_NAV.factors)`** 等切换视图，避免文案子串与 **strict** 歧义（见 **`frontend/README.md`**「E2E」）。

另：**`npm run test:e2e:smoke`** / **`:smoke:connected`** 只跑 **`main-nav-smoke`** 与 **`turnover-tab`** 两条 spec，改顶栏或侧栏 tab 后适合快速验证。**`npm run test:e2e:chromium`** / **`npm run test:e2e:chrome`** 等价于方式 A 下临时设置 **`PLAYWRIGHT_CHANNEL`**；**`npm run test:e2e:connected:chromium`** / **`:connected:chrome`** 为方式 B 同步固定通道。子集示例 **`npm run test:e2e:chromium -- e2e/main-nav-smoke.spec.js`**（`--` 后参数会传给 Playwright）。**Windows**：若已执行 **`npx playwright install chromium`**，`playwright.config.js` **默认优先内置 Chromium**（减少系统 Chrome headless 下「browser closed」）；未安装内置浏览器时仍用本机 **Google Chrome**。若已下载 **`chrome-win64.zip`**（Chrome for Testing）：解压后把 **`PLAYWRIGHT_EXECUTABLE_PATH`** 指到 **`chrome.exe`**（常见 **`…\chrome-win64\chrome-win64\chrome.exe`**），E2E 会**最优先**使用该浏览器（见 **`frontend/playwright.config.js`** 注释）。要固定走 Chrome：**`npm run test:e2e:chrome`** 或 **`$env:PLAYWRIGHT_CHANNEL='chrome'`**；要固定走内置：**`npm run test:e2e:chromium`**。**macOS / Linux** 默认 Chromium，首次需 **`npx playwright install chromium`**；若要用系统 Chrome，设 **`PLAYWRIGHT_CHANNEL=chrome`**。详见根目录 **`README.md`**「测试」。

## 常见问题

**Q: 看板空白或「API 未就绪」？**  
先确认本机 API 已启动（默认 `8000`，若用 `run_api.py` 则以 `.env` 中 `API_PORT` 为准），且 `frontend` 里未把 `VITE_API_BASE` 指错。

**Q: pip 安装失败？**

```powershell
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

**Q: baostock 拉数很慢？**  
正常；先用 `--limit` 缩小范围。注意接口频率，可适当调大 `fetch_data.py` 的 `--baostock-delay`。日常更新请优先用 **`--profile daily`** 或 **`--mode daily`**。

**Q: 云库 `daily_kline` 里没有 `sh.000001` 等指数，看板「主要指数」为空？**  
指数成交量常超过 32 位 `INT` 上限，旧表若仍是 `INT` 会导致写入失败。在 MySQL 上执行：  
`ALTER TABLE daily_kline MODIFY COLUMN volume BIGINT NULL;`  
然后重新：`python scripts\fetch_data.py --mode indices --index-days 730`（或与 `feed_dashboard` 等效步骤）。

**Q: 涨跌榜首次加载很慢？**  
云库上常见原因是：按交易日排序涨跌幅要对大量行排序。请在 MySQL 上补复合索引（已有库需手动执行一次）：  
`CREATE INDEX ix_daily_kline_trade_date_pct ON daily_kline (trade_date, change_pct);`  
接口已合并为单次查询并绑定最新交易日，可减少一次往返。

**Q: 还想用旧版静态页？**  
仓库里仍保留 `dashboard\index.html`（已标注迁移说明），需自行把其中的 API 地址指到后端；**推荐以 Vue 看板为准**。

## 每日使用流程

```powershell
cd C:\Users\Administrator\Desktop\trading-buddy

# 推荐：一键日常增量（刷新股票表 + 增量指数 + 增量全市场日 K）
python scripts\feed_dashboard.py --profile daily --skip-init

# 或仅跑拉数脚本（等价逻辑）
python scripts\fetch_data.py --mode daily
```

也可使用 `scripts\scheduler.py` 在后台按固定时间触发（详见脚本内注释）；生产环境更推荐用系统计划任务直接执行上述命令之一。

## V1.x 发布与归档（当前 **1.2.2**）

在**拉数任务已全部跑完**（或日常增量已稳定）、且**测试通过**后，将当前代码树标记为发布版本（示例 **v1.2.2**）：

```powershell
cd C:\Users\Administrator\Desktop\trading-buddy

# 工作区应已提交，无未跟踪的重要文件
git status

python -m pytest -q

# 可选：栈探活（需 API、MySQL、Redis 等按 .env 已可达）
python scripts\verify_stack.py
```

打**附注标签**并推送远程（按需）：

```powershell
git tag -a v1.2.2 -m "Trading Buddy V1.2.2: 截面导出 Parquet + manifest 片段、factor_set_id 辅助（详见 CHANGELOG.md）"
git push origin v1.2.2
```

本地生成**源码归档包**（不依赖远程）：

```powershell
git archive --format=zip -o trading-buddy-v1.2.2.zip v1.2.2
```

版本号与 OpenAPI、`GET /`、`GET /health` 中的 `app_version` 一致，定义在 `src/common/__init__.py` 的 `__version__`。

## 下一步

V1 功能已就绪：

- [x] 股票列表查询
- [x] 日K线数据
- [x] 实时行情
- [x] Vue 看板（Meridian）
- [x] 双均线与买入持有日线最小回测（HTTP / CSV / CLI **`scripts/run_backtest.py`** 含 **`--buy-hold`**；β/α 可选相对指数基准）

V2 规划中：

- [ ] 策略模板解析
- [ ] 信号计算引擎
- [ ] 通用回测引擎（多策略、参数寻优、绩效归因）
- [ ] 券商 API 对接
