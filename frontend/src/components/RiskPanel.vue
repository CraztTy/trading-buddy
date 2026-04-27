<script setup>
import { onMounted, ref } from "vue";
import { fetchJson } from "../composables/api.js";

import { computed, onMounted, onUnmounted, ref } from "vue";

const loading = ref(false);
const error = ref("");
const rules = ref([]);
const availableTypes = ref([]);

// 实时风控状态
const rtLoading = ref(false);
const rtState = ref(null);
let rtTimer = null;

// 试算风控表单
const checkCash = ref(150000);
const checkEquity = ref(1000000);
const checkPositions = ref("sh.600000,100,10.0,1000,0.1\nsh.600001,200,20.0,4000,0.4");
const checkResult = ref(null);
const checking = ref(false);

async function loadRules() {
  loading.value = true;
  error.value = "";
  try {
    const data = await fetchJson("risk/rules", { toast: false });
    rules.value = Array.isArray(data?.rules) ? data.rules : [];
    availableTypes.value = Array.isArray(data?.available_types) ? data.available_types : [];
  } catch (e) {
    error.value = e?.message || "加载风控规则失败";
    rules.value = [];
  } finally {
    loading.value = false;
  }
}

async function loadRealtimeState() {
  rtLoading.value = true;
  try {
    const data = await fetchJson("risk/realtime", { toast: false });
    rtState.value = data;
  } catch {
    rtState.value = null;
  } finally {
    rtLoading.value = false;
  }
}

const varClass = computed(() => {
  const v = rtState.value?.var_result?.var_95;
  if (!v) return "";
  return Math.abs(v) >= 0.02 ? "danger" : "";
});

const alertClass = computed(() => {
  const n = rtState.value?.alerts?.length ?? 0;
  return n > 0 ? "danger" : "";
});

const maxDrawdown = computed(() => {
  const dd = rtState.value?.drawdowns;
  if (!dd) return "—";
  const max = Math.max(...Object.values(dd).map((d) => d.drawdown_pct ?? 0));
  return max > 0 ? `${(max * 100).toFixed(2)}%` : "—";
});

function formatVar(v) {
  if (v == null || v === undefined) return "—";
  return `${(Math.abs(v) * 100).toFixed(2)}%`;
}

function fmtTime(ts) {
  if (!ts) return "—";
  try {
    const d = new Date(ts * 1000);
    return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return "—";
  }
}

async function toggleRule(rule, index) {
  const original = rule.enabled;
  // 乐观更新
  rule.enabled = !original;
  try {
    await fetchJson(`risk/rules/${rule.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: rule.enabled }),
      toast: false,
    });
  } catch (e) {
    // 回滚
    rule.enabled = original;
    error.value = e?.message || "更新失败";
  }
}

async function updateRuleParam(rule, key, value) {
  try {
    const num = parseFloat(value);
    const newParams = { ...rule.params, [key]: isNaN(num) ? value : num };
    await fetchJson(`risk/rules/${rule.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ params: newParams }),
      toast: false,
    });
    rule.params = newParams;
  } catch (e) {
    error.value = e?.message || "更新参数失败";
  }
}

async function runCheck() {
  checking.value = true;
  checkResult.value = null;
  error.value = "";
  try {
    const positions = [];
    const lines = (checkPositions.value || "").split("\n");
    for (const line of lines) {
      const parts = line.trim().split(",");
      if (parts.length < 5) continue;
      positions.push({
        code: parts[0].trim(),
        quantity: parseFloat(parts[1]) || 0,
        avg_price: parseFloat(parts[2]) || 0,
        market_value: parseFloat(parts[3]) || 0,
        weight: parseFloat(parts[4]) || 0,
      });
    }
    const data = await fetchJson("risk/check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        cash: Number(checkCash.value) || 0,
        total_equity: Number(checkEquity.value) || 0,
        positions,
      }),
      toast: false,
    });
    checkResult.value = data;
  } catch (e) {
    error.value = e?.message || "风控试算失败";
  } finally {
    checking.value = false;
  }
}

function paramLabel(ruleType, key) {
  const labels = {
    max_drawdown_pct: "最大回撤(%)",
    max_weight_pct: "单票上限(%)",
    max_sector_weight_pct: "行业上限(%)",
    max_daily_loss_pct: "单日亏损(%)",
    min_cash_pct: "最低现金(%)",
  };
  return labels[key] || key;
}

