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

export async function fetchJson(path, options = {}) {
  const res = await fetch(apiUrl(path), options);
  if (res.status === 429) {
    throw new Error("请求过于频繁，请稍后再试");
  }
  if (!res.ok) {
    const hint = res.status === 503 ? "服务暂不可用" : `${res.status} ${res.statusText}`;
    throw new Error(hint);
  }
  return res.json();
}
