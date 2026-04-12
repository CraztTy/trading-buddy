<script setup>
import { computed, onMounted, ref, watch } from "vue";
import VChart from "vue-echarts";
import { apiUrl } from "../composables/api.js";

const props = defineProps({
  code: { type: String, default: "sh.000001" },
});

const emit = defineEmits(["select-code", "open-market"]);

/** @typedef {{ id: string; window: string; column: string; series_keys: string[]; notes?: string | null }} FactorCatalogOp */

const localCode = ref(props.code);
const column = ref("close");
const op = ref("rolling_mean");
const windowStr = ref("20");
const bollKStr = ref("2");
const macdFastStr = ref("12");
const macdSlowStr = ref("26");
const macdSigStr = ref("9");
const kdjM1Str = ref("3");
const kdjM2Str = ref("3");
const limitStr = ref("500");
const startDate = ref("");
const endDate = ref("");

const loading = ref(false);
const csvBusy = ref(false);
const errMsg = ref("");
/** @type {import('vue').Ref<null | Record<string, unknown>>} */
const preview = ref(null);

/** 自 GET /api/factors/catalog；空数组表示尚未加载成功（用本地回退规则与静态下拉里项） */
/** @type {import('vue').Ref<FactorCatalogOp[]>} */
const catalogOps = ref([]);
const catalogLoading = ref(true);
const catalogLoadErr = ref("");

/** 下拉展示顺序（与后端 catalog 并存：有目录时按此排序） */
const OP_UI_ORDER = [
  "rolling_sum",
  "rolling_mean",
  "rolling_std",
  "rolling_zscore",
  "rolling_max",
  "rolling_min",
  "ema",
  "pct_change_1",
  "pct_change_n",
  "roc",
  "trix",
  "diff_n",
  "rsi",
  "atr",
  "adx",
  "aroon",
  "bollinger",
  "donchian",
  "macd",
  "kdj",
  "cci",
  "williams_r",
  "mfi",
  "obv",
  "vwap",
];

const OP_SELECT_LABELS = {
  rolling_sum: "rolling_sum",
  rolling_mean: "rolling_mean",
  rolling_std: "rolling_std",
  rolling_zscore: "rolling_zscore",
  rolling_max: "rolling_max",
  rolling_min: "rolling_min",
  ema: "ema",
  pct_change_1: "pct_change_1",
  pct_change_n: "pct_change_n",
  roc: "roc（变动率 %）",
  trix: "trix（三重 EMA 变动率 %）",
  diff_n: "diff_n",
  rsi: "rsi（Wilder）",
  atr: "atr（Wilder）",
  adx: "adx（DMI / Wilder ADX）",
  aroon: "aroon（Up / Down / Osc）",
  bollinger: "bollinger（SMA ± k·σ）",
  donchian: "donchian（唐奇安 H/L）",
  macd: "macd（DIF/DEA/HIST）",
  kdj: "kdj（K/D/J）",
  cci: "cci（商品通道）",
  williams_r: "williams_r（%R）",
  mfi: "mfi（资金流量）",
  obv: "obv（能量潮）",
  vwap: "vwap（典型价加权；留空 window=日级累计）",
};

/** @param {FactorCatalogOp | { id: string }} row */
function opSelectLabel(row) {
  const id = row.id;
  return OP_SELECT_LABELS[id] || id;
}

/** @param {FactorCatalogOp[]} raw */
function orderCatalogOpsForUi(raw) {
  const byId = new Map(raw.map((o) => [o.id, o]));
  const seen = new Set();
  /** @type {FactorCatalogOp[]} */
  const out = [];
  for (const id of OP_UI_ORDER) {
    const o = byId.get(id);
    if (o) {
      out.push(o);
      seen.add(id);
    }
  }
  for (const o of raw) {
    if (!seen.has(o.id)) out.push(o);
  }
  return out;
}

/** 目录未就绪时的静态下拉里项（与 OP_UI_ORDER 一致） */
const staticOpOptions = computed(() =>
  OP_UI_ORDER.map((id) => ({ id, label: OP_SELECT_LABELS[id] || id })),
);

const opSelectRows = computed(() => {
  if (catalogOps.value.length) {
    return catalogOps.value.map((row) => ({ id: row.id, label: opSelectLabel(row) }));
  }
  return staticOpOptions.value;
});

const currentOpEntry = computed(() => catalogOps.value.find((o) => o.id === op.value) || null);

/** 目录未加载前与后端契约对齐的本地回退 */
function legacyNeedsWindow(ov) {
  return (
    ov === "rolling_sum" ||
    ov === "rolling_mean" ||
    ov === "rolling_std" ||
    ov === "rolling_zscore" ||
    ov === "rolling_max" ||
    ov === "rolling_min" ||
    ov === "ema" ||
    ov === "pct_change_n" ||
    ov === "diff_n" ||
    ov === "rsi" ||
    ov === "atr" ||
    ov === "bollinger" ||
    ov === "kdj" ||
    ov === "cci" ||
    ov === "williams_r" ||
    ov === "mfi" ||
    ov === "roc" ||
    ov === "trix" ||
    ov === "adx" ||
    ov === "aroon" ||
    ov === "donchian"
  );
}

