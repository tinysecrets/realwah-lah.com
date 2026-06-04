#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════════╗
# ║          WAH-LAH ONE-SHOT FLY.IO DEPLOY SCRIPT                  ║
# ║                                                                  ║
# ║  Fill in the blanks below, save, then:                           ║
# ║    chmod +x deploy.sh && ./deploy.sh                             ║
# ║                                                                  ║
# ║  Run this from inside /app on your laptop after cloning the      ║
# ║  GitHub repo. Requires flyctl installed:                         ║
# ║      curl -L https://fly.io/install.sh | sh                      ║
# ║                                                                  ║
# ║  Safe to re-run — every step is idempotent.                      ║
# ╚══════════════════════════════════════════════════════════════════╝

set -euo pipefail

# ====================================================================
# 1. FILL THESE IN AFTER ROTATING EVERY KEY THAT WAS LEAKED IN CHAT
# ====================================================================

# --- Fly.io ---
FLY_APP="wah-lah"                                # name in fly.toml — don't change unless you renamed the Fly app
FLY_TOKEN=''                                     # OPTIONAL: paste fresh FlyV1 fm2_... here, OR run 'flyctl auth login' beforehand and leave this blank

# --- Stripe (https://dashboard.stripe.com/apikeys) ---
STRIPE_API_KEY=""                                # sk_live_... or rk_live_... (REQUIRED - backend uses this to charge cards)
STRIPE_PUBLISHABLE_KEY=""                        # pk_live_... (REQUIRED - frontend uses this to render the Stripe widget)
STRIPE_WEBHOOK_SECRET=""                         # whsec_... — OPTIONAL on first deploy; add later (see step 2 at end)

# --- Resend (https://resend.com/api-keys) ---
RESEND_API_KEY=""                                # re_...
EMAIL_FROM="WAH-LAH <onboarding@resend.dev>"     # safe default until wah-lah.com is verified in Resend
CUSTOM_EMAIL_FROM="WAH-LAH <noreply@wah-lah.com>"  # switches over once Resend verifies wah-lah.com

# --- Cerebras (https://cloud.cerebras.ai) — Boss Genie LLM ---
CEREBRAS_API_KEY=""                              # csk_...
CEREBRAS_MODEL="qwen-3-235b-a22b-instruct-2507"

# --- Cloudflare (https://dash.cloudflare.com → My Profile → API Tokens) ---
CLOUDFLARE_API_TOKEN=""                          # cfat_...
CLOUDFLARE_ZONE_ID=""                            # found at Cloudflare → wah-lah.com → Overview → right sidebar → Zone ID

# --- MongoDB Atlas (https://cloud.mongodb.com → Cluster → Connect → Drivers → Python) ---
MONGO_URL=""                                     # mongodb+srv://user:pwd@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
DB_NAME="wahlah_prod"

# --- Admin seed account (auto-created on first boot) ---
ADMIN_EMAIL="admin@wah-lah.com"
ADMIN_PASSWORD=""                                # 16+ chars random — stash in a password manager

# --- Payment tag (already set, leave unless you swap Cash App handles) ---
CARD_PAYMENT_TAG="\$jrs092393"

# --- Optional: Sugar Sweeps hub creds (leave blank to skip Playwright bot init at boot) ---
SUGAR_SWEEPS_USERNAME=""                         # e.g. jrs092393@gmail.com
SUGAR_SWEEPS_PASSWORD=""

# ====================================================================
# 2. DO NOT EDIT BELOW (unless you know what you're doing)
# ====================================================================

c_green() { printf "\033[0;32m%s\033[0m\n" "$*"; }
c_red()   { printf "\033[0;31m%s\033[0m\n" "$*"; }
c_yel()   { printf "\033[0;33m%s\033[0m\n" "$*"; }
c_blue()  { printf "\033[0;34m%s\033[0m\n" "$*"; }

# --- Preflight: tools installed ---
c_blue "==> [1/7] Preflight"
if ! command -v flyctl >/dev/null 2>&1; then
    c_red "flyctl is not installed. Install it first:"
    echo "    curl -L https://fly.io/install.sh | sh"
    echo "    export PATH=\"\$HOME/.fly/bin:\$PATH\""
    exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
    c_red "python3 is required (used to generate JWT_SECRET and PROXY_ENCRYPTION_KEY)."
    exit 1
fi

# --- Preflight: auth (either via token in script OR existing flyctl login) ---
if [[ -n "$FLY_TOKEN" ]]; then
    export FLY_API_TOKEN="$FLY_TOKEN"
