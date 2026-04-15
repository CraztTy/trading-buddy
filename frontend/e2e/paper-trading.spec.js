import { test, expect } from "@playwright/test";
import { installApiMocks } from "./fixtures/installApiMocks.js";
import { MAIN_NAV } from "./fixtures/mainNavTestIds.js";

test.describe("Paper trading panel", () => {
  test.beforeEach(async ({ page }) => {
    await installApiMocks(page);
  });

  test("tab, state, mock buy", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByTestId(MAIN_NAV.paper).click();
    await expect(page.getByRole("heading", { name: "纸交易" })).toBeVisible();
    await expect(page.locator(".paper .big")).toContainText("现金");
    await expect(page.locator(".paper .big")).toContainText(/1[,.]?000[,.]?000/);

    await expect(page.getByRole("button", { name: "复制纸交易账户状态 API 路径" })).toBeEnabled();
    await expect(page.getByRole("button", { name: "复制纸交易成交记录 API 路径" })).toBeEnabled();
    await page.getByRole("button", { name: "复制纸交易账户状态 API 路径" }).click();
    await expect(page.getByTestId("toast-stack")).toContainText(/纸交易账户状态 API 路径/);
    await page.getByRole("button", { name: "复制纸交易成交记录 API 路径" }).click();
    await expect(page.getByTestId("toast-stack")).toContainText(/纸交易成交记录 API 路径/);

    await page.getByRole("button", { name: "复制纸交易市价下单 POST 说明" }).click();
    await expect(page.getByTestId("toast-stack")).toContainText(/市价下单 POST 说明/);
    await page.getByRole("button", { name: "复制纸交易账户重置 POST 说明" }).click();
    await expect(page.getByTestId("toast-stack")).toContainText(/账户重置 POST 路径/);

    await page.getByRole("textbox").first().fill("sh.600000");
    await page.getByRole("button", { name: "市价提交" }).click();
    await expect(page.locator(".paper").getByRole("status")).toContainText(/已成交 buy/);

    await page.getByRole("button", { name: "复制成交列表中的代码" }).click();
    await expect(page.getByTestId("toast-stack")).toContainText(/已复制 1 条不重复代码/);
  });

  test("backtest opens paper with draft", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByTestId(MAIN_NAV.backtest).click();
    await page.getByTestId("backtest-open-paper").click();
    await expect(page.getByRole("heading", { name: "纸交易" })).toBeVisible();
    const inp = page.locator(".paper .inp.mono").first();
    await expect(inp).toHaveValue("sh.000001");
  });

  test("paper draft cleared after leaving tab", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByTestId(MAIN_NAV.backtest).click();
    await page.getByTestId("backtest-open-paper").click();
    await expect(page.locator(".paper .inp.mono").first()).toHaveValue("sh.000001");
    await page.getByTestId(MAIN_NAV.market).click();
    await page.getByTestId(MAIN_NAV.paper).click();
    await expect(page.locator(".paper .inp.mono").first()).toHaveValue("sh.600000");
  });
});