function paramValueDisplay(val) {
  if (typeof val === "number") {
    if (Math.abs(val) < 1) return `${(val * 100).toFixed(1)}%`;
    return String(val);
  }
  return String(val);
}

onMounted(() => {
  loadRules();
  loadRealtimeState();
  rtTimer = setInterval(loadRealtimeState, 5000);
});
onUnmounted(() => {
  if (rtTimer) clearInterval(rtTimer);
});
</script>

<template>
  <section class="risk">
    <header class="hd">
      <div>
        <p class="eyebrow">风控</p>
        <h2 class="h2">风险管控</h2>
        <p class="sub">
          配置风控规则并试算组合状态。规则在<strong>组合回测执行前</strong>与<strong>纸交易下单前</strong>自动拦截违规操作。
        </p>
      </div>
      <div class="hd-actions">
        <button type="button" class="ghost" :disabled="loading" @click="loadRules">
          {{ loading ? "加载中…" : "刷新" }}
        </button>
      </div>
    </header>

    <p v-if="error" class="err">{{ error }}</p>

    <!-- 实时风控状态 -->
    <div class="card full">
      <p class="card-hd">
        实时风控监控
        <span v-if="rtState?.stress_active" class="stress-badge">压力场景激活</span>
        <span v-else class="status-badge ok">正常</span>
      </p>
      <div v-if="rtLoading" class="mono meta">加载中…</div>
      <div v-else-if="rtState" class="rt-grid">
        <div class="rt-item">
          <span class="rt-label">监控持仓</span>
          <span class="rt-val mono">{{ rtState.positions_count ?? 0 }}</span>
        </div>
        <div class="rt-item">
          <span class="rt-label">VaR(95%)</span>
          <span class="rt-val mono" :class="varClass">{{ formatVar(rtState.var_result?.var_95) }}</span>
        </div>
        <div class="rt-item">
          <span class="rt-label">最大回撤</span>
          <span class="rt-val mono">{{ maxDrawdown }}</span>
        </div>
        <div class="rt-item">
          <span class="rt-label">告警</span>
          <span class="rt-val mono" :class="alertClass">{{ rtState.alerts?.length ?? 0 }}</span>
        </div>
      </div>
      <div v-if="rtState?.alerts?.length" class="alert-list">
        <div v-for="(alert, i) in rtState.alerts.slice(-5)" :key="i" class="alert-item">
          <span class="alert-time">{{ fmtTime(alert.timestamp) }}</span>
          <span class="alert-type">{{ alert.type }}</span>
          <span class="alert-code mono">{{ alert.code }}</span>
          <span class="alert-pct">{{ (alert.change_pct * 100).toFixed(2) }}%</span>
        </div>
      </div>
    </div>

    <!-- 规则列表 -->
    <div class="card full">
      <p class="card-hd">风控规则</p>
      <p v-if="!rules.length && !loading" class="mono meta empty">暂无规则</p>
      <ul v-if="rules.length" class="rule-list">
        <li v-for="(rule, idx) in rules" :key="idx" class="rule-row">
          <div class="rule-main">
            <label class="switch">
              <input
                type="checkbox"
                :checked="rule.enabled"
                @change="toggleRule(rule, idx)"
              />
              <span class="slider" />
            </label>
            <div class="rule-info">
              <span class="rule-name">{{ rule.name }}</span>
              <span class="rule-type mono">{{ rule.rule_type }}</span>
            </div>
          </div>
          <div class="rule-params">
            <label
              v-for="(val, key) in rule.params"
              :key="key"
              class="param-field"
            >
              <span class="param-label">{{ paramLabel(rule.rule_type, key) }}</span>
              <input
                :value="val"
                type="text"
                class="inp mono inp--sm"
                @blur="(e) => updateRuleParam(rule, key, e.target.value)"
                @keyup.enter="(e) => updateRuleParam(rule, key, e.target.value)"
              />
            </label>
          </div>
        </li>
      </ul>
    </div>

    <!-- 试算风控 -->
    <div class="card full">
      <p class="card-hd">试算风控</p>
      <div class="check-grid">
        <label class="field">
          <span class="lbl">现金</span>
          <input v-model.number="checkCash" type="number" class="inp mono" />
        </label>
        <label class="field">
          <span class="lbl">总权益</span>
          <input v-model.number="checkEquity" type="number" class="inp mono" />
        </label>
      </div>
      <label class="field wide">
        <span class="lbl">
          持仓列表（每行：代码,数量,成本价,市值,权重）
        </span>
        <textarea v-model="checkPositions" class="inp mono" rows="4" />
      </label>
      <button
        type="button"
        class="run"
        :disabled="checking"
        @click="runCheck"
      >
        {{ checking ? "检查中…" : "运行风控检查" }}
      </button>

      <!-- 检查结果 -->
      <div v-if="checkResult" class="check-result">
        <p
          class="check-summary"
          :class="checkResult.all_passed ? 'pass' : 'fail'"
        >
          {{ checkResult.all_passed ? "✓ 全部通过" : "✗ 存在风险" }}
        </p>
        <ul v-if="checkResult.results?.length" class="result-list">
          <li
            v-for="r in checkResult.results"
            :key="r.rule_type"
            class="result-item"
            :class="r.passed ? 'pass' : 'fail'"
          >
            <span class="result-badge">{{ r.passed ? "通过" : "未通过" }}</span>
            <span class="result-name">{{ r.rule_name }}</span>
            <span v-if="r.message" class="result-msg">{{ r.message }}</span>
          </li>
        </ul>
        <ul v-if="checkResult.errors?.length" class="error-list">
          <li v-for="err in checkResult.errors" :key="err" class="error-item">
            {{ err }}
          </li>
        </ul>
      </div>
    </div>
  </section>
