<script setup>
import { onMounted, ref, watch } from "vue";
import { fetchJson } from "../composables/api.js";
import { writeClipboardText } from "../composables/clipboardWrite.js";
import { showToast } from "../composables/useToast.js";

const props = defineProps({
  /** 从回测「下一步」带入 { code, quantity } */
  draft: { type: Object, default: null },
  adjustFlag: { type: String, default: "3" },
});

const emit = defineEmits(["navigate-backtest"]);

const loading = ref(false);
const submitting = ref(false);
const resetting = ref(false);
const error = ref("");
const tip = ref("");
const state = ref(null);

const orderCode = ref("sh.600000");
const orderSide = ref("buy");
const orderQty = ref(100);
/** 自选（下单代码联想 + 快捷 chip） */
const wlItems = ref([]);
const wlLoadErr = ref("");

watch(
  () => props.draft,
  (d) => {
    if (d?.code) {
      orderCode.value = String(d.code).trim().toLowerCase();
      const q = Number(d.quantity) || 100;
      orderQty.value = Math.max(100, Math.floor(q / 100) * 100);
    }
  },
  { immediate: true, deep: true }
);

const ORDER_PAGE = 30;
const orders = ref([]);
const ordersTotal = ref(0);
const ordersLoading = ref(false);
const ordersFilterCode = ref("");
const ordersError = ref("");
/** 最近一次成功的 GET /api/paper/state */
const lastPaperStateApiPath = ref("");
/** 最近一次成功的 GET /api/paper/orders?… */
const lastPaperOrdersApiPath = ref("");

function ordersQuery(reset) {
  const off = reset ? 0 : orders.value.length;
  const p = new URLSearchParams({
    limit: String(ORDER_PAGE),
    offset: String(off),
  });
  const c = ordersFilterCode.value.trim().toLowerCase();
  if (c) p.set("code", c);
  return p.toString();
}

async function loadOrders(reset) {
  ordersLoading.value = true;
  ordersError.value = "";
  const qs = ordersQuery(reset);
  try {
    const data = await fetchJson(`paper/orders?${qs}`, { toast: false });
    lastPaperOrdersApiPath.value = `/api/paper/orders?${qs}`;
    if (reset) orders.value = data.items || [];
    else orders.value = (orders.value || []).concat(data.items || []);
    ordersTotal.value = data.total ?? 0;
  } catch (e) {
    if (reset) orders.value = [];
    ordersTotal.value = 0;
    ordersError.value = e?.message || "成交记录加载失败";
    lastPaperOrdersApiPath.value = "";
  } finally {
    ordersLoading.value = false;
  }
}

async function loadWatchlist() {
  wlLoadErr.value = "";
  try {
    const data = await fetchJson("watchlist/items", { toast: false });
    wlItems.value = Array.isArray(data?.items) ? data.items : [];
  } catch (e) {
    wlItems.value = [];
    wlLoadErr.value = e?.message || "自选列表加载失败";
  }
}

function pickWlCode(code) {
  const c = String(code || "").trim().toLowerCase();
  if (c) orderCode.value = c;
}

async function loadState() {
  loading.value = true;
  error.value = "";
  lastPaperStateApiPath.value = "";
  lastPaperOrdersApiPath.value = "";
  try {
    const qs = new URLSearchParams({ adjust_flag: props.adjustFlag });
    state.value = await fetchJson(`paper/state?${qs}`, { toast: false });
    lastPaperStateApiPath.value = `/api/paper/state?${qs}`;
  } catch (e) {
    state.value = null;
    orders.value = [];
    ordersTotal.value = 0;
    error.value = e?.message || "加载失败";
    return;
  } finally {
    loading.value = false;
  }
  await loadOrders(true);
  await loadWatchlist();
}

watch(() => props.adjustFlag, () => loadState());

async function applyOrderFilter() {
  await loadOrders(true);
}

async function loadMoreOrders() {
  await loadOrders(false);
}

/** 与「市价提交」一致：股数取整到 100 的整数倍且不少于 100 */
function normalizedOrderPayload() {
  const raw = Math.floor(Number(orderQty.value) || 0);
  const qty = Math.max(100, Math.floor(raw / 100) * 100);
  return {
    code: orderCode.value.trim(),
    side: orderSide.value,
    quantity: qty,
    adjust_flag: props.adjustFlag,
  };
}

