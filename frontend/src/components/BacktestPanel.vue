<script setup>
import { computed, ref, watch } from "vue";
import VChart from "vue-echarts";
import { apiUrl, fetchJson } from "../composables/api.js";

const props = defineProps({
  code: { type: String, default: "sh.000001" },
});

/** 单标的 | 批量扫描 */
const innerTab = ref("single");

const fast = ref(5);
const slow = ref(20);
const limit = ref(500);
/** 万分之几 */
const feeWan = ref(0);
const slipWan = ref(0);

const loading = ref(false);
const error = ref("");
const result = ref(null);

const scanCodesText = ref("sh.000001\nsh.000300\nsz.399001");
const scanLoading = ref(false);
const scanCsvLoading = ref(false);
const scanError = ref("");
const scanResult = ref(null);

const PRESET_MAJORS = "sh.000001\nsz.399001\nsz.399006\nsh.000300";

const feeRate = computed(() => Math.max(0, Number(feeWan.value) || 0) / 10000);
const slipRate = computed(() => Math.max(0, Number(slipWan.value) || 0) / 10000);

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
  return new URLSearchParams({
    fast: String(fast.value),
    slow: String(slow.value),
    limit: String(limit.value),
    commission_rate: String(feeRate.value),
    slippage_rate: String(slipRate.value),
  });
}

function downloadSingleJson() {
  if (!result.value) return;
  const text = JSON.stringify(result.value, null, 2);
  const blob = new Blob([text], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `ma_cross_${(props.code || "code").replace(/[^a-z0-9.]/gi, "_")}_${Date.now()}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

async function runBacktest() {
  loading.value = true;
  error.value = "";
  result.value = null;
  const c = (props.code || "").trim();
  if (!c) {
    error.value = "请先选择标的";
    loading.value = false;
    return;
  }
  const params = commonParams();
  params.set("code", c);
  try {
    result.value = await fetchJson(`backtest/ma-cross?${params.toString()}`);
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
  const raw = (scanCodesText.value || "").trim();
  if (!raw) {
    scanError.value = "请填写至少一个代码";
    scanLoading.value = false;
    return;
  }
  const params = commonParams();
  params.set("codes", raw);
  params.set("export", "json");
  try {
    scanResult.value = await fetchJson(`backtest/ma-cross/scan?${params.toString()}`);
  } catch (e) {
    scanError.value = e?.message || "请求失败";
  } finally {
    scanLoading.value = false;
  }
}

function fillPresetMajors() {
  scanCodesText.value = PRESET_MAJORS;
}

async function downloadScanCsv() {
  const raw = (scanCodesText.value || "").trim();
  if (!raw) {
    scanError.value = "请填写至少一个代码";
    return;
  }
  scanCsvLoading.value = true;
  scanError.value = "";
  const params = commonParams();
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

    <template v-if="innerTab === 'single'">
      <header class="hd">
        <div>
          <p class="eyebrow">策略回测</p>
          <h2 class="h2">双均线（日线）</h2>
          <p class="sub mono">标的 {{ (code || "—").trim() }} · 与行情看板当前代码联动</p>
        </div>
        <div class="hd-actions">
          <button type="button" class="run" :disabled="loading" @click="runBacktest">
            {{ loading ? "计算中…" : "运行回测" }}
          </button>
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
          <p class="sub">相同参数下对列表逐只回测，按策略收益率降序排列（最多 25 只）。</p>
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
      </div>

      <div class="codes-toolbar">
        <label class="block-label">代码列表（每行一个或逗号分隔）</label>
        <button type="button" class="linkish" @click="fillPresetMajors">填入主要指数</button>
      </div>
      <textarea v-model="scanCodesText" class="codes-ta mono" rows="5" spellcheck="false" />

      <div v-if="scanError" class="err">{{ scanError }}</div>

      <div v-if="scanResult?.items?.length" class="scan-wrap">
        <table class="scan-table">
          <thead>
            <tr>
              <th>代码</th>
              <th>策略收益 %</th>
              <th>买入持有 %</th>
              <th>超额 %</th>
              <th>夏普</th>
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
              <td class="mono">{{ row.error ? "—" : row.sharpe_ratio?.toFixed(3) }}</td>
              <td class="mono">{{ row.error ? "—" : row.signal_changes }}</td>
              <td class="err-cell">{{ row.error || "" }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
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
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
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
</style>
