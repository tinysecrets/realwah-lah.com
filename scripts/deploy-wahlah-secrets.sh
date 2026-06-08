#!/usr/bin/env bash
set -euo pipefail

# Main Wah-Lah Fly.io secrets deployment.
# Copy .wahlah-secrets.env.example to .wahlah-secrets.env, fill real values,
# then run this script from the repository root.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

APP_NAME="${APP_NAME:-wah-lah}"
ENV_FILE="${ENV_FILE:-.wahlah-secrets.env}"

if [[ ! -f "$ENV_FILE" && -f ".env-examples/.wahlah-secrets.env.example" ]]; then
  echo "No $ENV_FILE found. Run: bash scripts/setup-secrets.sh"
  exit 1
fi

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

is_placeholder() {
  local value="${1:-}"
  [[ -z "$value" || "$value" == *REPLACE* || "$value" == *YOUR_* || "$value" == *xxxxx* ]]
}

require_secret() {
  local name="$1"
  local min_len="${2:-1}"
  local value="${!name:-}"

  if is_placeholder "$value"; then
    echo "Missing or placeholder value: $name"
    exit 1
  fi

  if (( ${#value} < min_len )); then
    echo "$name must be at least $min_len characters"
    exit 1
  fi
}

require_secret MONGO_URL 12
require_secret DB_NAME 1

if is_placeholder "${JWT_SECRET:-}"; then
  JWT_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(64))')"
  echo "Generated JWT_SECRET"
fi
if is_placeholder "${PROXY_ENCRYPTION_KEY:-}"; then
  PROXY_ENCRYPTION_KEY="$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())' 2>/dev/null || python3 -c 'import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())')"
  echo "Generated PROXY_ENCRYPTION_KEY"
fi
require_secret ADMIN_EMAIL 3
require_secret ADMIN_PASSWORD 16
require_secret STRIPE_API_KEY 8
require_secret RESEND_API_KEY 8

FRONTEND_URL="${FRONTEND_URL:-https://wah-lah.com}"
CORS_ORIGINS="${CORS_ORIGINS:-https://wah-lah.com,https://www.wah-lah.com,https://api.wah-lah.com}"
COOKIE_SECURE="${COOKIE_SECURE:-true}"
COOKIE_SAMESITE="${COOKIE_SAMESITE:-lax}"
ENFORCE_CANONICAL_HOST="${ENFORCE_CANONICAL_HOST:-true}"
CANONICAL_HOST="${CANONICAL_HOST:-wah-lah.com}"
CARD_PAYMENT_TAG="${CARD_PAYMENT_TAG:-\$WahLah}"
CEREBRAS_MODEL="${CEREBRAS_MODEL:-qwen-3-235b-a22b-instruct-2507}"
VENICE_MODEL="${VENICE_MODEL:-venice-uncensored}"
OLLAMA_MODEL="${OLLAMA_MODEL:-dolphin-mixtral:8x7b}"
BLOCKED_STATES="${BLOCKED_STATES:-WA,ID,MT,NV,LA,TN,MI,UT,AZ}"
KYC_BASIC_THRESHOLD_USD="${KYC_BASIC_THRESHOLD_USD:-500}"
KYC_ENHANCED_THRESHOLD_USD="${KYC_ENHANCED_THRESHOLD_USD:-5000}"
CTR_THRESHOLD_USD="${CTR_THRESHOLD_USD:-10000}"
SAR_FREQ_WINDOW_HOURS="${SAR_FREQ_WINDOW_HOURS:-24}"
SAR_FREQ_THRESHOLD="${SAR_FREQ_THRESHOLD:-3}"
CASHTAG_KEEP_RATE="${CASHTAG_KEEP_RATE:-0.12}"
GIFTCARD_FEE_RATE="${GIFTCARD_FEE_RATE:-0.05}"
BTC_FEE_RATE="${BTC_FEE_RATE:-0.10}"
PROXY_DEFAULT_PER_TRANSFER_CAP="${PROXY_DEFAULT_PER_TRANSFER_CAP:-500}"
PROXY_DEFAULT_DAILY_CAP="${PROXY_DEFAULT_DAILY_CAP:-5000}"
PROXY_COOLDOWN_FAILURES="${PROXY_COOLDOWN_FAILURES:-3}"
PROXY_LOCK_FAILURES="${PROXY_LOCK_FAILURES:-5}"
PROXY_COOLDOWN_MINUTES="${PROXY_COOLDOWN_MINUTES:-30}"

SECRET_ARGS=(
  "MONGO_URL=$MONGO_URL"
  "DB_NAME=$DB_NAME"
  "JWT_SECRET=$JWT_SECRET"
  "PROXY_ENCRYPTION_KEY=$PROXY_ENCRYPTION_KEY"
  "ADMIN_EMAIL=$ADMIN_EMAIL"
  "ADMIN_PASSWORD=$ADMIN_PASSWORD"
  "STRIPE_API_KEY=$STRIPE_API_KEY"
  "RESEND_API_KEY=$RESEND_API_KEY"
  "FRONTEND_URL=$FRONTEND_URL"
  "CORS_ORIGINS=$CORS_ORIGINS"
  "COOKIE_SECURE=$COOKIE_SECURE"
  "COOKIE_SAMESITE=$COOKIE_SAMESITE"
  "ENFORCE_CANONICAL_HOST=$ENFORCE_CANONICAL_HOST"
  "CANONICAL_HOST=$CANONICAL_HOST"
  "CARD_PAYMENT_TAG=$CARD_PAYMENT_TAG"
  "BLOCKED_STATES=$BLOCKED_STATES"
  "KYC_BASIC_THRESHOLD_USD=$KYC_BASIC_THRESHOLD_USD"
  "KYC_ENHANCED_THRESHOLD_USD=$KYC_ENHANCED_THRESHOLD_USD"
  "CTR_THRESHOLD_USD=$CTR_THRESHOLD_USD"
  "SAR_FREQ_WINDOW_HOURS=$SAR_FREQ_WINDOW_HOURS"
  "SAR_FREQ_THRESHOLD=$SAR_FREQ_THRESHOLD"
  "CASHTAG_KEEP_RATE=$CASHTAG_KEEP_RATE"
  "GIFTCARD_FEE_RATE=$GIFTCARD_FEE_RATE"
  "BTC_FEE_RATE=$BTC_FEE_RATE"
  "PROXY_DEFAULT_PER_TRANSFER_CAP=$PROXY_DEFAULT_PER_TRANSFER_CAP"
  "PROXY_DEFAULT_DAILY_CAP=$PROXY_DEFAULT_DAILY_CAP"
  "PROXY_COOLDOWN_FAILURES=$PROXY_COOLDOWN_FAILURES"
  "PROXY_LOCK_FAILURES=$PROXY_LOCK_FAILURES"
  "PROXY_COOLDOWN_MINUTES=$PROXY_COOLDOWN_MINUTES"
)

optional_secret() {
  local name="$1"
  local value="${!name:-}"
  if [[ -n "$value" ]]; then
    SECRET_ARGS+=("$name=$value")
  fi
}

optional_secret STRIPE_WEBHOOK_SECRET
optional_secret STRIPE_PUBLISHABLE_KEY
optional_secret EMAIL_FROM
optional_secret CUSTOM_EMAIL_FROM
optional_secret CEREBRAS_API_KEY
optional_secret CEREBRAS_MODEL
optional_secret VENICE_API_KEY
optional_secret VENICE_MODEL
optional_secret OLLAMA_BASE_URL
optional_secret OLLAMA_MODEL
optional_secret CLOUDFLARE_API_TOKEN
optional_secret CLOUDFLARE_ZONE_ID
optional_secret SENTRY_DSN
optional_secret SUGAR_SWEEPS_USERNAME
optional_secret SUGAR_SWEEPS_PASSWORD
optional_secret SUGAR_SWEEPS_URL
optional_secret CRYPTO_WALLET_ADDRESS
optional_secret LIGHTNING_ADDRESS
optional_secret BTC_WEBHOOK_SECRET
optional_secret BTC_GATEWAY_API_URL
optional_secret BTC_GATEWAY_API_KEY
optional_secret BTCPAY_STORE_ID

if ! command -v flyctl >/dev/null 2>&1; then
  echo "flyctl is required. Install it from https://fly.io/docs/flyctl/install/"
  exit 1
fi

echo "Setting ${#SECRET_ARGS[@]} secrets on Fly.io app: $APP_NAME"
flyctl secrets set -a "$APP_NAME" "${SECRET_ARGS[@]}"

echo
echo "Secrets currently configured on $APP_NAME:"
flyctl secrets list -a "$APP_NAME"
