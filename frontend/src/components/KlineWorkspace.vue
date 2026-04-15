<script setup>
import { computed, ref, watch } from "vue";
import VChart from "vue-echarts";
import { fetchJson } from "../composables/api.js";
import { writeClipboardText } from "../composables/clipboardWrite.js";
import { showToast } from "../composables/useToast.js";

/** 与后端一致；API 未返回 name 或后端未重启时仍显示中文名 */
const MAJOR_INDEX_NAMES = {
  "sh.000001": "上证指数",
  "sz.399001": "深证成指",
  "sz.399006": "创业板指",
  "sh.000300": "沪深300",
};

function chartTitle(code, apiName) {
  const k = (code || "").trim().toLowerCase();
  return (apiName && String(apiName).trim()) || MAJOR_INDEX_NAMES[k] || code;
}

const props = defineProps({
  code: { type: String, default: "sh.000001" },
});

const title = ref("上证指数");
const stockCode = ref(props.code);
const indicators = ref({ ma5: null, ma10: null, ma20: null });
const volumeLabel = ref("—");
const history = ref([]);
const chartError = ref("");
const chartLoading = ref(false);
/** 最近一次成功请求的 `GET …/klines/analysis/…?limit=60` 相对路径（含 `/api`） */
const lastKlineApiPath = ref("");
/** 复权类型: 1=后复权, 2=前复权, 3=不复权 */
const adjustFlag = ref("3");

function normalizeCode(input) {
  let code = input.trim().toLowerCase();
  if (!code) return props.code;
  if (!code.startsWith("sh.") && !code.startsWith("sz.") && !code.startsWith("bj.")) {
    if (code.startsWith("6")) code = `sh.${code}`;
    else if (code.startsWith("0") || code.startsWith("3")) code = `sz.${code}`;
    else code = `sh.${code}`;
  }
  return code;
}

function onSearchKey(e) {
  if (e.key !== "Enter") return;
  const next = normalizeCode(e.target.value);
  e.target.blur();
  emit("update:code", next);
}

const emit = defineEmits(["update:code"]);

watch(
  () => props.code,
  (c) => {
    stockCode.value = c;
    const k = (c || "").trim().toLowerCase();
    if (MAJOR_INDEX_NAMES[k]) title.value = MAJOR_INDEX_NAMES[k];
    loadKline(c);
  },
  { immediate: true }
);

watch(adjustFlag, () => {
  if (props.code) loadKline(props.code);
});

async function copyAnalysisApiPath() {
  const u = lastKlineApiPath.value.trim();
  if (!u) return;
  try {
    await writeClipboardText(u);
    showToast("已复制 K 线分析 API 路径（含 limit=60；curl 请自行拼接主机）", {
      type: "info",
      duration: 3200,
    });
  } catch {
    showToast("无法写入剪贴板，请检查浏览器权限", { type: "error" });
  }
}

async function loadKline(code) {
  chartLoading.value = true;
  chartError.value = "";
  const enc = encodeURIComponent(code);
  const qs = new URLSearchParams({ limit: "60", adjust_flag: adjustFlag.value });
  const relPath = `/api/klines/analysis/${enc}?${qs}`;
  try {
    const data = await fetchJson(`klines/analysis/${enc}?${qs}`, {
      toast: false,
    });
    lastKlineApiPath.value = relPath;
    if (data.error || !data.history?.length) {
      history.value = [];
      chartError.value = "未找到数据";
      title.value = chartTitle(code, data.name);
      return;
    }
    const h = data.history;
    history.value = h;
    title.value = chartTitle(code, data.name);
    stockCode.value = code;
    if (data.indicators) {
      indicators.value = {
        ma5: data.indicators.ma5,
        ma10: data.indicators.ma10,
        ma20: data.indicators.ma20,
      };
    }
    const latest = h[h.length - 1];
    volumeLabel.value = latest?.volume
      ? `${(latest.volume / 10000).toFixed(0)} 万`
      : "—";
  } catch (e) {
    lastKlineApiPath.value = "";
    history.value = [];
    chartError.value = e?.message || "加载失败";
  } finally {
    chartLoading.value = false;
  }
}

function calculateMA(period, hist) {
  const result = [];
  for (let i = 0; i < hist.length; i++) {
    if (i < period - 1) result.push("-");
    else {
      const sum = hist.slice(i - period + 1, i + 1).reduce((a, d) => a + d.close, 0);
      result.push((sum / period).toFixed(2));
    }
  }
  return result;
}