function legacyColumnIgnored(ov) {
  return (
    ov === "atr" ||
    ov === "kdj" ||
    ov === "cci" ||
    ov === "williams_r" ||
    ov === "mfi" ||
    ov === "obv" ||
    ov === "adx" ||
    ov === "aroon" ||
    ov === "donchian" ||
    ov === "vwap"
  );
}

const needsWindow = computed(() => {
  const e = currentOpEntry.value;
  if (e) return e.window === "required";
  return legacyNeedsWindow(op.value);
});

const columnIgnored = computed(() => {
  const e = currentOpEntry.value;
  if (e) return e.column === "ignored";
  return legacyColumnIgnored(op.value);
});

const needsMacdParams = computed(() => op.value === "macd");

const needsKdjParams = computed(() => op.value === "kdj");

const needsBbK = computed(() => op.value === "bollinger");

/** VWAP：window 可选（留空=日级累计）；其余算子按 needsWindow */
const windowFieldEnabled = computed(() => {
  const e = currentOpEntry.value;
  if (e) return e.window === "required" || e.window === "optional";
  return legacyNeedsWindow(op.value) || op.value === "vwap";
});

watch(
  () => props.code,
  (c) => {
    localCode.value = c;
  }
);

onMounted(async () => {
  catalogLoadErr.value = "";
  catalogLoading.value = true;
  try {
    const res = await fetch(apiUrl("factors/catalog"));
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      const d = body?.detail;
      catalogLoadErr.value =
        typeof d === "string"
          ? d
          : Array.isArray(d)
            ? d.map((x) => x?.msg || JSON.stringify(x)).join("; ")
            : `HTTP ${res.status}`;
      return;
    }
    if (!Array.isArray(body?.ops) || body.ops.length === 0) {
      catalogLoadErr.value = "算子目录为空";
      return;
    }
    catalogOps.value = orderCatalogOpsForUi(body.ops);
    if (!catalogOps.value.some((o) => o.id === op.value)) {
      op.value = "rolling_mean";
    }
  } catch (e) {
    catalogLoadErr.value = e?.message || "无法加载算子目录";
  } finally {
    catalogLoading.value = false;
  }
});

watch(op, (o) => {
  if (o === "pct_change_1" || o === "obv" || o === "vwap") windowStr.value = "";
  else if (!windowStr.value.trim()) windowStr.value = "20";
  if (o === "bollinger" && !bollKStr.value.trim()) bollKStr.value = "2";
  if (o === "macd") {
    if (!macdFastStr.value.trim()) macdFastStr.value = "12";
    if (!macdSlowStr.value.trim()) macdSlowStr.value = "26";
    if (!macdSigStr.value.trim()) macdSigStr.value = "9";
  }
  if (o === "kdj") {
    if (!windowStr.value.trim()) windowStr.value = "9";
    if (!kdjM1Str.value.trim()) kdjM1Str.value = "3";
    if (!kdjM2Str.value.trim()) kdjM2Str.value = "3";
  }
  if (o === "cci" && !windowStr.value.trim()) windowStr.value = "20";
  if (o === "williams_r" && !windowStr.value.trim()) windowStr.value = "14";
  if (o === "mfi" && !windowStr.value.trim()) windowStr.value = "14";
  if (o === "roc" && !windowStr.value.trim()) windowStr.value = "12";
  if (o === "trix" && !windowStr.value.trim()) windowStr.value = "14";
  if (o === "adx" && !windowStr.value.trim()) windowStr.value = "14";
  if (o === "aroon" && !windowStr.value.trim()) windowStr.value = "14";
  if (o === "donchian" && !windowStr.value.trim()) windowStr.value = "20";
});

function normalizeCode(input) {
  let code = String(input || "").trim().toLowerCase();
  if (!code) return props.code;
  if (!code.startsWith("sh.") && !code.startsWith("sz.") && !code.startsWith("bj.")) {
    if (code.startsWith("6")) code = `sh.${code}`;
    else if (code.startsWith("0") || code.startsWith("3")) code = `sz.${code}`;
    else code = `sh.${code}`;
  }
  return code;
}

function onCodeEnter(e) {
  if (e.key !== "Enter") return;
  const next = normalizeCode(e.target.value);
  e.target.blur();
  localCode.value = next;
  emit("select-code", next);
}

