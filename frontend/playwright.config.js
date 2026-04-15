import { defineConfig } from "@playwright/test";
import { existsSync } from "node:fs";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const frontendDir = dirname(fileURLToPath(import.meta.url));

const baseURL = process.env.PLAYWRIGHT_BASE_URL || "http://127.0.0.1:4173";
process.stdout.write(`[playwright] config loaded, baseURL=${baseURL}\n`);

function bundledChromiumExecutableExists() {
  try {
    const p = chromium.executablePath();
    return typeof p === "string" && p.length > 0 && existsSync(p);
  } catch {
    return false;
  }
}

/**
 * **`PLAYWRIGHT_EXECUTABLE_PATH`**：若指向已解压的 **Chrome for Testing** 的 **`chrome.exe`**
 *（存在且可读），则**最优先**用该可执行文件（`browserName: chromium` + `launchOptions.executablePath`），
 * 覆盖下述 channel / Windows 自动选 Chromium 逻辑。
 *
 * **CI** 或 **`PLAYWRIGHT_CHANNEL=chromium`**：Playwright 自带 Chromium。
 * **`PLAYWRIGHT_CHANNEL=chrome`**：系统 Google Chrome（任意系统）。
 * **Windows 本机**（非 CI、未显式 `chrome`、未设 `PLAYWRIGHT_EXECUTABLE_PATH`）：若已 **`npx playwright install chromium`**，
 * 则**优先**用内置 Chromium，减少系统 Chrome 在 headless 下「browser closed」类问题；
 * 未安装内置浏览器时仍走 **`channel: "chrome"`**。
 * 非 Windows 默认 Chromium；要用系统 Chrome 时设 **`PLAYWRIGHT_CHANNEL=chrome`**。
 */
const explicitChannel = (process.env.PLAYWRIGHT_CHANNEL || "").trim().toLowerCase();
/** 解压 Chrome for Testing 的 `chrome-win64.zip` 后，指向其中的 `chrome.exe`（优先于 channel / 内置 Chromium）。 */
const explicitExecutable = (process.env.PLAYWRIGHT_EXECUTABLE_PATH || "").trim();
const useExecutablePath =
  explicitExecutable.length > 0 && existsSync(explicitExecutable);
if (explicitExecutable.length > 0 && !useExecutablePath) {
  process.stdout.write(
    `[playwright] WARN: PLAYWRIGHT_EXECUTABLE_PATH not found (${explicitExecutable}), using default browser selection\n`
  );
}

const useBundledChromium =
  process.env.CI === "true" ||
  explicitChannel === "chromium" ||
  (process.platform === "win32" &&
    process.env.CI !== "true" &&
    explicitChannel !== "chrome" &&
    bundledChromiumExecutableExists());
const useChromeChannel =
  explicitChannel === "chrome" ||
  (process.platform === "win32" && !useBundledChromium);
const winAutoBundledChromium =
  process.platform === "win32" &&
  process.env.CI !== "true" &&
  explicitChannel !== "chrome" &&
  explicitChannel !== "chromium" &&
  bundledChromiumExecutableExists();

if (useExecutablePath) {
  process.stdout.write(
    `[playwright] using PLAYWRIGHT_EXECUTABLE_PATH=${explicitExecutable}\n`
  );
} else if (useChromeChannel) {
  process.stdout.write(
    "[playwright] using channel=chrome (PLAYWRIGHT_CHANNEL=chromium for bundled browser)\n"
  );
} else if (winAutoBundledChromium) {
  process.stdout.write(
    "[playwright] Windows: bundled Chromium found, using it (PLAYWRIGHT_CHANNEL=chrome for system Chrome)\n"
  );
}

/** 本机 Windows 多 worker 易触发「browser closed」类噪声；可用 PLAYWRIGHT_WORKERS 覆盖。 */
const playwrightWorkers =
  process.env.PLAYWRIGHT_WORKERS != null && process.env.PLAYWRIGHT_WORKERS !== ""
    ? Number(process.env.PLAYWRIGHT_WORKERS)
    : process.platform === "win32" && process.env.CI !== "true"
      ? 1
      : undefined;

export default defineConfig({
  globalSetup: process.env.PLAYWRIGHT_BASE_URL
    ? undefined
    : "./e2e/global-setup.cjs",
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 20_000 },
  fullyParallel: true,
  ...(playwrightWorkers != null && !Number.isNaN(playwrightWorkers)
    ? { workers: playwrightWorkers }
    : {}),
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  // early-reporter：用例收集完、起浏览器前打一行；line：逐条用例输出
  reporter: [["./e2e/early-reporter.js"], ["line"]],
  use: {
    ...(useExecutablePath
      ? {
          browserName: "chromium",
          launchOptions: { executablePath: explicitExecutable },
        }
      : useChromeChannel
        ? { channel: "chrome" }
        : { browserName: "chromium" }),
    viewport: { width: 1280, height: 800 },
    // CI 通过 PLAYWRIGHT_BASE_URL 指向已 build + 独立起的 preview；本机裸跑 `npx playwright test` 时由 webServer 负责 build+preview，避免 dist 过期（如新增算子 option）。
    baseURL,
    trace: "on-first-retry",
  },
  ...(process.env.PLAYWRIGHT_BASE_URL
    ? {}
    : {
        webServer: {
          command:
            "npx vite preview --host 127.0.0.1 --port 4173 --strictPort",
          cwd: frontendDir,
          url: "http://127.0.0.1:4173",
          // 本机已有 `vite preview` / `e2e:preview` 占 4173 时直接复用；CI 必须独占进程
          reuseExistingServer: process.env.CI !== "true",
          timeout: 120_000,
        },
      }),
});
