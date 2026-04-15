<script setup>
import { computed } from "vue";
import { writeClipboardText } from "../composables/clipboardWrite.js";
import { showToast } from "../composables/useToast.js";
import { useApiHealth } from "../composables/useApiHealth.js";

const { state, detail, readyDetail, refresh } = useApiHealth();

const HEALTH_PATHS_TEXT = "/health\n/health/ready";

async function copyHealthPaths() {
  try {
    await writeClipboardText(HEALTH_PATHS_TEXT);
    showToast("已复制 /health 与 /health/ready（每行一条，同源 JSON GET）", {
      type: "info",
      duration: 2800,
    });
  } catch {
    showToast("无法写入剪贴板，请检查浏览器权限", { type: "error" });
  }
}

const shortLabel = computed(() => {
  switch (state.value) {
    case "loading":
      return "检测…";
    case "ok":
      return "在线";
    case "degraded":
      return "半在线";
    case "down":
      return "离线";
    default:
      return "—";
  }
});

const ariaLabel = computed(() => {
  switch (state.value) {
    case "loading":
      return "后端 API：正在检测";
    case "ok":
      return "后端 API：在线，数据库与 Redis 就绪检查通过";
    case "degraded":
      return "后端 API：进程在线，但就绪检查未通过（数据库或 Redis）";
    case "down":
      return "后端 API：无法连接或返回异常";
    default:
      return "后端 API";
  }
});

const title = computed(() => {
  const d = detail.value;
  const r = readyDetail.value;
  const lines = [];
  if (d && typeof d === "object") {
    if (d.app_version != null) lines.push(`版本 ${d.app_version}`);
    if (d.database_mode != null) lines.push(`库 ${d.database_mode}`);
    if (d.redis_enabled != null) lines.push(`Redis ${d.redis_enabled ? "开" : "关"}`);
  }
  if (r && typeof r === "object") {
    lines.push(`就绪 ${r.status}`);
    if (r.database) lines.push(`DB ${r.database}`);
    if (r.redis) lines.push(`Redis ${r.redis}`);
    if (r.probe_ms != null) lines.push(`探测 ${r.probe_ms}ms`);
  }
  lines.push("点击立即重检");
  return lines.join(" · ");
});
</script>

<template>
  <div class="api-health-wrap">
    <button
      type="button"
      class="api-health"
      :class="state"
      data-testid="api-health"
      :aria-busy="state === 'loading'"
      :aria-label="ariaLabel"
      :title="title"
      @click="refresh"
    >
      <span class="api-health-dot" aria-hidden="true" />
      <span class="api-health-text">{{ shortLabel }}</span>
    </button>
    <button
      type="button"
      class="api-health-copy"
      title="复制 /health 与 /health/ready（每行一条）"
      aria-label="复制健康检查路径"
      @click.stop="copyHealthPaths"
    >
      路径
    </button>
  </div>
</template>

<style scoped>
.api-health-wrap {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
}

.api-health {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px 3px 8px;
  font-family: var(--font-mono);
  font-size: 0.58rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  border-radius: 100px;
  border: 1px solid var(--rule-faint);
  background: rgba(18, 18, 28, 0.55);
  color: var(--mist-dim);
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    color 0.2s ease,
    background 0.2s ease;
}

.api-health:hover {
  color: var(--mist);
  border-color: rgba(62, 224, 255, 0.25);
}

.api-health.loading {
  border-color: rgba(232, 197, 71, 0.25);
}

.api-health.ok {
  color: var(--jade);
  border-color: rgba(46, 230, 168, 0.35);
  background: rgba(46, 230, 168, 0.06);
}

.api-health.degraded {
  color: var(--gold);
  border-color: rgba(232, 197, 71, 0.4);
  background: rgba(232, 197, 71, 0.07);
}

.api-health.down {
  color: #f4717a;
  border-color: rgba(244, 113, 122, 0.45);
  background: rgba(244, 113, 122, 0.06);
}

.api-health-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  flex-shrink: 0;
  background: var(--mist-dim);
}

.api-health.loading .api-health-dot {
  background: var(--gold);
  animation: api-pulse 1.2s ease-in-out infinite;
}

.api-health.ok .api-health-dot {
  background: var(--jade);
  box-shadow: 0 0 8px var(--jade);
}

.api-health.degraded .api-health-dot {
  background: var(--gold);
  box-shadow: 0 0 8px rgba(232, 197, 71, 0.35);
}

.api-health.down .api-health-dot {
  background: #f4717a;
}

@keyframes api-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.35;
  }
}

.api-health-text {
  text-transform: none;
  letter-spacing: 0.04em;
}

.api-health-copy {
  flex-shrink: 0;
  padding: 3px 8px;
  font-family: var(--font-mono);
  font-size: 0.52rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  border-radius: 100px;
  border: 1px solid var(--rule-faint);
  background: rgba(18, 18, 28, 0.45);
  color: var(--mist-dim);
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    color 0.2s ease;
}

.api-health-copy:hover {
  color: var(--meridian);
  border-color: rgba(62, 224, 255, 0.3);
}

.api-health-copy:focus-visible {
  outline: 2px solid var(--meridian);
  outline-offset: 2px;
}
</style>
