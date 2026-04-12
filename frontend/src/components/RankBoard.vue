<script setup>
import { ref, watch } from "vue";
import { fetchJson } from "../composables/api.js";

const props = defineProps({
  tab: { type: String, default: "gainers" },
});

const emit = defineEmits(["select", "update:tab"]);

const rows = ref([]);
const loading = ref(true);
const error = ref("");
/** 仅「成交额」页：可选 YYYY-MM-DD，空则走后端默认最新交易日 */
const turnoverDate = ref("");

function fmtAmount(v) {
  if (v == null || !Number.isFinite(Number(v))) return "—";
  const x = Number(v);
  if (x >= 1e8) return `${(x / 1e8).toFixed(2)} 亿`;
  if (x >= 1e4) return `${(x / 1e4).toFixed(1)} 万`;
  return `${x.toFixed(0)}`;
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    if (props.tab === "turnover") {
      const p = new URLSearchParams({ limit: "20" });
      const d = (turnoverDate.value || "").trim();
      if (d) p.set("trade_date", d);
      const data = await fetchJson(`dashboard/turnover?${p.toString()}`);
      rows.value = Array.isArray(data?.stocks) ? data.stocks : [];
    } else {
      const ep = props.tab === "gainers" ? "gainers" : "losers";
      rows.value = await fetchJson(`dashboard/${ep}?limit=20`);
    }
  } catch (e) {
    error.value = e?.message || "加载失败";
    rows.value = [];
  } finally {
    loading.value = false;
  }
}

watch(
  () => props.tab,
  () => load(),
  { immediate: true }
);

watch(turnoverDate, () => {
  if (props.tab === "turnover") load();
});
</script>

<template>
  <section class="rank">
    <div class="tabs">
      <button
        type="button"
        class="tab"
        :class="{ active: tab === 'gainers' }"
        @click="emit('update:tab', 'gainers')"
      >
        <span class="tab-icon up">▲</span>
        涨幅榜
      </button>
      <button
        type="button"
        class="tab"
        :class="{ active: tab === 'losers' }"
        @click="emit('update:tab', 'losers')"
      >
        <span class="tab-icon down">▼</span>
        跌幅榜
      </button>
      <button
        type="button"
        class="tab"
        :class="{ active: tab === 'turnover' }"
        @click="emit('update:tab', 'turnover')"
      >
        <span class="tab-icon vol">◇</span>
        成交额
      </button>
    </div>

    <div v-if="tab === 'turnover'" class="turnover-opts">
      <label class="dt-lbl">
        <span>交易日（可选）</span>
        <input v-model="turnoverDate" type="date" class="dt-inp mono" />
      </label>
      <span class="dt-hint mono">空 = 库中最新交易日</span>
    </div>

    <div v-if="loading" class="state shimmer">
      <div class="skel-list" aria-hidden="true">
        <div v-for="n in 8" :key="n" class="skel-row" />
      </div>
      <p class="load-hint">加载排行…</p>
    </div>
    <div v-else-if="error" class="state state-err">{{ error }}</div>
    <div v-else-if="rows.length === 0" class="state state-empty">
      暂无数据（可先跑拉数脚本写入日 K，或换交易日再试）
    </div>
    <ul v-else class="list">
      <li
        v-for="(stock, i) in rows"
        :key="stock.code"
        class="row"
        @click="emit('select', stock.code)"
      >
        <span class="accent" aria-hidden="true" />
        <span class="num mono">{{ String(i + 1).padStart(2, "0") }}</span>
        <div class="meta">
          <span class="nm">{{ stock.name }}</span>
          <span class="cd mono">{{ stock.code }}</span>
        </div>
        <div v-if="tab === 'turnover'" class="rhs rhs-turnover">
          <span class="mono pr">{{ stock.price?.toFixed(2) ?? "—" }}</span>
          <span class="mono amt">{{ fmtAmount(stock.amount) }}</span>
        </div>
        <div v-else class="rhs">
          <span class="mono pr">{{ stock.price?.toFixed(2) ?? "—" }}</span>
          <span
            class="mono pct"
            :class="(stock.pct_change || 0) >= 0 ? 'up' : 'down'"
          >
            {{ (stock.pct_change || 0) >= 0 ? "+" : "" }}{{ stock.pct_change?.toFixed(2) ?? "0" }}%
          </span>
        </div>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.rank {
  border: 1px solid var(--rule);
  border-radius: 2px;
  background: linear-gradient(180deg, var(--ink-card) 0%, rgba(10, 10, 15, 0.4) 100%);
  overflow: hidden;
  min-height: 340px;
  box-shadow: var(--shadow-lift);
}

.tabs {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 0;
  padding: 6px;
  background: var(--void);
  border-bottom: 1px solid var(--rule-faint);
}

