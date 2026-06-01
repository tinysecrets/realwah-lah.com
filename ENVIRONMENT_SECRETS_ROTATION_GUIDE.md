# Environment Variables and Secrets Rotation Guide

Last updated: 2026-06-01
Scope: `tinysecrets/realwah-lah.com`
Fly app: `wah-lah`
Runtime port: `8001`

This repo is already wired for Fly.io on port `8001`:

- [fly.toml](fly.toml): `PORT = "8001"` and `internal_port = 8001`
- [Dockerfile](Dockerfile): `EXPOSE 8001` and Uvicorn starts with `--port 8001`
- [backend/Procfile](backend/Procfile): uses `$PORT`, which Fly provides from `fly.toml`

Do not commit real secrets. Put live values in Fly secrets only.

## Required Runtime Secrets

The main backend reads these directly at startup or during critical flows:

```text
MONGO_URL
DB_NAME
JWT_SECRET
STRIPE_API_KEY
RESEND_API_KEY
ADMIN_EMAIL
ADMIN_PASSWORD
PROXY_ENCRYPTION_KEY
```

Recommended production values:

```text
FRONTEND_URL=https://wah-lah.com
CORS_ORIGINS=https://wah-lah.com,https://www.wah-lah.com,https://api.wah-lah.com
COOKIE_SECURE=true
COOKIE_SAMESITE=lax
ENFORCE_CANONICAL_HOST=true
CANONICAL_HOST=wah-lah.com
```

Optional integrations:

```text
STRIPE_WEBHOOK_SECRET
STRIPE_PUBLISHABLE_KEY
CEREBRAS_API_KEY
CEREBRAS_MODEL
VENICE_API_KEY
VENICE_MODEL
OLLAMA_BASE_URL
OLLAMA_MODEL
CLOUDFLARE_API_TOKEN
CLOUDFLARE_ZONE_ID
SENTRY_DSN
SUGAR_SWEEPS_USERNAME
SUGAR_SWEEPS_PASSWORD
SUGAR_SWEEPS_URL
BTC_WEBHOOK_SECRET
BTC_GATEWAY_API_URL
BTC_GATEWAY_API_KEY
BTCPAY_STORE_ID
CRYPTO_WALLET_ADDRESS
LIGHTNING_ADDRESS
```

Compliance and limits:

```text
BLOCKED_STATES=WA,ID,MT,NV,LA,TN,MI,UT,AZ
KYC_BASIC_THRESHOLD_USD=500
KYC_ENHANCED_THRESHOLD_USD=5000
CTR_THRESHOLD_USD=10000
SAR_FREQ_WINDOW_HOURS=24
SAR_FREQ_THRESHOLD=3
PROXY_DEFAULT_PER_TRANSFER_CAP=500
PROXY_DEFAULT_DAILY_CAP=5000
PROXY_COOLDOWN_FAILURES=3
PROXY_LOCK_FAILURES=5
PROXY_COOLDOWN_MINUTES=30
```

## Main App Rotation Command

Use the helper script:

```bash
cp .wahlah-secrets.env.example .wahlah-secrets.env
# Fill .wahlah-secrets.env with live values.
./deploy-wahlah-secrets.sh
flyctl deploy -a wah-lah
```

Manual copy-paste form:

```bash
flyctl secrets set -a wah-lah \
  MONGO_URL='mongodb+srv://...' \
  DB_NAME='sugar_city_sweeps' \
  JWT_SECRET='generate-with-python-secrets-token-urlsafe-64' \
  ADMIN_EMAIL='your-admin-email@example.com' \
  ADMIN_PASSWORD='your-strong-admin-password' \
  STRIPE_API_KEY='sk_live_or_test_value' \
  STRIPE_WEBHOOK_SECRET='whsec_optional_until_webhook_is_ready' \
  RESEND_API_KEY='re_value' \
  EMAIL_FROM='WAH-LAH <onboarding@resend.dev>' \
  CUSTOM_EMAIL_FROM='WAH-LAH <noreply@wah-lah.com>' \
  FRONTEND_URL='https://wah-lah.com' \
  CORS_ORIGINS='https://wah-lah.com,https://www.wah-lah.com,https://api.wah-lah.com' \
  COOKIE_SECURE='true' \
  COOKIE_SAMESITE='lax' \
  ENFORCE_CANONICAL_HOST='true' \
  CANONICAL_HOST='wah-lah.com' \
  CARD_PAYMENT_TAG='$WahLah' \
  CEREBRAS_API_KEY='csk_optional_value' \
  CEREBRAS_MODEL='qwen-3-235b-a22b-instruct-2507' \
  CLOUDFLARE_API_TOKEN='cf_optional_value' \
  CLOUDFLARE_ZONE_ID='zone_optional_value' \
  PROXY_ENCRYPTION_KEY='generate-with-cryptography-fernet' \
  BLOCKED_STATES='WA,ID,MT,NV,LA,TN,MI,UT,AZ' \
  KYC_BASIC_THRESHOLD_USD='500' \
  KYC_ENHANCED_THRESHOLD_USD='5000' \
  CTR_THRESHOLD_USD='10000' \
  SAR_FREQ_WINDOW_HOURS='24' \
  SAR_FREQ_THRESHOLD='3' \
  PROXY_DEFAULT_PER_TRANSFER_CAP='500' \
  PROXY_DEFAULT_DAILY_CAP='5000' \
  PROXY_COOLDOWN_FAILURES='3' \
  PROXY_LOCK_FAILURES='5' \
  PROXY_COOLDOWN_MINUTES='30'
```

## Genie Sidekick Rotation Command

Genie uses separate namespaced auth secrets so it does not share the main app JWT/admin credentials:

```bash
cp .genie-secrets.env.example .genie-secrets.env
# Fill .genie-secrets.env with live values.
./deploy-genie-secrets.sh
flyctl deploy -a genie-sidekick -c genie-sidekick/fly.toml
```

## Safe Rotation Checklist

1. Generate new secrets locally, not in chat:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(64))'
python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

2. Confirm current Fly app and port:

```bash
flyctl status -a wah-lah
flyctl config validate -a wah-lah
grep -n '8001' fly.toml Dockerfile
```

3. Set secrets:

```bash
./deploy-wahlah-secrets.sh
flyctl secrets list -a wah-lah
```

4. Deploy and watch health:

```bash
flyctl deploy -a wah-lah
flyctl status -a wah-lah
curl -fsS https://wah-lah.com/api/health
```

5. Verify critical flows:

```bash
curl -fsS https://api.wah-lah.com/api/health
curl -i -X POST https://api.wah-lah.com/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"ADMIN_EMAIL_HERE","password":"ADMIN_PASSWORD_HERE"}'
```

6. Revoke old provider credentials only after the new deployment is healthy.

JWT rotation logs out active users. `PROXY_ENCRYPTION_KEY` rotation can make previously encrypted proxy credentials unreadable unless those records are re-saved with the new key.
