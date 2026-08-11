#!/usr/bin/env bash
# Lightweight supervisor for the Telegram bridge. Meant for simple deployments or local testing.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

BRIDGE_POLL_INTERVAL=${BRIDGE_POLL_INTERVAL:-60}

while true; do
  echo "[$(date -Iseconds)] Running process_telegram_queue.py"
  python3 backend/scripts/process_telegram_queue.py || echo "process failed: $?"
  sleep "$BRIDGE_POLL_INTERVAL"
done