.tab {
  position: relative;
  padding: 12px 8px;
  border: none;
  border-radius: 2px;
  background: transparent;
  color: var(--paper-muted);
  font-family: var(--font-ui);
  font-size: 0.78rem;
  font-weight: 600;
  cursor: pointer;
  transition:
    color 0.3s var(--ease-out-expo),
    background 0.3s var(--ease-out-expo);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.tab-icon {
  font-size: 0.65rem;
  opacity: 0.7;
}

.tab-icon.up {
  color: var(--gain);
}

.tab-icon.down {
  color: var(--danger);
}

.tab-icon.vol {
  color: var(--meridian);
}

.tab.active {
  color: var(--mist);
  background: linear-gradient(180deg, var(--ink-highlight) 0%, var(--ink-card) 100%);
  box-shadow: inset 0 0 0 1px var(--rule-faint);
}

.tab:focus-visible {
  outline: 2px solid var(--meridian);
  outline-offset: 2px;
}

.turnover-opts {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 14px;
  padding: 10px 14px 8px;
  border-bottom: 1px solid var(--rule-faint);
  background: rgba(8, 8, 12, 0.35);
}

.dt-lbl {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 0.65rem;
  color: var(--paper-muted);
}

.dt-inp {
  border: 1px solid var(--rule-faint);
  border-radius: 8px;
  padding: 6px 8px;
  background: rgba(8, 8, 12, 0.65);
  color: var(--mist);
  font-size: 0.8rem;
}

.dt-hint {
  font-size: 0.62rem;
  color: var(--mist-dim);
}

.state {
  padding: 2.5rem;
  text-align: center;
  color: var(--paper-muted);
  font-size: 0.9rem;
}

.state-err {
  color: var(--danger);
}

.state-empty {
  line-height: 1.5;
  max-width: 260px;
  margin: 0 auto;
}

.load-hint {
  margin: 1rem 0 0;
  font-size: 0.82rem;
  color: var(--paper-muted);
}

.skel-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-width: 280px;
  margin: 0 auto;
}

.skel-row {
  height: 44px;
  border-radius: 2px;
  background: linear-gradient(
    90deg,
    rgba(232, 197, 71, 0.06) 0%,
    rgba(62, 224, 255, 0.08) 50%,
    rgba(232, 197, 71, 0.06) 100%
  );
  background-size: 200% 100%;
  animation: skel-shine 1.1s ease-in-out infinite;
}

@keyframes skel-shine {
  0% {
    background-position: 100% 0;
  }
  100% {
    background-position: -100% 0;
  }
}

.shimmer {
  animation: pulse-text 1.2s ease-in-out infinite;
}

@keyframes pulse-text {
  0%,
  100% {
    opacity: 0.5;
  }
  50% {
    opacity: 1;
  }
}

.list {
  list-style: none;
  margin: 0;
  padding: 4px 0;
  max-height: 540px;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--gold-muted) var(--void);
}

.list::-webkit-scrollbar {
  width: 6px;
}

.list::-webkit-scrollbar-track {
  background: var(--void);
}

.list::-webkit-scrollbar-thumb {
  background: linear-gradient(180deg, var(--gold-muted), var(--meridian));
  border-radius: 3px;
}

.row {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px 12px 16px;
  margin: 0 6px;
  border-radius: 2px;
  cursor: pointer;
  transition:
    background 0.25s var(--ease-out-expo),
    transform 0.25s var(--ease-out-expo);
}

.accent {
  position: absolute;
  left: 6px;
  top: 50%;
  transform: translateY(-50%) scaleY(0);
  width: 3px;
  height: 0;
  background: linear-gradient(180deg, var(--gold), var(--meridian));
  border-radius: 2px;
  transition:
    height 0.3s var(--ease-out-expo),
    transform 0.3s var(--ease-out-expo);
}

.row:hover .accent {
  height: 60%;
  transform: translateY(-50%) scaleY(1);
}

.row:hover {
  background: rgba(232, 197, 71, 0.06);
}

.row:focus-within,
.row:active {
  background: rgba(62, 224, 255, 0.05);
}

.num {
  width: 26px;
  font-size: 0.72rem;
  color: var(--gold-muted);
  font-weight: 500;
}

.meta {
  flex: 1;
  min-width: 0;
}

.nm {
  display: block;
  font-size: 0.88rem;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.cd {
  font-size: 0.68rem;
  color: var(--paper-muted);
  margin-top: 2px;
}

.rhs {
  text-align: right;
}

.rhs-turnover .amt {
  display: block;
  margin-top: 2px;
  font-size: 0.76rem;
  font-weight: 600;
  color: var(--meridian);
}

.pr {
  display: block;
  font-size: 0.88rem;
  color: var(--mist);
}

.pct {
  font-size: 0.76rem;
  font-weight: 600;
}

.pct.up {
  color: var(--gain);
}

.pct.down {
  color: var(--danger);
}
</style>
