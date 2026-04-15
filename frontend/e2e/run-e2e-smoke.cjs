"use strict";
/**
 * 固定少量 spec 的快速冒烟（mock，不依赖后端）。
 *
 *   npm run test:e2e:smoke              # 方式 A（与 test:e2e 相同 base / webServer 语义）
 *   npm run test:e2e:smoke:connected    # 方式 B（需终端一 e2e:preview 或 e2e:preview:only）
 *
 * 追加 Playwright 参数：npm run test:e2e:smoke -- --reporter=list
 */
const { spawnSync } = require("child_process");
const path = require("path");

const root = path.join(__dirname, "..");
const mode = (process.argv[2] || "").trim().toLowerCase();
if (mode !== "local" && mode !== "a" && mode !== "connected" && mode !== "b") {
  process.stderr.write(
    "[e2e] usage: node ./e2e/run-e2e-smoke.cjs local|connected [-- playwright-args...]\n"
  );
  process.exit(1);
}

let forwarded = process.argv.slice(3);
if (forwarded[0] === "--") forwarded = forwarded.slice(1);

/** 变更主导航 / 侧栏 tab 时请视情况更新此列表 */
const SMOKE_SPECS = ["e2e/main-nav-smoke.spec.js", "e2e/turnover-tab.spec.js"];

let env = { ...process.env };
if (mode === "connected" || mode === "b") {
  const trimmed = (process.env.PLAYWRIGHT_BASE_URL || "").trim();
  env.PLAYWRIGHT_BASE_URL = trimmed || "http://127.0.0.1:4173";
}

const node = process.execPath;
const preflight = path.join(__dirname, "preflight.cjs");
const heartbeat = path.join(__dirname, "run-pw-heartbeat.cjs");

const r1 = spawnSync(node, [preflight], { cwd: root, stdio: "inherit", env, windowsHide: false });
if (r1.status !== 0) process.exit(r1.status == null ? 1 : r1.status);
const r2 = spawnSync(node, [heartbeat, ...SMOKE_SPECS, ...forwarded], {
  cwd: root,
  stdio: "inherit",
  env,
  windowsHide: false,
});
process.exit(r2.status == null ? 1 : r2.status);
