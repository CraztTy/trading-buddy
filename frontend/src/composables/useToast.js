import { ref } from "vue";

const open = ref(false);
const message = ref("");
const kind = ref("error");

let hideTimer = 0;

/**
 * @param {string} text
 * @param {{ type?: "error" | "info"; duration?: number }} [opts]
 */
export function showToast(text, opts = {}) {
  const { type = "error", duration = 4800 } = opts;
  const t = String(text || "").trim().slice(0, 400);
  message.value = t || "出错了";
  kind.value = type === "info" ? "info" : "error";
  open.value = true;
  if (hideTimer) window.clearTimeout(hideTimer);
  hideTimer = window.setTimeout(() => {
    open.value = false;
    hideTimer = 0;
  }, Math.max(1200, duration));
}

export function dismissToast() {
  open.value = false;
  if (hideTimer) {
    window.clearTimeout(hideTimer);
    hideTimer = 0;
  }
}

export function useToast() {
  return { open, message, kind, show: showToast, dismiss: dismissToast };
}
