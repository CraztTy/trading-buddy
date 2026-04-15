"use strict";
/**
 * Runs before Playwright CLI (ASCII only for Windows consoles).
 *
 * - **PLAYWRIGHT_BASE_URL** set (non-empty): probe that URL (way B — preview already up).
 * - **Unset or empty**: skip TCP probe (way A — Playwright `webServer` or `reuseExistingServer`
 *   brings up / reuses 4173 after this script exits).
 */
const http = require("http");
const fs = require("fs");
const { writeSync } = fs;

function out(msg) {
  writeSync(1, `${msg}\n`);
}

function printBrowserNotes() {
  const pwExe = (process.env.PLAYWRIGHT_EXECUTABLE_PATH || "").trim();
  if (pwExe) {
    if (fs.existsSync(pwExe)) {
      out(`[e2e] note PLAYWRIGHT_EXECUTABLE_PATH -> ${pwExe}`);
    } else {
      out(`[e2e] WARN PLAYWRIGHT_EXECUTABLE_PATH missing file: ${pwExe}`);
    }
  }
  if (process.platform === "win32") {
    if (process.env.CI === "true") {
      out(
        "[e2e] WARN CI=true -> bundled Chromium not Chrome. Local: Remove-Item Env:CI -ErrorAction SilentlyContinue"
      );
    } else if (process.env.PLAYWRIGHT_CHANNEL === "chromium") {
      out("[e2e] note PLAYWRIGHT_CHANNEL=chromium -> bundled Chromium (not Chrome)");
    } else if (process.env.PLAYWRIGHT_CHANNEL === "chrome") {
      out("[e2e] note PLAYWRIGHT_CHANNEL=chrome -> Google Chrome channel");
    } else {
      try {
        const { chromium } = require("playwright-core");
        const p = chromium.executablePath();
        if (typeof p === "string" && p && fs.existsSync(p)) {
          out(
            "[e2e] note Windows -> bundled Chromium installed; playwright.config uses it by default (PLAYWRIGHT_CHANNEL=chrome for Chrome only)"
          );
        } else {
          out(
            "[e2e] note Windows -> Google Chrome channel (install Chromium: npx playwright install chromium for stable default)"
          );
        }
      } catch {
        out(
          "[e2e] note Windows -> Google Chrome channel (install Chromium: npx playwright install chromium for stable default)"
        );
      }
    }
  }
}

const rawBase = process.env.PLAYWRIGHT_BASE_URL;
const probeUserPreview = rawBase != null && String(rawBase).trim() !== "";

if (!probeUserPreview) {
  out(
    "[e2e] 0 PLAYWRIGHT_BASE_URL unset -> skip preview probe (Playwright webServer / reuseExistingServer handles 4173)"
  );
  printBrowserNotes();
  process.exit(0);
}

const base = String(rawBase).trim().replace(/\/$/, "");
const u = new URL(`${base}/`);

out("[e2e] 0 starting (next: probe preview)...");

const port = u.port ? Number(u.port) : u.protocol === "https:" ? 443 : 80;
const pathPart = u.pathname || "/";

function probe() {
  return new Promise((resolve, reject) => {
    const lib = u.protocol === "https:" ? require("https") : http;
    const req = lib.request(
      {
        hostname: u.hostname,
        port,
        path: pathPart === "" ? "/" : pathPart,
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
    printBrowserNotes();
    process.exit(0);
  })
  .catch((e) => {
    out(`[e2e] FAIL cannot reach preview ${base}/ (${e.message})`);
    out("[e2e]    Terminal 1: cd frontend && npm run e2e:preview");
    out(
      "[e2e]    Or unset PLAYWRIGHT_BASE_URL so Playwright starts webServer (Remove-Item Env:PLAYWRIGHT_BASE_URL -ErrorAction SilentlyContinue)"
    );
    process.exit(1);
  });
