<script setup>
import { ref } from "vue";
import { useAuth } from "../composables/useAuth.js";

const { login, register, loading } = useAuth();

const emit = defineEmits(["close", "success"]);

const mode = ref("login"); // 'login' | 'register'
const username = ref("");
const password = ref("");
const error = ref("");

function close() {
  username.value = "";
  password.value = "";
  error.value = "";
  emit("close");
}

async function onSubmit() {
  error.value = "";
  const u = (username.value || "").trim();
  const p = (password.value || "").trim();
  if (!u || !p) {
    error.value = "请填写用户名和密码";
    return;
  }
  if (p.length < 6) {
    error.value = "密码至少 6 位";
    return;
  }

  if (mode.value === "register") {
    const ok = await register(u, p);
    if (ok) {
      mode.value = "login";
      error.value = "注册成功，请登录";
    }
    return;
  }

  const ok = await login(u, p);
  if (ok) {
    emit("success");
    close();
  }
}

function switchMode() {
  mode.value = mode.value === "login" ? "register" : "login";
  error.value = "";
}
</script>

<template>
  <div class="login-overlay" @click.self="close">
    <div class="login-modal">
      <button type="button" class="login-close" @click="close">&times;</button>
      <h3 class="login-title">{{ mode === "login" ? "登录" : "注册" }}</h3>

      <form class="login-form" @submit.prevent="onSubmit">
        <label class="login-field">
          <span class="login-lbl">用户名</span>
          <input
            v-model="username"
            type="text"
            class="login-inp mono"
            placeholder="字母/数字/下划线"
            autocomplete="username"
          />
        </label>
        <label class="login-field">
          <span class="login-lbl">密码</span>
          <input
            v-model="password"
            type="password"
            class="login-inp mono"
            placeholder="至少 6 位"
            autocomplete="current-password"
          />
        </label>

        <p v-if="error" class="login-err">{{ error }}</p>

        <button type="submit" class="login-submit" :disabled="loading">
          {{ loading ? "处理中…" : mode === "login" ? "登录" : "注册" }}
        </button>
      </form>

      <p class="login-switch">
        {{ mode === "login" ? "还没有账号？" : "已有账号？" }}
        <button type="button" class="login-link" @click="switchMode">
          {{ mode === "login" ? "注册" : "登录" }}
        </button>
      </p>
    </div>
  </div>
</template>

<style scoped>
.login-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(0, 0, 0, 0.65);
  display: flex;
  align-items: center;
  justify-content: center;
  backdrop-filter: blur(4px);
}

.login-modal {
  position: relative;
  width: 360px;
  max-width: 92vw;
  padding: 28px 24px 22px;
  border-radius: 14px;
  border: 1px solid rgba(232, 197, 71, 0.2);
  background: linear-gradient(165deg, rgba(24, 20, 8, 0.98) 0%, rgba(12, 10, 4, 0.96) 100%);
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.55);
}

.login-close {
  position: absolute;
  top: 10px;
  right: 14px;
  background: none;
  border: none;
  color: var(--mist-dim);
  font-size: 1.4rem;
  cursor: pointer;
  line-height: 1;
}

.login-close:hover {
  color: var(--mist);
}

.login-title {
  margin: 0 0 18px;
  font-family: var(--font-display);
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--gold);
  text-align: center;
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.login-field {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.login-lbl {
  font-size: 0.72rem;
  color: var(--mist-dim);
}

.login-inp {
  padding: 9px 12px;
  border-radius: 8px;
  border: 1px solid var(--rule-faint);
  background: rgba(8, 8, 12, 0.7);
  color: var(--mist);
  font-size: 0.8rem;
  outline: none;
  transition: border-color 0.2s ease;
}

.login-inp:focus {
  border-color: rgba(232, 197, 71, 0.45);
}

.login-err {
  margin: 0;
  font-size: 0.72rem;
  color: #ff9a9a;
  text-align: center;
}

.login-submit {
  margin-top: 6px;
  padding: 10px 16px;
  border-radius: 8px;
  border: 1px solid rgba(232, 197, 71, 0.35);
  background: rgba(232, 197, 71, 0.12);
  color: var(--gold);
  font-family: var(--font-display);
  font-size: 0.8rem;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.2s ease;
}

.login-submit:hover:not(:disabled) {
  background: rgba(232, 197, 71, 0.22);
  border-color: rgba(232, 197, 71, 0.55);
}

.login-submit:disabled {
  opacity: 0.5;
  cursor: wait;
}

.login-switch {
  margin: 14px 0 0;
  text-align: center;
  font-size: 0.72rem;
  color: var(--mist-dim);
}

.login-link {
  background: none;
  border: none;
  color: var(--meridian);
  font-size: 0.72rem;
  cursor: pointer;
  text-decoration: underline;
  padding: 0;
}

.login-link:hover {
  color: var(--gold);
}
</style>
