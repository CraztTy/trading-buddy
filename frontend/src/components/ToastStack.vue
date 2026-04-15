<script setup>
import { useToast } from "../composables/useToast.js";

const { open, message, kind, dismiss } = useToast();
</script>

<template>
  <Teleport to="body">
    <Transition name="toast-pop">
      <div
        v-if="open"
        class="toast-host"
        role="alert"
        aria-live="assertive"
        data-testid="toast-stack"
      >
        <div class="toast" :class="kind">
          <span class="toast-msg">{{ message }}</span>
          <button type="button" class="toast-x" aria-label="关闭" @click="dismiss">×</button>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.toast-host {
  position: fixed;
  z-index: 200;
  left: 50%;
  bottom: max(24px, env(safe-area-inset-bottom, 0px));
  transform: translateX(-50%);
  width: min(92vw, 420px);
  pointer-events: none;
}

.toast {
  pointer-events: auto;
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px 14px 12px 16px;
  border-radius: 10px;
  border: 1px solid var(--rule-faint);
  background: linear-gradient(160deg, rgba(20, 20, 31, 0.98) 0%, rgba(10, 10, 15, 0.96) 100%);
  box-shadow:
    0 20px 48px rgba(0, 0, 0, 0.55),
    0 0 0 1px rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(16px);
}

.toast.error {
  border-color: rgba(255, 92, 69, 0.35);
  box-shadow:
    0 20px 48px rgba(0, 0, 0, 0.55),
    0 0 28px rgba(255, 92, 69, 0.12);
}

.toast.info {
  border-color: rgba(62, 224, 255, 0.28);
  box-shadow:
    0 20px 48px rgba(0, 0, 0, 0.55),
    0 0 24px rgba(62, 224, 255, 0.1);
}

.toast-msg {
  flex: 1;
  min-width: 0;
  font-family: var(--font-ui);
  font-size: 0.88rem;
  line-height: 1.45;
  color: var(--mist);
}

.toast.error .toast-msg {
  color: rgba(255, 210, 200, 0.95);
}

.toast-x {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  margin: -4px -6px -4px 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--mist-dim);
  font-size: 1.25rem;
  line-height: 1;
  cursor: pointer;
  transition: color 0.15s ease, background 0.15s ease;
}

.toast-x:hover {
  color: var(--mist);
  background: rgba(255, 255, 255, 0.06);
}

.toast-pop-enter-active,
.toast-pop-leave-active {
  transition:
    opacity 0.28s var(--ease-out-expo),
    transform 0.32s var(--ease-out-expo);
}

.toast-pop-enter-from,
.toast-pop-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(12px);
}

.toast-pop-enter-to,
.toast-pop-leave-from {
  opacity: 1;
  transform: translateX(-50%) translateY(0);
}
</style>
