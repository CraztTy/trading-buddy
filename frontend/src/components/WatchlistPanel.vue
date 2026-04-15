<script setup>
import { onMounted, ref } from "vue";
import { fetchJson } from "../composables/api.js";
import { writeClipboardText } from "../composables/clipboardWrite.js";
import { showToast } from "../composables/useToast.js";

const emit = defineEmits(["select"]);

const loading = ref(false);
const error = ref("");
const items = ref([]);
const watchlistId = ref(null);
/** 最近一次成功的 GET /api/watchlist/items */
const lastWatchlistApiPath = ref("");

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const data = await fetchJson("watchlist/items", { toast: false });
    watchlistId.value = data.watchlist_id;
    items.value = Array.isArray(data.items) ? data.items : [];
    lastWatchlistApiPath.value = "/api/watchlist/items";
  } catch (e) {
    items.value = [];
    error.value = e?.message || "加载失败";
    lastWatchlistApiPath.value = "";
  } finally {
    loading.value = false;
  }
}

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

async function removeCode(code) {
  const c = (code || "").trim();
  if (!c) return;
  if (!window.confirm(`从自选移除 ${c}？`)) return;
  error.value = "";
  try {
    await fetchJson(`watchlist/items/${encodeURIComponent(c)}`, { method: "DELETE", toast: false });
    await load();
  } catch (e) {
    error.value = e?.message || "删除失败";
  }
}

function goChart(code) {
  emit("select", (code || "").trim().toLowerCase());
}

async function copyWatchlistApiPath() {
  const u = lastWatchlistApiPath.value.trim();
  if (!u) return;
  try {
    await writeClipboardText(u);
    showToast("已复制自选列表 API 路径（curl 请自行拼接主机）", {
      type: "info",
      duration: 3000,
    });
  } catch {
    showToast("无法写入剪贴板，请检查浏览器权限", { type: "error" });
  }
}

async function copyAllCodes() {
  const lines = items.value.map((it) => String(it.code || "").trim()).filter(Boolean);
  if (!lines.length) return;
  const text = lines.join("\n");
  try {
    await writeClipboardText(text);
    showToast(`已复制 ${lines.length} 条代码（每行一条）`, { type: "info", duration: 2400 });
  } catch {
    showToast("无法写入剪贴板，请检查浏览器权限", { type: "error" });
  }
}

onMounted(load);
</script>

<template>
  <section class="wl">
    <header class="hd">
      <div>
        <p class="eyebrow">研究</p>
        <h2 class="h2">我的自选</h2>
        <p class="sub">
          与 <span class="mono">GET /api/watchlist/items</span> 同步；点击名称或代码切到<strong>行情看板</strong>并切换标的；删除仅从自选移除。可将全部代码<strong>复制到剪贴板</strong>（每行一条）。
        </p>
      </div>
      <div class="hd-actions">
        <button
          type="button"
          class="ghost"
          :disabled="loading || !items.length"
          title="每行一个标的代码"
          aria-label="复制自选全部代码"
          @click="copyAllCodes"
        >
          复制代码
        </button>
        <button
          type="button"
          class="ghost"
          :disabled="loading || !!error || !lastWatchlistApiPath"
          title="复制 GET /api/watchlist/items 路径"
          aria-label="复制自选列表 API 路径"
          @click="copyWatchlistApiPath"
        >
          复制 API 路径
        </button>
        <button type="button" class="ghost" :disabled="loading" @click="load">刷新</button>
      </div>
    </header>

    <p v-if="watchlistId != null" class="meta mono">watchlist_id {{ watchlistId }}</p>
    <p v-if="error" class="err">{{ error }}</p>

    <p v-if="!loading && !items.length && !error" class="hint">暂无自选。在「股票列表」中点击「加自选」添加。</p>

    <ul v-else-if="items.length" class="rows mono">
      <li v-for="it in items" :key="it.code" class="row">
        <button type="button" class="link-name" @click="goChart(it.code)">
          {{ it.name || it.code }}
        </button>
        <span class="cd">{{ it.code }}</span>
        <span class="dim">{{ fmtShort(it.created_at) }}</span>
        <button type="button" class="ghost sm" @click="goChart(it.code)">行情</button>
        <button type="button" class="ghost sm danger" @click="removeCode(it.code)">移除</button>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.wl {
  border: 1px solid var(--rule);
  border-radius: 2px;
  background: linear-gradient(180deg, var(--ink-card) 0%, rgba(10, 10, 15, 0.4) 100%);
  padding: 20px 22px 24px;
}

.hd {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 14px;
}

.hd-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
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
  max-width: 560px;
  line-height: 1.45;
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
  flex-shrink: 0;
}

.ghost.sm {
  padding: 6px 10px;
  font-size: 0.58rem;
}

.ghost.danger {
  border-color: rgba(255, 120, 120, 0.35);
  color: #ff9a9a;
}

.meta {
  font-size: 0.68rem;
  color: var(--mist-dim);
  margin: 0 0 8px;
}

.err {
  color: #ff8a8a;
  font-size: 0.85rem;
}

.hint {
  color: var(--mist-dim);
  font-size: 0.82rem;
}

.rows {
  list-style: none;
  margin: 0;
  padding: 0;
}

.row {
  display: grid;
  grid-template-columns: 1fr auto auto auto auto;
  gap: 10px;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid rgba(42, 40, 53, 0.5);
  font-size: 0.8rem;
}

.link-name {
  text-align: left;
  background: none;
  border: none;
  color: var(--meridian);
  cursor: pointer;
  font: inherit;
  padding: 0;
}

.cd {
  color: var(--mist);
}

.dim {
  color: var(--mist-dim);
  font-size: 0.72rem;
}
</style>