</template>

<style scoped>
.risk {
  border: 1px solid var(--rule);
  border-radius: 2px;
  background: linear-gradient(180deg, var(--ink-card) 0%, rgba(10, 10, 15, 0.4) 100%);
  padding: 20px 22px 24px;
}

.hd {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 16px;
}

.eyebrow {
  margin: 0 0 4px;
  font-size: 0.62rem;
  letter-spacing: 0.2em;
  color: var(--gold-muted);
  font-weight: 700;
}

.h2 {
  margin: 0;
  font-family: var(--font-display);
  font-size: 1.1rem;
  color: var(--mist);
}

.sub {
  margin: 8px 0 0;
  font-size: 0.78rem;
  color: var(--mist-dim);
  max-width: 640px;
  line-height: 1.45;
}

.hd-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.ghost {
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

.err {
  color: #ff8a8a;
  font-size: 0.85rem;
  margin: 0 0 10px;
}

.card {
  border: 1px solid var(--rule-faint);
  border-radius: 10px;
  padding: 14px 16px;
  background: rgba(8, 8, 12, 0.45);
}

.card.full {
  margin-top: 14px;
}

.card-hd {
  margin: 0 0 10px;
  font-size: 0.65rem;
  letter-spacing: 0.14em;
  color: var(--mist-dim);
  font-weight: 700;
}

.empty {
  margin: 6px 0 0;
}

.meta {
  font-size: 0.68rem;
  color: var(--mist-dim);
}

/* 规则列表 */
.rule-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.rule-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid var(--rule-faint);
  background: rgba(8, 8, 12, 0.35);
}

.rule-main {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1 1 200px;
}

/* switch */
.switch {
  position: relative;
  display: inline-block;
  width: 36px;
  height: 20px;
  flex-shrink: 0;
}

.switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.slider {
  position: absolute;
  cursor: pointer;
  inset: 0;
  background: rgba(42, 40, 53, 0.8);
  border-radius: 20px;
  transition: 0.2s;
  border: 1px solid var(--rule-faint);
}

.slider::before {
  position: absolute;
  content: "";
  height: 14px;
  width: 14px;
  left: 2px;
  bottom: 2px;
  background: var(--mist-dim);
  border-radius: 50%;
  transition: 0.2s;
}

.switch input:checked + .slider {
  background: rgba(62, 224, 255, 0.25);
  border-color: rgba(62, 224, 255, 0.4);
}

.switch input:checked + .slider::before {
  transform: translateX(16px);
  background: var(--meridian);
}

.rule-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.rule-name {
  font-size: 0.82rem;
  color: var(--mist);
  font-weight: 600;
}

.rule-type {
  font-size: 0.65rem;
  color: var(--mist-dim);
}

