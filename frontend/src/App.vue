<script setup>
import { onMounted, onUnmounted, ref, watch } from "vue";
import MarketIndices from "./components/MarketIndices.vue";
import TradeCalendarStatus from "./components/TradeCalendarStatus.vue";
import KlineWorkspace from "./components/KlineWorkspace.vue";
import RankBoard from "./components/RankBoard.vue";
import BacktestPanel from "./components/BacktestPanel.vue";
import StockListPanel from "./components/StockListPanel.vue";
import PaperTradingPanel from "./components/PaperTradingPanel.vue";
import WatchlistPanel from "./components/WatchlistPanel.vue";
import FactorPreviewPanel from "./components/FactorPreviewPanel.vue";
import RiskPanel from "./components/RiskPanel.vue";
import KillSwitchPill from "./components/KillSwitchPill.vue";
import ApiHealthPill from "./components/ApiHealthPill.vue";
import ToastStack from "./components/ToastStack.vue";
import LoginModal from "./components/LoginModal.vue";
import { writeClipboardText } from "./composables/clipboardWrite.js";
import { showToast } from "./composables/useToast.js";
import { useAuth } from "./composables/useAuth.js";

const SS_MAIN = "tb_mainView";
const SS_CODE = "tb_currentCode";
const SS_RANK = "tb_rankTab";
const SS_DASHBOARD_ADJUST = "tb_dashboardAdjust";
const CODE_RE = /^(sh|sz|bj)\.[\w.-]+$/i;

const VIEW_KEY_CODES = ["Digit1", "Digit2", "Digit3", "Digit4", "Digit5", "Digit6", "Digit7"];
const VIEW_IDS = ["market", "stocks", "watchlist", "factors", "backtest", "paper", "risk"];

const { isLoggedIn, username, logout } = useAuth();

const mainView = ref("market");
const currentCode = ref("sh.000001");
const rankTab = ref("gainers");
const dashboardAdjustFlag = ref("3");
const clock = ref("");
const showLoginModal = ref(false);
/** 从回测带入纸单的代码与股数 */
const paperDraft = ref(null);

function tick() {
  clock.value = new Date().toLocaleTimeString("zh-CN", { hour12: false });
}
let clockId;

function restoreSessionPrefs() {
  try {
    const mv = sessionStorage.getItem(SS_MAIN);
    if (
      mv === "market" ||
      mv === "stocks" ||
      mv === "watchlist" ||
      mv === "factors" ||
      mv === "backtest" ||
      mv === "paper" ||
      mv === "risk"
    )
      mainView.value = mv;
    const cc = sessionStorage.getItem(SS_CODE);
    if (cc && CODE_RE.test(cc) && cc.length <= 48) currentCode.value = cc;
    const rt = sessionStorage.getItem(SS_RANK);
    if (rt === "gainers" || rt === "losers" || rt === "turnover") rankTab.value = rt;
    const da = sessionStorage.getItem(SS_DASHBOARD_ADJUST);
    if (da === "1" || da === "2" || da === "3") dashboardAdjustFlag.value = da;
  } catch {
    /* private mode / disabled storage */
  }
}

function persistSessionPrefs() {
  try {
    sessionStorage.setItem(SS_MAIN, mainView.value);
    sessionStorage.setItem(SS_CODE, currentCode.value);
    sessionStorage.setItem(SS_RANK, rankTab.value);
    sessionStorage.setItem(SS_DASHBOARD_ADJUST, dashboardAdjustFlag.value);
  } catch {
    /* ignore */
  }
}

onMounted(() => {
  restoreSessionPrefs();
  tick();
  clockId = setInterval(tick, 1000);
  persistSessionPrefs();
  window.addEventListener("keydown", onGlobalKeydown);
});
onUnmounted(() => {
  clearInterval(clockId);
  window.removeEventListener("keydown", onGlobalKeydown);
});