/** 列表时间列：本地短格式 */
function fmtShort(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return String(iso).slice(0, 16);
    return d.toLocaleString(undefined, {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "—";
  }
}

async function submitOrder() {
  submitting.value = true;
  error.value = "";
  tip.value = "";
  try {
    const payload = normalizedOrderPayload();
    const body = await fetchJson("paper/orders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      toast: false,
    });
    tip.value = `已成交 ${body.side} ${body.quantity} @ ${body.fill_price}，现金 ${body.cash_after}`;
    try {
      state.value = await fetchJson("paper/state", { toast: false });
    } catch (e) {
      error.value = e?.message || "刷新资金失败";
    }
    await loadOrders(true);
    await loadWatchlist();
  } catch (e) {
    error.value = e?.message || "下单失败";
  } finally {
    submitting.value = false;
  }
}

async function copyPaperStateApiPath() {
  const u = lastPaperStateApiPath.value.trim();
  if (!u) return;
  try {
    await writeClipboardText(u);
    showToast("已复制纸交易账户状态 API 路径（curl 请自行拼接主机）", {
      type: "info",
      duration: 3000,
    });
  } catch {
    showToast("无法写入剪贴板，请检查浏览器权限", { type: "error" });
  }
}

async function copyPaperOrdersApiPath() {
  const u = lastPaperOrdersApiPath.value.trim();
  if (!u) return;
  try {
    await writeClipboardText(u);
    showToast("已复制纸交易成交记录 API 路径（含 limit/offset/筛选；curl 请自行拼接主机）", {
      type: "info",
      duration: 3200,
    });
  } catch {
    showToast("无法写入剪贴板，请检查浏览器权限", { type: "error" });
  }
}

async function copyPaperOrderPostHint() {
  if (loading.value || submitting.value) return;
  const payload = normalizedOrderPayload();
  if (!payload.code) {
    showToast("请先填写标的代码", { type: "error", duration: 2400 });
    return;
  }
  const json = JSON.stringify(payload);
  const text = `POST /api/paper/orders\nContent-Type: application/json\n\n${json}`;
  try {
    await writeClipboardText(text);
    showToast("已复制市价下单 POST 说明（含当前表单 JSON；curl 请自行拼接主机）", {
      type: "info",
      duration: 3400,
    });
  } catch {
    showToast("无法写入剪贴板，请检查浏览器权限", { type: "error" });
  }
}

async function copyPaperResetPostHint() {
  if (resetting.value) return;
  const text = "POST /api/paper/account/reset";
  try {
    await writeClipboardText(text);
    showToast("已复制账户重置 POST 路径（无请求体；curl 请自行拼接主机）", {
      type: "info",
      duration: 3000,
    });
  } catch {
    showToast("无法写入剪贴板，请检查浏览器权限", { type: "error" });
  }
}

async function copyOrdersCodes() {
  if (ordersLoading.value || !orders.value.length) return;
  const seen = new Set();
  const lines = [];
  for (const o of orders.value) {
    const c = String(o?.code || "").trim().toLowerCase();
    if (!c || seen.has(c)) continue;
    seen.add(c);
    lines.push(c);
  }
  if (!lines.length) return;
  try {
    await writeClipboardText(lines.join("\n"));
    showToast(`已复制 ${lines.length} 条不重复代码（当前成交列表，每行一条）`, {
      type: "info",
      duration: 2600,
    });
  } catch {
    showToast("无法写入剪贴板，请检查浏览器权限", { type: "error" });
  }
}

async function resetAccount() {
  if (!window.confirm("清空纸单与持仓，现金恢复为初始 100 万？")) return;
  resetting.value = true;
  error.value = "";
  try {
    await fetchJson("paper/account/reset", { method: "POST", toast: false });
    tip.value = "已重置纸账户";
    await loadState();
  } catch (e) {
    error.value = e?.message || "重置失败";
  } finally {
    resetting.value = false;
  }
}

onMounted(loadState);
</script>

