import { test, expect } from "@playwright/test";
import { installApiMocks } from "./fixtures/installApiMocks.js";
import { MAIN_NAV } from "./fixtures/mainNavTestIds.js";

test.describe("Watchlist panel", () => {
  test.beforeEach(async ({ page }) => {
    await installApiMocks(page);
  });

  test("copy all codes after adding from stock list", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });

    await page.getByTestId(MAIN_NAV.stocks).click();
    await expect(page.getByRole("heading", { name: "股票列表" })).toBeVisible();
    await page.getByRole("button", { name: "查询", exact: true }).click();
    await expect(page.getByText("Pudong-Dev-Bank-e2e")).toBeVisible();
    await page.getByRole("button", { name: "加入自选" }).first().click();

    await page.getByTestId(MAIN_NAV.watchlist).click();
    await expect(page.getByRole("heading", { name: "我的自选" })).toBeVisible();

    await page.getByRole("button", { name: "复制自选全部代码" }).click();
    await expect(page.getByTestId("toast-stack")).toContainText(/已复制 1 条代码/);
  });
});