.rule-params {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  flex: 1 1 auto;
  justify-content: flex-end;
}

.param-field {
  display: flex;
  align-items: center;
  gap: 6px;
}

.param-label {
  font-size: 0.62rem;
  color: var(--mist-dim);
}

/* 表单 */
.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 10px;
}

.lbl {
  font-size: 0.62rem;
  color: var(--mist-dim);
}

.inp {
  border: 1px solid var(--rule-faint);
  border-radius: 8px;
  padding: 8px 10px;
  background: rgba(8, 8, 12, 0.65);
  color: var(--mist);
  font-size: 0.85rem;
}

.inp--sm {
  max-width: 120px;
  padding: 6px 8px;
  font-size: 0.78rem;
}

.check-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

@media (max-width: 640px) {
  .check-grid {
    grid-template-columns: 1fr;
  }
}

.run {
  font-family: var(--font-display);
  font-size: 0.65rem;
  font-weight: 800;
  letter-spacing: 0.1em;
  padding: 10px 16px;
  border-radius: 10px;
  border: 1px solid rgba(62, 224, 255, 0.35);
  background: rgba(62, 224, 255, 0.12);
  color: var(--meridian);
  cursor: pointer;
  margin-top: 4px;
}

/* 检查结果 */
.check-result {
  margin-top: 14px;
  padding: 12px;
  border-radius: 8px;
  border: 1px solid var(--rule-faint);
  background: rgba(8, 8, 12, 0.35);
}

.check-summary {
  margin: 0 0 10px;
  font-size: 0.9rem;
  font-weight: 700;
}

.check-summary.pass {
  color: var(--gain);
}

.check-summary.fail {
  color: #ff8a8a;
}

.result-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.result-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  font-size: 0.78rem;
}

.result-item.pass {
  background: rgba(62, 224, 120, 0.08);
}

.result-item.fail {
  background: rgba(255, 120, 120, 0.08);
}

.result-badge {
  font-size: 0.6rem;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 4px;
  flex-shrink: 0;
}

.result-item.pass .result-badge {
  background: rgba(62, 224, 120, 0.2);
  color: var(--gain);
}

.result-item.fail .result-badge {
  background: rgba(255, 120, 120, 0.2);
  color: #ff9a9a;
}

.result-name {
  color: var(--mist);
  font-weight: 600;
}

.result-msg {
  color: var(--mist-dim);
  flex: 1;
  text-align: right;
}

.error-list {
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
}

.error-item {
  font-size: 0.75rem;
  color: #ff9a9a;
  padding: 4px 0;
}

/* 实时风控状态 */
.rt-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 12px;
}

@media (max-width: 640px) {
  .rt-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

.rt-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  border: 1px solid var(--rule-faint);
  border-radius: 8px;
  background: rgba(8, 8, 12, 0.4);
}

.rt-label {
  font-size: 0.62rem;
  color: var(--mist-dim);
  letter-spacing: 0.06em;
}

.rt-val {
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--mist);
}

.rt-val.danger {
  color: #ff8a8a;
}

.status-badge {
  font-size: 0.58rem;
  font-weight: 800;
  padding: 2px 8px;
  border-radius: 4px;
  margin-left: 8px;
}

.status-badge.ok {
  border: 1px solid rgba(46, 230, 168, 0.4);
  background: rgba(46, 230, 168, 0.12);
  color: #2ee6a8;
}

.stress-badge {
  font-size: 0.58rem;
  font-weight: 800;
  padding: 2px 8px;
  border-radius: 4px;
  margin-left: 8px;
  border: 1px solid rgba(255, 92, 69, 0.4);
  background: rgba(255, 92, 69, 0.12);
  color: #ff5c45;
}

.alert-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--rule-faint);
}

.alert-item {
  display: flex;
  gap: 10px;
  align-items: center;
  font-size: 0.72rem;
  padding: 6px 10px;
  border-radius: 6px;
  background: rgba(255, 92, 69, 0.08);
  border: 1px solid rgba(255, 92, 69, 0.15);
}

.alert-time {
  color: var(--mist-dim);
  font-size: 0.65rem;
}

.alert-type {
  color: #ff8a8a;
  font-weight: 600;
}

.alert-code {
  color: var(--mist);
}

.alert-pct {
  margin-left: auto;
  color: #ff8a8a;
  font-weight: 600;
}
</style>