<template>
  <section class="paper">
    <header class="hd">
      <div>
        <p class="eyebrow">闭环</p>
        <h2 class="h2">纸交易</h2>
        <p class="sub">
          研究 / 回测后在此下<strong>模拟单</strong>：市价按标的<strong>最近一根日 K 收盘价</strong>撮合（无滑点与手续费 MVP）。股数须为
          <strong>100 的整数倍</strong>；<strong>卖出 T+1</strong>（买入日须早于当前定价日 K 线交易日，FIFO 批）。与真实交易无关。
        </p>
      </div>
      <div class="hd-actions">
        <button
          type="button"
          class="ghost"
          :disabled="loading || !lastPaperStateApiPath"
          title="复制 GET /api/paper/state"
          aria-label="复制纸交易账户状态 API 路径"
          @click="copyPaperStateApiPath"
        >
          状态
        </button>
        <button
          type="button"
          class="ghost"
          :disabled="ordersLoading || !!ordersError || !lastPaperOrdersApiPath"
          title="复制当前成交列表 GET 路径"
          aria-label="复制纸交易成交记录 API 路径"
          @click="copyPaperOrdersApiPath"
        >
          成交
        </button>
        <button
          type="button"
          class="ghost"
          :disabled="loading || submitting"
          title="复制 POST /api/paper/orders 与当前代码/方向/股数 JSON（非提交）"
          aria-label="复制纸交易市价下单 POST 说明"
          @click="copyPaperOrderPostHint"
        >
          POST 下单
        </button>
        <button
          type="button"
          class="ghost"
          :disabled="resetting"
          title="复制 POST /api/paper/account/reset（无请求体）。执行清账请点「重置账户」"
          aria-label="复制纸交易账户重置 POST 说明"
          @click="copyPaperResetPostHint"
        >
          清账 POST
        </button>
        <button type="button" class="ghost" :disabled="loading" @click="loadState">刷新</button>
        <button type="button" class="ghost danger" :disabled="resetting || loading" @click="resetAccount">
          重置账户
        </button>
      </div>
    </header>

    <p v-if="tip" class="tip mono" role="status">{{ tip }}</p>
    <p v-if="error" class="err">{{ error }}</p>

    <div v-if="state" class="grid">
      <div class="card">
        <p class="card-hd">资金</p>
        <p class="mono big">现金 {{ state.account.cash?.toLocaleString?.() ?? state.account.cash }}</p>
        <p class="mono dim">初始 {{ state.account.initial_cash?.toLocaleString?.() ?? state.account.initial_cash }}</p>
        <p class="mono dim">估算权益 {{ state.equity?.toLocaleString?.() ?? state.equity }}</p>
      </div>

      <div class="card">
        <p class="card-hd">下单</p>
        <label class="field">
          <span class="lbl">代码</span>
          <input
            v-model="orderCode"
            type="text"
            class="inp mono"
            spellcheck="false"
            list="paper-wl-codes"
            autocapitalize="off"
            autocomplete="off"
          />
          <datalist id="paper-wl-codes">
            <option v-for="w in wlItems" :key="w.code" :value="w.code">{{ w.name || w.code }}</option>
          </datalist>
        </label>
        <p v-if="wlLoadErr" class="err err--sub mono" role="alert" data-testid="paper-wl-err">{{ wlLoadErr }}</p>
        <div v-if="wlItems.length" class="wl-chips">
          <span class="wl-chips-lbl">自选</span>
          <button
            v-for="w in wlItems"
            :key="w.code"
            type="button"
            class="wl-chip mono"
            @click="pickWlCode(w.code)"
          >
            {{ w.code }}
          </button>
        </div>
        <label class="field">
          <span class="lbl">方向</span>
          <select v-model="orderSide" class="inp mono">
            <option value="buy">买入</option>
            <option value="sell">卖出</option>
          </select>
        </label>
        <label class="field">
          <span class="lbl">股数（100 整数倍）</span>
          <input
            v-model.number="orderQty"
            type="number"
            min="100"
            step="100"
            class="inp mono"
          />
        </label>
        <button type="button" class="run" :disabled="submitting || loading" @click="submitOrder">
          {{ submitting ? "提交中…" : "市价提交" }}
        </button>
        <button type="button" class="linkish" @click="emit('navigate-backtest')">返回策略回测</button>
      </div>
    </div>

    <div v-if="state?.positions?.length" class="card full">
      <p class="card-hd">持仓</p>
      <ul class="rows mono">
        <li v-for="p in state.positions" :key="p.code" class="row row--6">
          <span>{{ p.code }}</span>
          <span>总 {{ p.quantity }}</span>
          <span>可卖 {{ p.sellable_quantity ?? "—" }}</span>
          <span>锁 {{ p.locked_quantity ?? "—" }}</span>
          <span>成本 {{ p.avg_price }}</span>
          <span>昨收 {{ p.last_close }}</span>
        </li>
      </ul>
    </div>

    <div v-if="state" class="card full">
      <p class="card-hd">成交记录</p>
      <p v-if="ordersError" class="err err--sub">{{ ordersError }}</p>
      <div class="order-toolbar">
        <label class="field field--inline">
          <span class="lbl">筛选代码</span>
          <input
            v-model="ordersFilterCode"
            type="text"
            class="inp mono inp--sm"
            spellcheck="false"
            placeholder="留空为全部"
            @keyup.enter="applyOrderFilter"
          />
        </label>
        <button type="button" class="ghost" :disabled="ordersLoading" @click="applyOrderFilter">筛选</button>
        <button
          type="button"
          class="ghost"
          :disabled="ordersLoading || !orders.length"
          title="按当前列表顺序，每行一个代码（同代码多笔只出现一次）"
          aria-label="复制成交列表中的代码"
          @click="copyOrdersCodes"
        >
          复制代码
        </button>
        <span v-if="ordersTotal > 0" class="mono meta">共 {{ ordersTotal }} 条</span>
      </div>
      <ul v-if="orders.length" class="rows mono small">
        <li v-for="o in orders" :key="o.id" class="row row--7">
          <span>#{{ o.id }}</span>
          <span>{{ o.code }}</span>
          <span>{{ o.side }}</span>
          <span>{{ o.quantity }}</span>
          <span>@ {{ o.fill_price }}</span>
          <span>{{ o.trade_date || "—" }}</span>
          <span class="meta" :title="o.created_at">{{ fmtShort(o.created_at) }}</span>
        </li>
      </ul>
      <p v-else-if="!ordersLoading" class="mono meta empty-orders">暂无成交</p>
      <button
        v-if="orders.length > 0 && orders.length < ordersTotal"
        type="button"
        class="ghost load-more"
        :disabled="ordersLoading"
        @click="loadMoreOrders"
      >
        {{ ordersLoading ? "加载中…" : "加载更多" }}
      </button>
    </div>
  </section>
