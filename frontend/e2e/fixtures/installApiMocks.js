/**
 * 拦截 /api/**，不依赖后端，供 E2E 稳定跑在 CI。
 * @param {import('@playwright/test').Page} page
 */

import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const E2E_FACTOR_CATALOG_BODY = fs.readFileSync(path.join(__dirname, "factor-catalog.json"), "utf8");
const E2E_BACKTEST_CATALOG_BODY = fs.readFileSync(path.join(__dirname, "backtest-catalog.json"), "utf8");

const STOCK_LIST_E2E_TOTAL = 120;

/** 与旧用例一致：前 50 条含 Pudong/Pingan + filler；offset 50 起含 ZhaoShang/BOC；之后为 tail。 */
function buildStockListE2eItems() {
  const out = [];
  out.push({ code: "sh.600000", name: "Pudong-Dev-Bank-e2e", status: "ok" });
  out.push({ code: "sz.000001", name: "Pingan-e2e", status: "ok" });
  for (let i = 2; i < 50; i++) {
    out.push({
      code: `sz.${String(200000 + i).padStart(6, "0")}`,
      name: `Filler-e2e-${i}`,
      status: "ok",
    });
  }
  out.push({ code: "sh.600036", name: "ZhaoShang-e2e-p2", status: "ok" });
  out.push({ code: "sh.601988", name: "BOC-e2e-p2", status: "ok" });
  for (let i = 52; i < STOCK_LIST_E2E_TOTAL; i++) {
    out.push({
      code: `sh.${String(603000 + i).padStart(6, "0")}`,
      name: `Tail-e2e-${i}`,
      status: "ok",
    });
  }
  return out;
}

const STOCK_LIST_E2E_ITEMS = buildStockListE2eItems();

function createPaperE2eState() {
  return {
    cash: 1_000_000,
    initial: 1_000_000,
    /** @type {{ code: string; quantity: number; buyDate: string; buyPrice: number }[]} */
    lots: [],
    orders: [],
    nextOrderId: 1,
    /** 模拟「最近日 K」交易日；买入成功后推进一日，便于 E2E 测 T+1 卖出 */
    pricingDate: "2024-01-05",
    /** 聚合持仓，供 GET state */
    positions: [],
  };
}

/** @type {ReturnType<typeof createPaperE2eState>} */
let paperE2eState = createPaperE2eState();

/** @type {{ code: string; name: string | null; created_at: string }[]} */
let watchlistE2eItems = [];

/** @type {{ id: number; kind: string; summary: string; request_params: Record<string, unknown>; response_payload: Record<string, unknown>; created_at: string }[]} */
let backtestRunsE2e = [];
let backtestRunsE2eNextId = 1;

/** 异步 mock：前 N 次 GET 为 pending，再 running → completed；POST cancel 仅在 pending 窗口内 200 */
const ASYNC_E2E_PENDING_POLLS = 5;

let backtestE2eAsyncJobs = new Map();
let backtestE2eAsyncJobSeq = 0;

function backtestE2eNextJobId() {
  backtestE2eAsyncJobSeq += 1;
  return backtestE2eAsyncJobSeq.toString(16).padStart(32, "0");
}

/** 与 GET /api/backtest/ma-cross JSON 体一致；供 GET 与 POST /run（result）复用 */
function mockMaCrossSingleResponseJson(code, bench, fast, slow) {
  const c = (code || "sh.000001").trim() || "sh.000001";
  const fp = Number.isFinite(fast) && fast > 0 ? fast : 5;
  const sp = Number.isFinite(slow) && slow > 0 ? slow : 20;
  return {
    code: c,
    fast_period: fp,
    slow_period: sp,
    bars_used: 120,
    commission_rate: 0,
    slippage_rate: 0,
    first_trade_date: "2024-01-02",
    last_trade_date: "2024-06-30",
    total_return_pct: 12.34,
    buy_hold_return_pct: 3.21,
    excess_return_pct: 9.13,
    max_drawdown_pct: -2.5,
    sharpe_ratio: 0.42,
    signal_changes: 4,
    annualized_return_pct: 5.1,
    buy_hold_annualized_return_pct: 2.2,
    annualized_volatility_pct: 11.0,
    sortino_ratio: 0.55,
    calmar_ratio: 0.33,
    long_trades_count: 3,
    win_rate_pct: 66.7,
    avg_holding_return_pct: 1.1,
    underlying_beta: 1.05,
    underlying_alpha_ann_pct: 0.5,
    benchmark_code: bench || null,
    note: "e2e-mock-ma-cross single",
    equity_curve: [
      { trade_date: "2024-01-02", equity: 1.0 },
      { trade_date: "2024-01-03", equity: 1.02 },
      { trade_date: "2024-01-04", equity: 1.01 },
    ],
  };
}

/** 与 GET /api/backtest/ma-cross/scan JSON 体一致；供 E2E GET scan 与 POST /run（scan_result）复用 */
/** 与 GET /api/backtest/buy-hold JSON 体一致；fast_period/slow_period 为占位 1/2 */
function mockBuyHoldSingleResponseJson(code, bench) {
  const c = (code || "sh.000001").trim() || "sh.000001";
  return {
    code: c,
    fast_period: 1,
    slow_period: 2,
    bars_used: 120,
    commission_rate: 0,
    slippage_rate: 0,
    first_trade_date: "2024-01-02",
    last_trade_date: "2024-06-30",
    total_return_pct: 3.21,
    buy_hold_return_pct: 3.21,
    excess_return_pct: 0,
    max_drawdown_pct: -1.2,
    sharpe_ratio: 0.35,
    signal_changes: 0,
    annualized_return_pct: 2.8,
    buy_hold_annualized_return_pct: 2.8,
    annualized_volatility_pct: 10.5,
    sortino_ratio: 0.5,
    calmar_ratio: 0.28,
    long_trades_count: 1,
    win_rate_pct: 55.0,
    avg_holding_return_pct: 0.9,
    underlying_beta: 1.0,
    underlying_alpha_ann_pct: 0.1,
    benchmark_code: bench || null,
    note: "e2e-mock-buy-hold",
    equity_curve: [
      { trade_date: "2024-01-02", equity: 1.0 },
      { trade_date: "2024-01-03", equity: 1.01 },
    ],
  };
}

