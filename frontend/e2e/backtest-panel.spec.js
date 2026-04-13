import { test, expect } from "@playwright/test";
import { installApiMocks } from "./fixtures/installApiMocks.js";

test.describe("Backtest panel", () => {
  test.beforeEach(async ({ page }) => {
    await installApiMocks(page);
  });

  test("single MA cross async job polls then shows mock metrics", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "策略回测" }).click();
    await expect(page.getByTestId("backtest-engine-catalog")).toBeVisible({ timeout: 10_000 });
    await page.getByTestId("mvp-async-run").check();
    await page.getByRole("button", { name: "运行回测" }).click();
    await expect(page.getByText("e2e-mock-ma-cross single")).toBeVisible();
    await expect(page.locator(".metrics").getByText("12.34")).toBeVisible();
  });

  test("single MA cross async cancel queued job shows status and error", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "策略回测" }).click();
    await expect(page.getByTestId("backtest-engine-catalog")).toBeVisible({ timeout: 10_000 });
    await page.getByTestId("mvp-async-run").check();
    await page.getByRole("button", { name: "运行回测" }).click();
    await expect(page.getByTestId("mvp-async-cancel")).toBeVisible({ timeout: 10_000 });
    await page.getByTestId("mvp-async-cancel").click();
    await expect(page.locator(".mvp-async-cancel-msg")).toContainText("已取消排队");
    await expect(page.locator(".err")).toContainText(/cancelled|任务已取消/i);
  });

  test("single buy_hold shows mock metrics and persists buy_hold_single", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "策略回测" }).click();
    await expect(page.getByTestId("backtest-engine-catalog")).toBeVisible({ timeout: 10_000 });
    await page.getByTestId("single-run-strategy-buy-hold").check();
    await expect(page.getByRole("heading", { name: "买入持有（日线）" })).toBeVisible();
    await expect(page.locator(".sig-line")).toHaveCount(0);
    await page.getByRole("button", { name: "运行回测" }).click();
    await expect(page.getByText("e2e-mock-buy-hold")).toBeVisible();
    await expect(page.locator(".metrics").getByText("3.21")).toBeVisible();
    await expect(page.locator(".save-tip")).toContainText(/已存档 #\d+/);
  });

  test("single MA cross shows mock metrics", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "策略回测" }).click();

    await expect(page.getByTestId("backtest-engine-catalog")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId("backtest-engine-catalog")).toContainText("engine 0.1");
    await expect(page.getByTestId("backtest-engine-catalog")).toContainText("双均线 · 单标的");
    await expect(page.getByTestId("backtest-engine-catalog")).toContainText("买入持有 · 单标的");
    await expect(page.getByTestId("backtest-engine-catalog")).toContainText("?async=1");
    await expect(page.getByTestId("backtest-engine-catalog")).toContainText("/api/backtest/jobs/{job_id}");

    await expect(page.getByTestId("run-kind-map-hint")).toContainText("GET /api/backtest/runs?kind=ma_cross_single");
    await expect(page.getByTestId("run-kind-map-hint")).toContainText("strategy_id=ma_cross");
    await expect(page.getByTestId("run-kind-map-hint")).toContainText("kind=buy_hold_single");
    await expect(page.getByTestId("run-kind-map-hint")).toContainText("strategy_id=buy_hold");

    await expect(page.getByRole("heading", { name: "双均线（日线）" })).toBeVisible();
    await page.getByRole("button", { name: "运行回测" }).click();

    await expect(page.getByText("e2e-mock-ma-cross single")).toBeVisible();
    await expect(page.locator(".metrics").getByText("12.34")).toBeVisible();
    await expect(page.locator(".sig-line")).toContainText("2024-06-28");
    await expect(page.locator(".sig-line")).toContainText("多");
  });

  test("strategy catalog and trial signal row", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "策略回测" }).click();
    await page.getByRole("button", { name: "策略目录" }).click();
    await expect(page.locator(".strategy-contract-pre").first()).toContainText("e2e-mock-catalog");
    await page.getByRole("button", { name: "试算信号" }).click();
    await expect(page.locator(".strategy-contract-pre").nth(1)).toContainText("e2e-mock-strategies-signal");
  });

  test("single run persists to archive and detail loads JSON", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "策略回测" }).click();
    await page.getByRole("button", { name: "运行回测" }).click();
    await expect(page.getByText("e2e-mock-ma-cross single")).toBeVisible();
    await expect(page.locator(".save-tip")).toContainText(/已存档 #\d+/);
    await expect(page.getByRole("button", { name: /^#\d+$/ })).toBeVisible();
    await page.getByRole("button", { name: /^#\d+$/ }).click();
    await expect(page.locator(".run-detail .run-pre").first()).toContainText('"code"');
    await expect(page.locator(".run-detail .run-pre").nth(1)).toContainText("e2e-mock-ma-cross");
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("button", { name: "导出 JSON" }).click(),
    ]);
    expect(download.suggestedFilename()).toMatch(/^backtest-run-\d+-ma_cross_single\.json$/);
    await expect(page.locator(".save-tip")).toContainText(/^已导出 backtest-run-/);
  });

  test("archive pagination shows range and disables prev next on single page", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "策略回测" }).click();
    await page.getByRole("button", { name: "运行回测" }).click();
    await expect(page.locator(".save-tip")).toContainText(/已存档 #\d+/);
    await expect(page.locator(".run-history-pagination")).toContainText(/第 1–1 条，共 1 条/);
    await expect(page.getByText(/共 1 页/)).toBeVisible();
    await expect(page.getByRole("button", { name: "上一页" })).toBeDisabled();
    await expect(page.getByRole("button", { name: "下一页" })).toBeDisabled();
    await page.getByRole("combobox", { name: "每页条数" }).selectOption("10");
    await expect(page.locator(".run-history-pagination")).toContainText(/第 1–1 条，共 1 条/);
    await page.getByRole("spinbutton", { name: "页码" }).fill("99");
    await page.getByRole("button", { name: "跳转" }).click();
    await expect(page.locator(".save-tip")).toContainText(/页码须在 1–1/);
    await page.getByRole("spinbutton", { name: "页码" }).fill("1");
    await page.getByRole("button", { name: "跳转" }).click();
    await expect(page.locator(".run-history-pagination")).toContainText(/第 1–1 条，共 1 条/);
  });

  test("batch checkbox zip export without opening detail", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "策略回测" }).click();
    await page.getByRole("button", { name: "运行回测" }).click();
    await expect(page.getByText("e2e-mock-ma-cross single")).toBeVisible();
    await page.getByRole("button", { name: "运行回测" }).click();
    await expect(page.getByRole("checkbox", { name: "选择存档 #2" })).toBeVisible();
    await expect(page.locator(".run-detail")).toHaveCount(0);
    await page.getByRole("checkbox", { name: "本页全选" }).check();
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("button", { name: /导出所选 ZIP/ }).click(),
    ]);
    expect(download.suggestedFilename()).toMatch(/^backtest-runs-export-\d{8}T\d{6}\.zip$/);
    await expect(page.locator(".save-tip")).toContainText(/^已导出 backtest-runs-export-/);
  });

  test("batch delete selected archives after confirm", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "策略回测" }).click();
    await page.getByRole("button", { name: "运行回测" }).click();
    await expect(page.locator(".save-tip")).toContainText(/已存档 #\d+/);
    await page.getByRole("button", { name: "运行回测" }).click();
    await expect(page.getByRole("checkbox", { name: "选择存档 #2" })).toBeVisible();
    await page.getByRole("checkbox", { name: "本页全选" }).check();
    page.once("dialog", (d) => d.accept());
    await page.getByRole("button", { name: /删除所选/ }).click();
    await expect(page.locator(".save-tip")).toContainText(/已删除 2 条/);
    await expect(page.getByRole("button", { name: /^#\d+$/ })).toHaveCount(0);
  });

  test("archive delete removes row after confirm", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "策略回测" }).click();
    await page.getByRole("button", { name: "运行回测" }).click();
    await expect(page.getByText("e2e-mock-ma-cross single")).toBeVisible();
    await expect(page.getByRole("button", { name: /^#\d+$/ })).toBeVisible();
    page.once("dialog", (d) => d.accept());
    await page.getByRole("button", { name: "删除", exact: true }).click();
    await expect(page.locator(".save-tip")).toContainText(/已删除 #\d+/);
    await expect(page.getByRole("button", { name: /^#\d+$/ })).toHaveCount(0);
  });

  test("batch scan shows mock row", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "策略回测" }).click();
    await page.getByRole("button", { name: "批量扫描" }).click();

    await expect(page.getByRole("heading", { name: "多标的批量扫描" })).toBeVisible();
    await page.getByRole("button", { name: "开始扫描" }).click();

    const table = page.locator(".scan-table");
    await expect(table.getByText("sh.000001")).toBeVisible();
    await expect(table.getByText("3.33")).toBeVisible();
    await expect(page.locator(".save-tip")).toContainText(/已存档 #\d+/);
  });

  test("batch scan async job polls then shows mock row", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "策略回测" }).click();
    await page.getByTestId("mvp-async-run").check();
    await page.getByRole("button", { name: "批量扫描" }).click();

    await expect(page.getByRole("heading", { name: "多标的批量扫描" })).toBeVisible();
    await page.getByRole("button", { name: "开始扫描" }).click();

    const table = page.locator(".scan-table");
    await expect(table.getByText("sh.000001")).toBeVisible();
    await expect(table.getByText("3.33")).toBeVisible();
    await expect(page.locator(".save-tip")).toContainText(/已存档 #\d+/);
  });

  test("batch scan fill watchlist button when empty shows hint", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "策略回测" }).click();
    await page.getByRole("button", { name: "批量扫描" }).click();
    await page.getByRole("button", { name: /填入自选/ }).click();
    await expect(page.getByText("自选为空")).toBeVisible();
  });
});