const chartOption = computed(() => {
  const hist = history.value;
  const err = chartError.value;
  const loading = chartLoading.value;
  if (!hist.length) {
    const text = loading ? "加载 K 线…" : err || "暂无数据";
    return {
      backgroundColor: "transparent",
      title: {
        text,
        left: "center",
        top: "center",
        textStyle: { color: "#6d6a7a", fontSize: 13, fontFamily: "Noto Serif SC" },
      },
    };
  }
  const dates = hist.map((d) => d.trade_date);
  const ma5 = calculateMA(5, hist);
  const ma10 = calculateMA(10, hist);
  const ma20 = calculateMA(20, hist);

  return {
    backgroundColor: "transparent",
    animation: true,
    animationDuration: 700,
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "cross" },
      backgroundColor: "rgba(8, 8, 12, 0.94)",
      borderColor: "rgba(232, 197, 71, 0.28)",
      textStyle: { color: "#b8b4c8", fontFamily: "IBM Plex Mono, monospace" },
    },
    legend: {
      data: ["MA5", "MA10", "MA20"],
      textStyle: { color: "#6d6a7a", fontFamily: "IBM Plex Mono, monospace" },
      top: 4,
      right: 8,
    },
    grid: { left: "3%", right: "4%", top: "18%", bottom: "16%", containLabel: true },
    xAxis: {
      type: "category",
      data: dates,
      axisLine: { lineStyle: { color: "#2a2835" } },
      axisLabel: { color: "#6d6a7a", fontSize: 10, fontFamily: "IBM Plex Mono" },
    },
    yAxis: {
      scale: true,
      position: "right",
      axisLine: { lineStyle: { color: "#2a2835" } },
      axisLabel: { color: "#6d6a7a", fontSize: 10, fontFamily: "IBM Plex Mono" },
      splitLine: { lineStyle: { color: "#1a1824" } },
    },
    dataZoom: [
      { type: "inside", xAxisIndex: 0, start: 50, end: 100 },
      {
        type: "slider",
        xAxisIndex: 0,
        start: 50,
        end: 100,
        height: 22,
        bottom: 4,
        borderColor: "transparent",
        backgroundColor: "#0a0a0f",
        fillerColor: "rgba(232, 197, 71, 0.12)",
        handleStyle: { color: "#e8c547" },
        textStyle: { color: "#6d6a7a" },
      },
    ],
    series: [
      {
        name: "K线",
        type: "candlestick",
        data: hist.map((d) => [d.open, d.close, d.low, d.high]),
        itemStyle: {
          color: "#ff5c45",
          color0: "#2ee6a8",
          borderColor: "#ff5c45",
          borderColor0: "#2ee6a8",
        },
      },
      {
        name: "MA5",
        type: "line",
        data: ma5,
        smooth: true,
        lineStyle: { width: 1.2, color: "#e8c547" },
        symbol: "none",
      },
      {
        name: "MA10",
        type: "line",
        data: ma10,
        smooth: true,
        lineStyle: { width: 1.2, color: "#3ee0ff" },
        symbol: "none",
      },
      {
        name: "MA20",
        type: "line",
        data: ma20,
        smooth: true,
        lineStyle: { width: 1.2, color: "#a78bfa" },
        symbol: "none",
      },
    ],
  };
});
</script>

<template>
  <section class="workspace">
    <header class="head">
      <div class="head-title-block">
        <h2 class="display">{{ title }}</h2>
        <p class="mono sub">{{ stockCode }}</p>
        <button
          type="button"
          class="copy-api"
          :disabled="!lastKlineApiPath"
          title="复制当前标的最近一次成功请求的 K 线分析路径"
          aria-label="复制 K 线分析 API 路径"
          @click="copyAnalysisApiPath"
        >
          复制 API 路径
        </button>
      </div>
      <div class="stats mono">
        <div><span class="lbl">MA5</span> {{ indicators.ma5?.toFixed(2) ?? "—" }}</div>
        <div><span class="lbl">MA10</span> {{ indicators.ma10?.toFixed(2) ?? "—" }}</div>
        <div><span class="lbl">MA20</span> {{ indicators.ma20?.toFixed(2) ?? "—" }}</div>
        <div><span class="lbl">量</span> {{ volumeLabel }}</div>
      </div>
    </header>

    <div class="search">
      <span class="icon">⌕</span>
      <input
        type="text"
        placeholder="代码，如 600519 或 sh.600519，回车"
        @keydown="onSearchKey"
      />
      <div class="search-divider" />
      <label class="adjust-label">
        <span class="adjust-lbl">复权</span>
        <select v-model="adjustFlag" class="adjust-select mono">
          <option value="3">不复权</option>
          <option value="2">前复权</option>
          <option value="1">后复权</option>
        </select>
      </label>
    </div>

    <div class="chart-wrap" :class="{ 'is-loading': chartLoading && !history.length }">
      <VChart class="chart" :option="chartOption" autoresize />
    </div>
  </section>