function mockMaCrossScanResponseJson(sortBy) {
  return {
    fast_period: 5,
    slow_period: 20,
    limit: 500,
    commission_rate: 0,
    slippage_rate: 0,
    sort_by: sortBy,
    max_concurrent: 8,
    start_date: null,
    end_date: null,
    benchmark_code: null,
    items: [
      {
        code: "sh.000001",
        error: null,
        bars_used: 200,
        total_return_pct: 3.33,
        buy_hold_return_pct: 1.0,
        excess_return_pct: 2.33,
        max_drawdown_pct: -1.0,
        sharpe_ratio: 0.5,
        signal_changes: 2,
        annualized_return_pct: 4.0,
        buy_hold_annualized_return_pct: 1.5,
        annualized_volatility_pct: 10.0,
        sortino_ratio: 0.6,
        calmar_ratio: 0.4,
        long_trades_count: 2,
        win_rate_pct: 50.0,
        avg_holding_return_pct: 0.8,
        underlying_beta: 1.0,
        underlying_alpha_ann_pct: 0.2,
      },
    ],
  };
}

function e2eBuildBacktestRunSummary(kind, responsePayload) {
  if (kind === "ma_cross_single") {
    const c = String(responsePayload?.code || "?");
    const fp = responsePayload?.fast_period;
    const sp = responsePayload?.slow_period;
    const tr = responsePayload?.total_return_pct;
    return `${c} MA${fp}/${sp} 策略${tr}%`;
  }
  if (kind === "ma_cross_scan") {
    const items = Array.isArray(responsePayload?.items) ? responsePayload.items : [];
    const fp = responsePayload?.fast_period;
    const sp = responsePayload?.slow_period;
    const ok = items.filter((x) => x && typeof x === "object" && !x.error).length;
    return `批量 ${items.length} 行（有效 ${ok}）MA${fp}/${sp}`;
  }
  if (kind === "buy_hold_single") {
    const c = String(responsePayload?.code || "?");
    const tr = responsePayload?.total_return_pct;
    return `${c} 买入持有 策略${tr}%`;
  }
  return String(kind || "unknown").slice(0, 200);
}

