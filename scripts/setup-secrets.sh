#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXAMPLE="${ROOT}/.env-examples/.wahlah-secrets.env.example"
TARGET="${ROOT}/.wahlah-secrets.env"

if [[ -f "$TARGET" ]]; then
  echo "Already exists: $TARGET"
  exit 0
fi

cp "$EXAMPLE" "$TARGET"
echo "Created $TARGET"
echo "Edit it with your MongoDB Atlas URI, Stripe keys, Resend, Cerebras, and Cloudflare tokens."
echo "Then run: npm run deploy:secrets && npm run deploy:backend"
