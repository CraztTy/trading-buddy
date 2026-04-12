<script setup>
import { onMounted, onUnmounted, ref, watch } from "vue";
import { apiUrl, fetchJson } from "../composables/api.js";

/** 单次请求条数（与后端上限一致） */
const EXPORT_ALL_PAGE = 500;
/** 单次「导出全部」最多行数，避免超大结果拖垮浏览器 */
const EXPORT_ALL_MAX = 10_000;

const emit = defineEmits(["select"]);

const market = ref("");
const industry = ref("");
const stockType = ref("");
const limit = ref(50);
const offset = ref(0);
const total = ref(0);
const loading = ref(false);
const error = ref("");
const rows = ref([]);
const clampHint = ref("");
const copyTip = ref("");
let copyTipTimer = 0;
const exportTip = ref("");
let exportTipTimer = 0;
const exportingAll = ref(false);
const exportProgress = ref("");
/** 自选代码集合（小写） */
const watchCodes = ref(new Set());
const watchTip = ref("");
let watchTipTimer = 0;

async function refreshWatchCodes() {
  try {
    const data = await fetchJson("watchlist/items");
    const items = Array.isArray(data?.items) ? data.items : [];
    watchCodes.value = new Set(items.map((x) => String(x.code || "").toLowerCase()));
  } catch {
    watchCodes.value = new Set();
  }
}

function flashWatchTip(msg) {
  watchTip.value = msg;
  if (watchTipTimer) clearTimeout(watchTipTimer);
  watchTipTimer = window.setTimeout(() => {
    watchTip.value = "";
    watchTipTimer = 0;
  }, 2200);
}

function isWatched(code) {
  return watchCodes.value.has(String(code || "").trim().toLowerCase());
}

async function toggleWatchlist(row) {
  const code = String(row?.code || "").trim().toLowerCase();
  if (!code) return;
  if (exportingAll.value) return;
  watchTip.value = "";
  const inList = isWatched(code);
  try {
    if (inList) {
      const res = await fetch(apiUrl(`watchlist/items/${encodeURIComponent(code)}`), { method: "DELETE" });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        const d = body?.detail;
        throw new Error(typeof d === "string" ? d : res.statusText || "移除失败");
      }
      flashWatchTip(`已从自选移除 ${code}`);
    } else {
      const res = await fetch(apiUrl("watchlist/items"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        const d = body?.detail;
        if (res.status === 409) throw new Error(typeof d === "string" ? d : "已在自选中");
        throw new Error(typeof d === "string" ? d : res.statusText || "添加失败");
      }
      flashWatchTip(`已加入自选 ${code}`);
    }
    await refreshWatchCodes();
  } catch (e) {
    flashWatchTip(e?.message || "自选操作失败");
  }
}

watch([market, industry, stockType], () => {
  offset.value = 0;
  clampHint.value = "";
});

watch(limit, () => {
  offset.value = 0;
  clampHint.value = "";
});

function applyStockListFilters(p) {
  const m = (market.value || "").trim().toLowerCase();
  if (m) p.set("market", m);
  const ind = (industry.value || "").trim();
  if (ind) p.set("industry", ind);
  const st = (stockType.value || "").trim().toLowerCase();
  if (st) p.set("stock_type", st);
}

async function load() {
  loading.value = true;
  error.value = "";
  clampHint.value = "";
  rows.value = [];
  const requestedOffset = Math.max(0, Number(offset.value) || 0);
  const p = new URLSearchParams();
  applyStockListFilters(p);
  p.set("limit", String(Math.max(1, Math.min(500, Number(limit.value) || 50))));
  p.set("offset", String(Math.max(0, Number(offset.value) || 0)));
  const q = p.toString();
  try {
    const data = await fetchJson(`stocks/list${q ? `?${q}` : ""}`);
    rows.value = Array.isArray(data?.items) ? data.items : [];
    total.value = Number.isFinite(data?.total) ? data.total : 0;
    if (Number.isFinite(data?.offset)) {
      const eff = data.offset;
      if (eff !== requestedOffset) {
        clampHint.value = `服务端已将 offset ${requestedOffset} 调整为 ${eff}（与总数、每页条数对齐）。`;
      }
      offset.value = eff;
    }
  } catch (e) {
    error.value = e?.message || "加载失败";
    total.value = 0;
    clampHint.value = "";
  } finally {
    loading.value = false;
  }
}