function paperNextIsoDay(iso) {
  const d = new Date(`${iso}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}

function paperRebuildPositionsFromLots() {
  const agg = {};
  for (const lot of paperE2eState.lots) {
    if (lot.quantity <= 0) continue;
    if (!agg[lot.code]) agg[lot.code] = { code: lot.code, quantity: 0, cost: 0 };
    agg[lot.code].quantity += lot.quantity;
    agg[lot.code].cost += lot.quantity * lot.buyPrice;
  }
  paperE2eState.positions = Object.values(agg).map((x) => ({
    code: x.code,
    quantity: x.quantity,
    avg_price: Math.round((x.cost / x.quantity) * 10000) / 10000,
  }));
}

function paperSellableQuantity(code, pricingDate) {
  return paperE2eState.lots
    .filter((l) => l.code === code && l.quantity > 0 && l.buyDate < pricingDate)
    .reduce((s, l) => s + l.quantity, 0);
}

function paperMockLastClose(code) {
  const c = (code || "").toLowerCase();
  if (c === "sh.600000") return 12.34;
  return 10;
}

export async function installApiMocks(page) {
  paperE2eState = createPaperE2eState();
  watchlistE2eItems = [];
  backtestRunsE2e = [];
  backtestRunsE2eNextId = 1;
  backtestE2eAsyncJobs = new Map();
  backtestE2eAsyncJobSeq = 0;
  await page.addInitScript(() => {
    try {
      sessionStorage.removeItem("tb_mainView");
      sessionStorage.removeItem("tb_currentCode");
      sessionStorage.removeItem("tb_rankTab");
      localStorage.removeItem("tb_backtest_mvp_async");
      localStorage.removeItem("tb_backtest_single_strategy");
    } catch {
      /* ignore */
    }
  });
  await page.route("**/api/**", async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const path = url.pathname;

    if (path === "/api/dashboard/overview") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          indices: [
            {
              code: "sh.000001",
              name: "上证指数",
              price: 3000,
              change: 10,
              pct_change: 0.33,
              high: 3010,
              low: 2990,
              volume: 1_000_000_000,
              date: "2024-03-07",
            },
            {
              code: "sz.399001",
              name: "深证成指",
              price: 9500,
              change: -5,
              pct_change: -0.05,
              high: 9520,
              low: 9480,
              volume: 800_000_000,
              date: "2024-03-07",
            },
            {
              code: "sz.399006",
              name: "创业板指",
              price: 1800,
              change: 3,
              pct_change: 0.17,
              high: 1810,
              low: 1795,
              volume: 500_000_000,
              date: "2024-03-07",
            },
            {
              code: "sh.000300",
              name: "沪深300",
              price: 3500,
              change: 8,
              pct_change: 0.23,
              high: 3510,
              low: 3490,
              volume: 600_000_000,
              date: "2024-03-07",
            },
          ],
        }),
      });
    }

    if (path === "/api/data/trade-calendar/options") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          exchanges: [
            { value: "cn", label: "cn · A 股" },
            { value: "hk", label: "hk" },
            { value: "us", label: "us" },
          ],
          default_exchange: "cn",
        }),
      });
    }

    if (path === "/api/data/trade-calendar/status") {
      const ex = (url.searchParams.get("exchange") || "cn").trim().toLowerCase();
      const mockBy = {
        cn: {
          exchange: "cn",
          row_count: 1840,
          date_min: "2020-01-02",
          date_max: "2024-06-28",
        },
        hk: { exchange: "hk", row_count: 0, date_min: null, date_max: null },
        us: {
          exchange: "us",
          row_count: 312,
          date_min: "2023-01-03",
          date_max: "2024-03-01",
        },
      };
      const body = mockBy[ex] || {
        exchange: ex,
        row_count: 0,
        date_min: null,
        date_max: null,
      };
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(body),
      });
    }

    if (path.startsWith("/api/klines/analysis/")) {
      const raw = path.slice("/api/klines/analysis/".length);
      const code = decodeURIComponent(raw.split("/")[0] || "sh.000001");
      const hist = synthKlines(code, 65);
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          code,
          name: "上证指数",
          count: hist.length,
          latest: hist[hist.length - 1],
          indicators: { ma5: 3001, ma10: 2998, ma20: 2995, ma60: 2980 },
          history: hist,
        }),
      });
    }

    if (path === "/api/dashboard/gainers") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            code: "sh.600018",
            name: "上港集团",
            price: 5.2,
            change: 0.1,
            pct_change: 1.96,
          },
          {
            code: "sh.600019",
            name: "宝钢股份",
            price: 6.1,
            change: 0.05,
            pct_change: 0.83,
          },
        ]),
      });
    }

    if (path === "/api/dashboard/losers") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            code: "sh.601288",
            name: "农业银行",
            price: 3.5,
            change: -0.02,
            pct_change: -0.57,
          },
        ]),
      });
    }

    if (path === "/api/backtest/catalog" && req.method() === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: E2E_BACKTEST_CATALOG_BODY,
      });
    }

    if (path === "/api/backtest/ma-cross/signal") {
      const code = (url.searchParams.get("code") || "sh.000001").trim().toLowerCase();
      const fast = parseInt(url.searchParams.get("fast") || "5", 10) || 5;
      const slow = parseInt(url.searchParams.get("slow") || "20", 10) || 20;
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          code,
          fast_period: fast,
          slow_period: slow,
          bars_used: 120,
          as_of_date: "2024-06-28",
          position: "long",
          close: 10.5,
          ma_fast: 10.2,
          ma_slow: 9.8,
          note: "e2e-mock-ma-cross-signal",
        }),
      });
    }

    if (path === "/api/strategies/catalog") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          strategies: [
            {
              id: "ma_cross",
              title: "双均线（日线收盘）",
              description: "e2e-mock-catalog",
              backtest_archive_kinds: ["ma_cross_single", "ma_cross_scan"],
              strategy_contract_version: "1",
              signal_params: { type: "object", properties: {} },
              backtest_run: {
                strategy_id: "ma_cross",
                strategy_version: "1",
                archive_kind: "ma_cross_single",
                description: "e2e-mock-backtest-run",
                params_schema: { type: "object", required: ["code"], properties: {} },
              },
            },
            {
              id: "ma_cross_scan",
              title: "双均线批量扫描（日线）",
              description: "e2e-mock-catalog-scan",
              backtest_archive_kinds: ["ma_cross_scan"],
              strategy_contract_version: "1",
              signal_params: {
                type: "object",
                description: "e2e-mock-no-signal",
                properties: {},
                required: [],
                maxProperties: 0,
                additionalProperties: false,
              },
              backtest_run: {
                strategy_id: "ma_cross_scan",
                strategy_version: "1",
                archive_kind: "ma_cross_scan",
                params_schema: { type: "object", required: ["codes"], properties: {} },
              },
            },
            {
              id: "buy_hold",
              title: "买入持有（日线收盘）",
              description: "e2e-mock-catalog-buy-hold",
              backtest_archive_kinds: ["buy_hold_single"],
              strategy_contract_version: "1",
              signal_params: {
                type: "object",
                description: "e2e-mock-no-signal",
                properties: {},
                required: [],
                maxProperties: 0,
                additionalProperties: false,
              },
              backtest_run: {
                strategy_id: "buy_hold",
                strategy_version: "1",
                archive_kind: "buy_hold_single",
                params_schema: { type: "object", required: ["code"], properties: {} },
              },
            },
          ],
        }),
      });
    }

    if (path === "/api/strategies/signal" && req.method() === "POST") {
      let body = {};
      try {
        body = /** @type {Record<string, unknown>} */ (req.postDataJSON() || {});
      } catch {
        /* ignore */
      }
      const kindRaw = String(body.kind || "ma_cross").trim();
      if (kindRaw === "ma_cross_scan") {
        return route.fulfill({
          status: 400,
          contentType: "application/json",
          body: JSON.stringify({
            detail:
              "kind=ma_cross_scan 不支持 POST /api/strategies/signal；请用 kind=ma_cross（e2e mock）",
          }),
        });
      }
      const code = String(body.code || "sh.000001")
        .trim()
        .toLowerCase();
      const params = /** @type {Record<string, unknown>} */ (
        typeof body.params === "object" && body.params ? body.params : {}
      );
      const fast = parseInt(String(params.fast ?? "5"), 10) || 5;
      const slow = parseInt(String(params.slow ?? "20"), 10) || 20;
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          kind: body.kind || "ma_cross",
          signal: {
            code,
            fast_period: fast,
            slow_period: slow,
            bars_used: 120,
            as_of_date: "2024-06-28",
            position: "long",
            close: 10.5,
            ma_fast: 10.2,
            ma_slow: 9.8,
            note: "e2e-mock-strategies-signal",
          },
        }),
      });
    }

    if (path === "/api/backtest/run" && req.method() === "POST") {
      let body = {};
      try {
        body = req.postDataJSON() || {};
      } catch {
        body = {};
      }
      const wantAsync = ["1", "true", "True"].includes(
        String(url.searchParams.get("async") || "").trim()
      );
      const sid = body.strategy_id;
      const ver = String(body.strategy_version || "");
      if (ver !== "1") {
        return route.fulfill({
          status: 400,
          contentType: "application/json",
          body: JSON.stringify({ detail: "strategy_version 无效" }),
        });
      }
      if (sid === "ma_cross") {
        const params = body.params && typeof body.params === "object" ? body.params : {};
        const code = String(params.code || "sh.000001").trim() || "sh.000001";
        const bench = String(params.benchmark_code || "").trim().toLowerCase();
        const fast = parseInt(String(params.fast ?? "5"), 10) || 5;
        const slow = parseInt(String(params.slow ?? "20"), 10) || 20;
        const single = mockMaCrossSingleResponseJson(code, bench, fast, slow);
        const syncBody = {
          engine_version: "0.1",
          strategy_id: "ma_cross",
          strategy_version: "1",
          assumptions: ["e2e-mock-single-assumptions"],
          result: single,
          scan_result: null,
        };
        if (wantAsync) {
          const jobId = backtestE2eNextJobId();
          const queuedAt = new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
          backtestE2eAsyncJobs.set(jobId, {
            polls: 0,
            full: syncBody,
            queuedAt,
            cancelled: false,
          });
          return route.fulfill({
            status: 202,
            contentType: "application/json",
            body: JSON.stringify({
              job_id: jobId,
              status: "accepted",
              status_path: `/api/backtest/jobs/${jobId}`,
            }),
          });
        }
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(syncBody),
        });
      }
      if (sid === "buy_hold") {
        const params = body.params && typeof body.params === "object" ? body.params : {};
        const code = String(params.code || "sh.000001").trim() || "sh.000001";
        const bench = String(params.benchmark_code || "").trim().toLowerCase();
        const single = mockBuyHoldSingleResponseJson(code, bench);
        const syncBody = {
          engine_version: "0.1",
          strategy_id: "buy_hold",
          strategy_version: "1",
          assumptions: ["e2e-mock-buy-hold-assumptions"],
          result: single,
          scan_result: null,
        };
        if (wantAsync) {
          const jobId = backtestE2eNextJobId();
          const queuedAt = new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
          backtestE2eAsyncJobs.set(jobId, {
            polls: 0,
            full: syncBody,
            queuedAt,
            cancelled: false,
          });
          return route.fulfill({
            status: 202,
            contentType: "application/json",
            body: JSON.stringify({
              job_id: jobId,
              status: "accepted",
              status_path: `/api/backtest/jobs/${jobId}`,
            }),
          });
        }
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(syncBody),
        });
      }
      if (sid === "ma_cross_scan") {
        const params = body.params && typeof body.params === "object" ? body.params : {};
        const sortBy =
          typeof params.sort_by === "string" && params.sort_by.trim()
            ? params.sort_by.trim()
            : "total_return";
        const syncBody = {
          engine_version: "0.1",
          strategy_id: "ma_cross_scan",
          strategy_version: "1",
          assumptions: ["e2e-mock-scan-assumptions"],
          result: null,
          scan_result: mockMaCrossScanResponseJson(sortBy),
        };
        if (wantAsync) {
          const jobId = backtestE2eNextJobId();
          const queuedAt = new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
          backtestE2eAsyncJobs.set(jobId, {
            polls: 0,
            full: syncBody,
            queuedAt,
            cancelled: false,
          });
          return route.fulfill({
            status: 202,
            contentType: "application/json",
            body: JSON.stringify({
              job_id: jobId,
              status: "accepted",
              status_path: `/api/backtest/jobs/${jobId}`,
            }),
          });
        }
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(syncBody),
        });
      }
      return route.fulfill({
        status: 400,
        contentType: "application/json",
        body: JSON.stringify({
          detail: "e2e: POST /backtest/run 仅 mock ma_cross / buy_hold / ma_cross_scan",
        }),
      });
    }

    if (path.startsWith("/api/backtest/jobs/") && req.method() === "POST") {
      const rawPost = path.slice("/api/backtest/jobs/".length);
      if (!rawPost.endsWith("/cancel")) {
        return route.continue();
      }
      const jobIdPost = decodeURIComponent(rawPost.slice(0, -"/cancel".length)).trim();
      if (!jobIdPost) {
        return route.fulfill({
          status: 404,
          contentType: "application/json",
          body: JSON.stringify({ detail: "not found" }),
        });
      }
      const recPost = backtestE2eAsyncJobs.get(jobIdPost);
      if (!recPost) {
        return route.fulfill({
          status: 404,
          contentType: "application/json",
          body: JSON.stringify({ detail: "job 不存在" }),
        });
      }
      if (recPost.cancelled || recPost.polls > ASYNC_E2E_PENDING_POLLS) {
        return route.fulfill({
          status: 409,
          contentType: "application/json",
          body: JSON.stringify({ detail: "e2e-mock: 仅 pending 阶段可取消" }),
        });
      }
      recPost.cancelled = true;
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ job_id: jobIdPost, status: "cancelled" }),
      });
    }

    if (path.startsWith("/api/backtest/jobs/") && req.method() === "GET") {
      const raw = path.slice("/api/backtest/jobs/".length);
      const jobId = decodeURIComponent(raw || "").trim();
      if (!jobId) {
        return route.fulfill({
          status: 404,
          contentType: "application/json",
          body: JSON.stringify({ detail: "not found" }),
        });
      }
      const rec = backtestE2eAsyncJobs.get(jobId);
      if (!rec) {
        return route.fulfill({
          status: 404,
          contentType: "application/json",
          body: JSON.stringify({ detail: "job 不存在" }),
        });
      }
      if (rec.cancelled) {
        const tCan = new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
        const qCan = typeof rec.queuedAt === "string" ? rec.queuedAt : tCan;
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            job_id: jobId,
            status: "cancelled",
            async_job_persistence: "memory",
            result: null,
            error: "cancelled",
            queued_at: qCan,
            started_at: null,
            finished_at: tCan,
          }),
        });
      }
      rec.polls += 1;
      if (rec.polls <= ASYNC_E2E_PENDING_POLLS) {
        const t0 = new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
        const q = typeof rec.queuedAt === "string" ? rec.queuedAt : t0;
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            job_id: jobId,
            status: "pending",
            async_job_persistence: "memory",
            result: null,
            error: null,
            queued_at: q,
            started_at: null,
            finished_at: null,
          }),
        });
      }
      if (rec.polls === ASYNC_E2E_PENDING_POLLS + 1) {
        const t0 = new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
        const q = typeof rec.queuedAt === "string" ? rec.queuedAt : t0;
        rec.startedAt = t0;
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            job_id: jobId,
            status: "running",
            async_job_persistence: "memory",
            result: null,
            error: null,
            queued_at: q,
            started_at: t0,
            finished_at: null,
          }),
        });
      }
      const t1 = new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
      const q = typeof rec.queuedAt === "string" ? rec.queuedAt : t1;
      const st = typeof rec.startedAt === "string" ? rec.startedAt : q;
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          job_id: jobId,
          status: "completed",
          async_job_persistence: "memory",
          result: rec.full,
          error: null,
          queued_at: q,
          started_at: st,
          finished_at: t1,
        }),
      });
    }

    if (path === "/api/backtest/ma-cross/scan") {
      const sortBy = url.searchParams.get("sort_by") || "total_return";
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(mockMaCrossScanResponseJson(sortBy)),
      });
    }

    if (path === "/api/backtest/ma-cross") {
      const code = url.searchParams.get("code") || "sh.000001";
      const bench = (url.searchParams.get("benchmark_code") || "").trim().toLowerCase();
      const fast = parseInt(url.searchParams.get("fast") || "5", 10) || 5;
      const slow = parseInt(url.searchParams.get("slow") || "20", 10) || 20;
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(mockMaCrossSingleResponseJson(code, bench, fast, slow)),
      });
    }

    if (path === "/api/backtest/buy-hold") {
      const code = url.searchParams.get("code") || "sh.000001";
      const bench = (url.searchParams.get("benchmark_code") || "").trim().toLowerCase();
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(mockBuyHoldSingleResponseJson(code, bench)),
      });
    }

    if (path === "/api/backtest/runs" && req.method() === "GET") {
      const limit = Math.min(
        100,
        Math.max(1, parseInt(url.searchParams.get("limit") || "30", 10) || 30)
      );
      const offset = Math.max(0, parseInt(url.searchParams.get("offset") || "0", 10) || 0);
      const kindRaw = (url.searchParams.get("kind") || "").trim();
      if (
        kindRaw &&
        kindRaw !== "ma_cross_single" &&
        kindRaw !== "ma_cross_scan" &&
        kindRaw !== "buy_hold_single"
      ) {
        return route.fulfill({
          status: 422,
          contentType: "application/json",
          body: JSON.stringify({ detail: "kind 无效" }),
        });
      }
      let ordered = backtestRunsE2e.slice().reverse();
      if (kindRaw === "ma_cross_single" || kindRaw === "ma_cross_scan" || kindRaw === "buy_hold_single") {
        ordered = ordered.filter((r) => r.kind === kindRaw);
      }
      const qRaw = (url.searchParams.get("q") || "").trim();
      if (qRaw.length > 120) {
        return route.fulfill({
          status: 422,
          contentType: "application/json",
          body: JSON.stringify({ detail: "q 过长" }),
        });
      }
      if (qRaw) {
        ordered = ordered.filter((r) => String(r.summary || "").includes(qRaw));
      }
      const total = ordered.length;
      const pageRows = ordered.slice(offset, offset + limit);
      const items = pageRows.map((r) => ({
        id: r.id,
        kind: r.kind,
        summary: r.summary,
        created_at: r.created_at,
      }));
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items, total, limit, offset }),
      });
    }

    if (path === "/api/backtest/runs" && req.method() === "POST") {
      let body = {};
      try {
        body = req.postDataJSON() || {};
      } catch {
        body = {};
      }
      const kind = body.kind;
      if (kind !== "ma_cross_single" && kind !== "ma_cross_scan" && kind !== "buy_hold_single") {
        return route.fulfill({
          status: 422,
          contentType: "application/json",
          body: JSON.stringify({ detail: "kind 无效" }),
        });
      }
      if (typeof body.request_params !== "object" || body.request_params === null) {
        return route.fulfill({
          status: 400,
          contentType: "application/json",
          body: JSON.stringify({ detail: "request_params 须为 JSON 对象" }),
        });
      }
      if (typeof body.response_payload !== "object" || body.response_payload === null) {
        return route.fulfill({
          status: 400,
          contentType: "application/json",
          body: JSON.stringify({ detail: "response_payload 须为 JSON 对象" }),
        });
      }
      const summary = e2eBuildBacktestRunSummary(kind, body.response_payload).slice(0, 512);
      const id = backtestRunsE2eNextId++;
      const created_at = new Date().toISOString();
      backtestRunsE2e.push({
        id,
        kind,
        summary,
        request_params: body.request_params,
        response_payload: body.response_payload,
        created_at,
      });
      return route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({ id, summary }),
      });
    }

    if (path.startsWith("/api/backtest/runs/") && req.method() === "DELETE") {
      const raw = path.slice("/api/backtest/runs/".length);
      const runId = parseInt(raw, 10);
      if (!Number.isFinite(runId) || String(runId) !== raw) {
        return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "not found" }) });
      }
      const idx = backtestRunsE2e.findIndex((r) => r.id === runId);
      if (idx < 0) {
        return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "记录不存在" }) });
      }
      backtestRunsE2e.splice(idx, 1);
      return route.fulfill({ status: 204, body: "" });
    }

    if (path.startsWith("/api/backtest/runs/") && req.method() === "GET") {
      const raw = path.slice("/api/backtest/runs/".length);
      const runId = parseInt(raw, 10);
      if (!Number.isFinite(runId) || String(runId) !== raw) {
        return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "not found" }) });
      }
      const row = backtestRunsE2e.find((r) => r.id === runId);
      if (!row) {
        return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "记录不存在" }) });
      }
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: row.id,
          kind: row.kind,
          summary: row.summary,
          created_at: row.created_at,
          request_params: row.request_params,
          response_payload: row.response_payload,
        }),
      });
    }

    if (path === "/api/stocks/list") {
      const limit = Math.min(
        500,
        Math.max(1, parseInt(url.searchParams.get("limit") || "50", 10) || 50)
      );
      const reqOff = Math.max(0, parseInt(url.searchParams.get("offset") || "0", 10) || 0);
      const total = STOCK_LIST_E2E_TOTAL;
      const maxStart = Math.max(0, Math.floor((total - 1) / limit) * limit);
      const offset = Math.min(reqOff, maxStart);
      const items = STOCK_LIST_E2E_ITEMS.slice(offset, offset + limit);
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items, total, limit, offset }),
      });
    }

    if (path === "/api/paper/state") {
      paperRebuildPositionsFromLots();
      const td = paperE2eState.pricingDate;
      const posOut = paperE2eState.positions.map((p) => {
        const last = paperMockLastClose(p.code);
        const sellable = paperSellableQuantity(p.code, td);
        const mv = Math.round(last * p.quantity * 100) / 100;
        return {
          code: p.code,
          quantity: p.quantity,
          avg_price: p.avg_price,
          last_close: last,
          market_value: mv,
          sellable_quantity: sellable,
          locked_quantity: Math.max(0, p.quantity - sellable),
        };
      });
      const mv = posOut.reduce((s, x) => s + x.market_value, 0);
      const equity = Math.round((paperE2eState.cash + mv) * 100) / 100;
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          account: {
            id: 1,
            label: "default",
            cash: paperE2eState.cash,
            initial_cash: paperE2eState.initial,
          },
          positions: posOut,
          equity,
        }),
      });
    }

    if (path === "/api/paper/orders" && req.method() === "GET") {
      const limit = Math.min(
        200,
        Math.max(1, parseInt(url.searchParams.get("limit") || "50", 10) || 50)
      );
      const offset = Math.max(0, parseInt(url.searchParams.get("offset") || "0", 10) || 0);
      const want = (url.searchParams.get("code") || "").trim().toLowerCase();
      let arr = paperE2eState.orders.slice().reverse();
      if (want) arr = arr.filter((o) => o.code === want);
      const total = arr.length;
      const items = arr.slice(offset, offset + limit);
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items, total, limit, offset }),
      });
    }

    if (path === "/api/paper/orders" && req.method() === "POST") {
      let body = {};
      try {
        body = req.postDataJSON() || {};
      } catch {
        body = {};
      }
      const code = String(body.code || "").trim().toLowerCase();
      const side = String(body.side || "").toLowerCase();
      const qty = Math.max(0, parseInt(String(body.quantity || "0"), 10) || 0);
      if (!code || (side !== "buy" && side !== "sell")) {
        return route.fulfill({ status: 400, contentType: "application/json", body: JSON.stringify({ detail: "bad request" }) });
      }
      if (qty < 100 || qty % 100 !== 0) {
        return route.fulfill({
          status: 422,
          contentType: "application/json",
          body: JSON.stringify({ detail: "股数须为 100 的整数倍且不少于 100" }),
        });
      }
      const price = paperMockLastClose(code);
      const gross = Math.round(price * qty * 100) / 100;
      const td = paperE2eState.pricingDate;
      if (side === "buy") {
        if (paperE2eState.cash + 1e-9 < gross) {
          return route.fulfill({
            status: 400,
            contentType: "application/json",
            body: JSON.stringify({ detail: "现金不足" }),
          });
        }
        paperE2eState.cash = Math.round((paperE2eState.cash - gross) * 100) / 100;
        paperE2eState.lots.push({ code, quantity: qty, buyDate: td, buyPrice: price });
        paperE2eState.pricingDate = paperNextIsoDay(td);
      } else {
        const sellable = paperSellableQuantity(code, td);
        if (sellable < qty) {
          return route.fulfill({
            status: 400,
            contentType: "application/json",
            body: JSON.stringify({
              detail: `卖出 T+1：当前可卖 ${sellable} 股，请求卖出 ${qty} 股`,
            }),
          });
        }
        const other = paperE2eState.lots.filter((l) => l.code !== code);
        const forCode = paperE2eState.lots
          .filter((l) => l.code === code && l.quantity > 0)
          .sort((a, b) => String(a.buyDate).localeCompare(String(b.buyDate)));
        let left = qty;
        const after = [];
        for (const lot of forCode) {
          if (lot.buyDate >= td) {
            after.push(lot);
            continue;
          }
          const take = Math.min(lot.quantity, left);
          const rem = lot.quantity - take;
          left -= take;
          if (rem > 0) after.push({ ...lot, quantity: rem });
        }
        if (left > 0) {
          return route.fulfill({
            status: 400,
            contentType: "application/json",
            body: JSON.stringify({ detail: "卖出 T+1：可卖不足" }),
          });
        }
        paperE2eState.lots = other.concat(after);
        paperE2eState.cash = Math.round((paperE2eState.cash + gross) * 100) / 100;
      }
      paperRebuildPositionsFromLots();
      const id = paperE2eState.nextOrderId++;
      paperE2eState.orders.push({
        id,
        code,
        side,
        quantity: qty,
        fill_price: price,
        fill_amount: gross,
        trade_date: td,
        created_at: new Date().toISOString(),
      });
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id,
          code,
          side,
          quantity: qty,
          fill_price: price,
          fill_amount: gross,
          trade_date: td,
          cash_after: paperE2eState.cash,
        }),
      });
    }

    if (path === "/api/paper/account/reset" && req.method() === "POST") {
      paperE2eState = createPaperE2eState();
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, cash: paperE2eState.cash }),
      });
    }

    if (path === "/api/watchlist/items" && req.method() === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ watchlist_id: 1, items: watchlistE2eItems.map((x) => ({ ...x })) }),
      });
    }

    if (path === "/api/watchlist/items" && req.method() === "POST") {
      let body = {};
      try {
        body = req.postDataJSON() || {};
      } catch {
        body = {};
      }
      const code = String(body.code || "").trim().toLowerCase();
      if (!code || !/^(sh|sz|bj)\./i.test(code)) {
        return route.fulfill({
          status: 400,
          contentType: "application/json",
          body: JSON.stringify({ detail: "bad code" }),
        });
      }
      if (watchlistE2eItems.some((x) => x.code === code)) {
        return route.fulfill({
          status: 409,
          contentType: "application/json",
          body: JSON.stringify({ detail: "已在自选中" }),
        });
      }
      watchlistE2eItems.push({
        code,
        name: code === "sh.600000" ? "Pudong-mock" : null,
        created_at: new Date().toISOString(),
      });
      return route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, code }),
      });
    }

    if (path.startsWith("/api/watchlist/items/") && req.method() === "DELETE") {
      const raw = path.slice("/api/watchlist/items/".length);
      const code = decodeURIComponent(raw || "").trim().toLowerCase();
      const idx = watchlistE2eItems.findIndex((x) => x.code === code);
      if (idx < 0) {
        return route.fulfill({
          status: 404,
          contentType: "application/json",
          body: JSON.stringify({ detail: "自选无此代码" }),
        });
      }
      watchlistE2eItems.splice(idx, 1);
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, code }),
      });
    }

    if (path === "/api/factors/catalog" && req.method() === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: E2E_FACTOR_CATALOG_BODY,
      });
    }

    if (path === "/api/factors/preview" && req.method() === "GET") {
      const code = (url.searchParams.get("code") || "sh.000001").trim().toLowerCase();
      const op = (url.searchParams.get("op") || "rolling_mean").trim();
      const col = (url.searchParams.get("column") || "close").trim();
      const winRaw = url.searchParams.get("window");
      let windowVal;
      if (op === "pct_change_1" || op === "macd" || op === "obv") {
        windowVal = null;
      } else if (op === "vwap") {
        if (winRaw == null || winRaw === "") {
          windowVal = null;
        } else {
          const parsed = parseInt(winRaw, 10);
          windowVal = Number.isFinite(parsed) && parsed >= 1 ? Math.min(500, parsed) : null;
        }
      } else {
        windowVal = Math.min(500, Math.max(1, parseInt(winRaw || "5", 10) || 5));
      }
      const lim = Math.min(5000, Math.max(30, parseInt(url.searchParams.get("limit") || "500", 10) || 500));
      const bbKRaw = url.searchParams.get("bb_k");
      const kk = Math.min(
        12,
        Math.max(0.25, parseFloat(bbKRaw != null && bbKRaw !== "" ? bbKRaw : "2") || 2)
      );
      const mf = Math.min(200, Math.max(1, parseInt(url.searchParams.get("macd_fast") || "12", 10) || 12));
      const ms = Math.min(200, Math.max(1, parseInt(url.searchParams.get("macd_slow") || "26", 10) || 26));
      const sg = Math.min(200, Math.max(1, parseInt(url.searchParams.get("macd_signal") || "9", 10) || 9));
      const trade_dates = [];
      const valueSeries = [];
      const upper = [];
      const lower = [];
      const dif = [];
      const dea = [];
      const hist = [];
      const kdjK = [];
      const kdjD = [];
      const kdjJ = [];
      const adxPlus = [];
      const adxMinus = [];
      const adxLine = [];
      const aroonUp = [];
      const aroonDown = [];
      const aroonOsc = [];
      const dcUpper = [];
      const dcMid = [];
      const dcLower = [];
      const km1 = Math.min(30, Math.max(1, parseInt(url.searchParams.get("kdj_m1") || "3", 10) || 3));
      const km2 = Math.min(30, Math.max(1, parseInt(url.searchParams.get("kdj_m2") || "3", 10) || 3));
      let vwapCumPv = 0;
      let vwapCumV = 0;
      for (let i = 0; i < 20; i++) {
        const d = new Date(Date.UTC(2024, 3, 1 + i));
        trade_dates.push(d.toISOString().slice(0, 10));
        if (op === "atr") {
          valueSeries.push(i < (windowVal ?? 5) ? null : 0.5 + i * 0.02);
        } else if (op === "bollinger") {
          const wv = windowVal ?? 5;
          const m = i < wv ? null : 100 + i * 0.1;
          valueSeries.push(m);
          if (m == null) {
            upper.push(null);
            lower.push(null);
          } else {
            const sp = 0.4 + (i % 3) * 0.1;
            upper.push(m + kk * sp);
            lower.push(m - kk * sp);
          }
        } else if (op === "macd") {
          const di = i * 0.01 - 0.05;
          const de = i * 0.008 - 0.04;
          dif.push(di);
          dea.push(de);
          hist.push(di - de);
        } else if (op === "kdj") {
          const wv = windowVal ?? 5;
          if (i < wv - 1) {
            kdjK.push(null);
            kdjD.push(null);
            kdjJ.push(null);
          } else {
            const kv = 50 + i * 0.4;
            const dv = 49 + i * 0.35;
            kdjK.push(kv);
            kdjD.push(dv);
            kdjJ.push(3 * kv - 2 * dv);
          }
        } else if (op === "cci") {
          const wv = windowVal ?? 5;
          valueSeries.push(i < wv - 1 ? null : -80 + i * 12);
        } else if (op === "williams_r") {
          const wv = windowVal ?? 5;
          valueSeries.push(i < wv - 1 ? null : -20 - (i % 5) * 8);
        } else if (op === "mfi") {
          const wv = windowVal ?? 5;
          valueSeries.push(i < wv ? null : 35 + (i % 7) * 8);
        } else if (op === "roc") {
          const wv = windowVal ?? 5;
          valueSeries.push(i < wv ? null : -2.0 + i * 0.35);
        } else if (op === "trix") {
          valueSeries.push(i === 0 ? null : -0.05 + i * 0.012);
        } else if (op === "adx") {
          const wv = windowVal ?? 5;
          const firstDi = wv - 1;
          const firstAdx = 2 * wv - 2;
          if (i < firstDi) {
            adxPlus.push(null);
            adxMinus.push(null);
          } else {
            adxPlus.push(22 + i * 0.6);
            adxMinus.push(18 + (i % 3) * 0.4);
          }
          if (i < firstAdx) adxLine.push(null);
          else adxLine.push(20 + i * 0.15);
        } else if (op === "aroon") {
          const wv = windowVal ?? 5;
          const first = wv - 1;
          if (i < first) {
            aroonUp.push(null);
            aroonDown.push(null);
            aroonOsc.push(null);
          } else {
            aroonUp.push(55 + i * 1.2);
            aroonDown.push(40 + (i % 4) * 2);
            aroonOsc.push(15 + i * 0.5);
          }
        } else if (op === "donchian") {
          const wv = windowVal ?? 20;
          const first = wv - 1;
          if (i < first) {
            dcUpper.push(null);
            dcMid.push(null);
            dcLower.push(null);
          } else {
            const u = 100 + i;
            const lo = 90 + i;
            dcUpper.push(u);
            dcLower.push(lo);
            dcMid.push((u + lo) / 2);
          }
        } else if (op === "vwap") {
          const hi = 10 + i * 0.1;
          const lo = 9.5 + i * 0.1;
          const cl = 10.2 + i * 0.1;
          const vol = 1000 + i * 10;
          const tp = (hi + lo + cl) / 3;
          if (windowVal == null) {
            vwapCumPv += tp * vol;
            vwapCumV += vol;
            valueSeries.push(vwapCumV > 0 ? vwapCumPv / vwapCumV : null);
          } else {
            const wv = windowVal;
            if (i < wv - 1) {
              valueSeries.push(null);
            } else {
              let spv = 0;
              let sv = 0;
              for (let j = i - wv + 1; j <= i; j++) {
                const hj = 10 + j * 0.1;
                const lj = 9.5 + j * 0.1;
                const cj = 10.2 + j * 0.1;
                const vj = 1000 + j * 10;
                const tj = (hj + lj + cj) / 3;
                spv += tj * vj;
                sv += vj;
              }
              valueSeries.push(sv > 0 ? spv / sv : null);
            }
          }
        } else if (op === "obv") {
          if (i === 0) valueSeries.push(1000);
          else valueSeries.push(valueSeries[i - 1] + (i % 2 === 1 ? 200 : -120));
        } else {
          valueSeries.push(i < 4 ? null : 10 + i * 0.1);
        }
      }
      const rf = (url.searchParams.get("response_format") || "json").toLowerCase();
      if (rf === "csv") {
        let rows;
        if (op === "bollinger") rows = ["trade_date,mid,upper,lower"];
        else if (op === "macd") rows = ["trade_date,dif,dea,hist"];
        else if (op === "kdj") rows = ["trade_date,k,d,j"];
        else if (op === "adx") rows = ["trade_date,plus_di,minus_di,adx"];
        else if (op === "aroon") rows = ["trade_date,aroon_up,aroon_down,aroon_osc"];
        else if (op === "donchian") rows = ["trade_date,dc_upper,dc_mid,dc_lower"];
        else rows = ["trade_date,value"];
        for (let i = 0; i < trade_dates.length; i++) {
          if (op === "bollinger") {
            const v = valueSeries[i];
            const u = upper[i];
            const lo = lower[i];
            rows.push(
              `${trade_dates[i]},${v == null ? "" : String(v)},${u == null ? "" : String(u)},${lo == null ? "" : String(lo)}`
            );
          } else if (op === "macd") {
            rows.push(
              `${trade_dates[i]},${String(dif[i])},${String(dea[i])},${String(hist[i])}`
            );
          } else if (op === "kdj") {
            const kv = kdjK[i];
            const dv = kdjD[i];
            const jv = kdjJ[i];
            rows.push(
              `${trade_dates[i]},${kv == null ? "" : String(kv)},${dv == null ? "" : String(dv)},${jv == null ? "" : String(jv)}`
            );
          } else if (op === "adx") {
            const pv = adxPlus[i];
            const mv = adxMinus[i];
            const av = adxLine[i];
            rows.push(
              `${trade_dates[i]},${pv == null ? "" : String(pv)},${mv == null ? "" : String(mv)},${av == null ? "" : String(av)}`
            );
          } else if (op === "aroon") {
            const u = aroonUp[i];
            const dn = aroonDown[i];
            const o = aroonOsc[i];
            rows.push(
              `${trade_dates[i]},${u == null ? "" : String(u)},${dn == null ? "" : String(dn)},${o == null ? "" : String(o)}`
            );
          } else if (op === "donchian") {
            const uu = dcUpper[i];
            const mm = dcMid[i];
            const ll = dcLower[i];
            rows.push(
              `${trade_dates[i]},${uu == null ? "" : String(uu)},${mm == null ? "" : String(mm)},${ll == null ? "" : String(ll)}`
            );
          } else {
            const v = valueSeries[i];
            rows.push(`${trade_dates[i]},${v == null ? "" : String(v)}`);
          }
        }
        const csvBody = `\ufeff${rows.join("\n")}\n`;
        const safe = code.replace(/[/\\]/g, "_");
        return route.fulfill({
          status: 200,
          contentType: "text/csv; charset=utf-8",
          headers: {
            "Content-Disposition": `attachment; filename="${safe}_${col}_${op}.csv"`,
          },
          body: csvBody,
        });
      }
      const note =
        op === "atr"
          ? "e2e-mock-factors-preview-atr"
          : op === "bollinger"
            ? "e2e-mock-factors-preview-bollinger"
            : op === "macd"
              ? "e2e-mock-factors-preview-macd"
              : op === "kdj"
                ? "e2e-mock-factors-preview-kdj"
                : op === "cci"
                  ? "e2e-mock-factors-preview-cci"
                  : op === "williams_r"
                    ? "e2e-mock-factors-preview-williams-r"
                    : op === "mfi"
                      ? "e2e-mock-factors-preview-mfi"
                      : op === "roc"
                        ? "e2e-mock-factors-preview-roc"
                        : op === "trix"
                          ? "e2e-mock-factors-preview-trix"
                          : op === "adx"
                            ? "e2e-mock-factors-preview-adx"
                            : op === "aroon"
                              ? "e2e-mock-factors-preview-aroon"
                              : op === "donchian"
                                ? "e2e-mock-factors-preview-donchian"
                                : op === "vwap"
                                  ? "e2e-mock-factors-preview-vwap"
                                  : op === "obv"
                                    ? "e2e-mock-factors-preview-obv"
                                    : "e2e-mock-factors-preview";
      let series;
      let meta;
      if (op === "bollinger") {
        series = { mid: valueSeries, upper, lower };
        meta = { bb_k: kk };
      } else if (op === "macd") {
        series = { dif, dea, hist };
        meta = { fast: mf, slow: ms, signal: sg };
      } else if (op === "kdj") {
        series = { k: kdjK, d: kdjD, j: kdjJ };
        meta = { n: windowVal ?? 5, m1: km1, m2: km2 };
      } else if (op === "adx") {
        series = { plus_di: adxPlus, minus_di: adxMinus, adx: adxLine };
        meta = { period: windowVal ?? 5 };
      } else if (op === "aroon") {
        series = { aroon_up: aroonUp, aroon_down: aroonDown, aroon_osc: aroonOsc };
        meta = { period: windowVal ?? 5 };
      } else if (op === "donchian") {
        series = { dc_upper: dcUpper, dc_mid: dcMid, dc_lower: dcLower };
        meta = { period: windowVal ?? 20 };
      } else if (op === "vwap") {
        series = { value: valueSeries };
        meta =
          windowVal == null ? { mode: "cumulative" } : { mode: "rolling", period: windowVal };
      } else {
        series = { value: valueSeries };
        meta = null;
      }
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          code,
          column: col,
          op,
          window: windowVal,
          limit: lim,
          bars: 20,
          trade_dates,
          series,
          meta,
          note,
        }),
      });
    }

    if (path === "/api/dashboard/turnover") {
      const td = url.searchParams.get("trade_date");
      const stocks = td
        ? [
            {
              code: "bj.430047",
              name: `mock-按日-${td}`,
              price: 10.12,
              volume: 1_000_000,
              amount: 9_500_000,
            },
          ]
        : [
            {
              code: "sh.600000",
              name: "浦发银行（成交额 mock）",
              price: 8.55,
              volume: 120_000_000,
              amount: 210_000_000,
            },
            {
              code: "sz.000001",
              name: "平安银行（成交额 mock）",
              price: 11.2,
              volume: 95_000_000,
              amount: 1_800_000_000,
            },
          ];
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ stocks }),
      });
    }

    return route.fulfill({
      status: 404,
      contentType: "text/plain",
      body: `e2e: no mock for ${path}`,
    });
  });
}

/** @param {string} code @param {number} n */
function synthKlines(code, n) {
  const out = [];
  let p = 3000;
  for (let i = 0; i < n; i++) {
    const d = new Date(Date.UTC(2024, 0, 2 + i));
    const td = d.toISOString().slice(0, 10);
    const o = +(p - 2 + (i % 3)).toFixed(2);
    const c = +(p + (i % 5) - 2).toFixed(2);
    const h = +(Math.max(o, c) + 4).toFixed(2);
    const l = +(Math.min(o, c) - 3).toFixed(2);
    out.push({
      code,
      trade_date: td,
      open: o,
      high: h,
      low: l,
      close: c,
      volume: 1_000_000 + i * 10_000,
      amount: 5e8 + i * 1e6,
      pct_change: 0.5,
    });
    p = c;
  }
  return out;
}
