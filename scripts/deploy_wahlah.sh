#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

FLY_APP="wah-lah"
PRIMARY_DOMAIN="wah-lah.com"
WWW_DOMAIN="www.${PRIMARY_DOMAIN}"
API_DOMAIN="api.${PRIMARY_DOMAIN}"
FLY_HEALTH_URL="https://${FLY_APP}.fly.dev/api/health"
PRIMARY_HEALTH_URL="https://${PRIMARY_DOMAIN}/api/health"

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

echo "Deploying ${PRIMARY_DOMAIN} via Fly app ${FLY_APP}..."
flyctl deploy --remote-only --config fly.toml

echo "Ensuring custom-domain certs are requested..."
for domain in "${PRIMARY_DOMAIN}" "${WWW_DOMAIN}" "${API_DOMAIN}"; do
  if flyctl certs add "${domain}" --app "${FLY_APP}"; then
    echo "Certificate requested or already present: ${domain}"
  else
    echo "Warning: certificate request failed for ${domain}; continuing to health checks."
  fi
done

echo "Checking production health..."
for url in "${PRIMARY_HEALTH_URL}" "${FLY_HEALTH_URL}"; do
  echo "Checking ${url}"
  curl --fail --show-error --silent --max-time 30 "${url}"
  echo
done

echo "Deploy complete."
