<script setup>
import { computed, onMounted, ref, watch } from "vue";
import JSZip from "jszip";
import VChart from "vue-echarts";
import { apiUrl, fetchJson } from "../composables/api.js";

/** 单次 ZIP 内最多包含的存档条数（避免浏览器内存压力过大） */
const ZIP_EXPORT_MAX = 50;

const LS_RUNS_LIMIT_KEY = "tb_backtest_runs_limit";
/** 策略回测「异步 job」勾选；E2E 会清掉以保证默认同步 */
const LS_MVP_ASYNC_KEY = "tb_backtest_mvp_async";
/** 单标的页：双均线 vs 买入持有；刷新后保留 */
const LS_SINGLE_RUN_STRATEGY_KEY = "tb_backtest_single_strategy";

/** 异步 202 后至轮询结束前的 job_id，用于「取消排队」 */
const mvpAsyncInFlightJobId = ref("");
const mvpAsyncCancelMsg = ref("");

function readStoredRunHistoryLimit() {
  try {
    const raw = localStorage.getItem(LS_RUNS_LIMIT_KEY);
    const n = parseInt(raw, 10);
    if (n === 10 || n === 30 || n === 50) return n;
  } catch {
    /* ignore */
  }
  return 30;
}

function readStoredMvpAsync() {
  try {
    return localStorage.getItem(LS_MVP_ASYNC_KEY) === "1";
  } catch {
    return false;
  }
}

function readStoredSingleRunStrategy() {
  try {
    const v = localStorage.getItem(LS_SINGLE_RUN_STRATEGY_KEY);
    if (v === "buy_hold" || v === "ma_cross") return v;
  } catch {
    /* ignore */
  }
  return "ma_cross";
}

const props = defineProps({
  code: { type: String, default: "sh.000001" },
});

const emit = defineEmits(["open-paper", "select-code"]);

function emitOpenPaper() {
  const c = (props.code || "").trim();
  if (!c) return;
  emit("open-paper", { code: c, quantity: 100 });
}

/** 单标的 | 批量扫描 */
const innerTab = ref("single");
/** 单标的页：POST /run 的 strategy_id（批量扫描仍为 ma_cross_scan） */
const singleRunStrategy = ref(readStoredSingleRunStrategy());

const fast = ref(5);
const slow = ref(20);
const limit = ref(500);
/** 万分之几 */
const feeWan = ref(0);
const slipWan = ref(0);
/** 可选日 K 过滤（含），单标的与批量扫描共用 → API start_date / end_date */
const tradeStartDate = ref("");
const tradeEndDate = ref("");
/** 可选：β/α 对基准日收益回归（如 sh.000300），留空则为对标的自身日收益 */
const benchmarkCode = ref("");

const loading = ref(false);
const error = ref("");
const result = ref(null);

const scanCodesText = ref("sh.000001\nsh.000300\nsz.399001");
/** 批量扫描排序：与 API sort_by 一致 */
const scanSortBy = ref("total_return");
const scanMaxConcurrent = ref(8);
const scanLoading = ref(false);
const scanCsvLoading = ref(false);
const scanError = ref("");
const scanResult = ref(null);
const wlItems = ref([]);

/** POST /run?async=1 并轮询 GET …/jobs/{id}；结果 JSON 与同步 200 同形；轮询体含 async_job_persistence（与 catalog 同源） */
const mvpAsyncRun = ref(readStoredMvpAsync());

const PRESET_MAJORS = "sh.000001\nsz.399001\nsz.399006\nsh.000300";
/** 与扫描 API max_codes 上限一致，避免填入过多被拒 */
const SCAN_CODES_FROM_WL_MAX = 40;

const signalSnap = ref(null);
const signalErr = ref("");

/** 策略目录 / 试算信号（POST /api/strategies/signal，与 GET ma-cross/signal 等价） */
/** 策略目录 JSON（HTML，含 <mark> 高亮；仅展示） */
const strategyCatalogHtml = ref("");
const strategySignalTrialText = ref("");
const strategyContractBusy = ref(false);
const strategyContractMsg = ref("");

/** GET /api/backtest/catalog — 与 POST /run 已注册策略对齐 */
const backtestCatalog = ref(null);
const backtestCatalogErr = ref("");
const backtestCatalogLoading = ref(true);

const backtestCatalogLine = computed(() => {
  const b = backtestCatalog.value;
  if (!b?.engine_version || !Array.isArray(b.strategies)) return "";
  const parts = b.strategies.map(
    (s) => `${s.title}（${s.strategy_id} v${s.strategy_version}）`,
  );
  let line = `engine ${b.engine_version} · ${parts.join(" · ")}`;
  const qp = b.async_run_query_param;
  const tmpl = b.async_job_status_path_template;
  if (typeof qp === "string" && qp.trim() && typeof tmpl === "string" && tmpl.includes("{job_id}")) {
    line += ` · 异步 ?${qp.trim()}=1 → ${tmpl.trim()}`;
  }
  const persist = b.async_job_persistence;
  if (persist === "redis") {
    line += " · 异步任务 Redis 队列";
    const d = b.async_job_queue_depth;
    if (typeof d === "number" && Number.isFinite(d)) {
      line += `（待消费 ${d}）`;
    }
  } else if (persist === "memory") {
    line += " · 异步任务进程内存";
  }
  return line;
});

const backtestCatalogTitleHint = computed(() => {
  const b = backtestCatalog.value;
  if (!b?.strategies?.length) return "";
  return b.strategies.map((s) => `${s.strategy_id}: ${s.description}`).join("\n\n");
});

/** 存档列表 kind 筛选：与 GET /runs?kind= 一致；选项文案来自 catalog（失败时用内置） */
const archiveKindFilterOptions = computed(() => {
  const b = backtestCatalog.value;
  if (!b?.strategies?.length) {
    return [
      { value: "ma_cross_single", label: "单标的（存档 kind=ma_cross_single）" },
      { value: "buy_hold_single", label: "买入持有（存档 kind=buy_hold_single）" },
      { value: "ma_cross_scan", label: "批量扫描（存档 kind=ma_cross_scan）" },
    ];
  }
  return b.strategies.map((s) => ({
    value: String(s.archive_kind || ""),
    label: `${s.title} — 存档 kind=${s.archive_kind} — POST /run ${s.strategy_id} v${s.strategy_version}`,
  }));
});

const runKindMapHint = computed(() => {
  const b = backtestCatalog.value;
  if (!b?.strategies?.length) return "";
  return b.strategies
    .map(
      (s) =>
        `GET /api/backtest/runs?kind=${s.archive_kind} ↔ POST /api/backtest/run（strategy_id=${s.strategy_id}，v${s.strategy_version}）`,
    )
    .join(" · ");
});

async function loadBacktestEngineCatalog() {
  backtestCatalogErr.value = "";
  backtestCatalogLoading.value = true;
  try {
    const res = await fetch(apiUrl("backtest/catalog"));
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      const d = body?.detail;
      backtestCatalogErr.value =
        typeof d === "string"
          ? d
          : Array.isArray(d)
            ? d.map((x) => x?.msg || JSON.stringify(x)).join("; ")
            : `HTTP ${res.status}`;
      return;
    }
    if (!body?.engine_version || !Array.isArray(body.strategies)) {
      backtestCatalogErr.value = "策略目录格式异常";
      return;
    }
    backtestCatalog.value = body;
  } catch (e) {
    backtestCatalogErr.value = e?.message || "无法加载策略目录";
  } finally {
    backtestCatalogLoading.value = false;
  }
}

const saveRunTip = ref("");
const runHistory = ref([]);
const runHistoryTotal = ref(0);
const runHistoryLoading = ref(false);
/** 存档列表筛选：'' 全部 | ma_cross_single | buy_hold_single | ma_cross_scan */
const runHistoryKindFilter = ref("");
/** 每页条数（与 GET /api/backtest/runs limit 一致；写入 localStorage） */
const runHistoryLimit = ref(readStoredRunHistoryLimit());
const runHistoryOffset = ref(0);
/** 跳转页码输入（与列表同步） */
const runHistoryJumpPage = ref("1");
/** 已生效的摘要搜索子串（与 GET q 一致） */
const runHistorySearchApplied = ref("");
/** 搜索框草稿 */
const runHistorySearchInput = ref("");
const selectedRunDetail = ref(null);
const selectedRunLoading = ref(false);
/** 列表行「导出」拉取详情时的 id，用于按钮 loading */
const exportRunIdBusy = ref(null);
/** 列表多选：准备批量 ZIP 的存档 id */
const runArchiveSelectedIds = ref([]);
const runZipBusy = ref(false);
const batchDeleteBusy = ref(false);

const runArchivePageAllChecked = computed(() => {
  const pageIds = runHistory.value.map((r) => r.id);
  if (!pageIds.length) return false;
  const sel = new Set(runArchiveSelectedIds.value);
  return pageIds.every((id) => sel.has(id));
});

const runHistoryHasPrev = computed(() => runHistoryOffset.value > 0);

const runHistoryHasNext = computed(
  () => runHistoryOffset.value + runHistory.value.length < runHistoryTotal.value
);

const runHistoryRangeLabel = computed(() => {
  const t = runHistoryTotal.value;
  if (t <= 0) return "";
  if (!runHistory.value.length) return `共 ${t} 条`;
  const from = runHistoryOffset.value + 1;
  const to = runHistoryOffset.value + runHistory.value.length;
  return `第 ${from}–${to} 条，共 ${t} 条`;
});

const runHistoryTotalPages = computed(() => {
  const t = runHistoryTotal.value;
  const lim = runHistoryLimit.value;
  if (t <= 0 || lim <= 0) return 1;
  return Math.max(1, Math.ceil(t / lim));
});

const runHistorySearchClearDisabled = computed(
  () => !runHistorySearchApplied.value && !(runHistorySearchInput.value || "").trim()
);

const feeRate = computed(() => Math.max(0, Number(feeWan.value) || 0) / 10000);
const slipRate = computed(() => Math.max(0, Number(slipWan.value) || 0) / 10000);

const benchSortBetaLabel = computed(() =>
  (benchmarkCode.value || "").trim() ? "β（对基准）" : "β（对标的）"
);
const benchSortAlphaLabel = computed(() =>
  (benchmarkCode.value || "").trim() ? "α 年化 %（对基准）" : "α 年化 %（对标的）"
);