/** @returns {URLSearchParams | null} */
function buildQueryParams() {
  const code = normalizeCode(localCode.value);
  localCode.value = code;

  const params = new URLSearchParams();
  params.set("code", code);
  params.set("column", column.value);
  params.set("op", op.value);
  const lim = Math.min(5000, Math.max(30, parseInt(limitStr.value, 10) || 500));
  limitStr.value = String(lim);
  params.set("limit", String(lim));

  if (needsWindow.value) {
    const w = parseInt(windowStr.value, 10);
    if (!Number.isFinite(w) || w < 1) {
      errMsg.value = "请填写有效的 window（正整数）";
      return null;
    }
    if (op.value === "kdj" && w < 2) {
      errMsg.value = "KDJ 的 window 为 RSV 周期 n，须 >= 2";
      return null;
    }
    if (op.value === "cci" && w < 2) {
      errMsg.value = "CCI 的 window 为周期 period，须 >= 2";
      return null;
    }
    if (op.value === "williams_r" && w < 2) {
      errMsg.value = "Williams %R 的 window 为周期 period，须 >= 2";
      return null;
    }
    if (op.value === "mfi" && w < 2) {
      errMsg.value = "MFI 的 window 为周期 period，须 >= 2";
      return null;
    }
    if (op.value === "adx" && w < 2) {
      errMsg.value = "ADX/DMI 的 window 为周期 period，须 >= 2";
      return null;
    }
    if (op.value === "aroon" && w < 2) {
      errMsg.value = "Aroon 的 window 为周期 period，须 >= 2";
      return null;
    }
    params.set("window", String(w));
  }

  if (op.value === "vwap") {
    const t = windowStr.value.trim();
    if (t !== "") {
      const w = parseInt(t, 10);
      if (!Number.isFinite(w) || w < 1) {
        errMsg.value = "VWAP 滚动请填写 window≥1，或留空为日级（自首根累计）";
        return null;
      }
      params.set("window", String(w));
    }
  }

  const sd = startDate.value.trim();
  const ed = endDate.value.trim();
  if (sd) params.set("start_date", sd);
  if (ed) params.set("end_date", ed);

  if (op.value === "bollinger") {
    const bk = parseFloat(bollKStr.value);
    if (!Number.isFinite(bk) || bk <= 0) {
      errMsg.value = "请填写有效的 bb_k（正数，默认 2）";
      return null;
    }
    params.set("bb_k", String(bk));
  }

  if (op.value === "macd") {
    const mf = parseInt(macdFastStr.value, 10);
    const ms = parseInt(macdSlowStr.value, 10);
    const sg = parseInt(macdSigStr.value, 10);
    if (!Number.isFinite(mf) || mf < 1 || !Number.isFinite(ms) || ms < 1 || !Number.isFinite(sg) || sg < 1) {
      errMsg.value = "MACD 请填写有效的 fast / slow / signal（正整数）";
      return null;
    }
    if (mf >= ms) {
      errMsg.value = "MACD 须满足 fast < slow（常见 12 / 26）";
      return null;
    }
    params.set("macd_fast", String(mf));
    params.set("macd_slow", String(ms));
    params.set("macd_signal", String(sg));
  }

  if (op.value === "kdj") {
    const m1 = parseInt(kdjM1Str.value, 10);
    const m2 = parseInt(kdjM2Str.value, 10);
    if (!Number.isFinite(m1) || m1 < 1 || !Number.isFinite(m2) || m2 < 1) {
      errMsg.value = "KDJ 请填写有效的 m1 / m2（正整数，默认 3）";
      return null;
    }
    params.set("kdj_m1", String(m1));
    params.set("kdj_m2", String(m2));
  }

  return params;
}

async function loadPreview() {
  errMsg.value = "";
  preview.value = null;
  const params = buildQueryParams();
  if (!params) return;

  loading.value = true;
  try {
    params.set("response_format", "json");
    const res = await fetch(`${apiUrl(`factors/preview?${params.toString()}`)}`);
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      const d = body?.detail;
      errMsg.value =
        typeof d === "string"
          ? d
          : Array.isArray(d)
            ? d.map((x) => x?.msg || JSON.stringify(x)).join("; ")
            : `${res.status} ${res.statusText}`;
      return;
    }
    preview.value = body;
    emit("select-code", normalizeCode(localCode.value));
  } catch (e) {
    errMsg.value = e?.message || "请求失败";
  } finally {
    loading.value = false;
  }
}

async function downloadCsv() {
  errMsg.value = "";
  const params = buildQueryParams();
  if (!params) return;
  params.set("response_format", "csv");

  csvBusy.value = true;
  try {
    const res = await fetch(`${apiUrl(`factors/preview?${params.toString()}`)}`);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      const d = body?.detail;
      errMsg.value =
        typeof d === "string"
          ? d
          : Array.isArray(d)
            ? d.map((x) => x?.msg || JSON.stringify(x)).join("; ")
            : `${res.status} ${res.statusText}`;
      return;
    }
    const blob = await res.blob();
    const cd = res.headers.get("content-disposition") || "";
    const m = cd.match(/filename="([^"]+)"/i);
    const fallback = `factor_${normalizeCode(localCode.value)}_${column.value}_${op.value}.csv`;
    const name = m ? m[1] : fallback;
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    errMsg.value = e?.message || "导出失败";
  } finally {
    csvBusy.value = false;
  }
}

