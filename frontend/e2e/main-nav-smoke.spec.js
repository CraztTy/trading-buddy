import { test, expect } from "@playwright/test";
import { installApiMocks } from "./fixtures/installApiMocks.js";

test.describe("Main nav views", () => {
  test.beforeEach(async ({ page }) => {
    await installApiMocks(page);
  });

  test("行情看板 / 股票列表 / 自选 / 因子预览 / 策略回测 地标切换", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });

    await expect(page.getByRole("heading", { name: "Trading Buddy" })).toBeVisible();
    await expect(page.getByText("上证指数").first()).toBeVisible();
    await expect(page.getByText("交易日历")).toBeVisible();
    await expect(page.getByText("1,840")).toBeVisible();

    const exSelect = page.locator('select[aria-label="trade_calendar 分区 exchange"]');
    await exSelect.selectOption("hk");
    await expect(page.getByText("无数据")).toBeVisible();
    await exSelect.selectOption("cn");
    await expect(page.getByText("1,840")).toBeVisible();

    await expect(page.getByText("上港集团")).toBeVisible();

    await page.getByRole("button", { name: "股票列表" }).click();
    await expect(page.getByRole("heading", { name: "股票列表" })).toBeVisible();

    await page.getByRole("button", { name: "自选" }).click();
    await expect(page.getByRole("heading", { name: "我的自选" })).toBeVisible();

    await page.getByRole("button", { name: "因子预览" }).click();
    await expect(page.getByRole("heading", { name: "因子预览" })).toBeVisible();

    await page.getByRole("button", { name: "策略回测" }).click();
    await expect(page.getByRole("heading", { name: "双均线（日线）" })).toBeVisible();

    await page.getByRole("button", { name: "行情看板" }).click();
    await expect(page.getByText("涨跌 / 成交额")).toBeVisible();
    await expect(page.getByText("上港集团")).toBeVisible();
  });
});