const chartOption = computed(() => {
  const curve = result.value?.equity_curve;
  if (!curve?.length) {
    return {
      backgroundColor: "transparent",
      title: {
        text: loading.value ? "计算中…" : error.value || "运行回测后显示权益曲线",
        left: "center",
        top: "center",
        textStyle: { color: "#6d6a7a", fontSize: 13, fontFamily: "Noto Serif SC" },
      },
    };
  }
  const dates = curve.map((p) => p.trade_date);
  const eq = curve.map((p) => p.equity);
  return {
    backgroundColor: "transparent",
    animationDuration: 500,
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(8, 8, 12, 0.94)",
      borderColor: "rgba(232, 197, 71, 0.28)",
      textStyle: { color: "#b8b4c8", fontFamily: "IBM Plex Mono, monospace" },
    },
    grid: { left: "3%", right: "4%", top: "12%", bottom: "14%", containLabel: true },
    xAxis: {
      type: "category",
      data: dates,
      axisLine: { lineStyle: { color: "#2a2835" } },
      axisLabel: { color: "#6d6a7a", fontSize: 9, fontFamily: "IBM Plex Mono", rotate: 32 },
    },
    yAxis: {
      scale: true,
      position: "right",
      axisLine: { lineStyle: { color: "#2a2835" } },
      axisLabel: { color: "#6d6a7a", fontSize: 10, fontFamily: "IBM Plex Mono" },
      splitLine: { lineStyle: { color: "#1a1824" } },
    },
    series: [
      {
        name: "权益",
        type: "line",
        data: eq,
        smooth: true,
        symbol: "none",
        lineStyle: { width: 1.6, color: "#3ee0ff" },
        areaStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: "rgba(62, 224, 255, 0.22)" },
              { offset: 1, color: "rgba(62, 224, 255, 0)" },
            ],
          },
        },
      },
    ],
  };
});

function commonParams() {
  const p = new URLSearchParams({
    fast: String(fast.value),
    slow: String(slow.value),
    limit: String(limit.value),
    commission_rate: String(feeRate.value),
    slippage_rate: String(slipRate.value),
  });
  const s = (tradeStartDate.value || "").trim();
  const e = (tradeEndDate.value || "").trim();
  if (s) p.set("start_date", s);
  if (e) p.set("end_date", e);
  const b = (benchmarkCode.value || "").trim().toLowerCase();
  if (b) p.set("benchmark_code", b);
  return p;
}

function tradeRangeInvalidMsg() {
  const s = (tradeStartDate.value || "").trim();
  const e = (tradeEndDate.value || "").trim();
  if (s && e && s > e) return "起始日不能晚于结束日";
  return "";
}

/** 扫描 / CSV 下载在 common 基础上附加排序与并发 */
function scanQueryParams() {
  const p = commonParams();
  p.set("sort_by", scanSortBy.value);
  p.set("max_concurrent", String(Math.max(1, Math.min(20, Number(scanMaxConcurrent.value) || 8))));
  return p;
}

/** 与 POST /api/backtest/run（strategy_id=ma_cross_scan）的 params 一致；用于预览与存档 request_params */
function scanRunParamsObject(codesRaw) {
  const qp = Object.fromEntries(commonParams().entries());
  const fast = parseInt(qp.fast, 10);
  const slow = parseInt(qp.slow, 10);
  const lim = parseInt(qp.limit, 10);
  const commission_rate = Number(qp.commission_rate);
  const slippage_rate = Number(qp.slippage_rate);
  const maxConcurrent = Math.max(1, Math.min(20, Number(scanMaxConcurrent.value) || 8));
  const out = {
    codes: codesRaw,
    fast,
    slow,
    limit: lim,
    commission_rate,
    slippage_rate,
    max_codes: SCAN_CODES_FROM_WL_MAX,
    sort_by: String(scanSortBy.value || "total_return"),
    max_concurrent: maxConcurrent,
  };
  const s = (qp.start_date || "").trim();
  const e = (qp.end_date || "").trim();
  if (s) out.start_date = s;
  if (e) out.end_date = e;
  const b = (qp.benchmark_code || "").trim().toLowerCase();
  if (b) out.benchmark_code = b;
  return out;
}

function scanRunMvpEnvelope(codesRaw) {
  return {
    strategy_id: "ma_cross_scan",
    strategy_version: "1",
    params: scanRunParamsObject(codesRaw),
  };
}

const SORT_BY_LABELS_SELF = {
  total_return: "策略收益",
  excess_return: "超额",
  sharpe: "夏普",
  buy_hold: "买入持有",
  ann_return: "年化收益",
  sortino: "Sortino",
  calmar: "Calmar",
  win_rate: "胜率(额权)",
  avg_holding: "均段收益",
  underlying_beta: "β(标的)",
  underlying_alpha: "α年化%",
};

const SORT_BY_LABELS_BENCH = {
  ...SORT_BY_LABELS_SELF,
  underlying_beta: "β(基准)",
  underlying_alpha: "α年化%(基准)",
};

const sortByLabels = computed(() =>
  (benchmarkCode.value || "").trim() ? SORT_BY_LABELS_BENCH : SORT_BY_LABELS_SELF
);

function scanSortLabel(sortBy) {
  return sortByLabels.value[sortBy] || sortBy || "—";
}

/** API 小数费率 → 万分之展示 */
function wanFromRate(r) {
  const n = Number(r);
  if (r == null || Number.isNaN(n)) return "—";
  return (n * 10000).toFixed(2);
}

function downloadSingleJson() {
  if (!result.value) return;
  const text = JSON.stringify(result.value, null, 2);
  const blob = new Blob([text], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  const tag = singleRunStrategy.value === "buy_hold" ? "buy_hold" : "ma_cross";
  a.download = `${tag}_${(props.code || "code").replace(/[^a-z0-9.]/gi, "_")}_${Date.now()}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

function downloadScanJson() {
  if (!scanResult.value?.items?.length) return;
  const text = JSON.stringify(scanResult.value, null, 2);
  const blob = new Blob([text], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `ma_cross_scan_${Date.now()}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

function cloneJson(obj) {
  try {
    return structuredClone(obj);
  } catch {
    return JSON.parse(JSON.stringify(obj));
  }
}

/** 与 POST /api/backtest/run（strategy_id=ma_cross）的 params 一致 */
function maCrossSingleRunParamsObject(code) {
  const qp = Object.fromEntries(commonParams().entries());
  const fastN = parseInt(qp.fast, 10);
  const slowN = parseInt(qp.slow, 10);
  const lim = parseInt(qp.limit, 10);
  const commission_rate = Number(qp.commission_rate);
  const slippage_rate = Number(qp.slippage_rate);
  const out = {
    code: String(code || "").trim(),
    fast: fastN,
    slow: slowN,
    limit: lim,
    commission_rate,
    slippage_rate,
  };
  const s = (qp.start_date || "").trim();
  const e = (qp.end_date || "").trim();
  if (s) out.start_date = s;
  if (e) out.end_date = e;
  const b = (qp.benchmark_code || "").trim().toLowerCase();
  if (b) out.benchmark_code = b;
  return out;
}

/** 与 POST /api/backtest/run（strategy_id=buy_hold）的 params 一致（无 fast/slow） */
function buyHoldSingleRunParamsObject(code) {
  const lim = Math.max(30, Math.min(5000, Number(limit.value) || 500));
  const commission_rate = feeRate.value;
  const slippage_rate = slipRate.value;
  const out = {
    code: String(code || "").trim(),
    limit: lim,
    commission_rate,
    slippage_rate,
  };
  const s = (tradeStartDate.value || "").trim();
  const e = (tradeEndDate.value || "").trim();
  if (s) out.start_date = s;
  if (e) out.end_date = e;
  const b = (benchmarkCode.value || "").trim().toLowerCase();
  if (b) out.benchmark_code = b;
  return out;
}

function singleRunArchiveKind() {
  return singleRunStrategy.value === "buy_hold" ? "buy_hold_single" : "ma_cross_single";
}

function singleRunMvpEnvelope(code) {
  if (singleRunStrategy.value === "buy_hold") {
    return {
      strategy_id: "buy_hold",
      strategy_version: "1",
      params: buyHoldSingleRunParamsObject(code),
    };
  }
  return {
    strategy_id: "ma_cross",
    strategy_version: "1",
    params: maCrossSingleRunParamsObject(code),
  };
}

function mvpHttpErrorMessage(status, statusText, jsonBody) {
  const d = jsonBody?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => x?.msg || JSON.stringify(x)).join("; ");
  if (status === 503) return "服务暂不可用";
  return `${status} ${statusText || ""}`.trim();
}

function sleepMvp(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

const MVP_DEFAULT_ASYNC_QPARAM = "async";
const MVP_DEFAULT_JOB_TEMPLATE = "/api/backtest/jobs/{job_id}";

/** 与 GET /api/backtest/catalog.async_run_query_param 一致；catalog 未载时用默认 */
function mvpCatalogAsyncQueryParam() {
  const b = backtestCatalog.value;
  const q = typeof b?.async_run_query_param === "string" ? b.async_run_query_param.trim() : "";
  return q || MVP_DEFAULT_ASYNC_QPARAM;
}

/** 与 catalog.async_job_status_path_template 一致 */
function mvpCatalogJobStatusTemplate() {
  const b = backtestCatalog.value;
  const t =
    typeof b?.async_job_status_path_template === "string" ? b.async_job_status_path_template.trim() : "";
  return t || MVP_DEFAULT_JOB_TEMPLATE;
}

/**
 * 将 catalog 中的绝对路径模板转为 apiUrl 用的相对 path（去掉 /api/ 前缀），并替换 {job_id}。
 */
function mvpJobStatusFetchPath(jobId) {
  const id = String(jobId || "").trim();
  const enc = encodeURIComponent(id);
  let tmpl = mvpCatalogJobStatusTemplate();
  if (!tmpl.includes("{job_id}")) {
    tmpl = MVP_DEFAULT_JOB_TEMPLATE;
  }
  let rel = tmpl.startsWith("/api/") ? tmpl.slice(5) : tmpl.replace(/^\/+/, "");
  rel = rel.split("{job_id}").join(enc);
  return rel;
}

function mvpAsyncPostRunSearch() {
  const qp = encodeURIComponent(mvpCatalogAsyncQueryParam());
  return `${qp}=1`;
}

/** 勾选说明：与当前 catalog（或默认）一致的 query 名与轮询路径模板 */
const mvpAsyncUiCatalogBits = computed(() => ({
  qp: mvpCatalogAsyncQueryParam(),
  pollTmpl: mvpCatalogJobStatusTemplate(),
}));

/** POST /api/backtest/run；同步 200 或异步 202 + 轮询 jobs，返回 MVP 根对象（含 result / scan_result） */
async function postMvpRunResolve(envelope) {
  if (!mvpAsyncRun.value) {
    return await fetchJson("backtest/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(envelope),
    });
  }
  const aq = mvpCatalogAsyncQueryParam();
  const res = await fetch(apiUrl(`backtest/run?${mvpAsyncPostRunSearch()}`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(envelope),
  });
  const body = await res.json().catch(() => ({}));
  if (res.status === 429) {
    throw new Error("请求过于频繁，请稍后再试");
  }
  if (res.status === 400 || res.status === 422) {
    throw new Error(mvpHttpErrorMessage(res.status, res.statusText, body));
  }
  if (!res.ok) {
    throw new Error(mvpHttpErrorMessage(res.status, res.statusText, body));
  }
  if (res.status !== 202) {
    throw new Error(
      res.status === 200
        ? `服务端返回同步 200：可能未启用 ?${aq}=1；请取消勾选「异步 job」或检查网关`
        : `异步模式期望 HTTP 202，实际 ${res.status}`
    );
  }
  const jobId = body?.job_id;
  if (!jobId || typeof jobId !== "string") {
    throw new Error("异步受理响应缺少 job_id");
  }
  mvpAsyncInFlightJobId.value = jobId;
  try {
    let last = "";
    for (let i = 0; i < 200; i++) {
      const st = await fetchJson(mvpJobStatusFetchPath(jobId));
      last = String(st?.status || "");
      if (last === "completed") {
        const inner = st?.result;
        if (!inner || typeof inner !== "object") {
          throw new Error("任务完成但缺少 result");
        }
        return inner;
      }
      if (last === "failed") {
        throw new Error(String(st?.error || "").trim() || "回测任务失败");
      }
      if (last === "cancelled") {
        throw new Error(String(st?.error || "").trim() || "任务已取消");
      }
      await sleepMvp(40);
    }
    throw new Error(`回测任务未在预期时间内完成（最后状态: ${last || "?"})`);
  } finally {
    mvpAsyncInFlightJobId.value = "";
  }
}

async function cancelMvpAsyncQueuedJob() {
  const id = mvpAsyncInFlightJobId.value?.trim();
  if (!id) return;
  const path = `backtest/jobs/${encodeURIComponent(id)}/cancel`;
  const res = await fetch(apiUrl(path), { method: "POST" });
  const body = await res.json().catch(() => ({}));
  if (res.status === 404) {
    throw new Error(typeof body?.detail === "string" ? body.detail : "任务不存在");
  }
  if (res.status === 409) {
    throw new Error(typeof body?.detail === "string" ? body.detail : "当前状态不可取消");
  }
  if (!res.ok) {
    throw new Error(mvpHttpErrorMessage(res.status, res.statusText, body));
  }
}

async function onCancelMvpAsyncQueued() {
  mvpAsyncCancelMsg.value = "";
  try {
    await cancelMvpAsyncQueuedJob();
    mvpAsyncCancelMsg.value = "已取消排队（若已进入 running 则不可取消）";
  } catch (e) {
    mvpAsyncCancelMsg.value = e?.message || "取消失败";
  }
}

async function persistRun(kind, requestParams, responsePayload) {
  saveRunTip.value = "";
  try {
    const res = await fetch(apiUrl("backtest/runs"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        kind,
        request_params: requestParams,
        response_payload: responsePayload,
      }),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      const d = body?.detail;
      throw new Error(typeof d === "string" ? d : res.statusText || "保存失败");
    }
    saveRunTip.value = `已存档 #${body.id}` + (body.summary ? ` · ${body.summary}` : "");
    await loadRunHistory({ resetPage: true });
  } catch (e) {
    saveRunTip.value = e?.message || "存档失败";
  }
}

