"use strict";
/**
 * 方式 A + Playwright UI：`preflight` 后执行 `playwright test --ui`（不设
 * PLAYWRIGHT_BASE_URL 时 preflight 跳过探测，由 config 的 webServer / reuse 起 4173）。
 *
 * 用法：`npm run test:e2e:ui` 或 `npm run test:e2e:ui -- e2e/main-nav-smoke.spec.js`
 */
const { spawnSync } = require("child_process");
const path = require("path");

const root = path.join(__dirname, "..");
const env = { ...process.env };
const node = process.execPath;
const preflight = path.join(__dirname, "preflight.cjs");
const cli = path.join(root, "node_modules", "@playwright", "test", "cli.js");
let forwarded = process.argv.slice(2);
if (forwarded[0] === "--") forwarded = forwarded.slice(1);

const r1 = spawnSync(node, [preflight], { cwd: root, stdio: "inherit", env, windowsHide: false });
if (r1.status !== 0) process.exit(r1.status == null ? 1 : r1.status);
const r2 = spawnSync(node, [cli, "test", "--ui", ...forwarded], {
  cwd: root,
  stdio: "inherit",
  env,
  windowsHide: false,
});
process.exit(r2.status == null ? 1 : r2.status);
