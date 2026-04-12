import { test, expect } from "@playwright/test";
import { installApiMocks } from "./fixtures/installApiMocks.js";

test.describe("Paper trading panel", () => {
  test.beforeEach(async ({ page }) => {
    await installApiMocks(page);
  });

  test("tab, state, mock buy", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "纸交易" }).click();
    await expect(page.getByRole("heading", { name: "纸交易" })).toBeVisible();
    await expect(page.locator(".paper .big")).toContainText("现金");
    await expect(page.locator(".paper .big")).toContainText(/1[,.]?000[,.]?000/);

    await page.getByRole("textbox").first().fill("sh.600000");
    await page.getByRole("button", { name: "市价提交" }).click();
    await expect(page.getByRole("status")).toContainText(/已成交 buy/);
  });

  test("backtest opens paper with draft", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "策略回测" }).click();
    await page.getByRole("button", { name: "闭环 · 纸交易" }).click();
    await expect(page.getByRole("heading", { name: "纸交易" })).toBeVisible();
    const inp = page.locator(".paper .inp.mono").first();
    await expect(inp).toHaveValue("sh.000001");
  });
});
