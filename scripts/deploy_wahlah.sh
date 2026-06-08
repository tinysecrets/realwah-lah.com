#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

FLY_APP="wah-lah"
API_DOMAIN="api.wah-lah.com"
FLY_HEALTH_URL="https://${FLY_APP}.fly.dev/api/health"
API_HEALTH_URL="https://${API_DOMAIN}/api/health"

if ! command -v flyctl >/dev/null 2>&1; then
  echo "flyctl is required: https://fly.io/docs/flyctl/install/"
  exit 1
fi

if [ -z "${FLY_API_TOKEN:-}" ]; then
  if ! flyctl auth whoami >/dev/null 2>&1; then
    echo "No Fly auth found. Run flyctl auth login or export FLY_API_TOKEN."
    exit 1
  fi
fi

echo "Deploying backend (${API_DOMAIN}) via Fly app ${FLY_APP}..."
flyctl deploy --remote-only --config fly.toml --app "${FLY_APP}"

echo "Ensuring API TLS cert..."
flyctl certs add "${API_DOMAIN}" --app "${FLY_APP}" 2>/dev/null || echo "Certificate already present or pending: ${API_DOMAIN}"

echo "Checking health..."
sleep 5
for url in "${FLY_HEALTH_URL}" "${API_HEALTH_URL}"; do
  echo "→ ${url}"
  if curl --fail --show-error --silent --max-time 30 "${url}"; then
    echo
  else
    echo "Warning: ${url} not ready yet. Try: flyctl logs -a ${FLY_APP}"
  fi
done

echo "Backend deploy complete."