function syncRunHistoryJumpField() {
  const t = runHistoryTotal.value;
  const lim = runHistoryLimit.value;
  if (t <= 0 || lim <= 0) {
    runHistoryJumpPage.value = "1";
    return;
  }
  const totalP = Math.max(1, Math.ceil(t / lim));
  const curP = Math.floor(runHistoryOffset.value / lim) + 1;
  runHistoryJumpPage.value = String(Math.min(totalP, Math.max(1, curP)));
}

function applyRunHistorySearch() {
  runHistorySearchApplied.value = (runHistorySearchInput.value || "").trim();
  runHistoryOffset.value = 0;
  void loadRunHistory({ resetPage: false });
}

function clearRunHistorySearch() {
  runHistorySearchApplied.value = "";
  runHistorySearchInput.value = "";
  runHistoryOffset.value = 0;
  void loadRunHistory({ resetPage: false });
}

async function loadRunHistory({ resetPage = false } = {}) {
  if (resetPage) runHistoryOffset.value = 0;
  runHistoryLoading.value = true;
  try {
    const lim = runHistoryLimit.value;
    const params = new URLSearchParams({
      limit: String(lim),
      offset: String(runHistoryOffset.value),
    });
    const k = (runHistoryKindFilter.value || "").trim();
    if (k) params.set("kind", k);
    const sq = (runHistorySearchApplied.value || "").trim();
    if (sq) params.set("q", sq);
    const data = await fetchJson(`backtest/runs?${params.toString()}`);
    runHistory.value = Array.isArray(data?.items) ? data.items : [];
    runHistoryTotal.value = data?.total ?? 0;
    const total = runHistoryTotal.value;
    if (total > 0 && runHistory.value.length === 0 && runHistoryOffset.value > 0) {
      const lastPageStart =
        Math.max(0, Math.ceil(total / lim) - 1) * lim;
      runHistoryOffset.value = lastPageStart;
      return await loadRunHistory({ resetPage: false });
    }
    syncRunHistoryJumpField();
  } catch {
    runHistory.value = [];
    runHistoryTotal.value = 0;
    runHistoryJumpPage.value = "1";
  } finally {
    runHistoryLoading.value = false;
  }
}

function runHistoryPrevPage() {
  const lim = runHistoryLimit.value;
  if (runHistoryOffset.value <= 0) return;
  runHistoryOffset.value = Math.max(0, runHistoryOffset.value - lim);
  void loadRunHistory({ resetPage: false });
}

function runHistoryNextPage() {
  if (!runHistoryHasNext.value) return;
  runHistoryOffset.value += runHistoryLimit.value;
  void loadRunHistory({ resetPage: false });
}

function runHistorySubmitJump() {
  const lim = runHistoryLimit.value;
  const totalP = runHistoryTotalPages.value;
  const raw = String(runHistoryJumpPage.value ?? "").trim();
  const p = parseInt(raw, 10);
  if (!Number.isFinite(p) || p < 1 || p > totalP) {
    saveRunTip.value = `页码须在 1–${totalP} 之间`;
    return;
  }
  saveRunTip.value = "";
  runHistoryOffset.value = (p - 1) * lim;
  void loadRunHistory({ resetPage: false });
}

async function deleteRunArchive(id, ev) {
  ev?.stopPropagation?.();
  ev?.preventDefault?.();
  if (!id || !window.confirm(`删除存档 #${id}？不可恢复。`)) return;
  saveRunTip.value = "";
  try {
    const res = await fetch(apiUrl(`backtest/runs/${id}`), { method: "DELETE" });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      const d = body?.detail;
      throw new Error(typeof d === "string" ? d : "删除失败");
    }
    if (selectedRunDetail.value?.id === id) selectedRunDetail.value = null;
    runArchiveSelectedIds.value = runArchiveSelectedIds.value.filter((x) => x !== id);
    saveRunTip.value = `已删除 #${id}`;
    await loadRunHistory({ resetPage: false });
  } catch (e) {
    saveRunTip.value = e?.message || "删除失败";
  }
}

async function deleteSelectedRunArchives() {
  if (runZipBusy.value) return;
  const ids = [...runArchiveSelectedIds.value].sort((a, b) => a - b);
  if (!ids.length) return;
  if (!window.confirm(`确定删除已选的 ${ids.length} 条存档？不可恢复。`)) return;
  saveRunTip.value = "";
  batchDeleteBusy.value = true;
  const concurrency = 6;
  let ok = 0;
  let fail = 0;
  try {
    for (let i = 0; i < ids.length; i += concurrency) {
      const slice = ids.slice(i, i + concurrency);
      const results = await Promise.all(
        slice.map(async (rid) => {
          try {
            const res = await fetch(apiUrl(`backtest/runs/${rid}`), { method: "DELETE" });
            if (!res.ok) {
              const body = await res.json().catch(() => ({}));
              const d = body?.detail;
              return { id: rid, ok: false, err: typeof d === "string" ? d : res.statusText };
            }
            return { id: rid, ok: true, err: null };
          } catch (e) {
            return { id: rid, ok: false, err: e?.message || "网络错误" };
          }
        })
      );
      for (const r of results) {
        if (r.ok) {
          ok++;
          if (selectedRunDetail.value?.id === r.id) selectedRunDetail.value = null;
          runArchiveSelectedIds.value = runArchiveSelectedIds.value.filter((x) => x !== r.id);
        } else {
          fail++;
        }
      }
    }
    await loadRunHistory({ resetPage: false });
    if (fail === 0) saveRunTip.value = `已删除 ${ok} 条`;
    else saveRunTip.value = `已删除 ${ok} 条，失败 ${fail} 条`;
  } catch (e) {
    saveRunTip.value = e?.message || "批量删除失败";
  } finally {
    batchDeleteBusy.value = false;
  }
}

async function openRunDetail(id) {
  selectedRunDetail.value = null;
  selectedRunLoading.value = true;
  try {
    selectedRunDetail.value = await fetchJson(`backtest/runs/${id}`);
  } catch {
    selectedRunDetail.value = null;
  } finally {
    selectedRunLoading.value = false;
  }
}

function archiveJsonBasename(detail) {
  const kindSafe = String(detail?.kind || "run").replace(/[^\w.-]+/g, "_");
  return `backtest-run-${detail.id}-${kindSafe}.json`;
}

function onRunArchivePickChange(id, ev) {
  const on = ev?.target?.checked === true;
  const sel = new Set(runArchiveSelectedIds.value);
  if (on) sel.add(id);
  else sel.delete(id);
  runArchiveSelectedIds.value = [...sel].sort((a, b) => a - b);
}

function onRunArchiveTogglePageAll(ev) {
  const on = ev?.target?.checked === true;
  const pageIds = runHistory.value.map((r) => r.id);
  const sel = new Set(runArchiveSelectedIds.value);
  if (on) pageIds.forEach((i) => sel.add(i));
  else pageIds.forEach((i) => sel.delete(i));
  runArchiveSelectedIds.value = [...sel].sort((a, b) => a - b);
}

function clearRunArchivePick() {
  runArchiveSelectedIds.value = [];
}

async function exportSelectedRunsZip() {
  if (batchDeleteBusy.value) return;
  const ids = [...runArchiveSelectedIds.value].sort((a, b) => a - b);
  if (!ids.length) return;
  if (ids.length > ZIP_EXPORT_MAX) {
    saveRunTip.value = `一次最多导出 ${ZIP_EXPORT_MAX} 条，请减少勾选`;
    return;
  }
  saveRunTip.value = "";
  runZipBusy.value = true;
  try {
    const zip = new JSZip();
    const root = zip.folder("backtest-runs");
    if (!root) throw new Error("ZIP 初始化失败");
    const batch = 8;
    for (let i = 0; i < ids.length; i += batch) {
      const slice = ids.slice(i, i + batch);
      const rows = await Promise.all(
        slice.map(async (rid) => {
          const d = await fetchJson(`backtest/runs/${rid}`);
          return d;
        })
      );
      for (const d of rows) {
        root.file(archiveJsonBasename(d), JSON.stringify(d, null, 2));
      }
    }
    const blob = await zip.generateAsync({ type: "blob", compression: "DEFLATE" });
    const stamp = new Date().toISOString().slice(0, 19).replace(/[:-]/g, "");
    const zname = `backtest-runs-export-${stamp}.zip`;
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = zname;
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    saveRunTip.value = `已导出 ${zname}（${ids.length} 个 JSON）`;
  } catch (e) {
    saveRunTip.value = e?.message || "ZIP 导出失败";
  } finally {
    runZipBusy.value = false;
  }
}

