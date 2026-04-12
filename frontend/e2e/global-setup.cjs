"use strict";

const { execSync } = require("node:child_process");
const path = require("node:path");

/**
 * When Playwright manages preview (no PLAYWRIGHT_BASE_URL), ensure dist matches
 * source so selectOption(new ops) does not time out on stale bundles.
 * CI sets PLAYWRIGHT_BASE_URL and runs `npm run build` separately — skip here.
 */
module.exports = function globalSetup() {
  if (process.env.PLAYWRIGHT_BASE_URL) return;
  const root = path.join(__dirname, "..");
  execSync("npm run build", { cwd: root, stdio: "inherit" });
};
