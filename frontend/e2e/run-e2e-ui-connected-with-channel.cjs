"use strict";
/**
 * 方式 B + Playwright UI + 固定 PLAYWRIGHT_CHANNEL（终端一已 `npm run e2e:preview`）。
 *
 * 用法：
 *   npm run test:e2e:ui:connected:chromium
 *   npm run test:e2e:ui:connected:chrome -- e2e/backtest-panel.spec.js
 */
const { spawnSync } = require("child_process");
const path = require("path");

const root = path.join(__dirname, "..");
const ch = (process.argv[2] || "").trim().toLowerCase();
if (ch !== "chromium" && ch !== "chrome") {
  process.stderr.write(
    "[e2e] usage: node ./e2e/run-e2e-ui-connected-with-channel.cjs chromium|chrome [-- playwright-args...]\n"
  );
  process.exit(1);
}

let forwarded = process.argv.slice(3);
if (forwarded[0] === "--") forwarded = forwarded.slice(1);

const trimmed = (process.env.PLAYWRIGHT_BASE_URL || "").trim();
const base = trimmed || "http://127.0.0.1:4173";
const env = { ...process.env, PLAYWRIGHT_BASE_URL: base, PLAYWRIGHT_CHANNEL: ch };
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
