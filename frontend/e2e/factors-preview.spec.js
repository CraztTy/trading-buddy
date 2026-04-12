import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { test, expect } from "@playwright/test";
import { installApiMocks } from "./fixtures/installApiMocks.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
/** 与 `fixtures/factor-catalog.json` 同步，避免算子增减时手改 magic number */
const FACTOR_CATALOG_OP_COUNT = JSON.parse(
  readFileSync(path.join(__dirname, "fixtures", "factor-catalog.json"), "utf8"),
).ops.length;

test.describe("Factor preview panel", () => {
  test.beforeEach(async ({ page }) => {
    await installApiMocks(page);
  });

  test("load preview shows bar count from mock API", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "因子预览" }).click();
    await expect(page.getByRole("heading", { name: "因子预览" })).toBeVisible();
    await expect(page.getByTestId("factor-catalog-sync")).toContainText(
      `已同步算子目录 ${FACTOR_CATALOG_OP_COUNT} 项`,
    );
    const opSelect = page.getByLabel("因子算子");
    await expect(opSelect).toBeEnabled({ timeout: 10_000 });
    await expect(opSelect.locator("option")).toHaveCount(FACTOR_CATALOG_OP_COUNT);
    await page.getByRole("button", { name: "加载预览" }).click();
    await expect(page.locator(".factor-meta")).toContainText("共 20 根");
  });

  test("export CSV downloads file with BOM header", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "因子预览" }).click();
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("button", { name: "导出 CSV" }).click(),
    ]);
    expect(download.suggestedFilename()).toMatch(/\.csv$/i);
    const path = await download.path();
    expect(path).toBeTruthy();
    const fs = await import("node:fs/promises");
    const buf = await fs.readFile(path);
    expect(buf[0] === 0xef && buf[1] === 0xbb && buf[2] === 0xbf).toBeTruthy();
    const text = buf.toString("utf8");
    expect(text).toContain("trade_date,value");
  });

  test("ATR op sends window and shows meta from mock", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "因子预览" }).click();
    await expect(page.getByRole("heading", { name: "因子预览" })).toBeVisible();
    await page.getByLabel("因子算子").selectOption("atr");
    await page.getByLabel("窗口或周期 n").fill("14");
    await page.getByRole("button", { name: "加载预览" }).click();
    await expect(page.locator(".factor-meta")).toContainText("atr");
    await expect(page.locator(".factor-meta")).toContainText("window=14");
  });

  test("MACD loads dif/dea/hist and shows params in meta", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "因子预览" }).click();
    await page.getByLabel("因子算子").selectOption("macd");
    await page.getByLabel("MACD 快线 span").fill("5");
    await page.getByLabel("MACD 慢线 span").fill("13");
    await page.getByLabel("MACD signal span").fill("4");
    await page.getByRole("button", { name: "加载预览" }).click();
    await expect(page.locator(".factor-meta")).toContainText("macd");
    await expect(page.locator(".factor-meta")).toContainText("MACD 5/13/4");
  });

  test("ADX loads plus_di/minus_di/adx and shows period in meta", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "因子预览" }).click();
    await page.getByLabel("因子算子").selectOption("adx");
    await page.getByLabel("窗口或周期 n").fill("6");
    await page.getByRole("button", { name: "加载预览" }).click();
    await expect(page.locator(".factor-meta")).toContainText("adx");
    await expect(page.locator(".factor-meta")).toContainText("window=6");
    await expect(page.locator(".factor-meta")).toContainText("ADX period=6");
  });

  test("Aroon loads up/down/osc and shows period in meta", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "因子预览" }).click();
    await page.getByLabel("因子算子").selectOption("aroon");
    await page.getByLabel("窗口或周期 n").fill("7");
    await page.getByRole("button", { name: "加载预览" }).click();
    await expect(page.locator(".factor-meta")).toContainText("aroon");
    await expect(page.locator(".factor-meta")).toContainText("window=7");
    await expect(page.locator(".factor-meta")).toContainText("Aroon period=7");
  });

  test("Donchian loads dc_upper/mid/lower and shows period in meta", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "因子预览" }).click();
    await page.getByLabel("因子算子").selectOption("donchian");
    await page.getByLabel("窗口或周期 n").fill("8");
    await page.getByRole("button", { name: "加载预览" }).click();
    await expect(page.locator(".factor-meta")).toContainText("donchian");
    await expect(page.locator(".factor-meta")).toContainText("window=8");
    await expect(page.locator(".factor-meta")).toContainText("Donchian period=8");
  });

  test("OBV loads without window and shows meta line", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "因子预览" }).click();
    await page.getByLabel("因子算子").selectOption("obv");
    await page.getByRole("button", { name: "加载预览" }).click();
    await expect(page.locator(".factor-meta")).toContainText("obv");
    await expect(page.locator(".factor-meta")).not.toContainText("window=");
  });

  test("CCI loads value series and shows window from mock", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "因子预览" }).click();
    await page.getByLabel("因子算子").selectOption("cci");
    await page.getByLabel("窗口或周期 n").fill("14");
    await page.getByRole("button", { name: "加载预览" }).click();
    await expect(page.locator(".factor-meta")).toContainText("cci");
    await expect(page.locator(".factor-meta")).toContainText("window=14");
  });

  test("MFI loads value series and shows window from mock", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "因子预览" }).click();
    await page.getByLabel("因子算子").selectOption("mfi");
    await page.getByLabel("窗口或周期 n").fill("12");
    await page.getByRole("button", { name: "加载预览" }).click();
    await expect(page.locator(".factor-meta")).toContainText("mfi");
    await expect(page.locator(".factor-meta")).toContainText("window=12");
  });

  test("ROC loads value series and shows window from mock", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "因子预览" }).click();
    await page.getByLabel("因子算子").selectOption("roc");
    await page.getByLabel("窗口或周期 n").fill("8");
    await page.getByRole("button", { name: "加载预览" }).click();
    await expect(page.locator(".factor-meta")).toContainText("roc");
    await expect(page.locator(".factor-meta")).toContainText("window=8");
  });

  test("TRIX loads value series and shows window from mock", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "因子预览" }).click();
    await page.getByLabel("因子算子").selectOption("trix");
    await page.getByLabel("窗口或周期 n").fill("9");
    await page.getByRole("button", { name: "加载预览" }).click();
    await expect(page.locator(".factor-meta")).toContainText("trix");
    await expect(page.locator(".factor-meta")).toContainText("window=9");
  });

  test("Williams %R loads value series and shows window from mock", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "因子预览" }).click();
    await page.getByLabel("因子算子").selectOption("williams_r");
    await page.getByLabel("窗口或周期 n").fill("10");
    await page.getByRole("button", { name: "加载预览" }).click();
    await expect(page.locator(".factor-meta")).toContainText("williams_r");
    await expect(page.locator(".factor-meta")).toContainText("window=10");
  });

  test("KDJ loads k/d/j and shows n m1 m2 in meta", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "因子预览" }).click();
    await page.getByLabel("因子算子").selectOption("kdj");
    await page.getByLabel("窗口或周期 n").fill("9");
    await page.getByLabel("KDJ 平滑参数 m1").fill("3");
    await page.getByLabel("KDJ 平滑参数 m2").fill("3");
    await page.getByRole("button", { name: "加载预览" }).click();
    await expect(page.locator(".factor-meta")).toContainText("kdj");
    await expect(page.locator(".factor-meta")).toContainText("window=9");
    await expect(page.locator(".factor-meta")).toContainText("KDJ n=9 m1=3 m2=3");
  });

  test("Bollinger loads series and shows k from meta", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "因子预览" }).click();
    await page.getByLabel("因子算子").selectOption("bollinger");
    await page.getByLabel("窗口或周期 n").fill("5");
    await page.getByLabel("布林带带宽倍数 bb_k").fill("2.5");
    await page.getByRole("button", { name: "加载预览" }).click();
    await expect(page.locator(".factor-meta")).toContainText("bollinger");
    await expect(page.locator(".factor-meta")).toContainText("k=2.5");
  });

  test("ATR CSV export uses op in filename", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "因子预览" }).click();
    await page.getByLabel("因子算子").selectOption("atr");
    await page.getByLabel("窗口或周期 n").fill("14");
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("button", { name: "导出 CSV" }).click(),
    ]);
    expect(download.suggestedFilename()).toMatch(/_close_atr\.csv$/i);
    const p = await download.path();
    expect(p).toBeTruthy();
    const fs = await import("node:fs/promises");
    const buf = await fs.readFile(p);
    const text = buf.toString("utf8");
    expect(text).toContain("2024-04-15,0.78");
  });

  test("Aroon CSV export uses op in filename and three value columns", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "因子预览" }).click();
    await page.getByLabel("因子算子").selectOption("aroon");
    await page.getByLabel("窗口或周期 n").fill("5");
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("button", { name: "导出 CSV" }).click(),
    ]);
    expect(download.suggestedFilename()).toMatch(/_close_aroon\.csv$/i);
    const p = await download.path();
    expect(p).toBeTruthy();
    const fs = await import("node:fs/promises");
    const buf = await fs.readFile(p);
    const text = buf.toString("utf8");
    expect(text).toContain("trade_date,aroon_up,aroon_down,aroon_osc");
    // installApiMocks: i=14 → 2024-04-15, 55+16.8, 40+4, 15+7
    expect(text).toContain("2024-04-15,71.8,44,22");
  });

  test("Donchian CSV export uses op in filename and dc_* columns", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "因子预览" }).click();
    await page.getByLabel("因子算子").selectOption("donchian");
    await page.getByLabel("窗口或周期 n").fill("5");
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("button", { name: "导出 CSV" }).click(),
    ]);
    expect(download.suggestedFilename()).toMatch(/_close_donchian\.csv$/i);
    const p = await download.path();
    expect(p).toBeTruthy();
    const fs = await import("node:fs/promises");
    const buf = await fs.readFile(p);
    const text = buf.toString("utf8");
    expect(text).toContain("trade_date,dc_upper,dc_mid,dc_lower");
    // installApiMocks: i=14 → 2024-04-15, 100+14, (114+104)/2, 90+14
    expect(text).toContain("2024-04-15,114,109,104");
  });

  test("VWAP cumulative omits window and shows meta", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "因子预览" }).click();
    await page.getByLabel("因子算子").selectOption("vwap");
    await page.getByLabel("窗口或周期 n").fill("");
    await page.getByRole("button", { name: "加载预览" }).click();
    await expect(page.locator(".factor-meta")).toContainText("vwap");
    await expect(page.locator(".factor-meta")).toContainText("VWAP 日级（自首根累计）");
    await expect(page.locator(".factor-meta")).not.toContainText("window=");
  });

  test("VWAP rolling sends window and shows period in meta", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "因子预览" }).click();
    await page.getByLabel("因子算子").selectOption("vwap");
    await page.getByLabel("窗口或周期 n").fill("6");
    await page.getByRole("button", { name: "加载预览" }).click();
    await expect(page.locator(".factor-meta")).toContainText("vwap");
    await expect(page.locator(".factor-meta")).toContainText("window=6");
    await expect(page.locator(".factor-meta")).toContainText("VWAP 滚动 period=6");
  });

  test("VWAP CSV cumulative uses op in filename and first row value", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "因子预览" }).click();
    await page.getByLabel("因子算子").selectOption("vwap");
    await page.getByLabel("窗口或周期 n").fill("");
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("button", { name: "导出 CSV" }).click(),
    ]);
    expect(download.suggestedFilename()).toMatch(/_close_vwap\.csv$/i);
    const p = await download.path();
    expect(p).toBeTruthy();
    const fs = await import("node:fs/promises");
    const buf = await fs.readFile(p);
    const text = buf.toString("utf8");
    expect(text).toContain("trade_date,value");
    expect(text).toContain("2024-04-01,9.9");
  });

  test("VWAP CSV rolling first numeric row matches mock window=6", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "因子预览" }).click();
    await page.getByLabel("因子算子").selectOption("vwap");
    await page.getByLabel("窗口或周期 n").fill("6");
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("button", { name: "导出 CSV" }).click(),
    ]);
    expect(download.suggestedFilename()).toMatch(/_close_vwap\.csv$/i);
    const p = await download.path();
    expect(p).toBeTruthy();
    const fs = await import("node:fs/promises");
    const buf = await fs.readFile(p);
    const text = buf.toString("utf8");
    expect(text).toContain("trade_date,value");
    expect(text).not.toContain("2024-04-01,9.9");
    expect(text).toMatch(/2024-04-06,10\.15284/);
  });
});
