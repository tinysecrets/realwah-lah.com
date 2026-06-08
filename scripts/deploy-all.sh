#!/usr/bin/env bash
# Full production deploy: Fly secrets → Fly backend.
# Frontend deploys separately via Cloudflare Pages (Git push auto-build).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SECRETS_FILE="${SECRETS_FILE:-.wahlah-secrets.env}"

if [[ ! -f "$SECRETS_FILE" ]]; then
  echo "Missing $SECRETS_FILE — run: bash scripts/setup-secrets.sh"
  exit 1
fi

echo "==> Setting Fly.io secrets from $SECRETS_FILE"
ENV_FILE="$SECRETS_FILE" bash scripts/deploy-wahlah-secrets.sh

echo "==> Deploying backend to Fly.io"
bash scripts/deploy_wahlah.sh

cat <<'EOF'

Backend deploy finished.

Cloudflare Pages (frontend) — one-time setup:
  1. Workers & Pages → Create → Connect Git → this repo
  2. Build command:  cd frontend && yarn install --frozen-lockfile && yarn build
  3. Output dir:     frontend/build
  4. Env var:        REACT_APP_BACKEND_URL=https://api.wah-lah.com
  5. Custom domains: wah-lah.com, www.wah-lah.com

DNS (Cloudflare → wah-lah.com):
  CNAME @   → <pages-project>.pages.dev  (proxied)
  CNAME www → <pages-project>.pages.dev  (proxied)
  CNAME api → wah-lah.fly.dev            (DNS only / grey cloud)

EOF