watch([mainView, currentCode, rankTab, dashboardAdjustFlag], persistSessionPrefs);

/** 离开纸交易后丢弃回测带入草稿，避免再次进入时误覆盖表单 */
watch(mainView, (view, prev) => {
  if (prev === "paper" && view !== "paper") {
    paperDraft.value = null;
  }
});

function onSelectCode(code) {
  currentCode.value = code;
}

function onStockListSelect(code) {
  currentCode.value = code;
  mainView.value = "market";
}

function onOpenPaper(payload) {
  paperDraft.value = {
    code: payload?.code || currentCode.value,
    quantity: Math.max(1, Number(payload?.quantity) || 100),
  };
  mainView.value = "paper";
}

function onPaperNavigateBacktest() {
  mainView.value = "backtest";
}

function onFactorOpenMarket(code) {
  const c = (code || "").trim();
  if (c) currentCode.value = c;
  mainView.value = "market";
}

function isTypingTarget(el) {
  if (!el || el === document.body) return false;
  const tag = el.tagName?.toLowerCase();
  if (tag === "input" || tag === "textarea" || tag === "select") return true;
  if (el.isContentEditable) return true;
  return false;
}

function onGlobalKeydown(e) {
  if (e.repeat || e.metaKey || e.ctrlKey) return;

  if (e.altKey && e.shiftKey && e.code === "KeyC") {
    if (isTypingTarget(document.activeElement)) return;
    e.preventDefault();
    void copyCurrentCode();
    return;
  }

  if (!e.altKey || e.shiftKey) return;
  const i = VIEW_KEY_CODES.indexOf(e.code);
  if (i < 0) return;
  if (isTypingTarget(document.activeElement)) return;
  e.preventDefault();
  mainView.value = VIEW_IDS[i];
}

