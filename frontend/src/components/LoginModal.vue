<script setup>
import { ref, computed } from "vue";
import { useAuth } from "../composables/useAuth.js";

const { login, register, loading } = useAuth();

const emit = defineEmits(["close", "success"]);

const mode = ref("login"); // 'login' | 'register'
const username = ref("");
const password = ref("");
const error = ref("");
const showPassword = ref(false);
const messageType = ref("error"); // 'error' | 'success'

function close() {
  username.value = "";
  password.value = "";
  error.value = "";
  messageType.value = "error";
  emit("close");
}

const isFormValid = computed(() => {
  const u = (username.value || "").trim();
  const p = (password.value || "").trim();
  return u.length >= 3 && p.length >= 6;
});

async function onSubmit() {
  error.value = "";
  const u = (username.value || "").trim();
  const p = (password.value || "").trim();
  
  if (!u) {
    error.value = "请输入用户名";
    messageType.value = "error";
    return;
  }
  
  if (u.length < 3) {
    error.value = "用户名至少 3 位";
    messageType.value = "error";
    return;
  }
  
  if (!p) {
    error.value = "请输入密码";
    messageType.value = "error";
    return;
  }
  
  if (p.length < 6) {
    error.value = "密码至少 6 位";
    messageType.value = "error";
    return;
  }

  if (mode.value === "register") {
    const ok = await register(u, p);
    if (ok) {
      mode.value = "login";
      error.value = "注册成功，请登录";
      messageType.value = "success";
      password.value = "";
    } else {
      messageType.value = "error";
    }
    return;
  }

  const ok = await login(u, p);
  if (ok) {
    emit("success");
    close();
  } else {
    messageType.value = "error";
  }
}

function switchMode() {
  mode.value = mode.value === "login" ? "register" : "login";
  error.value = "";
  messageType.value = "error";
}

function togglePassword() {
  showPassword.value = !showPassword.value;
}
</script>

<template>
  <div class="login-overlay" @click.self="close">
    <div class="login-modal">
      <button type="button" class="login-close" @click="close" aria-label="关闭">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="18" y1="6" x2="6" y2="18"/>
          <line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
      </button>
      
      <div class="login-header">
        <div class="login-logo">◈</div>
        <h3 class="login-title">{{ mode === "login" ? "登录" : "注册" }}</h3>
        <p class="login-subtitle">{{ mode === "login" ? "欢迎回来" : "创建账户" }}</p>
      </div>

      <form class="login-form" @submit.prevent="onSubmit">
        <label class="login-field">
          <span class="login-lbl">用户名</span>
          <div class="input-wrapper">
            <input
              v-model="username"
              type="text"
              class="login-inp mono"
              :class="{ 'is-invalid': error && !username.trim() }"
              placeholder="字母/数字/下划线 (至少3位)"
              autocomplete="username"
              maxlength="32"
            />
            <span v-if="username.trim().length >= 3" class="input-valid">✓</span>
          </div>
        </label>
        
        <label class="login-field">
          <span class="login-lbl">密码</span>
          <div class="input-wrapper">
            <input
              v-model="password"
              :type="showPassword ? 'text' : 'password'"
              class="login-inp mono"
              :class="{ 'is-invalid': error && !password.trim() }"
              placeholder="至少 6 位字符"
              autocomplete="current-password"
              maxlength="64"
            />
            <button
              type="button"
              class="toggle-password"
              @click="togglePassword"
              :aria-label="showPassword ? '隐藏密码' : '显示密码'"
            >
              <svg v-if="!showPassword" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                <circle cx="12" cy="12" r="3"/>
              </svg>
              <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1 4.24 4.24"/>
                <line x1="1" y1="1" x2="23" y2="23"/>
              </svg>
            </button>
            <span v-if="password.length >= 6" class="input-valid">✓</span>
          </div>
        </label>

        <p v-if="error" class="login-message" :class="messageType">{{ error }}</p>

        <button type="submit" class="login-submit" :disabled="loading || !isFormValid">
          <span v-if="loading" class="login-spinner"></span>
          {{ loading ? "处理中…" : mode === "login" ? "登 录" : "注 册" }}
        </button>
      </form>

      <p class="login-switch">
        {{ mode === "login" ? "还没有账号？" : "已有账号？" }}
        <button type="button" class="login-link" @click="switchMode">
          {{ mode === "login" ? "立即注册" : "立即登录" }}
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
  background: rgba(0, 0, 0, 0.75);
  display: flex;
  align-items: center;
  justify-content: center;
  backdrop-filter: blur(8px);
  animation: fade-in 0.2s ease-out;
}

@keyframes fade-in {
  from { opacity: 0; }
  to { opacity: 1; }
}

