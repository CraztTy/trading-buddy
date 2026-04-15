import { onMounted, onUnmounted, ref } from "vue";
import { fetchJsonAbs } from "./api.js";

const POLL_MS = 60_000;

/**
 * 轮询根路径 /health 与 /health/ready（经 Vite 代理到后端）。
 * @returns {{ state: import('vue').Ref<'loading'|'ok'|'degraded'|'down'>, detail: import('vue').Ref<object|null>, readyDetail: import('vue').Ref<object|null>, refresh: () => Promise<void> }}
 */
export function useApiHealth() {
  const state = ref("loading");
  const detail = ref(null);
  const readyDetail = ref(null);

  async function refresh() {
    try {
      const j = await fetchJsonAbs("/health", {
        headers: { Accept: "application/json" },
      });
      detail.value = j;
      if (j.status !== "healthy") {
        state.value = "down";
        readyDetail.value = null;
        return;
      }

      try {
        const rj = await fetchJsonAbs("/health/ready", {
          headers: { Accept: "application/json" },
        });
        readyDetail.value = rj;
        state.value = rj.status === "ready" ? "ok" : "degraded";
      } catch {
        readyDetail.value = null;
        state.value = "degraded";
      }
    } catch {
      state.value = "down";
      detail.value = null;
      readyDetail.value = null;
    }
  }

  let timer;

  onMounted(() => {
    refresh();
    timer = setInterval(refresh, POLL_MS);
  });

  onUnmounted(() => {
    if (timer) clearInterval(timer);
  });

  return { state, detail, readyDetail, refresh };
}