async function copyCurrentCode() {
  const c = (currentCode.value || "").trim();
  if (!c) return;
  try {
    await writeClipboardText(c);
    showToast(`已复制 ${c}`, { type: "info", duration: 2200 });
  } catch {
    showToast("无法写入剪贴板，请检查浏览器权限", { type: "error" });
  }
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
        <ApiHealthPill />
        <KillSwitchPill />
      </div>

      <div class="status mono">
        <button
          type="button"
          class="code-chip"
          :title="`当前标的 ${currentCode}，点击复制；快捷键 Alt+Shift+C`"
          aria-label="复制当前标的代码"
          @click="copyCurrentCode"
        >
          {{ currentCode }}
        </button>
        <span class="time">{{ clock }}</span>
        <span class="tz">CST</span>
        <button
          v-if="isLoggedIn"
          type="button"
          class="auth-btn"
          @click="logout"
        >
          {{ username }} · 登出
        </button>
        <button
          v-else
          type="button"
          class="auth-btn"
          @click="showLoginModal = true"
        >
          登录
        </button>
      </div>
    </header>

    <main class="main">
      <div class="slant" aria-hidden="true" />

      <MarketIndices
        class="block"
        :adjust-flag="dashboardAdjustFlag"
        @update:adjust-flag="dashboardAdjustFlag = $event"
        @select="onSelectCode"
      />

      <TradeCalendarStatus class="block enter-stagger" />

      <nav class="view-tabs enter-stagger" aria-label="主视图">
        <button
          type="button"
          class="view-tab"
          data-testid="main-nav-market"
          :class="{ active: mainView === 'market' }"
          title="Alt+1"
          @click="mainView = 'market'"
        >
          行情看板
        </button>
        <button
          type="button"
          class="view-tab"
          data-testid="main-nav-stocks"
          :class="{ active: mainView === 'stocks' }"
          title="Alt+2"
          @click="mainView = 'stocks'"
        >
          股票列表
        </button>
        <button
          type="button"
          class="view-tab"
          data-testid="main-nav-watchlist"
          :class="{ active: mainView === 'watchlist' }"
          title="Alt+3"
          @click="mainView = 'watchlist'"
        >
          自选
        </button>
        <button
          type="button"
          class="view-tab"
          data-testid="main-nav-factors"
          :class="{ active: mainView === 'factors' }"
          title="Alt+4"
          @click="mainView = 'factors'"
        >
          因子预览
        </button>
        <button
          type="button"
          class="view-tab"
          data-testid="main-nav-backtest"
          :class="{ active: mainView === 'backtest' }"
          title="Alt+5"
          @click="mainView = 'backtest'"
        >
          策略回测
        </button>
        <button
          type="button"
          class="view-tab"
          data-testid="main-nav-paper"
          :class="{ active: mainView === 'paper' }"
          title="Alt+6"
          @click="mainView = 'paper'"
        >
          纸交易
        </button>
        <button
          type="button"
          class="view-tab"
          data-testid="main-nav-risk"
          :class="{ active: mainView === 'risk' }"
          title="Alt+7"
          @click="mainView = 'risk'"
        >
          风控
        </button>
      </nav>

      <div v-if="mainView === 'market'" class="split enter-stagger">
        <KlineWorkspace
          class="col chart-col"
          :code="currentCode"
          :adjust-flag="dashboardAdjustFlag"
          @update:code="onSelectCode"
          @update:adjust-flag="dashboardAdjustFlag = $event"
        />
        <aside class="col side-col">
          <p class="eyebrow">涨跌 / 成交额</p>
          <RankBoard
            v-model:tab="rankTab"
            :adjust-flag="dashboardAdjustFlag"
            @update:adjust-flag="dashboardAdjustFlag = $event"
            @select="onSelectCode"
          />
        </aside>
      </div>
      <StockListPanel
        v-else-if="mainView === 'stocks'"
        class="block enter-stagger"
        @select="onStockListSelect"
      />
      <WatchlistPanel
        v-else-if="mainView === 'watchlist'"
        class="block enter-stagger"
        @select="onStockListSelect"
      />
      <FactorPreviewPanel
        v-else-if="mainView === 'factors'"
        class="block enter-stagger"
        :code="currentCode"
        @select-code="onSelectCode"
        @open-market="onFactorOpenMarket"
      />
      <BacktestPanel
        v-else-if="mainView === 'backtest'"
        class="block enter-stagger"
        :code="currentCode"
        :adjust-flag="dashboardAdjustFlag"
        @update:adjust-flag="dashboardAdjustFlag = $event"
        @open-paper="onOpenPaper"
        @select-code="onSelectCode"
      />
      <PaperTradingPanel
        v-else-if="mainView === 'paper'"
        class="block enter-stagger"
        :draft="paperDraft"
        :adjust-flag="dashboardAdjustFlag"
        @navigate-backtest="onPaperNavigateBacktest"
      />
      <RiskPanel
        v-else-if="mainView === 'risk'"
        class="block enter-stagger"
      />
    </main>
    <ToastStack />
    <LoginModal v-if="showLoginModal" @close="showLoginModal = false" @success="showLoginModal = false" />
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

.code-chip {
  max-width: 11rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-right: 4px;
  padding: 4px 10px;
  border: 1px solid var(--rule-faint);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.04);
  color: var(--meridian);
  font: inherit;
  font-weight: 600;
  letter-spacing: 0.02em;
  cursor: pointer;
  transition:
    border-color 0.15s ease,
    background 0.15s ease,
    box-shadow 0.15s ease;
}

.code-chip:hover {
  border-color: rgba(62, 224, 255, 0.35);
  background: rgba(62, 224, 255, 0.08);
  box-shadow: 0 0 16px rgba(62, 224, 255, 0.12);
}

