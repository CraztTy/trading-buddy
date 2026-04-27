<script setup>
import { onMounted, ref } from "vue";
import { fetchJson } from "../composables/api.js";
import { showToast } from "../composables/useToast.js";

const killed = ref(false);
const loading = ref(false);

async function checkStatus() {
  try {
    const data = await fetchJson("kill-switch/status", { toast: false });
    killed.value = !!data?.killed;
  } catch {
    /* ignore */
  }
}

async function toggle() {
  loading.value = true;
  try {
    const next = !killed.value;
    const data = await fetchJson("kill-switch/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ killed: next }),
      toast: false,
    });
    killed.value = !!data?.killed;
    showToast(data?.message || (next ? "已暂停交易" : "已恢复交易"), {
      type: next ? "error" : "info",
      duration: 3000,
    });
  } catch (e) {
    showToast(e?.message || "操作失败", { type: "error" });
  } finally {
    loading.value = false;
  }
}

onMounted(checkStatus);
</script>

<template>
  <button
    type="button"
    class="kill-btn"
    :class="{ killed }"
    :disabled="loading"
    title="紧急停止所有交易与回测"
    @click="toggle"
  >
    <span class="pulse" />
    {{ killed ? "已暂停" : "紧急停止" }}
  </button>
</template>

<style scoped>
.kill-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-family: var(--font-display);
  font-size: 0.58rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  padding: 5px 10px;
  border-radius: 6px;
  border: 1px solid rgba(255, 80, 80, 0.4);
  background: rgba(255, 80, 80, 0.12);
  color: #ff9a9a;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.kill-btn:hover:not(:disabled) {
  background: rgba(255, 80, 80, 0.25);
  border-color: rgba(255, 80, 80, 0.6);
}

.kill-btn.killed {
  border-color: rgba(255, 80, 80, 0.7);
  background: rgba(255, 80, 80, 0.35);
  color: #fff;
  animation: breathe 2s ease-in-out infinite;
}

.kill-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.pulse {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #ff5050;
  display: inline-block;
}

@keyframes breathe {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}
</style>