function onRowClick(code) {
  emit("select", code);
}

function escapeCsvCell(value) {
  const v = String(value ?? "");
  if (/[",\n\r]/.test(v)) return `"${v.replace(/"/g, '""')}"`;
  return v;
}

/** 全量导出：序号 1…n（与列表页 offset 无关） */
function buildCsvDocument(allRows) {
  const header = ["序号", "代码", "名称", "状态"];
  const lines = [header.map(escapeCsvCell).join(",")];
  allRows.forEach((row, i) => {
    lines.push(
      [i + 1, row.code ?? "", row.name ?? "", row.status ?? ""].map(escapeCsvCell).join(",")
    );
  });
  return `\ufeff${lines.join("\n")}\n`;
}

/** 本页导出：序号 = offset + 行号 */
function buildCsvPageDocument(pageRows, listOffset) {
  const base = Math.max(0, Number(listOffset) || 0);
  const header = ["序号", "代码", "名称", "状态"];
  const lines = [header.map(escapeCsvCell).join(",")];
  pageRows.forEach((row, i) => {
    const seq = base + i + 1;
    lines.push(
      [seq, row.code ?? "", row.name ?? "", row.status ?? ""].map(escapeCsvCell).join(",")
    );
  });
  return `\ufeff${lines.join("\n")}\n`;
}

function exportCurrentPageCsv() {
  if (exportingAll.value) return;
  exportTip.value = "";
  exportProgress.value = "";
  if (copyTipTimer) clearTimeout(copyTipTimer);
  copyTip.value = "";
  if (!rows.value.length) return;
  const csvBody = buildCsvPageDocument(rows.value, offset.value);
  const stamp = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  const fname = `stocks_${stamp.getFullYear()}${pad(stamp.getMonth() + 1)}${pad(stamp.getDate())}_${pad(stamp.getHours())}${pad(stamp.getMinutes())}${pad(stamp.getSeconds())}_offset${offset.value}.csv`;
  triggerCsvDownload(csvBody, fname);
  exportTip.value = `已导出本页 ${rows.value.length} 条（${fname}）`;
  if (exportTipTimer) clearTimeout(exportTipTimer);
  exportTipTimer = window.setTimeout(() => {
    exportTip.value = "";
    exportTipTimer = 0;
  }, 3500);
}

function triggerCsvDownload(body, fname) {
  const blob = new Blob([body], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = fname;
  a.rel = "noopener";
  a.click();
  URL.revokeObjectURL(url);
}

async function exportAllMatchingCsv() {
  if (loading.value || exportingAll.value) return;
  const rawTotal = Number(total.value) || 0;
  if (rawTotal <= 0) return;
  const targetCount = Math.min(rawTotal, EXPORT_ALL_MAX);
  const truncated = rawTotal > EXPORT_ALL_MAX;
  if (exportTipTimer) clearTimeout(exportTipTimer);
  exportTipTimer = 0;
  exportTip.value = "";
  if (copyTipTimer) clearTimeout(copyTipTimer);
  copyTipTimer = 0;
  copyTip.value = "";
  exportProgress.value = "准备拉取…";
  exportingAll.value = true;
  try {
    const allRows = [];
    let reqOff = 0;
    while (allRows.length < targetCount) {
      exportProgress.value = `拉取中 ${allRows.length}/${targetCount}…`;
      const p = new URLSearchParams();
      applyStockListFilters(p);
      p.set("limit", String(EXPORT_ALL_PAGE));
      p.set("offset", String(reqOff));
      const data = await fetchJson(`stocks/list?${p.toString()}`);
      const items = Array.isArray(data?.items) ? data.items : [];
      const dataTotal = Number.isFinite(data?.total) ? data.total : rawTotal;
      const effOff = Number.isFinite(data?.offset) ? data.offset : reqOff;
      if (!items.length) break;
      for (let i = 0; i < items.length && allRows.length < targetCount; i++) {
        allRows.push(items[i]);
      }
      if (allRows.length >= targetCount) break;
      if (items.length < EXPORT_ALL_PAGE || effOff + items.length >= dataTotal) break;
      reqOff = effOff + items.length;
    }
    exportProgress.value = "";
    if (!allRows.length) {
      exportTip.value = "没有可导出的数据";
      exportTipTimer = window.setTimeout(() => {
        exportTip.value = "";
        exportTipTimer = 0;
      }, 3500);
      return;
    }
    const body = buildCsvDocument(allRows);
    const stamp = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    const fname = `stocks_all_${stamp.getFullYear()}${pad(stamp.getMonth() + 1)}${pad(stamp.getDate())}_${pad(stamp.getHours())}${pad(stamp.getMinutes())}${pad(stamp.getSeconds())}_n${allRows.length}.csv`;
    triggerCsvDownload(body, fname);
    exportTip.value = truncated
      ? `已导出 ${allRows.length} 条（共 ${rawTotal} 条，已按上限 ${EXPORT_ALL_MAX} 截断）· ${fname}`
      : `已导出全部 ${allRows.length} 条（${fname}）`;
    exportTipTimer = window.setTimeout(() => {
      exportTip.value = "";
      exportTipTimer = 0;
    }, 5000);
  } catch (e) {
    exportProgress.value = "";
    exportTip.value = e?.message || "导出失败";
    exportTipTimer = window.setTimeout(() => {
      exportTip.value = "";
      exportTipTimer = 0;
    }, 5000);
  } finally {
    exportingAll.value = false;
  }
}

async function copyStockCode(code) {
  const c = (code || "").trim();
  if (!c) return;
  exportProgress.value = "";
  exportTip.value = "";
  if (exportTipTimer) {
    clearTimeout(exportTipTimer);
    exportTipTimer = 0;
  }
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(c);
    } else {
      const ta = document.createElement("textarea");
      ta.value = c;
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
    copyTip.value = `已复制 ${c}`;
    if (copyTipTimer) clearTimeout(copyTipTimer);
    copyTipTimer = window.setTimeout(() => {
      copyTip.value = "";
      copyTipTimer = 0;
    }, 2500);
  } catch {
    copyTip.value = "复制失败（请检查浏览器权限）";
    if (copyTipTimer) clearTimeout(copyTipTimer);
    copyTipTimer = window.setTimeout(() => {
      copyTip.value = "";
      copyTipTimer = 0;
    }, 2500);
  }
}

onMounted(() => {
  refreshWatchCodes();
});

onUnmounted(() => {
  if (copyTipTimer) clearTimeout(copyTipTimer);
  if (exportTipTimer) clearTimeout(exportTipTimer);
  if (watchTipTimer) clearTimeout(watchTipTimer);
});

function prevPage() {
  const step = Math.max(1, Math.min(500, Number(limit.value) || 50));
  const off = Math.max(0, Number(offset.value) || 0);
  offset.value = Math.max(0, off - step);
  load();
}

function nextPage() {
  const step = Math.max(1, Math.min(500, Number(limit.value) || 50));
  const off = Math.max(0, Number(offset.value) || 0);
  if (off + step < total.value) {
    offset.value = off + step;
    load();
  }
}
</script>

<template>
  <section class="stock-list">
    <header class="hd">
      <div>
        <p class="eyebrow">数据</p>
        <h2 class="h2">股票列表</h2>
        <p class="sub">
          调用 <span class="mono">GET /api/stocks/list</span>（响应含
          <span class="mono">total</span> / <span class="mono">items</span>），点击行切换行情标的；行内「复制」仅复制代码；「导出本页
          CSV」仅导出当前页；「导出全部」按当前筛选分页拉取后合并（最多
          {{ EXPORT_ALL_MAX.toLocaleString() }} 条，UTF-8 BOM）
        </p>
      </div>
      <div class="hd-actions">
        <div class="hd-actions-row">
          <button
            type="button"
            class="export-csv export-csv--primary"
            :disabled="loading || exportingAll || total <= 0"
            aria-label="导出全部匹配 CSV"
            @click="exportAllMatchingCsv"
          >
            {{ exportingAll ? "导出中…" : "导出全部" }}
          </button>
          <button
            type="button"
            class="export-csv"
            :disabled="loading || exportingAll || rows.length === 0"
            aria-label="导出本页 CSV"
            @click="exportCurrentPageCsv"
          >
            导出本页 CSV
          </button>
        </div>
        <button type="button" class="run" :disabled="loading || exportingAll" @click="load">
          {{ loading ? "加载中…" : "查询" }}
        </button>
      </div>
    </header>

    <p v-if="clampHint && !error" class="clamp-hint">{{ clampHint }}</p>
    <p v-if="exportProgress" class="export-progress mono" aria-live="polite">{{ exportProgress }}</p>
    <p v-if="copyTip" class="copy-tip mono" role="status">{{ copyTip }}</p>
    <p v-if="watchTip" class="copy-tip mono" role="status">{{ watchTip }}</p>
    <p v-if="exportTip" class="export-tip mono" role="status">{{ exportTip }}</p>

    <p v-if="total > 0 && !error" class="total-line mono">
      共 {{ total }} 条 · 本页 {{ rows.length }} 条 · offset {{ offset }}
    </p>

    <div v-if="total > limit" class="pager">
      <button type="button" class="pg" :disabled="loading || exportingAll || offset <= 0" @click="prevPage">
        上一页
      </button>
      <button
        type="button"
        class="pg"
        :disabled="loading || exportingAll || offset + limit >= total"
        @click="nextPage"
      >
        下一页
      </button>
    </div>

    <div class="form">
      <label class="field">
        <span class="lbl">市场</span>
        <select v-model="market" class="inp mono" :disabled="exportingAll">
          <option value="">全部</option>
          <option value="sh">sh</option>
          <option value="sz">sz</option>
          <option value="bj">bj</option>
        </select>
      </label>
      <label class="field wide">
        <span class="lbl">行业前缀</span>
        <input
          v-model="industry"
          type="text"
          class="inp mono"
          placeholder="如 新能源、半导体"
          :disabled="exportingAll"
        />
      </label>
      <label class="field">
        <span class="lbl">类型</span>
        <select v-model="stockType" class="inp mono" :disabled="exportingAll">
          <option value="">不限</option>
          <option value="common">common</option>
          <option value="st">st</option>
          <option value="star">star</option>
          <option value="growth">growth</option>
          <option value="beijing">beijing</option>
        </select>
      </label>
      <label class="field">
        <span class="lbl">limit</span>
        <input v-model.number="limit" type="number" min="1" max="500" class="inp mono" :disabled="exportingAll" />
      </label>
      <label class="field">
        <span class="lbl">offset</span>
        <input v-model.number="offset" type="number" min="0" class="inp mono" :disabled="exportingAll" />
      </label>
    </div>

    <p v-if="error" class="err">{{ error }}</p>

    <div v-else-if="!loading && rows.length === 0" class="hint">点击「查询」拉取列表（空条件可列出前若干只）</div>

    <ul v-else-if="rows.length" class="list" :class="{ 'list--busy': exportingAll }">
      <li
        v-for="(row, i) in rows"
        :key="row.code"
        class="row"
        @click="onRowClick(row.code)"
      >
        <span class="num mono">{{ String(offset + i + 1).padStart(2, "0") }}</span>
        <div class="meta">
          <span class="nm">{{ row.name || row.code }}</span>
          <div class="code-line">
            <span class="cd mono">{{ row.code }}</span>
            <button
              type="button"
              class="copy-btn mono"
              title="复制代码"
              aria-label="复制代码"
              :disabled="exportingAll"
              @click.stop="copyStockCode(row.code)"
            >
              复制
            </button>
            <button
              type="button"
              class="wl-btn mono"
              :class="{ 'wl-btn--on': isWatched(row.code) }"
              :title="isWatched(row.code) ? '点击从自选移除' : '点击加入自选'"
              :aria-label="isWatched(row.code) ? '从自选移除' : '加入自选'"
              :disabled="exportingAll"
              @click.stop="toggleWatchlist(row)"
            >
              {{ isWatched(row.code) ? "自选 ✓" : "加自选" }}
            </button>
          </div>
        </div>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.stock-list {
  border: 1px solid var(--rule);
  border-radius: 2px;
  background: linear-gradient(180deg, var(--ink-card) 0%, rgba(10, 10, 15, 0.4) 100%);
  padding: 20px 22px 24px;
}

.hd {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
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
  max-width: 520px;
  line-height: 1.45;
}

.run {
  font-family: var(--font-display);
  font-size: 0.65rem;
  font-weight: 800;
  letter-spacing: 0.12em;
  padding: 10px 18px;
  border-radius: 10px;
  border: 1px solid rgba(62, 224, 255, 0.35);
  background: rgba(62, 224, 255, 0.12);
  color: var(--meridian);
  cursor: pointer;
  flex-shrink: 0;
}

.run:disabled {
  opacity: 0.5;
  cursor: default;
}

.hd-actions {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
}

.hd-actions-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}

.export-csv {
  font-family: var(--font-display);
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

.export-csv:disabled {
  opacity: 0.45;
  cursor: default;
}

.export-csv:hover:not(:disabled) {
  border-color: rgba(62, 224, 255, 0.28);
  color: var(--meridian);
}

.export-csv--primary {
  border-color: rgba(62, 224, 255, 0.32);
  background: rgba(62, 224, 255, 0.08);
  color: var(--meridian);
}

.export-progress {
  margin: 0 0 10px;
  font-size: 0.72rem;
  color: var(--mist-dim);
}

.list--busy {
  pointer-events: none;
  opacity: 0.62;
}

.export-tip {
  margin: 0 0 10px;
  font-size: 0.72rem;
  color: var(--gain);
}

.clamp-hint {
  margin: 0 0 10px;
  font-size: 0.72rem;
  color: var(--gold-muted);
  line-height: 1.45;
}

.copy-tip {
  margin: 0 0 10px;
  font-size: 0.72rem;
  color: var(--gain);
}

.total-line {
  margin: 0 0 10px;
  font-size: 0.72rem;
  color: var(--mist-dim);
}

.pager {
  display: flex;
  gap: 10px;
  margin-bottom: 12px;
}

.pg {
  font-family: var(--font-display);
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

.pg:disabled {
  opacity: 0.45;
  cursor: default;
}

.form {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 16px;
  margin-bottom: 14px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 100px;
}

.field.wide {
  flex: 1 1 200px;
}

.lbl {
  font-size: 0.65rem;
  color: var(--mist-dim);
  letter-spacing: 0.06em;
}

.inp {
  border: 1px solid var(--rule-faint);
  border-radius: 8px;
  padding: 8px 10px;
  background: rgba(8, 8, 12, 0.65);
  color: var(--mist);
  font-size: 0.85rem;
}

.mono {
  font-family: var(--font-mono);
}

.err {
  color: #ff8a8a;
  font-size: 0.85rem;
  margin: 0 0 10px;
}

.hint {
  font-size: 0.8rem;
  color: var(--mist-dim);
  margin: 8px 0 0;
}

.list {
  list-style: none;
  margin: 12px 0 0;
  padding: 0;
  border-top: 1px solid var(--rule-faint);
}

.row {
  display: grid;
  grid-template-columns: 36px 1fr;
  align-items: center;
  gap: 12px;
  padding: 10px 6px;
  border-bottom: 1px solid rgba(42, 40, 53, 0.6);
  cursor: pointer;
  transition: background 0.15s ease;
}

.row:hover {
  background: rgba(62, 224, 255, 0.06);
}

.num {
  font-size: 0.72rem;
  color: var(--mist-dim);
}

.meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.nm {
  font-size: 0.88rem;
  color: var(--mist);
  font-weight: 600;
}

.code-line {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  min-width: 0;
}

.cd {
  font-size: 0.72rem;
  color: var(--mist-dim);
}

.copy-btn {
  flex-shrink: 0;
  font-size: 0.62rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  padding: 3px 8px;
  border-radius: 6px;
  border: 1px solid var(--rule-faint);
  background: rgba(8, 8, 12, 0.55);
  color: var(--mist-dim);
  cursor: pointer;
  transition:
    color 0.15s ease,
    border-color 0.15s ease;
}

.copy-btn:hover {
  color: var(--meridian);
  border-color: rgba(62, 224, 255, 0.35);
}

.copy-btn:disabled {
  opacity: 0.45;
  cursor: default;
}

.wl-btn {
  flex-shrink: 0;
  margin-left: 6px;
  font-size: 0.58rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  padding: 3px 8px;
  border-radius: 6px;
  border: 1px solid var(--rule-faint);
  background: rgba(8, 8, 12, 0.55);
  color: var(--mist-dim);
  cursor: pointer;
}

.wl-btn--on {
  color: var(--gain);
  border-color: rgba(120, 220, 160, 0.35);
}

.wl-btn:hover {
  color: var(--meridian);
  border-color: rgba(62, 224, 255, 0.35);
}

.wl-btn:disabled {
  opacity: 0.45;
  cursor: default;
}
</style>