function downloadRunJsonFile(detail) {
  if (!detail?.id) return;
  const name = archiveJsonBasename(detail);
  const text = JSON.stringify(detail, null, 2);
  const blob = new Blob([text], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  saveRunTip.value = `已导出 ${name}`;
}

async function exportRunArchiveById(id, ev) {
  ev?.stopPropagation?.();
  ev?.preventDefault?.();
  if (!id) return;
  exportRunIdBusy.value = id;
  saveRunTip.value = "";
  try {
    const d = await fetchJson(`backtest/runs/${id}`);
    downloadRunJsonFile(d);
  } catch (e) {
    saveRunTip.value = e?.message || "导出失败";
  } finally {
    exportRunIdBusy.value = null;
  }
}

async function runBacktest() {
  loading.value = true;
  error.value = "";
  result.value = null;
  const rangeErr = tradeRangeInvalidMsg();
  if (rangeErr) {
    error.value = rangeErr;
    loading.value = false;
    return;
  }
  const c = (props.code || "").trim();
  if (!c) {
    error.value = "请先选择标的";
    loading.value = false;
    return;
  }
  const envelope = singleRunMvpEnvelope(c);
  try {
    const runRes = await postMvpRunResolve(envelope);
    const r = runRes?.result;
    if (!r || typeof r.code !== "string") {
      throw new Error("响应缺少 result");
    }
    result.value = r;
    await persistRun(singleRunArchiveKind(), envelope, cloneJson(r));
  } catch (e) {
    error.value = e?.message || "请求失败";
  } finally {
    loading.value = false;
  }
}

async function runScan() {
  scanLoading.value = true;
  scanError.value = "";
  scanResult.value = null;
  const rangeErr = tradeRangeInvalidMsg();
  if (rangeErr) {
    scanError.value = rangeErr;
    scanLoading.value = false;
    return;
  }
  const raw = (scanCodesText.value || "").trim();
  if (!raw) {
    scanError.value = "请填写至少一个代码";
    scanLoading.value = false;
    return;
  }
  const envelope = scanRunMvpEnvelope(raw);
  try {
    const runRes = await postMvpRunResolve(envelope);
    const sr = runRes?.scan_result;
    if (!sr || !Array.isArray(sr.items)) {
      throw new Error("响应缺少 scan_result");
    }
    scanResult.value = sr;
    await persistRun("ma_cross_scan", envelope, cloneJson(sr));
  } catch (e) {
    scanError.value = e?.message || "请求失败";
  } finally {
    scanLoading.value = false;
  }
}

function fillPresetMajors() {
  scanCodesText.value = PRESET_MAJORS;
}

function signalQueryParams() {
  const p = new URLSearchParams({
    fast: String(fast.value),
    slow: String(slow.value),
    limit: String(limit.value),
  });
  const s = (tradeStartDate.value || "").trim();
  const e = (tradeEndDate.value || "").trim();
  if (s) p.set("start_date", s);
  if (e) p.set("end_date", e);
  return p;
}

async function loadSignalSnapshot() {
  const c = (props.code || "").trim();
  if (!c || innerTab.value !== "single") {
    signalSnap.value = null;
    signalErr.value = "";
    return;
  }
  if (singleRunStrategy.value === "buy_hold") {
    signalSnap.value = null;
    signalErr.value = "";
    return;
  }
  const rangeErr = tradeRangeInvalidMsg();
  if (rangeErr) {
    signalSnap.value = null;
    signalErr.value = rangeErr;
    return;
  }
  signalErr.value = "";
  const p = signalQueryParams();
  p.set("code", c);
  try {
    signalSnap.value = await fetchJson(`backtest/ma-cross/signal?${p.toString()}`);
  } catch (e) {
    signalSnap.value = null;
    signalErr.value = e?.message || "信号加载失败";
  }
}

function strategyPostParams() {
  const o = {
    fast: Number(fast.value) || 5,
    slow: Number(slow.value) || 20,
    limit: Number(limit.value) || 500,
  };
  const s = (tradeStartDate.value || "").trim();
  const e = (tradeEndDate.value || "").trim();
  if (s) o.start_date = s;
  if (e) o.end_date = e;
  return o;
}

/** 展示用：是否支持 POST /api/strategies/signal（与 catalog.signal_params 一致） */
function catalogSignalSupported(strategy) {
  const sp = strategy?.signal_params;
  if (!sp || typeof sp !== "object") return false;
  if (sp.maxProperties === 0) return false;
  return true;
}

function enrichCatalogStrategiesForDisplay(strategies) {
  if (!Array.isArray(strategies)) return [];
  return strategies.map((s) => ({
    ...s,
    signal_supported: catalogSignalSupported(s),
  }));
}

function escapeHtmlText(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/** 在已转义的 JSON 文本上为契约关键键加 <mark>（仅展示层） */
function highlightCatalogJsonKeys(jsonString) {
  let s = escapeHtmlText(jsonString);
  s = s.replace(
    /"backtest_run"(\s*:)/g,
    '<mark class="catalog-hl catalog-hl-backtest-run">"backtest_run"</mark>$1'
  );
  s = s.replace(
    /"signal_supported"(\s*:)/g,
    '<mark class="catalog-hl catalog-hl-signal-supported">"signal_supported"</mark>$1'
  );
  return s;
}

async function loadStrategyCatalog() {
  strategyContractMsg.value = "";
  strategyContractBusy.value = true;
  try {
    const data = await fetchJson("strategies/catalog");
    const body = {
      strategies: enrichCatalogStrategiesForDisplay(data.strategies || []),
    };
    strategyCatalogHtml.value = highlightCatalogJsonKeys(JSON.stringify(body, null, 2));
  } catch (e) {
    strategyCatalogHtml.value = "";
    strategyContractMsg.value = e?.message || "目录加载失败";
  } finally {
    strategyContractBusy.value = false;
  }
}

async function postStrategySignalTrial() {
  strategyContractMsg.value = "";
  const c = (props.code || "").trim();
  if (!c) {
    strategyContractMsg.value = "请先在行情看板选择标的";
    return;
  }
  const rangeErr = tradeRangeInvalidMsg();
  if (rangeErr) {
    strategyContractMsg.value = rangeErr;
    return;
  }
  strategyContractBusy.value = true;
  try {
    const data = await fetchJson("strategies/signal", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        code: c,
        kind: "ma_cross",
        params: strategyPostParams(),
      }),
    });
    strategySignalTrialText.value = JSON.stringify(data, null, 2);
  } catch (e) {
    strategySignalTrialText.value = "";
    strategyContractMsg.value = e?.message || "试算失败";
  } finally {
    strategyContractBusy.value = false;
  }
}

async function fillScanFromWatchlist() {
  scanError.value = "";
  try {
    const data = await fetchJson("watchlist/items");
    const items = Array.isArray(data?.items) ? data.items : [];
    const codes = items
      .map((x) => String(x.code || "").trim().toLowerCase())
      .filter(Boolean)
      .slice(0, SCAN_CODES_FROM_WL_MAX);
    if (!codes.length) {
      scanError.value = "自选为空";
      return;
    }
    scanCodesText.value = codes.join("\n");
  } catch (e) {
    scanError.value = e?.message || "拉取自选失败";
  }
}

