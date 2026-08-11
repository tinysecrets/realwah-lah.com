#!/usr/bin/env bash
# Populate backend/.env from current environment variables for local testing.
# WARNING: This writes secrets to backend/.env. Do NOT commit the generated file.
set -euo pipefail
OUT=backend/.env
echo "# Generated from environment on $(date -u -Iseconds)" > "$OUT"
# List of keys to export if present
keys=(
  TELEGRAM_BOT_TOKEN
  TELEGRAM_WEBHOOK_SECRET
  TELEGRAM_ALLOWED_USERS
  TELEGRAM_ENABLED
  OPENROUTER_API_KEY
  OPENROUTER_API_URL
  OPENROUTER_MODEL
  GITHUB_REPO
  GITHUB_TOKEN
  CLOUDFLARE_API_TOKEN
  CLOUDFLARE_ACCOUNT_ID
  CLOUDFLARE_ZONE_ID
  RENDER_API_KEY
  RENDER_SERVICE_ID
  BRIDGE_BUILD_CMD
  BRIDGE_TEST_CMD
  BRIDGE_POLL_INTERVAL
)
for k in "${keys[@]}"; do
  v=${!k-}
  if [ -n "$v" ]; then
    # escape any existing $ characters
    esc=$(printf '%s' "$v" | sed -e 's/\$/\\$/g')
    echo "$k=$esc" >> "$OUT"
  else
    echo "# $k not set" >> "$OUT"
  fi
done
chmod 600 "$OUT"
printf "Wrote %s (permissions 600).\n" "$OUT"
printf "REMINDER: Do not commit backend/.env. Use CI/host secret stores for real deployments.\n" 