function previewSeriesReady(p) {
  if (!p?.trade_dates?.length || !p.series || typeof p.series !== "object") return false;
  const s = p.series;
  if (Array.isArray(s.mid) && Array.isArray(s.upper) && Array.isArray(s.lower)) return true;
  if (Array.isArray(s.dif) && Array.isArray(s.dea) && Array.isArray(s.hist)) return true;
  if (Array.isArray(s.k) && Array.isArray(s.d) && Array.isArray(s.j)) return true;
  if (Array.isArray(s.plus_di) && Array.isArray(s.minus_di) && Array.isArray(s.adx)) return true;
  if (
    Array.isArray(s.aroon_up) &&
    Array.isArray(s.aroon_down) &&
    Array.isArray(s.aroon_osc)
  )
    return true;
  if (
    Array.isArray(s.dc_upper) &&
    Array.isArray(s.dc_mid) &&
    Array.isArray(s.dc_lower)
  )
    return true;
  if (Array.isArray(s.value)) return true;
  return false;
}

const chartOption = computed(() => {
  const p = preview.value;
  if (!p || !previewSeriesReady(p)) {
    if (loading.value) {
      return {
        backgroundColor: "transparent",
        title: {
          text: "加载中…",
          left: "center",
          top: "center",
          textStyle: { color: "#6d6a7a", fontSize: 13, fontFamily: "Noto Serif SC" },
        },
      };
    }
    const t = errMsg.value || "设置参数后点击「加载预览」";
    return {
      backgroundColor: "transparent",
      title: {
        text: t,
        left: "center",
        top: "center",
        textStyle: { color: "#6d6a7a", fontSize: 13, fontFamily: "Noto Serif SC" },
      },
    };
  }
  const dates = p.trade_dates;
  const toNum = (v) => (v === null || v === undefined ? null : Number(v));
  const s = p.series;
  const hasBollinger =
    Array.isArray(s.mid) && Array.isArray(s.upper) && Array.isArray(s.lower);
  const hasDonchian =
    Array.isArray(s.dc_upper) && Array.isArray(s.dc_mid) && Array.isArray(s.dc_lower);
  const hasMacd = Array.isArray(s.dif) && Array.isArray(s.dea) && Array.isArray(s.hist);
  const hasKdj = Array.isArray(s.k) && Array.isArray(s.d) && Array.isArray(s.j);
  const hasAdx =
    Array.isArray(s.plus_di) && Array.isArray(s.minus_di) && Array.isArray(s.adx);
  const hasAroon =
    Array.isArray(s.aroon_up) && Array.isArray(s.aroon_down) && Array.isArray(s.aroon_osc);
  const multi = hasBollinger || hasDonchian || hasMacd || hasKdj || hasAdx || hasAroon;
  const vals = hasBollinger
    ? s.mid.map(toNum)
    : hasDonchian
      ? s.dc_mid.map(toNum)
      : (s.value || []).map(toNum);

  const baseChart = {
    backgroundColor: "transparent",
    animation: true,
    animationDuration: 500,
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(8, 8, 12, 0.94)",
      borderColor: "rgba(232, 197, 71, 0.28)",
      textStyle: { color: "#b8b4c8", fontFamily: "IBM Plex Mono, monospace" },
    },
    grid: { left: "3%", right: "4%", top: multi ? "18%" : "14%", bottom: "18%", containLabel: true },
    legend: multi
      ? {
          top: 4,
          right: 8,
          textStyle: { color: "#6d6a7a", fontSize: 10, fontFamily: "IBM Plex Mono" },
        }
      : undefined,
    xAxis: {
      type: "category",
      data: dates,
      axisLine: { lineStyle: { color: "#2a2835" } },
      axisLabel: { color: "#6d6a7a", fontSize: 9, fontFamily: "IBM Plex Mono", rotate: 40 },
    },
    yAxis: {
      scale: true,
      position: "right",
      axisLine: { lineStyle: { color: "#2a2835" } },
      axisLabel: { color: "#6d6a7a", fontSize: 10, fontFamily: "IBM Plex Mono" },
      splitLine: { lineStyle: { color: "#1a1824" } },
    },
    dataZoom: [
      { type: "inside", xAxisIndex: 0, start: Math.max(0, 100 - (dates.length > 40 ? 35 : 100)), end: 100 },
      {
        type: "slider",
        xAxisIndex: 0,
        start: Math.max(0, 100 - (dates.length > 40 ? 35 : 100)),
        end: 100,
        height: 22,
        bottom: 4,
        borderColor: "transparent",
        backgroundColor: "#0a0a0f",
        fillerColor: "rgba(62, 224, 255, 0.12)",
        handleStyle: { color: "#3ee0ff" },
        textStyle: { color: "#6d6a7a" },
      },
    ],
  };

  if (hasBollinger) {
    const up = s.upper.map(toNum);
    const lo = s.lower.map(toNum);
    return {
      ...baseChart,
      series: [
        {
          name: "upper",
          type: "line",
          data: up,
          connectNulls: false,
          smooth: false,
          lineStyle: { width: 1, color: "rgba(122, 136, 153, 0.95)", type: "dashed" },
          itemStyle: { color: "#7a8899" },
          symbol: "none",
          showSymbol: false,
        },
        {
          name: "lower",
          type: "line",
          data: lo,
          connectNulls: false,
          smooth: false,
          lineStyle: { width: 1, color: "rgba(122, 136, 153, 0.95)", type: "dashed" },
          itemStyle: { color: "#7a8899" },
          symbol: "none",
          showSymbol: false,
        },
        {
          name: "mid",
          type: "line",
          data: vals,
          connectNulls: false,
          smooth: false,
          lineStyle: { width: 1.6, color: "#e8c547" },
          itemStyle: { color: "#e8c547" },
          symbol: "circle",
          symbolSize: 4,
          showSymbol: dates.length <= 40,
        },
      ],
    };
  }

  if (hasDonchian) {
    const up = s.dc_upper.map(toNum);
    const lo = s.dc_lower.map(toNum);
    return {
      ...baseChart,
      series: [
        {
          name: "dc_upper",
          type: "line",
          data: up,
          connectNulls: false,
          smooth: false,
          lineStyle: { width: 1, color: "rgba(122, 184, 153, 0.95)", type: "dashed" },
          itemStyle: { color: "#7ab899" },
          symbol: "none",
          showSymbol: false,
        },
        {
          name: "dc_lower",
          type: "line",
          data: lo,
          connectNulls: false,
          smooth: false,
          lineStyle: { width: 1, color: "rgba(122, 184, 153, 0.95)", type: "dashed" },
          itemStyle: { color: "#7ab899" },
          symbol: "none",
          showSymbol: false,
        },
        {
          name: "dc_mid",
          type: "line",
          data: vals,
          connectNulls: false,
          smooth: false,
          lineStyle: { width: 1.6, color: "#e8a547" },
          itemStyle: { color: "#e8a547" },
          symbol: "circle",
          symbolSize: 4,
          showSymbol: dates.length <= 40,
        },
      ],
    };
  }

  if (hasMacd) {
    const dDif = s.dif.map(toNum);
    const dDea = s.dea.map(toNum);
    const dHist = s.hist.map(toNum);
    return {
      ...baseChart,
      series: [
        {
          name: "dif",
          type: "line",
          data: dDif,
          connectNulls: false,
          smooth: false,
          lineStyle: { width: 1.4, color: "#3ee0ff" },
          itemStyle: { color: "#3ee0ff" },
          symbol: "circle",
          symbolSize: 3,
          showSymbol: dates.length <= 40,
        },
        {
          name: "dea",
          type: "line",
          data: dDea,
          connectNulls: false,
          smooth: false,
          lineStyle: { width: 1.2, color: "#e8c547" },
          itemStyle: { color: "#e8c547" },
          symbol: "none",
          showSymbol: false,
        },
        {
          name: "hist",
          type: "line",
          data: dHist,
          connectNulls: false,
          smooth: false,
          lineStyle: { width: 1, color: "#7abf9e" },
          itemStyle: { color: "#7abf9e" },
          symbol: "none",
          showSymbol: false,
        },
      ],
    };
  }

  if (hasKdj) {
    const dK = s.k.map(toNum);
    const dD = s.d.map(toNum);
    const dJ = s.j.map(toNum);
    return {
      ...baseChart,
      series: [
        {
          name: "k",
          type: "line",
          data: dK,
          connectNulls: false,
          smooth: false,
          lineStyle: { width: 1.3, color: "#3ee0ff" },
          itemStyle: { color: "#3ee0ff" },
          symbol: "circle",
          symbolSize: 3,
          showSymbol: dates.length <= 40,
        },
        {
          name: "d",
          type: "line",
          data: dD,
          connectNulls: false,
          smooth: false,
          lineStyle: { width: 1.2, color: "#e8c547" },
          itemStyle: { color: "#e8c547" },
          symbol: "none",
          showSymbol: false,
        },
        {
          name: "j",
          type: "line",
          data: dJ,
          connectNulls: false,
          smooth: false,
          lineStyle: { width: 1, color: "#c99cff" },
          itemStyle: { color: "#c99cff" },
          symbol: "none",
          showSymbol: false,
        },
      ],
    };
  }

  if (hasAdx) {
    const dP = s.plus_di.map(toNum);
    const dM = s.minus_di.map(toNum);
    const dA = s.adx.map(toNum);
    return {
      ...baseChart,
      series: [
        {
          name: "+di",
          type: "line",
          data: dP,
          connectNulls: false,
          smooth: false,
          lineStyle: { width: 1.3, color: "#3ee0ff" },
          itemStyle: { color: "#3ee0ff" },
          symbol: "circle",
          symbolSize: 3,
          showSymbol: dates.length <= 40,
        },
        {
          name: "-di",
          type: "line",
          data: dM,
          connectNulls: false,
          smooth: false,
          lineStyle: { width: 1.2, color: "#e8c547" },
          itemStyle: { color: "#e8c547" },
          symbol: "none",
          showSymbol: false,
        },
        {
          name: "adx",
          type: "line",
          data: dA,
          connectNulls: false,
          smooth: false,
          lineStyle: { width: 1.4, color: "#c99cff" },
          itemStyle: { color: "#c99cff" },
          symbol: "none",
          showSymbol: false,
        },
      ],
    };
  }

  if (hasAroon) {
    const u = s.aroon_up.map(toNum);
    const dn = s.aroon_down.map(toNum);
    const os = s.aroon_osc.map(toNum);
    return {
      ...baseChart,
      series: [
        {
          name: "up",
          type: "line",
          data: u,
          connectNulls: false,
          smooth: false,
          lineStyle: { width: 1.3, color: "#3ee0ff" },
          itemStyle: { color: "#3ee0ff" },
          symbol: "circle",
          symbolSize: 3,
          showSymbol: dates.length <= 40,
        },
        {
          name: "down",
          type: "line",
          data: dn,
          connectNulls: false,
          smooth: false,
          lineStyle: { width: 1.2, color: "#e8c547" },
          itemStyle: { color: "#e8c547" },
          symbol: "none",
          showSymbol: false,
        },
        {
          name: "osc",
          type: "line",
          data: os,
          connectNulls: false,
          smooth: false,
          lineStyle: { width: 1.2, color: "#7abf9e" },
          itemStyle: { color: "#7abf9e" },
          symbol: "none",
          showSymbol: false,
        },
      ],
    };
  }

  const label = `${p.op} · ${p.column}`;
  return {
    ...baseChart,
    series: [
      {
        name: label,
        type: "line",
        data: vals,
        connectNulls: false,
        smooth: false,
        lineStyle: { width: 1.5, color: "#3ee0ff" },
        itemStyle: { color: "#3ee0ff" },
        symbol: "circle",
        symbolSize: 4,
        showSymbol: dates.length <= 40,
      },
    ],
  };
});
</script>