async function downloadScanCsv() {
  const rangeErr = tradeRangeInvalidMsg();
  if (rangeErr) {
    scanError.value = rangeErr;
    return;
  }
  const raw = (scanCodesText.value || "").trim();
  if (!raw) {
    scanError.value = "请填写至少一个代码";
    return;
  }
  scanCsvLoading.value = true;
  scanError.value = "";
  const params = scanQueryParams();
  params.set("codes", raw);
  params.set("export", "csv");
  try {
    const res = await fetch(apiUrl(`backtest/ma-cross/scan?${params.toString()}`));
    if (!res.ok) {
      const t = await res.text();
      throw new Error(t.slice(0, 200) || `${res.status}`);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `ma_cross_scan_${Date.now()}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    scanError.value = e?.message || "CSV 下载失败";
  } finally {
    scanCsvLoading.value = false;
  }
}

watch(
  () => props.code,
  () => {
    result.value = null;
    error.value = "";
  }
);

async function loadWatchlist() {
  try {
    const data = await fetchJson("watchlist/items");
    wlItems.value = Array.isArray(data?.items) ? data.items : [];
  } catch {
    wlItems.value = [];
  }
}

function pickWlForBacktest(code) {
  const c = String(code || "").trim().toLowerCase();
  if (c) emit("select-code", c);
}

watch(
  () => [
    innerTab.value,
    singleRunStrategy.value,
    props.code,
    fast.value,
    slow.value,
    limit.value,
    tradeStartDate.value,
    tradeEndDate.value,
  ],
  () => {
    loadSignalSnapshot();
  },
  { immediate: true }
);

watch(singleRunStrategy, (v) => {
  result.value = null;
  error.value = "";
  try {
    if (v === "buy_hold" || v === "ma_cross") {
      localStorage.setItem(LS_SINGLE_RUN_STRATEGY_KEY, v);
    }
  } catch {
    /* ignore */
  }
});

watch(runHistoryKindFilter, () => {
  runHistoryOffset.value = 0;
  loadRunHistory({ resetPage: false });
});

watch(runHistoryLimit, (v) => {
  try {
    localStorage.setItem(LS_RUNS_LIMIT_KEY, String(v));
  } catch {
    /* ignore */
  }
  runHistoryOffset.value = 0;
  void loadRunHistory({ resetPage: false });
});

watch(mvpAsyncRun, (v) => {
  try {
    if (v) localStorage.setItem(LS_MVP_ASYNC_KEY, "1");
    else localStorage.removeItem(LS_MVP_ASYNC_KEY);
  } catch {
    /* ignore */
  }
});

onMounted(() => {
  loadWatchlist();
  loadRunHistory();
  void loadBacktestEngineCatalog();
});
</script>

<template>
  <section class="bt">
    <div class="subtabs">
      <button
        type="button"
        class="subtab"
        :class="{ active: innerTab === 'single' }"
        @click="innerTab = 'single'"
      >
        单标的
      </button>
      <button
        type="button"
        class="subtab"
        :class="{ active: innerTab === 'scan' }"
        @click="innerTab = 'scan'"
      >
        批量扫描
      </button>
    </div>

    <p v-if="backtestCatalogLoading" class="mono bt-engine-catalog bt-engine-catalog--muted">
      加载 <span class="mono">GET /api/backtest/catalog</span> …
    </p>
    <p v-else-if="backtestCatalogErr" class="mono bt-engine-catalog bt-engine-catalog--warn" role="status">
      {{ backtestCatalogErr }}（POST /run 仍可用）
    </p>
    <p
      v-else-if="backtestCatalog"
      class="mono bt-engine-catalog"
      data-testid="backtest-engine-catalog"
      :title="backtestCatalogTitleHint"
    >
      {{ backtestCatalogLine }}
    </p>

    <div class="strategy-contract-bar">
      <span class="strategy-contract-lbl mono">策略目录 / 试算信号</span>
      <button
        type="button"
        class="ghost strategy-contract-btn"
        :disabled="strategyContractBusy"
        @click="loadStrategyCatalog"
      >
        策略目录
      </button>
      <button
        type="button"
        class="ghost strategy-contract-btn"
        :disabled="strategyContractBusy"
        @click="postStrategySignalTrial"
      >
        试算信号
      </button>
    </div>
    <p v-if="strategyContractMsg" class="strategy-contract-msg mono">{{ strategyContractMsg }}</p>
    <pre
      v-show="strategyCatalogHtml"
      class="strategy-contract-pre mono catalog-json-pre"
      v-html="strategyCatalogHtml"
    />
    <p v-show="strategyCatalogHtml" class="catalog-json-legend mono">
      高亮为展示层：<span class="catalog-legend-k catalog-legend-k--run">backtest_run</span>
      <span class="catalog-legend-sep">·</span>
      <span class="catalog-legend-k catalog-legend-k--sig">signal_supported</span>
      （由 <span class="mono">signal_params</span> 推导，非接口原样字段）
    </p>
    <pre v-show="strategySignalTrialText" class="strategy-contract-pre mono">{{ strategySignalTrialText }}</pre>

    <div class="trade-range-row">
      <label class="field">
        <span class="lbl">区间起始（可选，含）</span>
        <input v-model="tradeStartDate" type="date" class="inp mono" />
      </label>
      <label class="field">
        <span class="lbl">区间结束（可选，含）</span>
        <input v-model="tradeEndDate" type="date" class="inp mono" />
      </label>
    </div>
    <p class="trade-range-note">
      留空则按 K 根数从最新往回取；填写后作用于单标的与批量扫描（对应接口
      <span class="mono">start_date</span> / <span class="mono">end_date</span>）。
    </p>

    <div class="trade-range-row">
      <label class="field wide">
        <span class="lbl">基准代码（可选，β / α）</span>
        <input
          v-model="benchmarkCode"
          type="text"
          class="inp mono"
          placeholder="如 sh.000300；留空则对标的自身日收益"
          spellcheck="false"
        />
      </label>
    </div>
    <p class="trade-range-note">
      填写后日收益回归用基准收盘价序列（与标的交易日对齐，仅前向填充、无前视）。
    </p>

    <div class="mvp-async-row">
      <label class="mvp-async-label">
        <input v-model="mvpAsyncRun" type="checkbox" data-testid="mvp-async-run" />
        <span>
          异步 job（<span class="mono">POST …/run?{{ mvpAsyncUiCatalogBits.qp }}=1</span>（与顶栏目录
          <span class="mono">async_run_query_param</span> 一致），<span class="mono">{{ mvpAsyncUiCatalogBits.pollTmpl }}</span>
          轮询；与同步结果同形；存储见顶栏 <span class="mono">async_job_persistence</span>（Redis 或进程内）；本勾选会写入浏览器
          <span class="mono">localStorage</span>，刷新后保留）
        </span>
      </label>
      <button
        v-if="mvpAsyncRun && mvpAsyncInFlightJobId"
        type="button"
        class="btn mvp-async-cancel-btn"
        data-testid="mvp-async-cancel"
        @click="onCancelMvpAsyncQueued"
      >
        取消排队
      </button>
    </div>
    <p v-if="mvpAsyncCancelMsg" class="mono mvp-async-cancel-msg" role="status">{{ mvpAsyncCancelMsg }}</p>

    <template v-if="innerTab === 'single'">
      <div class="single-strategy-pick mono" data-testid="single-run-strategy-row">
        <span class="single-strategy-pick-lbl">单标的策略</span>
        <label class="single-strategy-opt">
          <input
            v-model="singleRunStrategy"
            type="radio"
            value="ma_cross"
            data-testid="single-run-strategy-ma-cross"
          />
          <span>双均线（<span class="mono">ma_cross</span>）</span>
        </label>
        <label class="single-strategy-opt">
          <input
            v-model="singleRunStrategy"
            type="radio"
            value="buy_hold"
            data-testid="single-run-strategy-buy-hold"
          />
          <span>买入持有（<span class="mono">buy_hold</span>）</span>
        </label>
      </div>
      <header class="hd">
        <div>
          <p class="eyebrow">策略回测</p>
          <h2 class="h2">{{ singleRunStrategy === "buy_hold" ? "买入持有（日线）" : "双均线（日线）" }}</h2>
          <p v-if="singleRunStrategy === 'buy_hold'" class="sub mono">
            标的 {{ (code || "—").trim() }} · 与行情看板当前代码联动；回测与存档走
            <span class="mono">POST /api/backtest/run</span>（<span class="mono">buy_hold</span>）；全样本做多，与
            <span class="mono">GET …/buy-hold</span> 同核。买入持有无均线信号行。
          </p>
          <p v-else class="sub mono">
            标的 {{ (code || "—").trim() }} · 与行情看板当前代码联动；回测与存档前试算走
            <span class="mono">POST /api/backtest/run</span>（<span class="mono">ma_cross</span>）；均线一行仍调
            <span class="mono">GET …/ma-cross/signal</span>。
          </p>
          <div v-if="wlItems.length" class="wl-chips">
            <span class="wl-chips-lbl">自选</span>
            <button
              v-for="w in wlItems"
              :key="w.code"
              type="button"
              class="wl-chip mono"
              @click="pickWlForBacktest(w.code)"
            >
              {{ w.code }}
            </button>
          </div>
          <template v-if="singleRunStrategy === 'ma_cross'">
            <p v-if="signalErr" class="sig-err mono">{{ signalErr }}</p>
            <p v-else-if="signalSnap" class="sig-line mono">
              信号（{{ signalSnap.as_of_date }}）：
              <strong>{{ signalSnap.position === "long" ? "多" : "空" }}</strong>
              · 收 {{ signalSnap.close }} · MA{{ signalSnap.fast_period }} {{ signalSnap.ma_fast }} / MA{{
                signalSnap.slow_period
              }}
              {{ signalSnap.ma_slow }}
            </p>
          </template>
        </div>
        <div class="hd-actions">
          <button type="button" class="run" :disabled="loading" @click="runBacktest">
            {{ loading ? "计算中…" : "运行回测" }}
          </button>
          <button type="button" class="run secondary" @click="emitOpenPaper">闭环 · 纸交易</button>
          <button
            type="button"
            class="run secondary"
            :disabled="!result"
            @click="downloadSingleJson"
          >
            下载 JSON
          </button>
        </div>
      </header>

      <div class="form">
        <label class="field">
          <span class="lbl">快线</span>
          <input
            v-model.number="fast"
            type="number"
            min="1"
            max="120"
            class="inp mono"
            :disabled="singleRunStrategy === 'buy_hold'"
            :title="singleRunStrategy === 'buy_hold' ? '买入持有不使用快慢线' : ''"
          />
        </label>
        <label class="field">
          <span class="lbl">慢线</span>
          <input
            v-model.number="slow"
            type="number"
            min="2"
            max="500"
            class="inp mono"
            :disabled="singleRunStrategy === 'buy_hold'"
            :title="singleRunStrategy === 'buy_hold' ? '买入持有不使用快慢线' : ''"
          />
        </label>
        <label class="field">
          <span class="lbl">K 根数</span>
          <input v-model.number="limit" type="number" min="30" max="5000" class="inp mono" />
        </label>
        <label class="field wide">
          <span class="lbl">单边手续费（万分之）</span>
          <input
            v-model.number="feeWan"
            type="number"
            min="0"
            step="0.1"
            class="inp mono"
            placeholder="0"
          />
          <span class="hint mono">→ {{ feeRate.toFixed(6) }}</span>
        </label>
        <label class="field wide">
          <span class="lbl">滑点（万分之，调仓日）</span>
          <input
            v-model.number="slipWan"
            type="number"
            min="0"
            step="0.1"
            class="inp mono"
            placeholder="0"
          />
          <span class="hint mono">→ {{ slipRate.toFixed(6) }}（与手续费之和勿超 0.08）</span>
        </label>
      </div>

      <div v-if="error" class="err">{{ error }}</div>

      <div v-if="result" class="metrics">
        <div class="m">
          <span class="mk">策略收益 %</span>
          <span
            class="mv mono"
            :class="{ up: result.total_return_pct > 0, down: result.total_return_pct < 0 }"
          >
            {{ result.total_return_pct?.toFixed?.(2) ?? "—" }}
          </span>
        </div>
        <div class="m">
          <span class="mk">买入持有 %</span>
          <span class="mv mono">{{ result.buy_hold_return_pct?.toFixed?.(2) ?? "—" }}</span>
        </div>
        <div class="m">
          <span class="mk">超额 %（相对买入持有）</span>
          <span
            class="mv mono"
            :class="{
              up: result.excess_return_pct > 0,
              down: result.excess_return_pct < 0,
            }"
          >
            {{ result.excess_return_pct?.toFixed?.(2) ?? "—" }}
          </span>
        </div>
        <div class="m">
          <span class="mk">最大回撤 %</span>
          <span class="mv mono down">{{ result.max_drawdown_pct?.toFixed?.(2) ?? "—" }}</span>
        </div>
        <div class="m">
          <span class="mk">夏普</span>
          <span class="mv mono">{{ result.sharpe_ratio?.toFixed?.(3) ?? "—" }}</span>
        </div>
        <div class="m">
          <span class="mk">Sortino</span>
          <span class="mv mono">{{ result.sortino_ratio?.toFixed?.(3) ?? "—" }}</span>
        </div>
        <div class="m">
          <span class="mk">Calmar</span>
          <span class="mv mono">{{ result.calmar_ratio?.toFixed?.(3) ?? "—" }}</span>
        </div>
        <div class="m">
          <span class="mk">年化收益 %</span>
          <span
            class="mv mono"
            :class="{
              up: result.annualized_return_pct > 0,
              down: result.annualized_return_pct < 0,
            }"
          >
            {{ result.annualized_return_pct?.toFixed?.(2) ?? "—" }}
          </span>
        </div>
        <div class="m">
          <span class="mk">买入持有年化 %</span>
          <span class="mv mono">{{ result.buy_hold_annualized_return_pct?.toFixed?.(2) ?? "—" }}</span>
        </div>
        <div class="m">
          <span class="mk">年化波动 %</span>
          <span class="mv mono">{{ result.annualized_volatility_pct?.toFixed?.(2) ?? "—" }}</span>
        </div>
        <div class="m">
          <span class="mk">多头段数</span>
          <span class="mv mono">{{ result.long_trades_count ?? "—" }}</span>
        </div>
        <div class="m">
          <span class="mk">段胜率 %(额权)</span>
          <span class="mv mono">{{ result.win_rate_pct?.toFixed?.(1) ?? "—" }}</span>
        </div>
        <div class="m">
          <span class="mk">段均收益 %</span>
          <span
            class="mv mono"
            :class="{
              up: result.avg_holding_return_pct > 0,
              down: result.avg_holding_return_pct < 0,
            }"
          >
            {{ result.avg_holding_return_pct?.toFixed?.(2) ?? "—" }}
          </span>
        </div>
        <div class="m">
          <span class="mk">{{
            result.benchmark_code
              ? `β（对 ${result.benchmark_code}）`
              : "β（对标的日收益）"
          }}</span>
          <span class="mv mono">{{ result.underlying_beta?.toFixed?.(3) ?? "—" }}</span>
        </div>
        <div class="m">
          <span class="mk">{{
            result.benchmark_code ? "α 年化 %（对基准，rf=0）" : "α 年化 %（对标的，rf=0）"
          }}</span>
          <span
            class="mv mono"
            :class="{
              up: result.underlying_alpha_ann_pct > 0,
              down: result.underlying_alpha_ann_pct < 0,
            }"
          >
            {{ result.underlying_alpha_ann_pct?.toFixed?.(2) ?? "—" }}
          </span>
        </div>
        <div class="m">
          <span class="mk">信号翻转</span>
          <span class="mv mono">{{ result.signal_changes ?? "—" }}</span>
        </div>
        <div class="m wide">
          <span class="mk">区间</span>
          <span class="mv mono sm">{{ result.first_trade_date }} → {{ result.last_trade_date }}</span>
        </div>
      </div>

      <div class="chart-wrap">
        <VChart class="chart" :option="chartOption" autoresize />
      </div>

      <p v-if="result?.note" class="note">{{ result.note }}</p>
    </template>

    <template v-else>
      <header class="hd">
        <div>
          <p class="eyebrow">策略回测</p>
          <h2 class="h2">多标的批量扫描</h2>
          <p class="sub">
            相同参数下对列表逐只回测；排序含收益、超额、夏普、Sortino、Calmar、年化、胜率、均段收益等（失败行沉底）。
            JSON 预览与存档前试算走 <span class="mono">POST /api/backtest/run</span>（<span class="mono">ma_cross_scan</span>，<span
              class="mono"
              >max_codes={{ SCAN_CODES_FROM_WL_MAX }}</span
            >
            与自选上限一致）；下载 CSV 仍直连 <span class="mono">GET …/ma-cross/scan?export=csv</span>。
          </p>
        </div>
        <div class="hd-actions">
          <button type="button" class="run gold" :disabled="scanLoading" @click="runScan">
            {{ scanLoading ? "扫描中…" : "开始扫描" }}
          </button>
          <button
            type="button"
            class="run secondary"
            :disabled="scanCsvLoading || scanLoading"
            @click="downloadScanCsv"
          >
            {{ scanCsvLoading ? "导出中…" : "下载 CSV" }}
          </button>
          <button
            type="button"
            class="run secondary"
            :disabled="!scanResult?.items?.length"
            @click="downloadScanJson"
          >
            下载 JSON
          </button>
        </div>
      </header>

      <div class="form">
        <label class="field">
          <span class="lbl">快线</span>
          <input v-model.number="fast" type="number" min="1" max="120" class="inp mono" />
        </label>
        <label class="field">
          <span class="lbl">慢线</span>
          <input v-model.number="slow" type="number" min="2" max="500" class="inp mono" />
        </label>
        <label class="field">
          <span class="lbl">K 根数</span>
          <input v-model.number="limit" type="number" min="30" max="5000" class="inp mono" />
        </label>
        <label class="field wide">
          <span class="lbl">单边手续费（万分之）</span>
          <input v-model.number="feeWan" type="number" min="0" step="0.1" class="inp mono" />
        </label>
        <label class="field wide">
          <span class="lbl">滑点（万分之）</span>
          <input v-model.number="slipWan" type="number" min="0" step="0.1" class="inp mono" />
        </label>
        <label class="field wide">
          <span class="lbl">结果排序</span>
          <select v-model="scanSortBy" class="inp mono">
            <option value="total_return">策略收益 %</option>
            <option value="excess_return">超额 %（相对买入持有）</option>
            <option value="sharpe">夏普</option>
            <option value="sortino">Sortino</option>
            <option value="calmar">Calmar</option>
            <option value="ann_return">年化收益 %</option>
            <option value="buy_hold">买入持有 %</option>
            <option value="win_rate">段胜率 %(额权)</option>
            <option value="avg_holding">段均收益 %</option>
            <option value="underlying_beta">{{ benchSortBetaLabel }}</option>
            <option value="underlying_alpha">{{ benchSortAlphaLabel }}</option>
          </select>
        </label>
        <label class="field">
          <span class="lbl">并发拉 K（MySQL）</span>
          <input
            v-model.number="scanMaxConcurrent"
            type="number"
            min="1"
            max="20"
            class="inp mono"
            title="SQLite 下后端会顺序拉取，此值无效"
          />
        </label>
      </div>

      <div class="codes-toolbar">
        <label class="block-label">代码列表（每行一个或逗号分隔）</label>
        <div class="codes-toolbar-actions">
          <button type="button" class="linkish" @click="fillPresetMajors">填入主要指数</button>
          <button type="button" class="linkish" @click="fillScanFromWatchlist">填入自选（最多 {{ SCAN_CODES_FROM_WL_MAX }}）</button>
        </div>
      </div>
      <textarea v-model="scanCodesText" class="codes-ta mono" rows="5" spellcheck="false" />

      <div v-if="scanError" class="err">{{ scanError }}</div>

      <p v-if="scanResult?.items?.length" class="scan-meta mono">
        <span>MA {{ scanResult.fast_period }}/{{ scanResult.slow_period }}</span>
        <span class="scan-meta-sep">·</span>
        <span>K {{ scanResult.limit }}</span>
        <span class="scan-meta-sep">·</span>
        <span>排序 {{ scanSortLabel(scanResult.sort_by) }}</span>
        <span class="scan-meta-sep">·</span>
        <span>并发 {{ scanResult.max_concurrent }}</span>
        <span class="scan-meta-sep">·</span>
        <span>手续费 {{ wanFromRate(scanResult.commission_rate) }}‱</span>
        <span class="scan-meta-sep">·</span>
        <span>滑点 {{ wanFromRate(scanResult.slippage_rate) }}‱</span>
        <span class="scan-meta-sep">·</span>
        <span>{{ scanResult.items.length }} 行</span>
        <template v-if="(scanResult.benchmark_code || '').trim()">
          <span class="scan-meta-sep">·</span>
          <span>基准 {{ scanResult.benchmark_code }}</span>
        </template>
        <template v-if="scanResult.start_date || scanResult.end_date">
          <span class="scan-meta-sep">·</span>
          <span>区间 {{ scanResult.start_date || "—" }} → {{ scanResult.end_date || "—" }}</span>
        </template>
      </p>

      <div v-if="scanResult?.items?.length" class="scan-wrap">
        <table class="scan-table">
          <thead>
            <tr>
              <th>代码</th>
              <th>策略 %</th>
              <th>BH %</th>
              <th>超额 %</th>
              <th>年化 %</th>
              <th>波动 %</th>
              <th>夏普</th>
              <th>So</th>
              <th>Ca</th>
              <th>段</th>
              <th>胜%权</th>
              <th>均段%</th>
              <th>β</th>
              <th>α年%</th>
              <th>翻转</th>
              <th>备注</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in scanResult.items" :key="row.code + (row.error || '')">
              <td class="mono">{{ row.code }}</td>
              <td
                class="mono"
                :class="{
                  up: row.total_return_pct != null && row.total_return_pct > 0,
                  down: row.total_return_pct != null && row.total_return_pct < 0,
                }"
              >
                {{ row.error ? "—" : row.total_return_pct?.toFixed(2) }}
              </td>
              <td class="mono">{{ row.error ? "—" : row.buy_hold_return_pct?.toFixed(2) }}</td>
              <td
                class="mono"
                :class="{
                  up: row.excess_return_pct != null && row.excess_return_pct > 0,
                  down: row.excess_return_pct != null && row.excess_return_pct < 0,
                }"
              >
                {{ row.error ? "—" : row.excess_return_pct?.toFixed(2) }}
              </td>
              <td class="mono">{{ row.error ? "—" : row.annualized_return_pct?.toFixed(2) }}</td>
              <td class="mono">{{ row.error ? "—" : row.annualized_volatility_pct?.toFixed(2) }}</td>
              <td class="mono">{{ row.error ? "—" : row.sharpe_ratio?.toFixed(3) }}</td>
              <td class="mono">{{ row.error ? "—" : row.sortino_ratio?.toFixed(3) }}</td>
              <td class="mono">{{ row.error ? "—" : row.calmar_ratio?.toFixed(3) }}</td>
              <td class="mono">{{ row.error ? "—" : row.long_trades_count }}</td>
              <td class="mono">{{ row.error ? "—" : row.win_rate_pct?.toFixed(1) }}</td>
              <td
                class="mono"
                :class="{
                  up: !row.error && row.avg_holding_return_pct > 0,
                  down: !row.error && row.avg_holding_return_pct < 0,
                }"
              >
                {{ row.error ? "—" : row.avg_holding_return_pct?.toFixed(2) }}
              </td>
              <td class="mono">{{ row.error ? "—" : row.underlying_beta?.toFixed(3) }}</td>
              <td
                class="mono"
                :class="{
                  up: !row.error && row.underlying_alpha_ann_pct > 0,
                  down: !row.error && row.underlying_alpha_ann_pct < 0,
                }"
              >
                {{ row.error ? "—" : row.underlying_alpha_ann_pct?.toFixed(2) }}
              </td>
              <td class="mono">{{ row.error ? "—" : row.signal_changes }}</td>
              <td class="err-cell">{{ row.error || "" }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <div class="run-archive">
      <div class="run-archive-hd">
        <h3 class="h3">结果存档</h3>
        <div class="run-archive-tools">
          <label class="run-filter-label">
            <span class="sr-only">类型</span>
            <select v-model="runHistoryKindFilter" class="run-kind-select mono" aria-label="存档类型筛选">
              <option value="">全部类型</option>
              <option v-for="o in archiveKindFilterOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>
          </label>
          <button type="button" class="ghost" :disabled="runHistoryLoading" @click="loadRunHistory">
            {{ runHistoryLoading ? "加载中…" : "刷新列表" }}
          </button>
        </div>
      </div>
      <p v-if="runKindMapHint" class="mono run-kind-map-hint" data-testid="run-kind-map-hint">{{ runKindMapHint }}</p>
      <div class="run-archive-search">
        <input
          v-model="runHistorySearchInput"
          type="search"
          class="run-search-input mono"
          placeholder="摘要关键字"
          aria-label="摘要搜索"
          @keyup.enter="applyRunHistorySearch"
        />
        <button type="button" class="ghost run-ghost-tight" :disabled="runHistoryLoading" @click="applyRunHistorySearch">
          搜索
        </button>
        <button
          type="button"
          class="ghost run-ghost-tight"
          :disabled="runHistoryLoading || runHistorySearchClearDisabled"
          @click="clearRunHistorySearch"
        >
          清除
        </button>
      </div>
      <p class="run-archive-note mono">
        自动调用 <span class="mono">POST /api/backtest/runs</span>；列表
        <span class="mono">GET /api/backtest/runs</span>，详情
        <span class="mono">GET /api/backtest/runs/{id}</span>；可选查询参数 <span class="mono">q</span> 按摘要子串过滤。列表可勾选（无需展开详情）、「本页全选」后
        <span class="mono">导出所选 ZIP</span>，包内 <span class="mono">backtest-runs/*.json</span>；可
        <span class="mono">删除所选</span>（批量 <span class="mono">DELETE</span>）；单条仍可用行内「删除」、「导出」或详情区
        <span class="mono">导出 JSON</span>。支持每页 10 / 30 / 50 条（记住本机）、跳转页码与摘要搜索。
      </p>
      <p v-if="saveRunTip" class="save-tip mono" role="status">{{ saveRunTip }}</p>
      <div v-if="runHistoryTotal > 0" class="run-history-pagination">
        <div class="run-pg-row">
          <span class="meta mono meta-range">{{ runHistoryRangeLabel }}</span>
          <span class="run-page-btns">
            <button
              type="button"
              class="ghost run-ghost-tight"
              :disabled="runHistoryLoading || !runHistoryHasPrev"
              @click="runHistoryPrevPage"
            >
              上一页
            </button>
            <button
              type="button"
              class="ghost run-ghost-tight"
              :disabled="runHistoryLoading || !runHistoryHasNext"
              @click="runHistoryNextPage"
            >
              下一页
            </button>
          </span>
        </div>
        <div class="run-pg-row run-pg-controls">
          <label class="mono run-limit-label">
            每页
            <select v-model.number="runHistoryLimit" class="run-limit-select mono" aria-label="每页条数">
              <option :value="10">10</option>
              <option :value="30">30</option>
              <option :value="50">50</option>
            </select>
            条
          </label>
          <div class="run-jump-wrap mono">
            <label class="run-jump-lbl">
              跳转
              <input
                v-model="runHistoryJumpPage"
                type="number"
                min="1"
                :max="runHistoryTotalPages"
                class="run-jump-input mono"
                aria-label="页码"
                @keyup.enter="runHistorySubmitJump"
              />
            </label>
            <span class="dim">/ 共 {{ runHistoryTotalPages }} 页</span>
            <button
              type="button"
              class="ghost run-ghost-tight"
              :disabled="runHistoryLoading"
              @click="runHistorySubmitJump"
            >
              跳转
            </button>
          </div>
        </div>
      </div>
      <div v-if="runHistory.length" class="run-archive-pick-bar">
        <label class="run-pick-all mono">
          <input
            type="checkbox"
            :checked="runArchivePageAllChecked"
            aria-label="本页全选"
            @change="onRunArchiveTogglePageAll"
          />
          本页全选
        </label>
        <button type="button" class="ghost run-ghost-tight" @click="clearRunArchivePick">清空选择</button>
        <button
          type="button"
          class="run-batch-del"
          :disabled="batchDeleteBusy || runZipBusy || runHistoryLoading || runArchiveSelectedIds.length === 0"
          @click="deleteSelectedRunArchives"
        >
          {{ batchDeleteBusy ? "删除中…" : `删除所选（${runArchiveSelectedIds.length}）` }}
        </button>
        <button
          type="button"
          class="run-zip-btn"
          :disabled="runZipBusy || batchDeleteBusy || runHistoryLoading || runArchiveSelectedIds.length === 0"
          @click="exportSelectedRunsZip"
        >
          {{ runZipBusy ? "打包中…" : `导出所选 ZIP（${runArchiveSelectedIds.length}）` }}
        </button>
      </div>
      <ul v-if="runHistory.length" class="run-ul">
        <li v-for="r in runHistory" :key="r.id" class="run-li mono">
          <label class="run-li-check" @click.stop>
            <input
              type="checkbox"
              :checked="runArchiveSelectedIds.includes(r.id)"
              :aria-label="`选择存档 #${r.id}`"
              @change="onRunArchivePickChange(r.id, $event)"
            />
          </label>
          <button type="button" class="run-li-btn" @click="openRunDetail(r.id)">#{{ r.id }}</button>
          <span class="run-li-sum">{{ r.summary }}</span>
          <span class="dim">{{ r.created_at }}</span>
          <span class="run-li-actions">
            <button
              type="button"
              class="run-li-exp"
              :disabled="exportRunIdBusy === r.id"
              @click="exportRunArchiveById(r.id, $event)"
            >
              {{ exportRunIdBusy === r.id ? "…" : "导出" }}
            </button>
            <button type="button" class="run-li-del" @click="deleteRunArchive(r.id, $event)">删除</button>
          </span>
        </li>
      </ul>
      <p v-else-if="!runHistoryLoading" class="dim">暂无存档</p>
      <p v-if="selectedRunLoading" class="dim mono">加载详情…</p>
      <div v-if="selectedRunDetail" class="run-detail">
        <div class="run-detail-hd">
          <p class="dim mono run-detail-id">#{{ selectedRunDetail.id }} · {{ selectedRunDetail.kind }}</p>
          <button type="button" class="run-export-btn" @click="downloadRunJsonFile(selectedRunDetail)">导出 JSON</button>
        </div>
        <p class="dim">request_params</p>
        <pre class="run-pre mono">{{ JSON.stringify(selectedRunDetail.request_params, null, 2) }}</pre>
        <p class="dim">response_payload</p>
        <pre class="run-pre mono">{{ JSON.stringify(selectedRunDetail.response_payload, null, 2) }}</pre>
      </div>
    </div>
  </section>
</template>

<style scoped>
.bt {
  border-radius: 16px;
  border: 1px solid var(--rule-faint);
  padding: 22px 24px 28px;
  background: linear-gradient(165deg, rgba(20, 20, 31, 0.96) 0%, rgba(10, 10, 15, 0.88) 100%);
  box-shadow: var(--shadow-lift);
}

.bt-engine-catalog {
  margin: 0 0 14px;
  font-size: 0.68rem;
  line-height: 1.45;
  color: var(--paper-muted);
}

.bt-engine-catalog--muted {
  opacity: 0.75;
}

.bt-engine-catalog--warn {
  color: #e8a547;
}

.subtabs {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
}

.subtab {
  font-family: var(--font-display);
  font-size: 0.65rem;
  font-weight: 800;
  letter-spacing: 0.12em;
  padding: 8px 16px;
  border-radius: 8px;
  border: 1px solid var(--rule-faint);
  background: rgba(12, 12, 18, 0.8);
  color: var(--mist-dim);
  cursor: pointer;
  transition:
    color 0.2s ease,
    border-color 0.2s ease,
    background 0.2s ease;
}

.subtab:hover {
  color: var(--mist);
}

.subtab.active {
  color: var(--meridian);
  border-color: rgba(62, 224, 255, 0.4);
  background: rgba(62, 224, 255, 0.08);
}

.strategy-contract-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid rgba(62, 224, 255, 0.15);
  background: rgba(62, 224, 255, 0.04);
}

.strategy-contract-lbl {
  margin-right: 4px;
  font-size: 0.62rem;
  letter-spacing: 0.06em;
  color: var(--mist-dim);
}

.strategy-contract-btn {
  font-size: 0.62rem;
  padding: 6px 12px;
  border-radius: 8px;
}

.strategy-contract-msg {
  margin: 0 0 8px;
  font-size: 0.65rem;
  color: #ff9a9a;
}

.strategy-contract-pre {
  margin: 0 0 10px;
  max-height: 220px;
  overflow: auto;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid var(--rule-faint);
  background: rgba(6, 6, 10, 0.75);
  font-size: 0.58rem;
  line-height: 1.35;
  color: var(--mist-dim);
}

.strategy-contract-pre.catalog-json-pre :deep(mark.catalog-hl) {
  padding: 0 3px;
  margin: 0 1px;
  border-radius: 4px;
  font-weight: 600;
}

.strategy-contract-pre.catalog-json-pre :deep(mark.catalog-hl-backtest-run) {
  background: rgba(255, 186, 86, 0.22);
  color: #ffd8a6;
  box-shadow: 0 0 0 1px rgba(255, 186, 86, 0.2);
}

.strategy-contract-pre.catalog-json-pre :deep(mark.catalog-hl-signal-supported) {
  background: rgba(86, 198, 255, 0.16);
  color: #b8ecff;
  box-shadow: 0 0 0 1px rgba(86, 198, 255, 0.18);
}

.catalog-json-legend {
  margin: -4px 0 10px;
  font-size: 0.55rem;
  line-height: 1.4;
  color: var(--mist-dim);
  opacity: 0.88;
}

.catalog-legend-k {
  padding: 1px 5px;
  border-radius: 4px;
  font-weight: 600;
}

.catalog-legend-k--run {
  background: rgba(255, 186, 86, 0.14);
  color: #e8c49a;
}

.catalog-legend-k--sig {
  background: rgba(86, 198, 255, 0.12);
  color: #9fdcf5;
}

.catalog-legend-sep {
  margin: 0 4px;
  opacity: 0.6;
}

.trade-range-row {
  display: flex;
  flex-wrap: wrap;
  gap: 14px 20px;
  margin-bottom: 6px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--rule-faint);
}

.trade-range-note {
  margin: 0 0 18px;
  font-size: 0.7rem;
  line-height: 1.45;
  color: var(--mist-dim);
}

.trade-range-note .mono {
  font-family: var(--font-mono);
  font-size: 0.68rem;
  color: var(--mist-dim);
}

.single-strategy-pick {
  margin: 0 0 14px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 16px;
  font-size: 0.72rem;
  color: var(--mist-dim);
}

.single-strategy-pick-lbl {
  margin-right: 4px;
  color: var(--mist);
}

.single-strategy-opt {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  cursor: pointer;
}

.single-strategy-opt input {
  width: 14px;
  height: 14px;
  accent-color: var(--meridian);
  cursor: pointer;
}

.mvp-async-row {
  margin: -8px 0 18px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 14px;
}

.mvp-async-cancel-btn {
  font-size: 0.75rem;
}

.mvp-async-cancel-msg {
  margin: -6px 0 14px;
  font-size: 0.72rem;
  color: var(--mist-dim);
}

.mvp-async-label {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin: 0;
  font-size: 0.7rem;
  line-height: 1.5;
  color: var(--mist-dim);
  cursor: pointer;
}

.mvp-async-label input {
  margin-top: 3px;
  flex-shrink: 0;
  width: 15px;
  height: 15px;
  accent-color: var(--meridian);
  cursor: pointer;
}

.hd {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
}

.hd-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}