.login-modal {
  position: relative;
  width: 360px;
  max-width: 92vw;
  padding: 28px 24px 28px;
  border-radius: 16px;
  border: 1px solid rgba(232, 197, 71, 0.18);
  background: linear-gradient(165deg, rgba(24, 20, 8, 0.98) 0%, rgba(12, 10, 4, 0.96) 100%);
  box-shadow: 
    0 24px 64px rgba(0, 0, 0, 0.6),
    0 0 40px rgba(232, 197, 71, 0.05);
  animation: slide-up 0.3s ease-out;
}

@keyframes slide-up {
  from {
    opacity: 0;
    transform: translateY(20px) scale(0.98);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

.login-close {
  position: absolute;
  top: 12px;
  right: 12px;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--rule-faint);
  border-radius: 8px;
  color: var(--mist-dim);
  cursor: pointer;
  transition: all 0.2s ease;
}

.login-close:hover {
  color: var(--mist);
  background: rgba(255, 255, 255, 0.08);
  border-color: var(--gold-muted);
}

.login-header {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-bottom: 24px;
}

.login-logo {
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.5rem;
  font-weight: 800;
  color: var(--void);
  background: linear-gradient(145deg, var(--gold) 0%, #f0e6a8 50%, #c9a227 100%);
  clip-path: polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%);
  box-shadow: 0 0 24px rgba(232, 197, 71, 0.3);
  margin-bottom: 12px;
}

.login-title {
  margin: 0 0 4px;
  font-family: var(--font-display);
  font-size: 1.3rem;
  font-weight: 700;
  color: var(--gold);
}

.login-subtitle {
  margin: 0;
  font-size: 0.75rem;
  color: var(--mist-dim);
  letter-spacing: 0.08em;
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.login-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.login-lbl {
  font-size: 0.72rem;
  color: var(--mist-dim);
  letter-spacing: 0.06em;
}

.input-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}

.login-inp {
  flex: 1;
  padding: 12px 14px;
  padding-right: 40px;
  border-radius: 10px;
  border: 1px solid var(--rule-faint);
  background: rgba(8, 8, 12, 0.8);
  color: var(--mist);
  font-size: 0.85rem;
  outline: none;
  transition: all 0.2s ease;
}

.login-inp:focus {
  border-color: rgba(232, 197, 71, 0.45);
  box-shadow: 0 0 0 3px rgba(232, 197, 71, 0.08);
}

.login-inp.is-invalid {
  border-color: rgba(255, 92, 69, 0.5);
}

.login-inp::placeholder {
  color: rgba(109, 106, 122, 0.6);
}

.toggle-password {
  position: absolute;
  right: 12px;
  background: none;
  border: none;
  color: var(--mist-dim);
  cursor: pointer;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: color 0.2s ease;
}

.toggle-password:hover {
  color: var(--meridian);
}

.input-valid {
  position: absolute;
  right: 36px;
  color: var(--jade);
  font-size: 0.85rem;
  font-weight: 600;
}

.login-message {
  margin: 0;
  font-size: 0.72rem;
  text-align: center;
  padding: 8px 12px;
  border-radius: 6px;
}

.login-message.error {
  color: #ff9a9a;
  background: rgba(255, 92, 69, 0.1);
}

.login-message.success {
  color: var(--jade);
  background: rgba(46, 230, 168, 0.1);
}

.login-submit {
  margin-top: 8px;
  padding: 13px 16px;
  border-radius: 10px;
  border: 1px solid rgba(232, 197, 71, 0.35);
  background: rgba(232, 197, 71, 0.14);
  color: var(--gold);
  font-family: var(--font-display);
  font-size: 0.85rem;
  font-weight: 700;
  letter-spacing: 0.1em;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.login-submit:hover:not(:disabled) {
  background: rgba(232, 197, 71, 0.24);
  border-color: rgba(232, 197, 71, 0.55);
  box-shadow: 0 0 20px rgba(232, 197, 71, 0.15);
}

.login-submit:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.login-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid var(--gold-muted);
  border-top-color: var(--gold);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.login-switch {
  margin: 16px 0 0;
  text-align: center;
  font-size: 0.74rem;
  color: var(--mist-dim);
}

.login-link {
  background: none;
  border: none;
  color: var(--meridian);
  font-size: 0.74rem;
  font-weight: 600;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 2px;
  padding: 0;
  transition: color 0.2s ease;
}

.login-link:hover {
  color: var(--gold);
}

/* 移动端优化 */
@media (max-width: 576px) {
  .login-modal {
    width: 94vw;
    padding: 22px 18px 22px;
  }
  
  .login-header {
    margin-bottom: 20px;
  }
  
  .login-logo {
    width: 40px;
    height: 40px;
    font-size: 1.25rem;
    margin-bottom: 10px;
  }
  
  .login-title {
    font-size: 1.15rem;
  }
  
  .login-form {
    gap: 12px;
  }
  
  .login-inp {
    padding: 11px 12px;
    padding-right: 36px;
    font-size: 0.8rem;
  }
}
</style>