<template>
  <section class="factor-panel" aria-labelledby="factor-preview-title">
    <header class="head">
      <div>
        <h2 id="factor-preview-title" class="display">因子预览</h2>
        <p class="sub mono">
          GET <span class="mono">/api/factors/catalog</span> 驱动算子下拉 ·
          <span class="mono">/api/factors/preview</span>（<span class="mono">series</span> +
          <span class="mono">response_format=json|csv</span>）· 只读不落库
        </p>
      </div>
      <button type="button" class="ghost-link" @click="emit('open-market', normalizeCode(localCode))">
        打开行情看板（当前标的）
      </button>
    </header>

    <p v-if="catalogLoadErr" class="catalog-warn" role="status">
      {{ catalogLoadErr }}（已使用内置算子列表与校验规则，仍可预览）
    </p>
    <p
      v-else-if="!catalogLoading && catalogOps.length"
      class="mono factor-catalog-sync"
      data-testid="factor-catalog-sync"
      role="status"
    >
      已同步算子目录 {{ catalogOps.length }} 项
    </p>

    <div class="controls">
      <label class="field">
        <span class="lbl">标的</span>
        <input v-model="localCode" class="inp mono" type="text" aria-label="标的代码" @keydown="onCodeEnter" />
      </label>
      <label class="field" :class="{ dim: columnIgnored }">
        <span class="lbl">列</span>
        <select v-model="column" class="inp mono" aria-label="K 线列" :disabled="columnIgnored">
          <option value="open">open</option>
          <option value="high">high</option>
          <option value="low">low</option>
          <option value="close">close</option>
          <option value="volume">volume</option>
          <option value="amount">amount</option>
        </select>
      </label>
      <label class="field">
        <span class="lbl">算子</span>
        <select
          v-model="op"
          class="inp mono"
          aria-label="因子算子"
          :disabled="catalogLoading"
        >
          <option v-for="row in opSelectRows" :key="row.id" :value="row.id">{{ row.label }}</option>
        </select>
      </label>
      <label class="field wide" :class="{ dim: !needsKdjParams }">
        <span class="lbl">KDJ m1 / m2</span>
        <div class="row2">
          <input
            v-model="kdjM1Str"
            class="inp mono"
            type="text"
            inputmode="numeric"
            :disabled="!needsKdjParams"
            aria-label="KDJ 平滑参数 m1"
          />
          <input
            v-model="kdjM2Str"
            class="inp mono"
            type="text"
            inputmode="numeric"
            :disabled="!needsKdjParams"
            aria-label="KDJ 平滑参数 m2"
          />
        </div>
      </label>
      <label class="field wide" :class="{ dim: !needsMacdParams }">
        <span class="lbl">MACD fast/slow/sig</span>
        <div class="row3">
          <input
            v-model="macdFastStr"
            class="inp mono"
            type="text"
            inputmode="numeric"
            :disabled="!needsMacdParams"
            aria-label="MACD 快线 span"
          />
          <input
            v-model="macdSlowStr"
            class="inp mono"
            type="text"
            inputmode="numeric"
            :disabled="!needsMacdParams"
            aria-label="MACD 慢线 span"
          />
          <input
            v-model="macdSigStr"
            class="inp mono"
            type="text"
            inputmode="numeric"
            :disabled="!needsMacdParams"
            aria-label="MACD signal span"
          />
        </div>
      </label>
      <label class="field" :class="{ dim: !needsBbK }">
        <span class="lbl">bb_k</span>
        <input
          v-model="bollKStr"
          class="inp mono"
          type="text"
          inputmode="decimal"
          :disabled="!needsBbK"
          aria-label="布林带带宽倍数 bb_k"
        />
      </label>
      <label class="field" :class="{ dim: !windowFieldEnabled }">
        <span class="lbl"
          >window<template v-if="op === 'vwap'">（可选）</template></span
        >
        <input
          v-model="windowStr"
          class="inp mono"
          type="text"
          inputmode="numeric"
          :disabled="!windowFieldEnabled"
          aria-label="窗口或周期 n"
        />
      </label>
      <label class="field">
        <span class="lbl">limit</span>
        <input v-model="limitStr" class="inp mono" type="text" inputmode="numeric" aria-label="拉取 K 根数上限" />
      </label>
      <label class="field wide">
        <span class="lbl">start / end</span>
        <div class="row2">
          <input v-model="startDate" class="inp mono" type="date" aria-label="起始日" />
          <input v-model="endDate" class="inp mono" type="date" aria-label="结束日" />
        </div>
      </label>
      <div class="btn-row">
        <button type="button" class="btn-run" :disabled="loading || csvBusy" @click="loadPreview">
          {{ loading ? "加载中…" : "加载预览" }}
        </button>
        <button type="button" class="btn-csv" :disabled="loading || csvBusy" @click="downloadCsv">
          {{ csvBusy ? "导出中…" : "导出 CSV" }}
        </button>
      </div>
    </div>

    <p v-if="errMsg" class="err" role="alert">{{ errMsg }}</p>
    <p v-else-if="preview" class="meta mono factor-meta">
      共 <strong>{{ preview.bars }}</strong> 根 · {{ preview.column }} · {{ preview.op
      }}<template v-if="preview.window != null"> · window={{ preview.window }}</template
      ><template v-if="preview.meta && preview.meta.bb_k != null"> · k={{ preview.meta.bb_k }}</template
      ><template v-if="preview.meta && preview.op === 'macd' && preview.meta.fast != null">
        · MACD {{ preview.meta.fast }}/{{ preview.meta.slow }}/{{ preview.meta.signal }}</template
      ><template v-if="preview.meta && preview.op === 'kdj' && preview.meta.n != null">
        · KDJ n={{ preview.meta.n }} m1={{ preview.meta.m1 }} m2={{ preview.meta.m2 }}</template
      ><template v-if="preview.meta && preview.op === 'adx' && preview.meta.period != null">
        · ADX period={{ preview.meta.period }}</template
      ><template v-if="preview.meta && preview.op === 'aroon' && preview.meta.period != null">
        · Aroon period={{ preview.meta.period }}</template
      ><template v-if="preview.meta && preview.op === 'donchian' && preview.meta.period != null">
        · Donchian period={{ preview.meta.period }}</template
      ><template v-if="preview.meta && preview.op === 'vwap' && preview.meta.mode === 'cumulative'">
        · VWAP 日级（自首根累计）</template
      ><template
        v-if="preview.meta && preview.op === 'vwap' && preview.meta.mode === 'rolling' && preview.meta.period != null"
      >
        · VWAP 滚动 period={{ preview.meta.period }}</template
      >
      · limit={{ preview.limit }}
    </p>

    <div class="chart-wrap" :class="{ 'is-loading': loading && !preview }">
      <VChart class="chart" :option="chartOption" autoresize />
    </div>

    <p class="hint">
      与 <span class="mono">docs/FACTORS.md</span> 原语一致；JSON 为 <span class="mono">series</span>（单轨
      <span class="mono">value</span>（含 vwap 等），布林带 <span class="mono">mid/upper/lower</span>，MACD
      <span class="mono">dif/dea/hist</span>，KDJ <span class="mono">k/d/j</span>，ADX
      <span class="mono">plus_di/minus_di/adx</span>，Aroon <span class="mono">aroon_up/down/osc</span>，Donchian
      <span class="mono">dc_upper/dc_mid/dc_lower</span>）；<span class="mono">atr/kdj/cci/williams_r/adx</span> 用 high/low/close；<span class="mono">aroon</span> 与
      <span class="mono">donchian</span> 用 high/low；<span class="mono">mfi</span> 另用
      volume；<span class="mono">roc</span> 与 <span class="mono">pct_change_n</span> 同属按列 N 期涨跌幅 %；      <span class="mono">trix</span> 为同 span 三次
      <span class="mono">ema</span> 再相邻变动率 %；<span class="mono">obv</span> 用 close+volume；<span class="mono">vwap</span> 用
      high/low/close+volume（留空 window 为<strong>自首根累计</strong>，填 N 为<strong>滚动 N 根</strong>）。窗口不足处为
      <span class="mono">null</span>，图中为断点。
    </p>
  </section>
