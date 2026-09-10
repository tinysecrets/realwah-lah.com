#!/usr/bin/env bash
# Lightweight supervisor for the message queue processor. Meant for simple deployments or local testing.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

# Load backend/.env if present (local convenience). WARNING: do not commit backend/.env
ENV_FILE="$ROOT_DIR/backend/.env"
if [ -f "$ENV_FILE" ]; then
  set -o allexport
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +o allexport
  echo "Loaded env from $ENV_FILE"
fi

BRIDGE_POLL_INTERVAL=${BRIDGE_POLL_INTERVAL:-60}

while true; do
  echo "[$(date -Iseconds)] Running process_message_queues.py"
  PYTHONPATH=backend python3 backend/scripts/process_message_queues.py || echo "process failed: $?"
  sleep "$BRIDGE_POLL_INTERVAL"
done
