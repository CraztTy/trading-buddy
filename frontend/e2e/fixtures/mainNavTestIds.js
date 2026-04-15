/**
 * `App.vue` 主导航 `nav[aria-label="主视图"]` 内按钮的 `data-testid`，供 E2E 稳定选顶栏切换（避免文案子串与 strict 歧义）。
 * @type {const}
 */
export const MAIN_NAV = {
  market: "main-nav-market",
  stocks: "main-nav-stocks",
  watchlist: "main-nav-watchlist",
  factors: "main-nav-factors",
  backtest: "main-nav-backtest",
  paper: "main-nav-paper",
};