</template>

<style scoped>
.factor-panel {
  position: relative;
  border: 1px solid var(--rule);
  border-radius: 2px;
  background: linear-gradient(165deg, var(--ink-card) 0%, rgba(8, 8, 12, 0.6) 100%);
  padding: 20px 20px 16px;
  box-shadow: var(--shadow-lift);
}

.head {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 16px;
}

.display {
  margin: 0;
  font-family: var(--font-display);
  font-size: clamp(1.15rem, 2.6vw, 1.5rem);
  font-weight: 800;
  letter-spacing: -0.03em;
  color: var(--mist);
}

.sub {
  margin: 6px 0 0;
  font-size: 0.72rem;
  color: var(--paper-muted);
}

.ghost-link {
  font-family: var(--font-ui);
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  padding: 8px 14px;
  border-radius: 8px;
  border: 1px solid rgba(62, 224, 255, 0.28);
  background: rgba(62, 224, 255, 0.06);
  color: var(--meridian);
  cursor: pointer;
}

.ghost-link:hover {
  border-color: rgba(62, 224, 255, 0.45);
  color: var(--mist);
}

.controls {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 12px 14px;
  align-items: end;
  margin-bottom: 12px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.field.wide {
  grid-column: span 2;
}

.field.dim .lbl {
  opacity: 0.45;
}

.lbl {
  font-size: 0.62rem;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--brass-dim);
}

