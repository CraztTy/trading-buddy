import { computed, ref } from "vue";
import { apiUrl, fetchJson } from "./api.js";

/**
 * 用 GET /api/dashboard/overview 首条指数的 date 作为 as_of_date，拼 GET /api/factors/cross-section。
 * 与主要指数卡片同一交易日，供行情侧栏与因子页共用。
 */
export function useCrossSectionOverviewLink() {
  const crossSectionAsOf = ref("");
  const crossSectionHref = computed(() => {
    const d = crossSectionAsOf.value.trim();
    if (!d) return "";
    const q = new URLSearchParams({
      as_of_date: d,
      period: "20",
      max_codes: "100",
    });
    return apiUrl(`factors/cross-section?${q.toString()}`);
  });

  async function refreshCrossSectionAsOf() {
    try {
      // 与 MarketIndices 同源：失败时由指数区展示即可，避免重复 Toast
      const data = await fetchJson("dashboard/overview", { toast: false });
      const first = Array.isArray(data?.indices) ? data.indices[0] : null;
      crossSectionAsOf.value = typeof first?.date === "string" ? first.date.trim() : "";
    } catch {
      crossSectionAsOf.value = "";
    }
  }

  return { crossSectionAsOf, crossSectionHref, refreshCrossSectionAsOf };
}
