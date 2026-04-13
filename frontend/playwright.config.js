import { defineConfig } from "@playwright/test";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

const frontendDir = dirname(fileURLToPath(import.meta.url));

const baseURL = process.env.PLAYWRIGHT_BASE_URL || "http://127.0.0.1:4173";
process.stdout.write(`[playwright] config loaded, baseURL=${baseURL}\n`);

/** Windows local: prefer Google Chrome (faster than first bundled Chromium + AV). CI: bundled Chromium. */
const useBundledChromium =
  process.env.CI === "true" || process.env.PLAYWRIGHT_CHANNEL === "chromium";
const useChromeChannel = process.platform === "win32" && !useBundledChromium;
if (useChromeChannel) {
  process.stdout.write("[playwright] using channel=chrome (set PLAYWRIGHT_CHANNEL=chromium to force bundled)\n");
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
    ...(useChromeChannel ? { channel: "chrome" } : { browserName: "chromium" }),
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
          reuseExistingServer: false,
          timeout: 120_000,
        },
      }),
});
