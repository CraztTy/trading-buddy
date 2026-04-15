"use strict";
/**
 * 方式 B：连接已在 4173 运行的 preview（终端一先 `npm run e2e:preview`）。
 * 设置 PLAYWRIGHT_BASE_URL 后串联 preflight（探测）+ Playwright CLI。
 *
 * 用法（在 frontend/）：
 *   npm run test:e2e:connected
 *   npm run test:e2e:connected -- e2e/main-nav-smoke.spec.js
 */
const { spawnSync } = require("child_process");
const path = require("path");

const root = path.join(__dirname, "..");
const base = (process.env.PLAYWRIGHT_BASE_URL || "").trim() || "http://127.0.0.1:4173";
const env = { ...process.env, PLAYWRIGHT_BASE_URL: base };
const node = process.execPath;
const preflight = path.join(__dirname, "preflight.cjs");
const heartbeat = path.join(__dirname, "run-pw-heartbeat.cjs");
let forwarded = process.argv.slice(2);
if (forwarded[0] === "--") forwarded = forwarded.slice(1);

const r1 = spawnSync(node, [preflight], { cwd: root, stdio: "inherit", env, windowsHide: false });
if (r1.status !== 0) process.exit(r1.status == null ? 1 : r1.status);
const r2 = spawnSync(node, [heartbeat, ...forwarded], {
  cwd: root,
  stdio: "inherit",
  env,
  windowsHide: false,
});
process.exit(r2.status == null ? 1 : r2.status);
