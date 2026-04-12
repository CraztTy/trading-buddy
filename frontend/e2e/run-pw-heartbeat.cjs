"use strict";
/**
 * Spawns Playwright CLI with stdio inherited; prints a heartbeat every 20s on stderr
 * so a hung browser/driver does not look like a dead terminal (ASCII only).
 */
const { spawn } = require("child_process");
const path = require("path");

const root = path.join(__dirname, "..");
const cli = path.join(root, "node_modules", "@playwright", "test", "cli.js");
const forwarded = process.argv.slice(2);

const child = spawn(process.execPath, [cli, "test", ...forwarded], {
  cwd: root,
  stdio: "inherit",
  env: { ...process.env },
  windowsHide: false,
});

const interval = setInterval(() => {
  const ts = new Date().toISOString();
  // One short line so narrow terminals do not break mid-word.
  process.stderr.write(`[e2e] heartbeat ${ts} playwright still running\n`);
}, 20_000);

child.on("exit", (code, signal) => {
  clearInterval(interval);
  if (signal) process.exit(1);
  process.exit(code === null ? 1 : code);
});

child.on("error", (err) => {
  clearInterval(interval);
  process.stderr.write(`[e2e] FAIL spawn Playwright: ${err.message}\n`);
  process.exit(1);
});