.run.secondary {
  border-color: rgba(255, 255, 255, 0.2);
  background: rgba(255, 255, 255, 0.06);
  color: var(--mist);
}

.eyebrow {
  margin: 0 0 4px;
  font-size: 0.62rem;
  letter-spacing: 0.28em;
  text-transform: uppercase;
  color: var(--gold-muted);
  font-weight: 700;
}

.h2 {
  margin: 0;
  font-family: var(--font-display);
  font-size: 1.25rem;
  font-weight: 800;
  color: var(--mist);
}

.sub {
  margin: 8px 0 0;
  font-size: 0.78rem;
  color: var(--mist-dim);
}

.run {
  font-family: var(--font-display);
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.12em;
  padding: 12px 22px;
  border-radius: 10px;
  border: 1px solid rgba(62, 224, 255, 0.45);
  background: rgba(62, 224, 255, 0.12);
  color: var(--meridian);
  cursor: pointer;
  transition: background 0.2s var(--ease-out-expo), transform 0.15s ease;
}

.run.gold {
  border-color: rgba(232, 197, 71, 0.45);
  background: rgba(232, 197, 71, 0.12);
  color: var(--gold);
}

.run:hover:not(:disabled) {
  filter: brightness(1.08);
  transform: translateY(-1px);
}

