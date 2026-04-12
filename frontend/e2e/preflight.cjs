"use strict";
/**
 * Runs before Playwright CLI (ASCII only for Windows consoles).
 * Probes preview so you see [e2e] 1 ... before the long Chromium load.
 */
const http = require("http");
const { writeSync } = require("fs");

function out(msg) {
  writeSync(1, `${msg}\n`);
}

const baseRaw = process.env.PLAYWRIGHT_BASE_URL || "http://127.0.0.1:4173";
const base = baseRaw.replace(/\/$/, "");
const u = new URL(`${base}/`);

out("[e2e] 0 starting (next: probe preview)...");

const port = u.port ? Number(u.port) : u.protocol === "https:" ? 443 : 80;
const path = u.pathname || "/";

function probe() {
  return new Promise((resolve, reject) => {
    const lib = u.protocol === "https:" ? require("https") : http;
    const req = lib.request(
      {
        hostname: u.hostname,
        port,
        path: path === "" ? "/" : path,
        method: "GET",
        timeout: 8000,
      },
      (res) => {
        res.resume();
        if (res.statusCode >= 200 && res.statusCode < 500) {
          resolve(res.statusCode);
        } else {
          reject(new Error(`HTTP ${res.statusCode}`));
        }
      }
    );
    req.on("timeout", () => {
      req.destroy();
      reject(new Error("timeout 8s"));
    });
    req.on("error", reject);
    req.end();
  });
}

probe()
  .then((code) => {
    out(`[e2e] 1 preview OK (${base}/ HTTP ${code})`);
    if (process.platform === "win32") {
      if (process.env.CI === "true") {
        out(
          "[e2e] WARN CI=true -> bundled Chromium not Chrome. Local: Remove-Item Env:CI -ErrorAction SilentlyContinue"
        );
      } else if (process.env.PLAYWRIGHT_CHANNEL === "chromium") {
        out("[e2e] note PLAYWRIGHT_CHANNEL=chromium -> bundled Chromium (not Chrome)");
      } else {
        out(
          "[e2e] note Windows -> playwright uses Google Chrome (channel=chrome) when installed"
        );
      }
    }
    process.exit(0);
  })
  .catch((e) => {
    out(`[e2e] FAIL cannot reach preview ${base}/ (${e.message})`);
    out("[e2e]    In another terminal: cd frontend && npm run e2e:preview");
    process.exit(1);
  });
