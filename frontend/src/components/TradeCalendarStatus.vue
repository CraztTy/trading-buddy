<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
import { fetchJson } from "../composables/api.js";

const FALLBACK_OPTIONS = [{ value: "cn", label: "cn" }];

const optionsLoading = ref(true);
const optionsError = ref("");
const exchangeOptions = ref([...FALLBACK_OPTIONS]);

const exchange = ref("cn");
const loading = ref(true);
const error = ref("");
const payload = ref(null);

let timer;

function exchangeQueryParam() {
  const raw = (exchange.value || "cn").trim().toLowerCase() || "cn";
  return encodeURIComponent(raw.slice(0, 32));
}

async function loadOptions() {
  optionsError.value = "";
  optionsLoading.value = true;
  try {
    const cfg = await fetchJson("data/trade-calendar/options");
    const list = Array.isArray(cfg.exchanges) ? cfg.exchanges : [];
    const normalized = list
      .filter((x) => x && typeof x.value === "string" && x.value.trim())
      .map((x) => ({
        value: String(x.value).trim().toLowerCase().slice(0, 32),
        label: typeof x.label === "string" && x.label.trim() ? x.label.trim() : String(x.value).trim(),
      }));
    exchangeOptions.value = normalized.length ? normalized : [...FALLBACK_OPTIONS];
    const def = typeof cfg.default_exchange === "string" ? cfg.default_exchange.trim().toLowerCase() : "";
    const allowed = new Set(exchangeOptions.value.map((o) => o.value));
    exchange.value = def && allowed.has(def) ? def : exchangeOptions.value[0].value;
  } catch (e) {
    optionsError.value = e?.message || "无法加载分区配置";
    exchangeOptions.value = [...FALLBACK_OPTIONS];
    exchange.value = "cn";
  } finally {
    optionsLoading.value = false;
  }
}

async function load() {
  error.value = "";
  loading.value = true;
  try {
    const q = exchangeQueryParam();
    payload.value = await fetchJson(`data/trade-calendar/status?exchange=${q}`);
  } catch (e) {
    error.value = e?.message || "无法加载交易日历状态";
    payload.value = null;
  } finally {
    loading.value = false;
  }
}

async function onExchangeChange() {
  await load();
}

const rangeLabel = computed(() => {
  const p = payload.value;
  if (!p) return "—";
  const a = p.date_min || "—";
  const b = p.date_max || "—";
  if (p.row_count <= 0) return "无数据";
  return `${a} ~ ${b}`;
});

const statusTone = computed(() => {
  const p = payload.value;
  if (!p || error.value) return "muted";
  if (p.row_count <= 0) return "warn";
  if (!p.date_max) return "warn";
  return "ok";
});

onMounted(async () => {
  await loadOptions();
  await load();
  timer = setInterval(load, 60_000);
});
onUnmounted(() => clearInterval(timer));
</script>

<template>
  <section
    class="cal-wrap enter-stagger"
    aria-label="交易日历库 trade_calendar 状态"
  >
    <header class="sec-head">
      <p class="eyebrow">交易日历</p>
      <label class="ex-pick">
        <span class="ex-pick-label">分区</span>
        <select
          v-if="!optionsLoading"
          v-model="exchange"
          class="exchange-select mono"
          aria-label="trade_calendar 分区 exchange"
          @change="onExchangeChange"
        >
          <option v-for="opt in exchangeOptions" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </option>
        </select>
        <span v-else class="ex-loading mono">配置…</span>
      </label>
      <span class="deco-line" aria-hidden="true" />
    </header>

    <p v-if="optionsError" class="hint hint-warn">{{ optionsError }}（已回退 cn）</p>

    <div v-if="loading" class="hint" aria-busy="true">加载中…</div>
    <div v-else-if="error" class="hint hint-err">{{ error }}</div>
    <div v-else-if="payload" class="body" :class="`tone-${statusTone}`">
      <div class="row">
        <span class="label">exchange</span>
        <span class="mono val">{{ payload.exchange }}</span>
      </div>
      <div class="row">
        <span class="label">行数</span>
        <span class="mono val">{{ payload.row_count.toLocaleString("zh-CN") }}</span>
      </div>
      <div class="row">
        <span class="label">覆盖</span>
        <span class="mono val range">{{ rangeLabel }}</span>
      </div>
      <p class="api-ref mono">
        GET /api/data/trade-calendar/options · GET /api/data/trade-calendar/status?exchange={{ exchange }} · 每 60s
        刷新状态
      </p>
    </div>
  </section>
</template>

<style scoped>
.cal-wrap {
  position: relative;
  padding: 16px 20px 18px;
  border: 1px solid var(--rule);
  border-radius: 2px;
  background: linear-gradient(135deg, rgba(20, 20, 31, 0.92) 0%, rgba(10, 10, 15, 0.55) 100%);
  box-shadow: var(--shadow-lift);
}

.sec-head {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.sec-head .eyebrow {
  margin-bottom: 0;
}

.ex-pick {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.ex-pick-label {
  font-size: 0.65rem;
  letter-spacing: 0.12em;
  color: var(--mist-dim);
  text-transform: uppercase;
}

.ex-loading {
  font-size: 0.72rem;
  color: var(--mist-dim);
}

.exchange-select {
  appearance: none;
  padding: 6px 28px 6px 10px;
  font-size: 0.75rem;
  color: var(--mist);
  border: 1px solid var(--rule-faint);
  border-radius: 6px;
  background:
    linear-gradient(180deg, rgba(28, 28, 42, 0.95), rgba(14, 14, 22, 0.9))
    no-repeat;
  background-position: center;
  cursor: pointer;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

.exchange-select:focus {
  outline: none;
  border-color: rgba(62, 224, 255, 0.45);
  box-shadow: 0 0 0 1px rgba(62, 224, 255, 0.2);
}

.deco-line {
  flex: 1;
  min-width: 40px;
  height: 1px;
  background: linear-gradient(90deg, rgba(62, 224, 255, 0.35), transparent 72%);
  opacity: 0.55;
}

.hint {
  margin: 0;
  padding: 0.75rem 0;
  font-size: 0.88rem;
  color: var(--mist-dim);
  text-align: center;
}

.hint-err {
  color: var(--danger);
}

.hint-warn {
  color: var(--gold);
  font-size: 0.78rem;
  padding: 0.35rem 0 0.5rem;
  text-align: left;
}

.body {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  font-size: 0.88rem;
}

.label {
  flex-shrink: 0;
  color: var(--mist-dim);
  font-size: 0.78rem;
}

.val {
  text-align: right;
  color: var(--mist);
}

.range {
  font-size: 0.8rem;
  max-width: min(100%, 520px);
  word-break: break-all;
}

.tone-ok .val {
  color: var(--jade);
}

.tone-warn .val {
  color: var(--gold);
}

.tone-muted .val {
  color: var(--mist-dim);
}

.api-ref {
  margin: 10px 0 0;
  font-size: 0.62rem;
  color: var(--mist-dim);
  opacity: 0.85;
  line-height: 1.45;
}
</style>
