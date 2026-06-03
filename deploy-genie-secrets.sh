#!/usr/bin/env bash
set -euo pipefail

# Genie Sidekick secrets deployment.
# Loads values from the current shell or from a local env file, validates that
# placeholders were replaced, then writes them to the Fly.io app.

APP_NAME="${APP_NAME:-genie-sidekick}"
ENV_FILE="${ENV_FILE:-.genie-secrets.env}"

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

require_secret GENIE_JWT_SECRET 32
require_secret GENIE_ADMIN_EMAIL 3
require_secret GENIE_ADMIN_PASSWORD 16
require_secret MONGO_URL 12

DB_NAME="${DB_NAME:-genie_sidekick}"
CEREBRAS_MODEL="${CEREBRAS_MODEL:-qwen-3-235b-a22b-instruct-2507}"
OLLAMA_MODEL="${OLLAMA_MODEL:-dolphin-mixtral:8x7b}"
CORS_ORIGINS="${CORS_ORIGINS:-https://genie.wah-lah.com,https://wah-lah.com,https://www.wah-lah.com,http://localhost:5173}"

SECRET_ARGS=(
  "GENIE_JWT_SECRET=$GENIE_JWT_SECRET"
  "GENIE_ADMIN_EMAIL=$GENIE_ADMIN_EMAIL"
  "GENIE_ADMIN_PASSWORD=$GENIE_ADMIN_PASSWORD"
  "MONGO_URL=$MONGO_URL"
  "DB_NAME=$DB_NAME"
  "CORS_ORIGINS=$CORS_ORIGINS"
)

if [ -z "${FLY_API_TOKEN:-}" ]; then
    echo "Error: FLY_API_TOKEN is not set." >&2
    exit 1
fi # <-- Make sure this is present for every if statement

if [ ${#ADMIN_EMAIL} -lt 5 ]; then
    echo "Error: ADMIN_EMAIL is too short." >&2
    exit 1
fi # <-- Add this here as well

if [[ -n "${CEREBRAS_API_KEY:-}" ]]; then
  SECRET_ARGS+=("CEREBRAS_API_KEY=$CEREBRAS_API_KEY")
  SECRET_ARGS+=("CEREBRAS_MODEL=$CEREBRAS_MODEL")
fi

if [[ -n "${VENICE_API_KEY:-}" ]]; then
  SECRET_ARGS+=("VENICE_API_KEY=$VENICE_API_KEY")
  if [[ -n "${VENICE_MODEL:-}" ]]; then
    SECRET_ARGS+=("VENICE_MODEL=$VENICE_MODEL")
  fi
fi

if [[ -n "${OLLAMA_BASE_URL:-}" ]]; then
  SECRET_ARGS+=("OLLAMA_BASE_URL=$OLLAMA_BASE_URL")
  SECRET_ARGS+=("OLLAMA_MODEL=$OLLAMA_MODEL")
fi

if [[ -z "${CEREBRAS_API_KEY:-}" && -z "${VENICE_API_KEY:-}" && -z "${OLLAMA_BASE_URL:-}" ]]; then
  echo "Warning: no LLM provider configured. Login will work, but chat will return a provider error."
fi

if ! command -v flyctl >/dev/null 2>&1; then
  echo "flyctl is required. Install it from https://fly.io/docs/flyctl/install/"
  exit 1
fi

echo "Setting ${#SECRET_ARGS[@]} secrets on Fly.io app: $APP_NAME"
flyctl secrets set -a "$APP_NAME" "${SECRET_ARGS[@]}"

echo
echo "Secrets currently configured on $APP_NAME:"
flyctl secrets list -a "$APP_NAME"
