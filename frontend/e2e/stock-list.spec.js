import { readFile } from "node:fs/promises";
import { test, expect } from "@playwright/test";
import { installApiMocks } from "./fixtures/installApiMocks.js";
import { MAIN_NAV } from "./fixtures/mainNavTestIds.js";

test.describe("Stock list panel", () => {
  test.beforeEach(async ({ page }) => {
    await installApiMocks(page);
  });

  test("query and pagination", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByTestId(MAIN_NAV.stocks).click();

    await expect(page.getByRole("heading", { name: "股票列表" })).toBeVisible();
    await expect(
      page.getByText("点击「查询」拉取列表（空条件可列出前若干只）")
    ).toBeVisible();

    await page.getByRole("button", { name: "查询", exact: true }).click();
    await expect(page.getByText("Pudong-Dev-Bank-e2e")).toBeVisible();
    await expect(page.getByText(/共 120 条/)).toBeVisible();

    await page.getByRole("button", { name: "复制股票列表查询 API 路径" }).click();
    await expect(page.getByRole("status").filter({ hasText: /股票列表 API 路径/ })).toBeVisible();

    await page.getByRole("button", { name: "复制本页全部代码" }).click();
    await expect(page.getByRole("status").filter({ hasText: /已复制本页 50 条代码/ })).toBeVisible();

    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: "导出本页 CSV" }).click();
    const download = await downloadPromise;
    await expect(download.suggestedFilename()).toMatch(/^stocks_\d{8}_\d{6}_offset0\.csv$/);
    const p = await download.path();
    expect(p, "download path").toBeTruthy();
    const csv = await readFile(p, "utf8");
    expect(csv.charCodeAt(0)).toBe(0xfeff);
    expect(csv).toContain("序号,代码,名称,状态");
    expect(csv).toContain("sh.600000");
    expect(csv).toContain("Pudong-Dev-Bank-e2e");

    await expect(page.getByRole("status").filter({ hasText: /已导出本页/ })).toBeVisible();

    const dlAll = page.waitForEvent("download");
    await page.getByRole("button", { name: "导出全部匹配 CSV" }).click();
    const dall = await dlAll;
    await expect(dall.suggestedFilename()).toMatch(/^stocks_all_\d{8}_\d{6}_n120\.csv$/);
    const pAll = await dall.path();
    expect(pAll, "download path (all)").toBeTruthy();
    const csvAll = await readFile(pAll, "utf8");
    expect(csvAll.charCodeAt(0)).toBe(0xfeff);
    const linesAll = csvAll.replace(/^\uFEFF/, "").trim().split("\n");
    expect(linesAll.length).toBe(121);
    expect(linesAll.at(-1)).toContain("Tail-e2e-119");
    await expect(page.getByRole("status").filter({ hasText: /已导出全部 120 条/ })).toBeVisible();

    await page.getByRole("button", { name: "复制代码" }).first().click();
    await expect(page.getByRole("status").filter({ hasText: "已复制 sh.600000" })).toBeVisible();

    await page.getByRole("button", { name: "下一页" }).click();
    await expect(page.getByText("ZhaoShang-e2e-p2")).toBeVisible();
  });
});