.code-chip:focus-visible {
  outline: 2px solid var(--meridian);
  outline-offset: 2px;
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

/* 平板端响应式 (1024px - 768px) */
@media (max-width: 1024px) {
  .topbar {
    grid-template-columns: 1fr;
    text-align: center;
    padding: 12px 16px;
  }
  .brand {
    justify-content: center;
  }
  .brand-text .title {
    font-size: clamp(1rem, 2.5vw, 1.2rem);
  }
  .brand-text .tagline {
    font-size: 0.68rem;
  }
  .status {
    justify-content: center;
    font-size: 0.85rem;
  }
  .topbar-mid {
    max-width: 100%;
    order: 3;
  }
  .main {
    padding: 20px 16px 48px;
  }
  .split {
    grid-template-columns: 1fr;
  }
  .view-tabs {
    flex-wrap: wrap;
    gap: 8px;
  }
  .view-tab {
    padding: 8px 14px;
    font-size: 0.62rem;
  }
}

/* 移动端响应式 (768px - 576px) */
@media (max-width: 768px) {
  .topbar {
    padding: 10px 12px;
    gap: 12px;
  }
  .sigil-wrap {
    width: 36px;
    height: 36px;
  }
  .sigil {
    font-size: 1rem;
  }
  .brand {
    gap: 12px;
  }
  .brand-text .title {
    font-size: clamp(0.9rem, 3vw, 1.1rem);
  }
  .brand-text .tagline {
    font-size: 0.62rem;
    letter-spacing: 0.08em;
  }
  .main {
    padding: 16px 12px 60px;
  }
  .view-tabs {
    gap: 6px;
  }
  .view-tab {
    padding: 7px 12px;
    font-size: 0.58rem;
    letter-spacing: 0.1em;
  }
  .block {
    margin-bottom: 20px;
  }
  .status {
    gap: 6px;
    font-size: 0.78rem;
  }
  .code-chip {
    max-width: 8rem;
    padding: 3px 8px;
    font-size: 0.75rem;
  }
  .auth-btn {
    margin-left: 6px;
    padding: 4px 10px;
    font-size: 0.62rem;
  }
}

/* 小屏移动端响应式 (< 576px) */
@media (max-width: 576px) {
  .topbar {
    padding: 8px 10px;
    gap: 8px;
  }
  .sigil-wrap {
    width: 32px;
    height: 32px;
  }
  .brand {
    gap: 10px;
  }
  .brand-text .title {
    font-size: clamp(0.85rem, 3.5vw, 1rem);
  }
  .brand-text .tagline {
    font-size: 0.56rem;
    letter-spacing: 0.06em;
  }
  .main {
    padding: 12px 8px 70px;
  }
  .view-tabs {
    gap: 4px;
    margin-bottom: 16px;
  }
  .view-tab {
    padding: 6px 10px;
    font-size: 0.54rem;
    letter-spacing: 0.08em;
    border-radius: 6px;
  }
  .block {
    margin-bottom: 16px;
  }
  .session-pill {
    padding: 3px 8px;
    font-size: 0.52rem;
  }
  .status {
    gap: 4px;
    font-size: 0.72rem;
  }
  .code-chip {
    max-width: 6rem;
    padding: 2px 6px;
    font-size: 0.68rem;
  }
  .auth-btn {
    margin-left: 4px;
    padding: 3px 8px;
    font-size: 0.56rem;
    border-radius: 4px;
  }
  .time {
    font-size: 0.85rem;
  }
  .tz {
    font-size: 0.56rem;
  }
}

.auth-btn {
  margin-left: 10px;
  padding: 5px 12px;
  border-radius: 6px;
  border: 1px solid rgba(62, 224, 255, 0.25);
  background: rgba(10, 28, 36, 0.45);
  color: #9aefff;
  font-family: var(--font-mono);
  font-size: 0.68rem;
  cursor: pointer;
  transition: all 0.2s ease;
}

.auth-btn:hover {
  border-color: rgba(62, 224, 255, 0.5);
  background: rgba(10, 28, 36, 0.65);
  color: #c4f7ff;
}

.col {
  min-width: 0;
}
</style>
