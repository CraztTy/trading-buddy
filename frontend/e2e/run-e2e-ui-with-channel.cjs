"use strict";
/**
 * 方式 A + Playwright UI + 固定 PLAYWRIGHT_CHANNEL（不设 PLAYWRIGHT_BASE_URL，
 * 由 config 的 global-setup / webServer / reuse 处理 4173）。
 *
 * 用法：
 *   npm run test:e2e:ui:chromium
 *   npm run test:e2e:ui:chrome -- e2e/main-nav-smoke.spec.js
 */
const { spawnSync } = require("child_process");
const path = require("path");

const root = path.join(__dirname, "..");
const ch = (process.argv[2] || "").trim().toLowerCase();
if (ch !== "chromium" && ch !== "chrome") {
  process.stderr.write(
    "[e2e] usage: node ./e2e/run-e2e-ui-with-channel.cjs chromium|chrome [-- playwright-args...]\n"
  );
  process.exit(1);
}

let forwarded = process.argv.slice(3);
if (forwarded[0] === "--") forwarded = forwarded.slice(1);

const env = { ...process.env, PLAYWRIGHT_CHANNEL: ch };
const node = process.execPath;
const preflight = path.join(__dirname, "preflight.cjs");
const cli = path.join(root, "node_modules", "@playwright", "test", "cli.js");

const r1 = spawnSync(node, [preflight], { cwd: root, stdio: "inherit", env, windowsHide: false });
if (r1.status !== 0) process.exit(r1.status == null ? 1 : r1.status);
const r2 = spawnSync(node, [cli, "test", "--ui", ...forwarded], {
  cwd: root,
  stdio: "inherit",
  env,
  windowsHide: false,
});
process.exit(r2.status == null ? 1 : r2.status);
