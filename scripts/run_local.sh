#!/usr/bin/env bash
# Local dev: MongoDB in Docker + FastAPI on :8001
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

pkill -9 -f "uvicorn.*server:app" 2>/dev/null || true
docker stop local-mongo 2>/dev/null || true
docker rm local-mongo 2>/dev/null || true
docker run -d --name local-mongo -p 27017:27017 mongo:7

export MONGO_URL="${MONGO_URL:-mongodb://127.0.0.1:27017}"
export DB_NAME="${DB_NAME:-sugar_city_sweeps}"

cd "${ROOT}/backend"
exec python3 -m uvicorn server:app --host 0.0.0.0 --port 8001 --reload
