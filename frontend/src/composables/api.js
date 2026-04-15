import { showToast } from "./useToast.js";

/**
 * API 基址：
 * - 开发：留空，走 Vite 代理 /api -> 后端
 * - 生产：VITE_API_BASE=https://host:port/api
 */
const raw = import.meta.env.VITE_API_BASE;
const prefix = (typeof raw === "string" && raw.trim() ? raw.trim() : "/api").replace(
  /\/$/,
  ""
);

export function apiUrl(path) {
  const p = path.replace(/^\//, "");
  return `${prefix}/${p}`;
}

/**
 * 从 JSON 体中解析 FastAPI 常见 `detail`（字符串或校验错误数组）。
 * @param {unknown} body
 * @param {string} fallback
 */
export function formatApiErrorBody(body, fallback) {
  if (!body || typeof body !== "object") return fallback;
  const d = body.detail;
  if (typeof d === "string" && d.trim()) return d.trim().slice(0, 800);
  if (Array.isArray(d)) {
    const m = d
      .map((x) => {
        if (x && typeof x === "object") {
          const one = x.msg || x.message;
          if (one) return String(one);
          try {
            return JSON.stringify(x);
          } catch {
            return "";
          }
        }
        return x != null ? String(x) : "";
      })
      .filter(Boolean)
      .join("；");
    if (m) return m.slice(0, 800);
  }
  return fallback;
}

/**
 * 读取非 2xx 响应的人类可读说明（尽量解析 JSON `detail`）。
 * @param {Response} res
 */
export async function readHttpErrorMessage(res) {
  const fallback = res.status === 503 ? "服务暂不可用" : `${res.status} ${res.statusText}`;
  let text = "";
  try {
    text = await res.text();
  } catch {
    return fallback;
  }
  if (!text) return fallback;
  try {
    return formatApiErrorBody(JSON.parse(text), fallback);
  } catch {
    return text.length > 400 ? `${text.slice(0, 400)}…` : text;
  }
}

/**
 * 发起请求并在 2xx（含 204）时返回 `Response`；否则解析错误、可选 Toast 并 `throw`。
 * @param {string} url
 * @param {RequestInit & { toast?: boolean }} [options]
 * @param {boolean} [defaultToast=true]
 */
async function fetchOkResponseFromUrl(url, options = {}, defaultToast = true) {
  const { toast = defaultToast, ...fetchOpts } = options;
  let res;
  try {
    res = await fetch(url, fetchOpts);
  } catch (e) {
    const msg =
      e instanceof TypeError
        ? "网络不可达，请检查后端或代理"
        : String(e?.message || "请求失败").trim() || "请求失败";
    if (toast) showToast(msg, { type: "error" });
    throw new Error(msg);
  }
  if (res.status === 429) {
    if (toast) showToast("请求过于频繁，请稍后再试", { type: "error" });
    throw new Error("请求过于频繁，请稍后再试");
  }
  if (!res.ok) {
    const msg = await readHttpErrorMessage(res);
    if (toast) showToast(msg, { type: "error" });
    throw new Error(msg);
  }
  return res;
}

/**
 * @param {string} url 完整 URL 或同源绝对路径（如 `https://x/api/foo` 或 `/health`）
 * @param {RequestInit & { toast?: boolean }} [options]
 * @param {boolean} [defaultToast=true] 未传 `options.toast` 时的默认
 */
async function fetchJsonFromUrl(url, options = {}, defaultToast = true) {
  const { toast = defaultToast } = options;
  const res = await fetchOkResponseFromUrl(url, options, defaultToast);
  if (res.status === 204 || res.status === 205) return null;
  try {
    return await res.json();
  } catch (e) {
    const name = e?.name === "SyntaxError" ? "响应体不是合法 JSON" : "响应解析失败";
    if (toast) showToast(name, { type: "error" });
    throw new Error(name);
  }
}

/**
 * @param {string} path
 * @param {RequestInit & { toast?: boolean }} [options] 传入 `toast: false` 可关闭全局提示（轮询或与面板内错误重复时）
 */
export async function fetchJson(path, options = {}) {
  return fetchJsonFromUrl(apiUrl(path), options, true);
}

/**
 * 同源绝对路径 JSON（不经 `VITE_API_BASE` 的 `/api` 前缀），供 **`/health`** 等探针与网关同路径部署。
 * 默认 **`toast: false`**（避免轮询刷屏）；可显式传入 **`toast: true`**。
 * @param {string} urlPath 如 `/health`、`/health/ready`
 */
export async function fetchJsonAbs(urlPath, options = {}) {
  const url = urlPath.startsWith("/") ? urlPath : `/${urlPath}`;
  return fetchJsonFromUrl(url, options, false);
}

/**
 * 成功时返回 `Response`（可再 `.blob()` / `.text()`）；失败时解析错误、可选 Toast 并 `throw`。
 * @param {string} path
 * @param {RequestInit & { toast?: boolean }} [options]
 */
export async function fetchOkResponse(path, options = {}) {
  return fetchOkResponseFromUrl(apiUrl(path), options, true);
}
