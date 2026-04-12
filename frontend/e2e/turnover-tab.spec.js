import { test, expect } from "@playwright/test";
import { installApiMocks } from "./fixtures/installApiMocks.js";

test.describe("RankBoard 成交额", () => {
  test.beforeEach(async ({ page }) => {
    await installApiMocks(page);
  });

  test("切换 tab 与按日筛选", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: "Trading Buddy" })).toBeVisible();

    // 默认「涨幅榜」mock
    await expect(page.getByText("上港集团")).toBeVisible();

    await page.locator(".tabs button.tab").filter({ hasText: "成交额" }).click();
    await expect(page.getByText("交易日（可选）")).toBeVisible();
    await expect(page.getByText("浦发银行（成交额 mock）")).toBeVisible();
    await expect(page.getByText("2.10 亿")).toBeVisible();

    await page.locator(".turnover-opts input[type='date']").fill("2024-06-01");
    await expect(page.getByText("mock-按日-2024-06-01")).toBeVisible();
  });
});