</template>

<style scoped>
.workspace {
  position: relative;
  border: 1px solid var(--rule);
  border-radius: 2px;
  background: linear-gradient(165deg, var(--ink-card) 0%, rgba(8, 8, 12, 0.6) 100%);
  padding: 20px 20px 10px;
  box-shadow: var(--shadow-lift);
}

.workspace::before {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  padding: 1px;
  background: linear-gradient(135deg, rgba(232, 197, 71, 0.15), transparent 40%, rgba(62, 224, 255, 0.08));
  -webkit-mask:
    linear-gradient(#fff 0 0) content-box,
    linear-gradient(#fff 0 0);
  mask:
    linear-gradient(#fff 0 0) content-box,
    linear-gradient(#fff 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
  pointer-events: none;
}

.head {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 14px;
}

.head-title-block {
  min-width: 0;
}

.copy-api {
  margin-top: 10px;
  font-family: var(--font-ui);
  font-size: 0.62rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  padding: 6px 12px;
  border-radius: 8px;
  border: 1px solid var(--rule-faint);
  background: rgba(8, 8, 12, 0.5);
  color: var(--mist);
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    color 0.2s ease,
    background 0.2s ease;
}

.copy-api:hover:not(:disabled) {
  border-color: rgba(62, 224, 255, 0.28);
  color: var(--meridian);
}

.copy-api:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.copy-api:focus-visible {
  outline: 2px solid var(--meridian);
  outline-offset: 2px;
}
.display {
  margin: 0;
  font-family: var(--font-display);
  font-size: clamp(1.2rem, 2.8vw, 1.55rem);
  font-weight: 800;
  letter-spacing: -0.03em;
  line-height: 1.15;
  color: var(--mist);
}
.sub {
  margin: 4px 0 0;
  font-size: 0.8rem;
  color: var(--paper-muted);
}
.stats {
  display: flex;
  flex-wrap: wrap;
  gap: 14px 20px;
  font-size: 0.78rem;
  color: var(--paper-muted);
}
.lbl {
  color: var(--brass-dim);
  margin-right: 4px;
}
.search {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  padding: 10px 14px;
  border: 1px solid var(--rule-faint);
  border-radius: 2px;
  background: rgba(5, 5, 8, 0.65);
  transition:
    border-color 0.3s var(--ease-out-expo),
    box-shadow 0.3s var(--ease-out-expo);
}

.search:focus-within {
  border-color: rgba(62, 224, 255, 0.35);
  box-shadow: 0 0 0 1px rgba(62, 224, 255, 0.12);
}

.icon {
  color: var(--gold);
  font-size: 1.15rem;
  opacity: 0.9;
}
.search input {
  flex: 1;
  border: none;
  background: transparent;
  color: var(--paper);
  font-family: var(--font-mono);
  font-size: 0.88rem;
  outline: none;
}
.search input::placeholder {
  color: var(--paper-muted);
}

.search-divider {
  width: 1px;
  height: 18px;
  background: var(--rule-faint);
  margin: 0 4px;
}

.adjust-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.78rem;
  color: var(--paper-muted);
}

.adjust-lbl {
  color: var(--brass-dim);
  font-family: var(--font-ui);
  font-size: 0.72rem;
  letter-spacing: 0.04em;
}

.adjust-select {
  border: 1px solid var(--rule-faint);
  border-radius: 6px;
  background: rgba(8, 8, 12, 0.55);
  color: var(--paper);
  font-size: 0.76rem;
  padding: 4px 8px;
  outline: none;
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    background 0.2s ease;
}

.adjust-select:hover {
  border-color: rgba(62, 224, 255, 0.28);
  background: rgba(8, 8, 12, 0.75);
}

.adjust-select:focus-visible {
  outline: 2px solid var(--meridian);
  outline-offset: 2px;
}
.chart-wrap {
  height: 440px;
  width: 100%;
  filter: drop-shadow(0 4px 24px rgba(0, 0, 0, 0.25));
  transition: opacity 0.35s ease;
}

.chart-wrap.is-loading {
  opacity: 0.88;
}
.chart {
  width: 100%;
  height: 100%;
}
.mono {
  font-family: var(--font-mono);
}
</style>
