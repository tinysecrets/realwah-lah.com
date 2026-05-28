#!/bin/bash
# ╔══════════════════════════════════════════════════════════════════╗
# ║          WAH-LAH ONE-SHOT FLY.IO DEPLOY SCRIPT                  ║
# ║                                                                  ║
# ║  Fill in the blanks below, save, then:                           ║
# ║    chmod +x deploy.sh && ./deploy.sh                             ║
# ║                                                                  ║
# ║  Run this from inside /app on your laptop after cloning the      ║
# ║  GitHub repo. Requires flyctl installed (curl -L                 ║
# ║  https://fly.io/install.sh | sh).                                ║
# ╚══════════════════════════════════════════════════════════════════╝

set -e

# ====================================================================
# 1. FILL THESE IN AFTER ROTATING EVERY KEY
# ====================================================================

# --- Fly.io ---
FLY_APP="wah-lah"                                # name in fly.toml
FLY_TOKEN=""                                     # FlyV1 fm2_... (paste fresh after rotation)

# --- Stripe (get from https://dashboard.stripe.com/apikeys) ---
STRIPE_API_KEY=""                                # sk_live_... or rk_live_... (SECRET, not pk_live_)
STRIPE_PUBLISHABLE_KEY=""                        # pk_live_... (for frontend)
STRIPE_WEBHOOK_SECRET=""                         # whsec_... from https://dashboard.stripe.com/webhooks (add later if not yet)

# --- Resend (get from https://resend.com/api-keys) ---
RESEND_API_KEY=""                                # re_...
EMAIL_FROM="WAH-LAH <noreply@wah-lah.com>"      # must match a verified domain in Resend

# --- Cerebras (get from https://cloud.cerebras.ai/) ---
CEREBRAS_API_KEY=""                              # csk-...
CEREBRAS_MODEL="qwen-3-235b-a22b-instruct-2507"

# --- Cloudflare (get from https://dash.cloudflare.com/profile/api-tokens) ---
CLOUDFLARE_API_TOKEN=""                          # cfat_...
CLOUDFLARE_ZONE_ID=""                            # found at Overview → API → Zone ID

# --- MongoDB Atlas (get from https://cloud.mongodb.com → Cluster → Connect → Drivers) ---
MONGO_URL=""                                     # mongodb+srv://user:pwd@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
DB_NAME="wahlah_prod"

# --- Admin seed account (auto-created on first boot) ---
ADMIN_EMAIL="admin@wah-lah.com"
ADMIN_PASSWORD=""                                # set a 16+ char random pass; you'll use this to log in

# --- Cryptographic secrets (pre-generated for you — do NOT regenerate or you'll log everyone out) ---
JWT_SECRET="u2tZfvWWW0gXdHhqIY1iGdXKt__3eZ_aEQWU3CXciPZ5dgxLI-XV92_KSdqBI0s9YMuVtdl6o9ojeLppqkS4NA"
PROXY_ENCRYPTION_KEY="x_VG-1ZhJ_nVeD0gtsV_aTEiyq6nouhUBlpjhMduWK0="

# --- Payment tag (already set, won't change unless you swap Cash App handles) ---
CARD_PAYMENT_TAG="\$jrs092393"

# ====================================================================
# 2. DO NOT EDIT BELOW (unless you know what you're doing)
# ====================================================================

# Sanity check — refuse to deploy with blanks
REQUIRED=("FLY_TOKEN" "STRIPE_API_KEY" "RESEND_API_KEY" "CEREBRAS_API_KEY" "CLOUDFLARE_API_TOKEN" "CLOUDFLARE_ZONE_ID" "MONGO_URL" "ADMIN_PASSWORD")
MISSING=()
for v in "${REQUIRED[@]}"; do
    [[ -z "${!v}" ]] && MISSING+=("$v")
