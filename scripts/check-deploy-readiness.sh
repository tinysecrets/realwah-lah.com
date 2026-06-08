#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-.wahlah-secrets.env}"
READY=1

c_green() { printf "\033[0;32m%s\033[0m\n" "$*"; }
c_red()   { printf "\033[0;31m%s\033[0m\n" "$*"; }
c_blue()  { printf "\033[0;34m%s\033[0m\n" "$*"; }

check_var() {
  local label="$1"
  local value="$2"
  if [[ -n "$value" && "$value" != *REPLACE* && "$value" != *YOUR_* ]]; then
    c_green " ✓ $label"
  else
    c_red " ✗ $label — set in $ENV_FILE"
    READY=0
  fi
}

c_blue "WAH-LAH deployment readiness"

if [[ ! -f "$ENV_FILE" ]]; then
  c_red "Missing $ENV_FILE"
  echo "Run: bash scripts/setup-secrets.sh"
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

check_var "MONGO_URL" "${MONGO_URL:-}"
check_var "STRIPE_API_KEY" "${STRIPE_API_KEY:-}"
check_var "STRIPE_PUBLISHABLE_KEY" "${STRIPE_PUBLISHABLE_KEY:-}"
check_var "RESEND_API_KEY" "${RESEND_API_KEY:-}"
check_var "CEREBRAS_API_KEY" "${CEREBRAS_API_KEY:-}"
check_var "CLOUDFLARE_API_TOKEN" "${CLOUDFLARE_API_TOKEN:-}"
check_var "CLOUDFLARE_ZONE_ID" "${CLOUDFLARE_ZONE_ID:-}"
check_var "ADMIN_PASSWORD" "${ADMIN_PASSWORD:-}"

if command -v flyctl >/dev/null 2>&1 && flyctl auth whoami >/dev/null 2>&1; then
  c_green " ✓ flyctl authenticated"
else
  c_red " ✗ flyctl not authenticated — run: flyctl auth login"
  READY=0
fi

if [[ -f fly.toml && -f Dockerfile ]]; then
  c_green " ✓ fly.toml + Dockerfile at repo root"
else
  c_red " ✗ missing fly.toml or Dockerfile"
  READY=0
fi

if [[ $READY -eq 1 ]]; then
  c_green "READY — run: bash scripts/deploy-all.sh"
else
  c_red "NOT READY — fill secrets in $ENV_FILE"
  exit 1
fi
