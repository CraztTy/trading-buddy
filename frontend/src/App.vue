<script setup>
import { onMounted, onUnmounted, ref } from "vue";
import MarketIndices from "./components/MarketIndices.vue";
import KlineWorkspace from "./components/KlineWorkspace.vue";
import RankBoard from "./components/RankBoard.vue";
import BacktestPanel from "./components/BacktestPanel.vue";

const mainView = ref("market");
const currentCode = ref("sh.000001");
const rankTab = ref("gainers");
const clock = ref("");

function tick() {
  clock.value = new Date().toLocaleTimeString("zh-CN", { hour12: false });
}
let clockId;

onMounted(() => {
  tick();
  clockId = setInterval(tick, 1000);
});
onUnmounted(() => clearInterval(clockId));

function onSelectCode(code) {
  currentCode.value = code;
}
</script>

<template>
  <div class="mesh" aria-hidden="true" />
  <div class="noise" aria-hidden="true" />
  <div class="scanlines" aria-hidden="true" />
  <div class="app-frame">
    <header class="topbar">
      <div class="brand">
        <div class="sigil-wrap">
          <div class="sigil" aria-hidden="true">◈</div>
          <div class="sigil-ring" aria-hidden="true" />
        </div>
        <div class="brand-text">
          <h1 class="title">Trading Buddy</h1>
          <p class="tagline">Meridian · A 股行情</p>
        </div>
      </div>

      <div class="topbar-mid">
        <span class="session-pill">
          <span class="dot" aria-hidden="true" />
          SESSION
        </span>
        <div class="rule-anim" aria-hidden="true">
          <span class="rule-line" />
        </div>
      </div>

      <div class="status mono">
        <span class="time">{{ clock }}</span>
        <span class="tz">CST</span>
      </div>
    </header>

    <main class="main">
      <div class="slant" aria-hidden="true" />

      <MarketIndices class="block" @select="onSelectCode" />

      <nav class="view-tabs enter-stagger" aria-label="主视图">
        <button
          type="button"
          class="view-tab"
          :class="{ active: mainView === 'market' }"
          @click="mainView = 'market'"
        >
          行情看板
        </button>
        <button
          type="button"
          class="view-tab"
          :class="{ active: mainView === 'backtest' }"
          @click="mainView = 'backtest'"
        >
          策略回测
        </button>
      </nav>

      <div v-if="mainView === 'market'" class="split enter-stagger">
        <KlineWorkspace
          class="col chart-col"
          :code="currentCode"
          @update:code="onSelectCode"
        />
        <aside class="col side-col">
          <p class="eyebrow">涨跌幅排行</p>
          <RankBoard v-model:tab="rankTab" @select="onSelectCode" />
        </aside>
      </div>
      <BacktestPanel v-else class="block enter-stagger" :code="currentCode" />
    </main>
  </div>
</template>

<style scoped>
.topbar {
  position: sticky;
  top: 0;
  z-index: 50;
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 16px;
  padding: 16px 28px 18px;
  border-bottom: 1px solid var(--rule-faint);
  background: linear-gradient(180deg, rgba(10, 10, 15, 0.94) 0%, rgba(5, 5, 8, 0.88) 100%);
  backdrop-filter: blur(20px) saturate(1.2);
}

.brand {
  display: flex;
  align-items: center;
  gap: 16px;
  min-width: 0;
}

.sigil-wrap {
  position: relative;
  width: 48px;
  height: 48px;
  flex-shrink: 0;
}

.sigil {
  position: relative;
  z-index: 1;
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.25rem;
  color: var(--void);
  font-weight: 800;
  background: linear-gradient(145deg, var(--gold) 0%, #f0e6a8 50%, #c9a227 100%);
  clip-path: polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%);
  box-shadow:
    0 0 28px rgba(232, 197, 71, 0.35),
    inset 0 1px 0 rgba(255, 255, 255, 0.35);
}

.sigil-ring {
  position: absolute;
  inset: -4px;
  border: 1px solid rgba(232, 197, 71, 0.35);
  clip-path: polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%);
  animation: ring-pulse 3s ease-in-out infinite;
}

@keyframes ring-pulse {
  0%,
  100% {
    opacity: 0.5;
    transform: scale(1);
  }
  50% {
    opacity: 1;
    transform: scale(1.06);
  }
}

