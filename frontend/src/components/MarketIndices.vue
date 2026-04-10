<script setup>
import { onMounted, onUnmounted, ref } from "vue";
import { fetchJson } from "../composables/api.js";

const indices = ref([]);
const loading = ref(true);
const error = ref("");
let timer;

async function load() {
  error.value = "";
  loading.value = true;
  try {
    const data = await fetchJson("dashboard/overview");
    indices.value = data.indices || [];
  } catch (e) {
    error.value = e?.message || "API 未就绪或网络错误";
    indices.value = [];
  } finally {
    loading.value = false;
  }
}

const emit = defineEmits(["select"]);

onMounted(() => {
  load();
  timer = setInterval(load, 30_000);
});
onUnmounted(() => clearInterval(timer));
</script>

<template>
  <section class="indices-wrap enter-stagger">
    <header class="sec-head">
      <p class="eyebrow">主要指数</p>
      <span class="deco-line" aria-hidden="true" />
    </header>
    <div v-if="loading" class="load-block" aria-busy="true">
      <div class="grid skel-grid">
        <div v-for="n in 4" :key="n" class="card skel-card" />
      </div>
      <p class="load-caption">加载指数…</p>
    </div>
    <div v-else-if="error" class="hint hint-err">{{ error }}</div>
    <div v-else-if="indices.length === 0" class="hint hint-empty">
      暂无指数数据（请确认已拉取指数 K 线入库）
    </div>
    <div v-else class="grid">
      <button
        v-for="idx in indices"
        :key="idx.code"
        type="button"
        class="card"
        :class="(idx.pct_change || 0) >= 0 ? 'up' : 'down'"
        @click="emit('select', idx.code)"
      >
        <span class="card-corner tl" aria-hidden="true" />
        <span class="card-corner br" aria-hidden="true" />
        <div class="name">
          {{ idx.name }}
          <span class="code mono">{{ idx.code.replace(/^sh\.|^sz\./, "") }}</span>
        </div>
        <div class="price mono">{{ idx.price?.toFixed(2) ?? "—" }}</div>
        <div class="chg mono">
          <span>{{ (idx.pct_change || 0) >= 0 ? "+" : "" }}{{ idx.change?.toFixed(2) ?? "0" }}</span>
          <span class="pct">{{ (idx.pct_change || 0) >= 0 ? "+" : "" }}{{ idx.pct_change?.toFixed(2) ?? "0" }}%</span>
        </div>
      </button>
    </div>
  </section>
</template>

<style scoped>
.indices-wrap {
  position: relative;
  padding: 20px 22px 22px;
  border: 1px solid var(--rule);
  border-radius: 2px;
  background:
    linear-gradient(135deg, rgba(20, 20, 31, 0.95) 0%, rgba(10, 10, 15, 0.5) 100%);
  box-shadow: var(--shadow-lift);
}

.sec-head {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 18px;
}

.sec-head .eyebrow {
  margin-bottom: 0;
}

.deco-line {
  flex: 1;
  height: 1px;
  background: linear-gradient(90deg, var(--gold-muted), transparent 70%);
  opacity: 0.5;
}

.hint {
  padding: 1.25rem;
  border: 1px dashed var(--rule);
  color: var(--paper-muted);
  font-size: 0.9rem;
  text-align: center;
}

.hint-err {
  border-color: rgba(255, 92, 69, 0.35);
  color: var(--danger);
}

.hint-empty {
  line-height: 1.5;
}

.load-block {
  margin-bottom: 0;
}

.skel-grid {
  min-height: 100px;
}

.skel-card {
  min-height: 108px;
  cursor: default;
  pointer-events: none;
  border: 1px solid var(--rule-faint);
  background: linear-gradient(
    120deg,
    rgba(232, 197, 71, 0.05) 0%,
    rgba(62, 224, 255, 0.07) 45%,
    rgba(232, 197, 71, 0.05) 100%
  );
  background-size: 220% 100%;
  animation: idx-skel 1.2s ease-in-out infinite;
}

@keyframes idx-skel {
  0% {
    background-position: 100% 0;
  }
  100% {
    background-position: -100% 0;
  }
}

.load-caption {
  margin: 12px 0 0;
  text-align: center;
  font-size: 0.82rem;
  color: var(--paper-muted);
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(168px, 1fr));
  gap: 14px;
}

.card {
  position: relative;
  text-align: left;
  padding: 16px 16px 14px;
  border: 1px solid var(--rule-faint);
  background: linear-gradient(160deg, var(--ink-card) 0%, var(--ink-raised) 100%);
  border-radius: 2px;
  cursor: pointer;
  color: inherit;
  font: inherit;
  transition:
    border-color 0.35s var(--ease-out-expo),
    transform 0.35s var(--ease-out-expo),
    box-shadow 0.35s var(--ease-out-expo);
}

.card-corner {
  position: absolute;
  width: 10px;
  height: 10px;
  border-color: var(--gold-muted);
  border-style: solid;
  border-width: 0;
  opacity: 0;
  transition: opacity 0.3s ease;
}

.card-corner.tl {
  top: 6px;
  left: 6px;
  border-top-width: 1px;
  border-left-width: 1px;
}

.card-corner.br {
  bottom: 6px;
  right: 6px;
  border-bottom-width: 1px;
  border-right-width: 1px;
}

.card:hover .card-corner,
.card:focus-visible .card-corner {
  opacity: 0.85;
}

.card:hover {
  border-color: rgba(232, 197, 71, 0.45);
  transform: translateY(-4px);
  box-shadow:
    0 20px 40px rgba(0, 0, 0, 0.35),
    0 0 0 1px rgba(232, 197, 71, 0.12);
}

.card:focus-visible {
  outline: none;
  border-color: var(--meridian);
  box-shadow: 0 0 0 2px rgba(62, 224, 255, 0.25);
}

.card.up {
  box-shadow: inset 0 -3px 0 rgba(46, 230, 168, 0.25);
}

.card.down {
  box-shadow: inset 0 -3px 0 rgba(255, 92, 69, 0.28);
}

.name {
  font-size: 0.86rem;
  font-weight: 600;
  margin-bottom: 8px;
  letter-spacing: 0.02em;
}

.code {
  display: inline-block;
  margin-left: 6px;
  font-size: 0.62rem;
  color: var(--paper-muted);
  opacity: 0.9;
}

.price {
  font-size: 1.42rem;
  font-weight: 600;
  color: var(--paper);
  margin-bottom: 6px;
  letter-spacing: -0.02em;
}

.chg {
  font-size: 0.78rem;
  display: flex;
  gap: 10px;
  color: var(--paper-muted);
}

.card.up .pct {
  color: var(--gain);
  text-shadow: 0 0 16px rgba(46, 230, 168, 0.25);
}

.card.down .pct {
  color: var(--danger);
  text-shadow: 0 0 16px rgba(255, 92, 69, 0.2);
}

.mono {
  font-family: var(--font-mono);
}
</style>
