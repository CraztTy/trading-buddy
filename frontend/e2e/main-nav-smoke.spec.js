import { test, expect } from "@playwright/test";
import { installApiMocks } from "./fixtures/installApiMocks.js";
import { MAIN_NAV } from "./fixtures/mainNavTestIds.js";

test.describe("Main nav views", () => {
  test.beforeEach(async ({ page }) => {
    await installApiMocks(page);
  });

  test("行情看板 / 股票列表 / 自选 / 因子预览 / 策略回测 / 纸交易 地标切换", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });

    await expect(page.getByRole("heading", { name: "Trading Buddy" })).toBeVisible();
    await expect(page.getByText("上证指数").first()).toBeVisible();
    await expect(page.getByRole("button", { name: "复制 K 线分析 API 路径" })).toBeEnabled({ timeout: 10_000 });
    await page.getByRole("button", { name: "复制 K 线分析 API 路径" }).click();
    await expect(page.getByTestId("toast-stack")).toContainText(/已复制 K 线分析 API 路径/);

    await page.getByRole("button", { name: "复制主要指数全部代码" }).click();
    await expect(page.getByTestId("toast-stack")).toContainText(/已复制 4 条代码（主要指数/);

    await page.getByRole("button", { name: "复制主要指数概览 API 路径" }).click();
    await expect(page.getByTestId("toast-stack")).toContainText(/主要指数概览 API 路径/);

    await expect(page.getByText("交易日历")).toBeVisible();
    await expect(page.getByTestId("api-health")).toContainText("在线", { timeout: 10_000 });
    await page.getByRole("button", { name: "复制健康检查路径" }).click();
    await expect(page.getByTestId("toast-stack")).toContainText(/已复制 \/health/);

    await expect(page.getByText("1,840")).toBeVisible();
    await page.getByRole("button", { name: "复制交易日历状态 API 路径" }).click();
    await expect(page.getByTestId("toast-stack")).toContainText(/已复制交易日历状态/);
    await page.getByRole("button", { name: "复制交易日历分区配置 API 路径" }).click();
    await expect(page.getByTestId("toast-stack")).toContainText(/已复制交易日历分区配置/);

    const exSelect = page.locator('select[aria-label="trade_calendar 分区 exchange"]');
    await exSelect.selectOption("hk");
    await expect(page.getByText("无数据")).toBeVisible();
    await exSelect.selectOption("cn");
    await expect(page.getByText("1,840")).toBeVisible();

    await expect(page.getByText("上港集团")).toBeVisible();

    await page.getByRole("button", { name: "复制排行榜全部代码" }).click();
    await expect(page.getByTestId("toast-stack")).toContainText(/已复制 2 条代码（涨幅榜/);

    await page.getByRole("button", { name: "复制排行榜数据 API 路径" }).click();
    await expect(page.getByTestId("toast-stack")).toContainText(/排行榜数据 API 路径/);

    const codeChip = page.getByRole("button", { name: "复制当前标的代码" });
    await expect(codeChip).toContainText("sh.000001");
    await codeChip.click();
    await expect(page.getByTestId("toast-stack")).toContainText("已复制 sh.000001");

    await page.getByRole("heading", { name: "Trading Buddy" }).click();
    await page.keyboard.press("Alt+Shift+C");
    await expect(page.getByTestId("toast-stack")).toContainText("已复制 sh.000001");

    await page.getByTestId(MAIN_NAV.stocks).click();
    await expect(page.getByRole("heading", { name: "股票列表" })).toBeVisible();

    await page.getByTestId(MAIN_NAV.watchlist).click();
    await expect(page.getByRole("heading", { name: "我的自选" })).toBeVisible();
    await expect(page.getByRole("button", { name: "复制自选全部代码" })).toBeDisabled();
    await expect(page.getByRole("button", { name: "复制自选列表 API 路径" })).toBeEnabled();
    await page.getByRole("button", { name: "复制自选列表 API 路径" }).click();
    await expect(page.getByTestId("toast-stack")).toContainText(/自选列表 API 路径/);

    await page.getByTestId(MAIN_NAV.factors).click();
    await expect(page.getByRole("heading", { name: "因子预览" })).toBeVisible();

    await page.getByTestId(MAIN_NAV.backtest).click();
    await expect(page.getByRole("heading", { name: "双均线（日线）" })).toBeVisible();

    await page.getByTestId(MAIN_NAV.paper).click();
    await expect(page.getByRole("heading", { name: "纸交易" })).toBeVisible();

    await page.getByTestId(MAIN_NAV.market).click();
    await expect(page.getByText("涨跌 / 成交额")).toBeVisible();
    await expect(page.getByText("上港集团")).toBeVisible();
  });
});