done
if [ ${#MISSING[@]} -gt 0 ]; then
    echo "❌ STOP. Fill in these variables in deploy.sh first:"
    printf '   - %s\n' "${MISSING[@]}"
    echo ""
    echo "💡 Did you forget that STRIPE_API_KEY must start with 'sk_live_' or 'rk_live_',"
    echo "   NOT 'pk_live_'? The publishable key cannot charge cards."
    exit 1
fi
if [[ "$STRIPE_API_KEY" == pk_* ]]; then
    echo "❌ STRIPE_API_KEY starts with 'pk_'. That's the PUBLISHABLE key — it can't charge cards."
    echo "   Go to https://dashboard.stripe.com/apikeys and reveal the SECRET key (sk_live_...)."
    exit 1
fi
echo "✅ Pre-flight checks passed."

# Auth flyctl
export FLY_API_TOKEN="$FLY_TOKEN"

echo ""
echo "🚀 Setting secrets on Fly app: $FLY_APP"
flyctl secrets set \
    STRIPE_API_KEY="$STRIPE_API_KEY" \
    STRIPE_PUBLISHABLE_KEY="$STRIPE_PUBLISHABLE_KEY" \
    STRIPE_WEBHOOK_SECRET="$STRIPE_WEBHOOK_SECRET" \
    RESEND_API_KEY="$RESEND_API_KEY" \
    EMAIL_FROM="$EMAIL_FROM" \
    CUSTOM_EMAIL_FROM="$EMAIL_FROM" \
    CEREBRAS_API_KEY="$CEREBRAS_API_KEY" \
    CEREBRAS_MODEL="$CEREBRAS_MODEL" \
    CLOUDFLARE_API_TOKEN="$CLOUDFLARE_API_TOKEN" \
    CLOUDFLARE_ZONE_ID="$CLOUDFLARE_ZONE_ID" \
    MONGO_URL="$MONGO_URL" \
    DB_NAME="$DB_NAME" \
    ADMIN_EMAIL="$ADMIN_EMAIL" \
    ADMIN_PASSWORD="$ADMIN_PASSWORD" \
    JWT_SECRET="$JWT_SECRET" \
    PROXY_ENCRYPTION_KEY="$PROXY_ENCRYPTION_KEY" \
    CARD_PAYMENT_TAG="$CARD_PAYMENT_TAG" \
    FRONTEND_URL="https://wah-lah.com" \
    CORS_ORIGINS="https://wah-lah.com,https://www.wah-lah.com,https://api.wah-lah.com" \
    COOKIE_SECURE="true" \
    COOKIE_SAMESITE="lax" \
    ENFORCE_CANONICAL_HOST="true" \
    BLOCKED_STATES="WA,ID,MT,NV,LA,TN,MI,UT,AZ" \
    KYC_BASIC_THRESHOLD_USD="500" \
    KYC_ENHANCED_THRESHOLD_USD="5000" \
    CTR_THRESHOLD_USD="10000" \
    SAR_FREQ_WINDOW_HOURS="24" \
    SAR_FREQ_THRESHOLD="3" \
    CASHTAG_KEEP_RATE="0.12" \
    GIFTCARD_FEE_RATE="0.05" \
    BTC_FEE_RATE="0.10" \
    PROXY_DEFAULT_PER_TRANSFER_CAP="500" \
    PROXY_DEFAULT_DAILY_CAP="5000" \
    PROXY_COOLDOWN_FAILURES="3" \
    PROXY_LOCK_FAILURES="5" \
    PROXY_COOLDOWN_MINUTES="30" \
    -a "$FLY_APP"

echo ""
echo "🚢 Deploying app..."
flyctl deploy -a "$FLY_APP" --remote-only

echo ""
echo "🌐 Provisioning TLS certs for wah-lah.com..."
flyctl certs add wah-lah.com -a "$FLY_APP" 2>/dev/null || echo "(cert for wah-lah.com already exists)"
flyctl certs add www.wah-lah.com -a "$FLY_APP" 2>/dev/null || echo "(cert for www.wah-lah.com already exists)"
flyctl certs add api.wah-lah.com -a "$FLY_APP" 2>/dev/null || echo "(cert for api.wah-lah.com already exists)"

echo ""
echo "✅ DEPLOY COMPLETE"
echo ""
echo "Next steps (one-time):"
echo "  1. Cloudflare DNS for wah-lah.com:"
echo "     Add A and AAAA records pointing to the Fly IPs shown by:"
flyctl ips list -a "$FLY_APP" 2>/dev/null || true
echo ""
echo "  2. Stripe webhook (one-time):"
echo "     https://dashboard.stripe.com/webhooks → Add endpoint:"
echo "     URL:    https://api.wah-lah.com/api/webhook/stripe"
echo "     Events: checkout.session.completed, checkout.session.expired"
echo "     → copy the whsec_... and run:"
echo "       flyctl secrets set STRIPE_WEBHOOK_SECRET='whsec_...' -a $FLY_APP"
echo ""
echo "  3. Smoke test:"
echo "       curl https://api.wah-lah.com/api/health"
echo "     should return {\"status\":\"ok\"...} within 200ms."
echo ""
echo "🪔 You are live."