fi
if ! flyctl auth whoami >/dev/null 2>&1; then
    c_red "Not logged in to Fly. Either:"
    echo "    A) Paste a token into FLY_TOKEN at the top of this script, OR"
    echo "    B) Run 'flyctl auth login' once, then re-run ./deploy.sh"
    exit 1
fi
c_green "  ✓ flyctl installed & authenticated as: $(flyctl auth whoami)"

# --- Preflight: required vars filled in ---
REQUIRED=("STRIPE_API_KEY" "STRIPE_PUBLISHABLE_KEY" "RESEND_API_KEY" "CEREBRAS_API_KEY" "CLOUDFLARE_API_TOKEN" "CLOUDFLARE_ZONE_ID" "MONGO_URL" "ADMIN_PASSWORD")
MISSING=()
for v in "${REQUIRED[@]}"; do
    [[ -z "${!v}" ]] && MISSING+=("$v")
done
if [ ${#MISSING[@]} -gt 0 ]; then
    c_red "STOP. Fill in these variables at the top of deploy.sh first:"
    printf '   - %s\n' "${MISSING[@]}"
    exit 1
fi

# --- Preflight: shape checks (catches the #1 / #2 / #3 most common mistakes) ---
if [[ "$STRIPE_API_KEY" == pk_* ]]; then
    c_red "STRIPE_API_KEY starts with 'pk_' — that's the PUBLISHABLE key. Can't charge cards."
    echo "   Go to https://dashboard.stripe.com/apikeys → reveal the SECRET (sk_live_...)."
    exit 1
fi
if [[ "$STRIPE_API_KEY" != sk_live_* && "$STRIPE_API_KEY" != rk_live_* && "$STRIPE_API_KEY" != sk_test_* && "$STRIPE_API_KEY" != rk_test_* ]]; then
    c_yel "  ⚠ STRIPE_API_KEY doesn't start with sk_live_/rk_live_/sk_test_/rk_test_. Continuing — double-check it."
fi
if [[ "$STRIPE_PUBLISHABLE_KEY" != pk_* ]]; then
    c_red "STRIPE_PUBLISHABLE_KEY must start with 'pk_'."
    exit 1
fi
if [[ "$MONGO_URL" != mongodb+srv://* && "$MONGO_URL" != mongodb://* ]]; then
    c_red "MONGO_URL must start with mongodb+srv:// (Atlas) or mongodb:// (self-hosted)."
    exit 1
fi
if [[ "$MONGO_URL" == *localhost* || "$MONGO_URL" == *127.0.0.1* ]]; then
    c_red "MONGO_URL points at localhost. That won't work inside Fly — use your MongoDB Atlas URL."
    exit 1
fi
if [[ ${#ADMIN_PASSWORD} -lt 16 ]]; then
    c_yel "  ⚠ ADMIN_PASSWORD is shorter than 16 chars. Strongly recommend 16+."
fi

# --- Preflight: confirm Fly app exists & you have access ---
if ! flyctl status -a "$FLY_APP" >/dev/null 2>&1; then
    c_red "Fly app '$FLY_APP' not found (or you lack access)."
    echo "   First-time setup:  flyctl launch --no-deploy --name $FLY_APP --copy-config --yes"
    echo "   Or update FLY_APP at top of this script to match your real app name."
    exit 1
fi
c_green "  ✓ Fly app '$FLY_APP' reachable"
c_green "Preflight passed."

# ====================================================================
# 3. AUTO-GENERATE CRYPTO SECRETS (only if missing on Fly)
# ====================================================================
c_blue "==> [2/7] Crypto secrets (JWT_SECRET, PROXY_ENCRYPTION_KEY)"
EXISTING_SECRETS="$(flyctl secrets list -a "$FLY_APP" --json 2>/dev/null || echo '[]')"

CRYPTO_ARGS=()
if echo "$EXISTING_SECRETS" | grep -q '"JWT_SECRET"'; then
    c_green "  ✓ JWT_SECRET already set on Fly — keeping it (rotating would log every user out)"
else
    NEW_JWT="$(python3 -c 'import secrets;print(secrets.token_urlsafe(64))')"
    CRYPTO_ARGS+=("JWT_SECRET=$NEW_JWT")
    c_green "  ✓ Generated fresh JWT_SECRET (64 bytes)"
fi
if echo "$EXISTING_SECRETS" | grep -q '"PROXY_ENCRYPTION_KEY"'; then
    c_green "  ✓ PROXY_ENCRYPTION_KEY already set on Fly — keeping it"
else
    NEW_PROXY="$(python3 -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())' 2>/dev/null || python3 -c 'import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())')"
    CRYPTO_ARGS+=("PROXY_ENCRYPTION_KEY=$NEW_PROXY")
    c_green "  ✓ Generated fresh PROXY_ENCRYPTION_KEY"
fi

# ====================================================================
# 4. ASSEMBLE + SET ALL SECRETS
# ====================================================================
c_blue "==> [3/7] Setting Fly secrets"

SECRET_ARGS=(
    "STRIPE_API_KEY=$STRIPE_API_KEY"
    "STRIPE_PUBLISHABLE_KEY=$STRIPE_PUBLISHABLE_KEY"
    "RESEND_API_KEY=$RESEND_API_KEY"
    "EMAIL_FROM=$EMAIL_FROM"
    "CUSTOM_EMAIL_FROM=$CUSTOM_EMAIL_FROM"
    "CEREBRAS_API_KEY=$CEREBRAS_API_KEY"
    "CEREBRAS_MODEL=$CEREBRAS_MODEL"
    "CLOUDFLARE_API_TOKEN=$CLOUDFLARE_API_TOKEN"
    "CLOUDFLARE_ZONE_ID=$CLOUDFLARE_ZONE_ID"
    "MONGO_URL=$MONGO_URL"
    "DB_NAME=$DB_NAME"
    "ADMIN_EMAIL=$ADMIN_EMAIL"
    "ADMIN_PASSWORD=$ADMIN_PASSWORD"
    "CARD_PAYMENT_TAG=$CARD_PAYMENT_TAG"
    "FRONTEND_URL=https://wah-lah.com"
    "CORS_ORIGINS=https://wah-lah.com,https://www.wah-lah.com,https://api.wah-lah.com"
    "COOKIE_SECURE=true"
    "COOKIE_SAMESITE=lax"
    "ENFORCE_CANONICAL_HOST=true"
    "BLOCKED_STATES=WA,ID,MT,NV,LA,TN,MI,UT,AZ"
    "KYC_BASIC_THRESHOLD_USD=500"
    "KYC_ENHANCED_THRESHOLD_USD=5000"
    "CTR_THRESHOLD_USD=10000"
    "SAR_FREQ_WINDOW_HOURS=24"
    "SAR_FREQ_THRESHOLD=3"
    "CASHTAG_KEEP_RATE=0.12"
    "GIFTCARD_FEE_RATE=0.05"
    "DEPOSIT_BONUS_RATE=0.20"
    "DEPOSIT_BONUS_PLAYTHROUGH_MULTIPLIER=1.0"
    "BTC_FEE_RATE=0.10"
    "PROXY_DEFAULT_PER_TRANSFER_CAP=500"
    "PROXY_DEFAULT_DAILY_CAP=5000"
    "PROXY_COOLDOWN_FAILURES=3"
    "PROXY_LOCK_FAILURES=5"
    "PROXY_COOLDOWN_MINUTES=30"
)

# Optional: webhook secret (skip on first deploy — Stripe gives it to you AFTER your URL is live)
if [[ -n "$STRIPE_WEBHOOK_SECRET" ]]; then
    SECRET_ARGS+=("STRIPE_WEBHOOK_SECRET=$STRIPE_WEBHOOK_SECRET")
else
    c_yel "  ⚠ STRIPE_WEBHOOK_SECRET is blank — fine for first deploy. Set it after step 2 in the post-deploy checklist."
fi

# Optional: Sugar Sweeps creds (skip → bot bridge stays dormant on boot)
[[ -n "$SUGAR_SWEEPS_USERNAME" ]] && SECRET_ARGS+=("SUGAR_SWEEPS_USERNAME=$SUGAR_SWEEPS_USERNAME")
[[ -n "$SUGAR_SWEEPS_PASSWORD" ]] && SECRET_ARGS+=("SUGAR_SWEEPS_PASSWORD=$SUGAR_SWEEPS_PASSWORD")

# Merge in the freshly-generated crypto secrets (only if any were generated)
[[ ${#CRYPTO_ARGS[@]} -gt 0 ]] && SECRET_ARGS+=("${CRYPTO_ARGS[@]}")

# --stage = don't restart machines yet; we deploy in the next step
flyctl secrets set --stage -a "$FLY_APP" "${SECRET_ARGS[@]}"
c_green "  ✓ All secrets staged on Fly"

# ====================================================================
# 5. DEPLOY
# ====================================================================
c_blue "==> [4/7] Deploying (this takes ~2-4 min on first deploy)"
flyctl deploy -a "$FLY_APP" --remote-only --strategy=rolling

# ====================================================================
# 6. TLS CERTS (idempotent — safe to re-run)
# ====================================================================
c_blue "==> [5/7] Adding TLS certs (idempotent)"
flyctl certs add wah-lah.com     -a "$FLY_APP" 2>/dev/null || c_yel "  (cert for wah-lah.com already exists — ok)"
flyctl certs add www.wah-lah.com -a "$FLY_APP" 2>/dev/null || c_yel "  (cert for www.wah-lah.com already exists — ok)"
flyctl certs add api.wah-lah.com -a "$FLY_APP" 2>/dev/null || c_yel "  (cert for api.wah-lah.com already exists — ok)"

# ====================================================================
# 7. IPs (paste these into Cloudflare DNS) + smoke test
# ====================================================================
c_blue "==> [6/7] Fly IPs — paste into Cloudflare DNS if first deploy"
flyctl ips list -a "$FLY_APP" || true

c_blue "==> [7/7] Smoke test → curl https://${FLY_APP}.fly.dev/api/health"
HEALTH_URL="https://${FLY_APP}.fly.dev/api/health"
sleep 5   # give the machine a beat to finish rolling
if curl -fsS --max-time 20 "$HEALTH_URL" >/dev/null 2>&1; then
    c_green "  ✓ /api/health returned 200 — backend is alive"
else
    c_yel "  ⚠ /api/health did not return 200 yet. Tail logs to debug:"
    echo "      flyctl logs -a $FLY_APP"
fi

# ====================================================================
# 8. POST-DEPLOY CHECKLIST
# ====================================================================
cat <<EOF

$(c_green "════════════════════════════════════════════════════════════════")
$(c_green " DEPLOY COMPLETE — finish these manual steps:")
$(c_green "════════════════════════════════════════════════════════════════")

1. CLOUDFLARE DNS (first deploy only)
   Go to https://dash.cloudflare.com → wah-lah.com → DNS → Records
   Add records pointing to the Fly IPs printed above:
     • A     @     <Fly v4 IP>         proxied=ON
     • AAAA  @     <Fly v6 IP>         proxied=ON
     • CNAME www   ${FLY_APP}.fly.dev   proxied=ON
     • CNAME api   ${FLY_APP}.fly.dev   proxied=ON   (only if you want a separate api subdomain)

2. STRIPE WEBHOOK (first deploy only)
   https://dashboard.stripe.com/webhooks → Add endpoint
     URL:    https://wah-lah.com/api/webhook/stripe
     Events: checkout.session.completed, checkout.session.expired
   → Copy the whsec_... that Stripe gives you, then run:
       flyctl secrets set STRIPE_WEBHOOK_SECRET='whsec_...' -a $FLY_APP

3. RESEND DOMAIN VERIFICATION (so emails don't land in spam)
   https://resend.com/domains → Add Domain → wah-lah.com
   Add the TXT + MX records into Cloudflare DNS
   Once green, your emails will start sending from noreply@wah-lah.com.

4. SMOKE TEST ON THE LIVE DOMAIN
   • Register a new player at https://wah-lah.com
   • Claim AMOE credits (100)
   • Make a \$5 Stripe deposit, confirm credits land
   • Try a small gift card redemption — confirm 5% fee in:
       curl https://wah-lah.com/api/admin/revenue/ledger -H "Authorization: Bearer <admin-jwt>"

5. ADMIN LOGIN
   Email:    $ADMIN_EMAIL
   Password: (whatever you set in this script — stash in 1Password/Bitwarden)

$(c_blue "──── Money knobs (live-tunable, no redeploy) ────")
   Raise cashtag fee:    POST /api/admin/revenue/settings  { "cashtag": 0.15 }
   Promo gift card:      POST /api/admin/revenue/settings  { "giftcard": 0.03 }
   See P&L:              GET  /api/admin/revenue/summary?days=30

$(c_blue "──── Useful flyctl commands ────")
   Logs:     flyctl logs       -a $FLY_APP
   Status:   flyctl status     -a $FLY_APP
   Redeploy: flyctl deploy     -a $FLY_APP
   SSH:     flyctl ssh console -a $FLY_APP
   Rotate one secret: flyctl secrets set KEY='value' -a $FLY_APP

🪔 You are live.
EOF
