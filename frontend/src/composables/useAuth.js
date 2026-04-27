/**
 * 认证状态管理：登录、登出、token 持久化、用户信息获取。
 */
import { ref, computed } from "vue";
import { fetchJson } from "./api.js";
import { showToast } from "./useToast.js";

const LS_TOKEN_KEY = "tb_auth_token";
const LS_USER_KEY = "tb_auth_user";

const token = ref("");
const user = ref(null);
const loading = ref(false);

function readStoredToken() {
  try {
    return localStorage.getItem(LS_TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

function readStoredUser() {
  try {
    const raw = localStorage.getItem(LS_USER_KEY);
    if (raw) return JSON.parse(raw);
  } catch {
    /* ignore */
  }
  return null;
}

// 初始化时从 localStorage 恢复
token.value = readStoredToken();
user.value = readStoredUser();

export function useAuth() {
  const isLoggedIn = computed(() => !!token.value && !!user.value);
  const username = computed(() => user.value?.username || "");

  function _save(t, u) {
    token.value = t;
    user.value = u;
    try {
      if (t) localStorage.setItem(LS_TOKEN_KEY, t);
      else localStorage.removeItem(LS_TOKEN_KEY);
      if (u) localStorage.setItem(LS_USER_KEY, JSON.stringify(u));
      else localStorage.removeItem(LS_USER_KEY);
    } catch {
      /* ignore */
    }
  }

  async function login(usernameRaw, password) {
    loading.value = true;
    try {
      const body = await fetchJson("auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: usernameRaw.trim(), password }),
        toast: false,
      });
      if (!body?.access_token) {
        throw new Error("登录响应缺少 token");
      }
      _save(body.access_token, { username: body.username, id: null });
      // 拉取用户信息
      await loadMe();
      showToast(`欢迎回来，${user.value?.username || ""}`, { type: "success", duration: 2000 });
      return true;
    } catch (e) {
      showToast(e?.message || "登录失败", { type: "error" });
      return false;
    } finally {
      loading.value = false;
    }
  }

  async function register(usernameRaw, password) {
    loading.value = true;
    try {
      await fetchJson("auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: usernameRaw.trim(), password }),
        toast: false,
      });
      showToast("注册成功，请登录", { type: "success", duration: 2000 });
      return true;
    } catch (e) {
      showToast(e?.message || "注册失败", { type: "error" });
      return false;
    } finally {
      loading.value = false;
    }
  }

  async function loadMe() {
    if (!token.value) return;
    try {
      const body = await fetchJson("auth/me", { toast: false });
      user.value = { id: body.id, username: body.username, is_active: body.is_active };
      try {
        localStorage.setItem(LS_USER_KEY, JSON.stringify(user.value));
      } catch {
        /* ignore */
      }
    } catch {
      // token 无效，清空
      _save("", null);
    }
  }

  function logout() {
    _save("", null);
    showToast("已登出", { type: "info", duration: 1500 });
  }

  return {
    token,
    user,
    loading,
    isLoggedIn,
    username,
    login,
    register,
    logout,
    loadMe,
  };
}