.run:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.form {
  display: flex;
  flex-wrap: wrap;
  gap: 14px 20px;
  margin-bottom: 18px;
  padding-bottom: 18px;
  border-bottom: 1px solid var(--rule-faint);
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 100px;
}

.field.wide {
  flex: 1;
  min-width: 200px;
}

.lbl {
  font-size: 0.68rem;
  letter-spacing: 0.06em;
  color: var(--mist-dim);
}

.inp {
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid var(--rule-faint);
  background: var(--ink);
  color: var(--mist);
  font-size: 0.88rem;
}

.inp:focus {
  outline: none;
  border-color: rgba(62, 224, 255, 0.45);
}

.hint {
  font-size: 0.68rem;
  color: var(--mist-dim);
}

.err {
  padding: 10px 12px;
  border-radius: 8px;
  background: rgba(255, 92, 69, 0.1);
  border: 1px solid rgba(255, 92, 69, 0.25);
  color: var(--ember);
  font-size: 0.85rem;
  margin-bottom: 14px;
}

.metrics {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 12px 16px;
  margin-bottom: 18px;
}

.m {
  padding: 12px 14px;
  border-radius: 10px;
  background: rgba(0, 0, 0, 0.25);
  border: 1px solid var(--rule-faint);
}

.m.wide {
  grid-column: 1 / -1;
}

