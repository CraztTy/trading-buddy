#!/usr/bin/env bash
# Stop local dev listeners used by Trading Buddy (API, Vite, preview).
# Default ports: 8000, 5173–5175, 4173 (same defaults as scripts/stop_dev.ps1).
set -uo pipefail

PORTS=(8000 5173 5174 5175 4173)
if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  echo "Usage: bash scripts/stop_dev.sh"
  echo "Requires: lsof (macOS/Linux) or fuser (Linux, optional)"
  exit 0
fi

stop_port() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -ti ":${port}" 2>/dev/null | while read -r pid; do
      [[ -n "${pid}" ]] || continue
      echo "Stopping PID ${pid} (port ${port})"
      kill -9 "${pid}" 2>/dev/null || true
    done
  elif command -v fuser >/dev/null 2>&1; then
    fuser -k "${port}/tcp" 2>/dev/null || true
  else
    echo "WARN: neither lsof nor fuser found; cannot stop port ${port}" >&2
  fi
}

for p in "${PORTS[@]}"; do
  stop_port "$p"
done

echo "Done."