.inp {
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid var(--rule-faint);
  background: rgba(10, 10, 15, 0.75);
  color: var(--mist);
  font-size: 0.82rem;
}

.inp:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.row2 {
  display: flex;
  gap: 8px;
}

.row2 .inp {
  flex: 1;
  min-width: 0;
}

.row3 {
  display: flex;
  gap: 6px;
}

.row3 .inp {
  flex: 1;
  min-width: 0;
}

.btn-run {
  font-family: var(--font-display);
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.16em;
  padding: 10px 22px;
  border-radius: 10px;
  border: 1px solid rgba(232, 197, 71, 0.45);
  background: linear-gradient(145deg, var(--gold) 0%, #d4b84a 100%);
  color: var(--void);
  cursor: pointer;
}

.btn-run:disabled {
  opacity: 0.55;
  cursor: wait;
}

.err {
  margin: 0 0 10px;
  font-size: 0.85rem;
  color: #ff7a6e;
}

.catalog-warn {
  margin: 0 0 12px;
  font-size: 0.75rem;
  color: #e8a547;
  line-height: 1.45;
}

.factor-catalog-sync {
  margin: 0 0 10px;
  font-size: 0.62rem;
  line-height: 1.45;
  color: var(--paper-muted);
}

.meta {
  margin: 0 0 10px;
  font-size: 0.78rem;
  color: var(--paper-muted);
}

.meta strong {
  color: var(--meridian);
}

.chart-wrap {
  position: relative;
  height: min(420px, 52vh);
  min-height: 280px;
}

.chart {
  width: 100%;
  height: 100%;
}

.chart-wrap.is-loading {
  opacity: 0.65;
}

.hint {
  margin: 12px 0 0;
  font-size: 0.72rem;
  color: var(--paper-muted);
  line-height: 1.5;
}

.btn-row {
  grid-column: 1 / -1;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}

.btn-csv {
  font-family: var(--font-display);
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.12em;
  padding: 10px 18px;
  border-radius: 10px;
  border: 1px solid rgba(62, 224, 255, 0.35);
  background: rgba(62, 224, 255, 0.08);
  color: var(--meridian);
  cursor: pointer;
}

.btn-csv:hover:not(:disabled) {
  border-color: rgba(62, 224, 255, 0.55);
  color: var(--mist);
}

.btn-csv:disabled {
  opacity: 0.5;
  cursor: wait;
}

@media (min-width: 900px) {
  .btn-row {
    grid-column: auto / span 2;
  }
}
</style>
