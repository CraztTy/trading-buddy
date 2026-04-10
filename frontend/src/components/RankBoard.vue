<script setup>
import { ref, watch } from "vue";
import { fetchJson } from "../composables/api.js";

const props = defineProps({
  tab: { type: String, default: "gainers" },
});

const emit = defineEmits(["select"]);

const rows = ref([]);
const loading = ref(true);
const error = ref("");

async function load() {
  loading.value = true;
  error.value = "";
  const ep = props.tab === "gainers" ? "gainers" : "losers";
  try {
    rows.value = await fetchJson(`dashboard/${ep}?limit=20`);
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
</script>

<template>
  <section class="rank">
    <div class="tabs">
      <button
        type="button"
        class="tab"
        :class="{ active: tab === 'gainers' }"
        @click="$emit('update:tab', 'gainers')"
      >
        <span class="tab-icon up">▲</span>
        涨幅榜
      </button>
      <button
        type="button"
        class="tab"
        :class="{ active: tab === 'losers' }"
        @click="$emit('update:tab', 'losers')"
      >
        <span class="tab-icon down">▼</span>
        跌幅榜
      </button>
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
        <div class="rhs">
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
  grid-template-columns: 1fr 1fr;
  gap: 0;
  padding: 6px;
  background: var(--void);
  border-bottom: 1px solid var(--rule-faint);
}

.tab {
  position: relative;
  padding: 12px 10px;
  border: none;
  border-radius: 2px;
  background: transparent;
  color: var(--paper-muted);
  font-family: var(--font-ui);
  font-size: 0.82rem;
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

.tab.active {
  color: var(--mist);
  background: linear-gradient(180deg, var(--ink-highlight) 0%, var(--ink-card) 100%);
  box-shadow: inset 0 0 0 1px var(--rule-faint);
}

.tab:focus-visible {
  outline: 2px solid var(--meridian);
  outline-offset: 2px;
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