.mk {
  display: block;
  font-size: 0.65rem;
  letter-spacing: 0.08em;
  color: var(--mist-dim);
  margin-bottom: 4px;
}

.mv {
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--mist);
}

.mv.sm {
  font-size: 0.82rem;
  font-weight: 600;
}

.mv.up {
  color: var(--jade);
}

.mv.down {
  color: var(--ember);
}

.chart-wrap {
  height: 320px;
  min-height: 240px;
}

.chart {
  width: 100%;
  height: 100%;
}

.note {
  margin: 14px 0 0;
  font-size: 0.72rem;
  line-height: 1.5;
  color: var(--mist-dim);
}

.codes-toolbar {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  margin-bottom: 8px;
}

.block-label {
  margin: 0;
  font-size: 0.68rem;
  letter-spacing: 0.06em;
  color: var(--mist-dim);
}

.linkish {
  font-family: var(--font-mono);
  font-size: 0.68rem;
  padding: 4px 10px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--meridian);
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 3px;
}

.linkish:hover {
  color: var(--mist);
}

.codes-ta {
  width: 100%;
  margin-bottom: 16px;
  padding: 12px 14px;
  border-radius: 10px;
  border: 1px solid var(--rule-faint);
  background: var(--ink);
  color: var(--mist);
  font-size: 0.82rem;
  line-height: 1.45;
  resize: vertical;
  min-height: 100px;
}

.codes-ta:focus {
  outline: none;
  border-color: rgba(232, 197, 71, 0.35);
}

.scan-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 4px;
  margin: 0 0 12px;
  font-size: 0.72rem;
  line-height: 1.5;
  color: var(--mist-dim);
}

.scan-meta-sep {
  opacity: 0.45;
  user-select: none;
}

.scan-wrap {
  overflow-x: auto;
  margin-top: 8px;
}

.scan-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.78rem;
}

.scan-table th,
.scan-table td {
  padding: 10px 12px;
  text-align: left;
  border-bottom: 1px solid var(--rule-faint);
}

.scan-table th {
  color: var(--gold-muted);
  font-family: var(--font-display);
  font-size: 0.62rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.scan-table td.up {
  color: var(--jade);
}

.scan-table td.down {
  color: var(--ember);
}

.err-cell {
  color: var(--ember);
  font-size: 0.72rem;
  max-width: 240px;
}

.wl-chips {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 10px;
}

.wl-chips-lbl {
  font-size: 0.58rem;
  letter-spacing: 0.12em;
  color: var(--mist-dim);
  font-weight: 700;
}

.wl-chip {
  font-size: 0.62rem;
  padding: 4px 8px;
  border-radius: 6px;
  border: 1px solid rgba(62, 224, 255, 0.25);
  background: rgba(62, 224, 255, 0.08);
  color: var(--meridian);
  cursor: pointer;
}

.wl-chip:hover {
  border-color: rgba(62, 224, 255, 0.45);
}

.codes-toolbar-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 16px;
  margin-top: 6px;
}

.sig-line {
  margin: 10px 0 0;
  font-size: 0.72rem;
  color: var(--mist-dim);
  line-height: 1.45;
}

.sig-err {
  margin: 10px 0 0;
  font-size: 0.72rem;
  color: #ff9a9a;
}

.run-archive {
  margin-top: 28px;
  padding-top: 20px;
  border-top: 1px solid var(--rule-faint);
}

.run-archive-hd {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.run-archive-tools {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.run-archive-search {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.run-search-input {
  flex: 1 1 160px;
  min-width: 140px;
  max-width: 360px;
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid var(--rule-faint);
  background: rgba(8, 8, 12, 0.65);
  color: var(--mist);
  font-size: 0.68rem;
}

.run-search-input::placeholder {
  color: var(--mist-dim);
}

.run-filter-label {
  margin: 0;
}

.run-kind-select {
  min-width: min(100%, 360px);
  max-width: 100%;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid var(--rule-faint);
  background: rgba(8, 8, 12, 0.65);
  color: var(--mist);
  font-size: 0.68rem;
  cursor: pointer;
}

.run-kind-map-hint {
  margin: 0 0 10px;
  font-size: 0.62rem;
  line-height: 1.45;
  color: var(--paper-muted);
  word-break: break-word;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

.h3 {
  margin: 0;
  font-family: var(--font-display);
  font-size: 0.95rem;
  color: var(--mist);
}

.run-archive .ghost {
  font-size: 0.62rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  padding: 8px 14px;
  border-radius: 8px;
  border: 1px solid var(--rule-faint);
  background: rgba(8, 8, 12, 0.5);
  color: var(--mist);
  cursor: pointer;
}

.run-archive-note {
  margin: 0 0 10px;
  font-size: 0.68rem;
  color: var(--mist-dim);
  line-height: 1.45;
}

.save-tip {
  margin: 0 0 8px;
  font-size: 0.72rem;
  color: var(--gain);
}

.meta {
  margin: 0 0 8px;
  font-size: 0.68rem;
  color: var(--mist-dim);
}

.run-history-pagination {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 0 0 10px;
}

.run-pg-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px 14px;
}

.run-pg-controls {
  justify-content: flex-start;
  gap: 18px 24px;
}

.run-history-pagination .meta-range {
  color: var(--mist-dim);
}

.run-page-btns {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 8px;
}

.run-limit-label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 0.72rem;
  color: var(--mist-dim);
}

.run-limit-select {
  min-width: 58px;
  padding: 6px 8px;
  border-radius: 8px;
  border: 1px solid var(--rule-faint);
  background: rgba(8, 8, 12, 0.65);
  color: var(--mist);
  font-size: 0.68rem;
  cursor: pointer;
}

.run-jump-wrap {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 10px;
}

.run-jump-lbl {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.72rem;
  color: var(--mist-dim);
}

.run-jump-input {
  width: 56px;
  padding: 6px 8px;
  border-radius: 6px;
  border: 1px solid var(--rule-faint);
  background: rgba(8, 8, 12, 0.65);
  color: var(--mist);
  font-size: 0.72rem;
}

.run-archive-pick-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 14px;
  margin: 0 0 12px;
}

.run-pick-all {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 0.72rem;
  color: var(--mist-dim);
  user-select: none;
}

.run-pick-all input {
  width: 15px;
  height: 15px;
  cursor: pointer;
  accent-color: var(--meridian);
}

.run-ghost-tight {
  padding: 6px 12px;
  font-size: 0.62rem;
}

.run-batch-del {
  font-size: 0.65rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  padding: 8px 16px;
  border-radius: 8px;
  border: 1px solid rgba(255, 120, 120, 0.45);
  background: rgba(44, 14, 14, 0.55);
  color: #ffb8b8;
  cursor: pointer;
}

.run-batch-del:hover:not(:disabled) {
  border-color: rgba(255, 154, 154, 0.65);
  color: #ffd6d6;
}

.run-batch-del:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.run-zip-btn {
  font-size: 0.65rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  padding: 8px 16px;
  border-radius: 8px;
  border: 1px solid rgba(232, 197, 71, 0.45);
  background: rgba(36, 28, 8, 0.55);
  color: #f0d78a;
  cursor: pointer;
}

.run-zip-btn:hover:not(:disabled) {
  border-color: rgba(232, 197, 71, 0.7);
  color: #fff2c4;
}

.run-zip-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.run-ul {
  list-style: none;
  margin: 0 0 14px;
  padding: 0;
}

.run-li {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  padding: 8px 0;
  border-bottom: 1px solid rgba(42, 40, 53, 0.45);
  font-size: 0.74rem;
}

.run-li-check {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
  margin: 0;
  cursor: pointer;
}

.run-li-check input {
  width: 15px;
  height: 15px;
  cursor: pointer;
  accent-color: var(--meridian);
}

.run-li-btn {
  background: none;
  border: none;
  color: var(--meridian);
  cursor: pointer;
  font: inherit;
  text-decoration: underline;
  padding: 0;
}

.run-li-actions {
  margin-left: auto;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.run-li-exp {
  font-size: 0.65rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  padding: 4px 10px;
  border-radius: 6px;
  border: 1px solid rgba(62, 224, 255, 0.35);
  background: rgba(10, 28, 36, 0.55);
  color: #9aefff;
  cursor: pointer;
}

.run-li-exp:hover:not(:disabled) {
  border-color: rgba(62, 224, 255, 0.55);
  color: #c4f7ff;
}

.run-li-exp:disabled {
  opacity: 0.55;
  cursor: wait;
}

.run-li-del {
  font-size: 0.65rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  padding: 4px 10px;
  border-radius: 6px;
  border: 1px solid rgba(255, 120, 120, 0.35);
  background: rgba(40, 12, 12, 0.45);
  color: #ffb4b4;
  cursor: pointer;
}

.run-li-del:hover {
  border-color: rgba(255, 154, 154, 0.55);
  color: #ffd0d0;
}

.run-li-sum {
  color: var(--mist);
  flex: 1;
  min-width: 120px;
}

.run-detail {
  margin-top: 10px;
}

.run-detail-hd {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
}

.run-detail-id {
  margin: 0;
}

.run-export-btn {
  font-size: 0.65rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  padding: 8px 14px;
  border-radius: 8px;
  border: 1px solid rgba(62, 224, 255, 0.4);
  background: rgba(10, 32, 40, 0.65);
  color: #9aefff;
  cursor: pointer;
}

.run-export-btn:hover {
  border-color: rgba(62, 224, 255, 0.65);
  color: #d2fbff;
}

.run-pre {
  max-height: 280px;
  overflow: auto;
  margin: 6px 0 14px;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid var(--rule-faint);
  background: rgba(6, 6, 10, 0.65);
  font-size: 0.65rem;
  line-height: 1.35;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