.brand-text {
  min-width: 0;
}

.title {
  margin: 0;
  font-family: var(--font-display);
  font-size: clamp(1.05rem, 2.5vw, 1.35rem);
  font-weight: 800;
  letter-spacing: -0.02em;
  line-height: 1.1;
  color: var(--mist);
  text-shadow: 0 0 40px rgba(62, 224, 255, 0.12);
}

.tagline {
  margin: 4px 0 0;
  font-family: var(--font-ui);
  font-size: 0.72rem;
  letter-spacing: 0.12em;
  color: var(--gold-muted);
  font-weight: 600;
}

.topbar-mid {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  max-width: 280px;
  width: 100%;
}

.session-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 4px 12px 4px 10px;
  font-family: var(--font-display);
  font-size: 0.58rem;
  font-weight: 700;
  letter-spacing: 0.35em;
  color: var(--jade);
  border: 1px solid rgba(46, 230, 168, 0.35);
  border-radius: 100px;
  background: rgba(46, 230, 168, 0.06);
}

.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--jade);
  box-shadow: 0 0 10px var(--jade);
  animation: blink-dot 1.8s ease-in-out infinite;
}

@keyframes blink-dot {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.35;
  }
}

.rule-anim {
  width: 100%;
  height: 2px;
  overflow: hidden;
  border-radius: 2px;
  background: var(--rule-faint);
}

.rule-line {
  display: block;
  height: 100%;
  width: 40%;
  background: linear-gradient(90deg, transparent, var(--gold), var(--meridian), transparent);
  animation: rule-sweep 4s ease-in-out infinite;
}

@keyframes rule-sweep {
  0% {
    transform: translateX(-100%);
  }
  100% {
    transform: translateX(350%);
  }
}

.status {
  display: flex;
  align-items: baseline;
  justify-content: flex-end;
  gap: 8px;
  font-size: 0.92rem;
  color: var(--mist-dim);
}

.time {
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  color: var(--meridian);
  text-shadow: 0 0 24px rgba(62, 224, 255, 0.25);
}

.tz {
  font-size: 0.65rem;
  letter-spacing: 0.2em;
  opacity: 0.7;
}

.mono {
  font-family: var(--font-mono);
}

.main {
  position: relative;
  max-width: 1720px;
  margin: 0 auto;
  padding: 28px 28px 56px;
  overflow: hidden;
}

.slant {
  position: absolute;
  top: -40px;
  right: -15%;
  width: 55%;
  height: 120px;
  background: linear-gradient(
    105deg,
    transparent 0%,
    rgba(232, 197, 71, 0.04) 40%,
    rgba(62, 224, 255, 0.03) 100%
  );
  transform: skewX(-12deg);
  pointer-events: none;
}

.block {
  margin-bottom: 28px;
}

.view-tabs {
  display: flex;
  gap: 10px;
  margin-bottom: 22px;
}

.view-tab {
  font-family: var(--font-display);
  font-size: 0.68rem;
  font-weight: 800;
  letter-spacing: 0.14em;
  padding: 10px 20px;
  border-radius: 10px;
  border: 1px solid var(--rule-faint);
  background: rgba(18, 18, 28, 0.6);
  color: var(--mist-dim);
  cursor: pointer;
  transition:
    color 0.2s ease,
    border-color 0.2s ease,
    background 0.2s ease;
}

.view-tab:hover {
  color: var(--mist);
  border-color: rgba(232, 197, 71, 0.25);
}

.view-tab.active {
  color: var(--void);
  background: linear-gradient(145deg, var(--gold) 0%, #d4b84a 100%);
  border-color: rgba(232, 197, 71, 0.55);
  box-shadow: 0 0 24px rgba(232, 197, 71, 0.18);
}

.split {
  display: grid;
  grid-template-columns: 1fr minmax(300px, 380px);
  gap: 24px;
  align-items: start;
}

@media (max-width: 1024px) {
  .topbar {
    grid-template-columns: 1fr;
    text-align: center;
  }
  .brand {
    justify-content: center;
  }
  .status {
    justify-content: center;
  }
  .topbar-mid {
    max-width: 100%;
    order: 3;
  }
  .split {
    grid-template-columns: 1fr;
  }
}

.col {
  min-width: 0;
}
</style>