</template>

<style scoped>
.paper {
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
  flex-wrap: wrap;
  gap: 8px;
  flex-shrink: 0;
  justify-content: flex-end;
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

.ghost.danger {
  border-color: rgba(255, 120, 120, 0.35);
  color: #ff9a9a;
}

.tip {
  color: var(--gain);
  font-size: 0.8rem;
  margin: 0 0 10px;
}

.err {
  color: #ff8a8a;
  font-size: 0.85rem;
  margin: 0 0 10px;
}

.err--sub {
  font-size: 0.78rem;
  margin: 0 0 8px;
}

.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

@media (max-width: 820px) {
  .grid {
    grid-template-columns: 1fr;
  }
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

.big {
  font-size: 1.05rem;
  margin: 0 0 6px;
}

.dim {
  margin: 4px 0;
  font-size: 0.75rem;
  color: var(--mist-dim);
}

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

.linkish {
  display: block;
  margin-top: 12px;
  background: none;
  border: none;
  color: var(--mist-dim);
  font-size: 0.72rem;
  cursor: pointer;
  text-decoration: underline;
}

.rows {
  list-style: none;
  margin: 0;
  padding: 0;
}

.row {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 8px;
  padding: 8px 0;
  border-bottom: 1px solid rgba(42, 40, 53, 0.5);
  font-size: 0.78rem;
}

.row--6 {
  grid-template-columns: repeat(6, 1fr);
}

.small .row {
  font-size: 0.7rem;
}

.row--7 {
  grid-template-columns: repeat(7, minmax(0, 1fr));
}

.order-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 10px;
  margin-bottom: 10px;
}

.field--inline {
  flex-direction: row;
  align-items: center;
  gap: 8px;
  margin-bottom: 0;
}

.inp--sm {
  max-width: 200px;
}

.meta {
  font-size: 0.68rem;
  color: var(--mist-dim);
}

.empty-orders {
  margin: 6px 0 0;
}

.load-more {
  margin-top: 12px;
}

.wl-chips {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin: 8px 0 0;
}

.wl-chips-lbl {
  font-size: 0.58rem;
  letter-spacing: 0.12em;
  color: var(--mist-dim);
  font-weight: 700;
}

.wl-chip {
  font-size: 0.62rem;
  padding: 4px 8px;
  border-radius: 6px;
  border: 1px solid rgba(62, 224, 255, 0.25);
  background: rgba(62, 224, 255, 0.08);
  color: var(--meridian);
  cursor: pointer;
}

.wl-chip:hover {
  border-color: rgba(62, 224, 255, 0.45);
}
</style>
