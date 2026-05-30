#!/usr/bin/env bash
# WAH-LAH DEPLOYMENT STATUS CHECK
# Run this to verify all required secrets are filled in

set -euo pipefail

SCRIPT="./deploy.sh"

c_green() { printf "\033[0;32m%s\033[0m\n" "$*"; }
c_red()   { printf "\033[0;31m%s\033[0m\n" "$*"; }
c_yel()   { printf "\033[0;33m%s\033[0m\n" "$*"; }
c_blue()  { printf "\033[0;34m%s\033[0m\n" "$*"; }

echo ""
c_blue "═══════════════════════════════════════════════════════════════"
c_blue "        WAH-LAH DEPLOYMENT READINESS CHECK"
c_blue "═══════════════════════════════════════════════════════════════"
echo ""

# Extract values from deploy.sh
FLY_TOKEN=$(grep "^FLY_TOKEN=" "$SCRIPT" | cut -d"'" -f2 | head -c 20)
STRIPE_API_KEY=$(grep "^STRIPE_API_KEY=" "$SCRIPT" | cut -d'"' -f2)
STRIPE_PUB=$(grep "^STRIPE_PUBLISHABLE_KEY=" "$SCRIPT" | cut -d'"' -f2 | head -c 15)
RESEND_KEY=$(grep "^RESEND_API_KEY=" "$SCRIPT" | cut -d'"' -f2 | head -c 15)
CEREBRAS_KEY=$(grep "^CEREBRAS_API_KEY=" "$SCRIPT" | cut -d'"' -f2)
CF_TOKEN=$(grep "^CLOUDFLARE_API_TOKEN=" "$SCRIPT" | cut -d'"' -f2 | head -c 20)
CF_ZONE=$(grep "^CLOUDFLARE_ZONE_ID=" "$SCRIPT" | cut -d'"' -f2)
MONGO_URL=$(grep "^MONGO_URL=" "$SCRIPT" | cut -d'"' -f2 | grep -o "mongodb.*" | head -c 30)
ADMIN_PWD=$(grep "^ADMIN_PASSWORD=" "$SCRIPT" | cut -d'"' -f2 | head -c 10)

# Check each required variable
check_var() {
    local name="$1"
    local value="$2"
    local label="$3"
    
    if [[ -z "$value" ]]; then
        c_red "  ✗ $label"
        echo "    → Set in deploy.sh"
        return 1
    else
        c_green "  ✓ $label"
        if [[ ${#value} -lt 20 ]]; then
            echo "    Value: $value"
        else
            echo "    Value: ${value}..."
        fi
        return 0
    fi
}

echo "REQUIRED VARIABLES:"
READY=1
check_var "STRIPE_API_KEY" "$STRIPE_API_KEY" "Stripe API Key (sk_live_...)" || READY=0
check_var "STRIPE_PUB" "$STRIPE_PUB" "Stripe Publishable Key (pk_live_...)" || READY=0
check_var "RESEND" "$RESEND_KEY" "Resend API Key (re_...)" || READY=0
check_var "CEREBRAS" "$CEREBRAS_KEY" "Cerebras API Key (csk_...)" || READY=0
check_var "CF_TOKEN" "$CF_TOKEN" "Cloudflare API Token (cfut_...)" || READY=0
check_var "CF_ZONE" "$CF_ZONE" "Cloudflare Zone ID" || READY=0

echo ""
echo "ALREADY SET:"
check_var "MONGO" "$MONGO_URL" "MongoDB Atlas URL" || true
check_var "ADMIN_PWD" "$ADMIN_PWD" "Admin Password" || true
check_var "FLY_TOKEN" "$FLY_TOKEN" "Fly.io Token (FlyV1...)" || true

echo ""
if [[ $READY -eq 1 ]]; then
    c_green "═══════════════════════════════════════════════════════════════"
    c_green " ✓ ALL REQUIRED VARIABLES SET — READY TO DEPLOY"
    c_green "═══════════════════════════════════════════════════════════════"
    echo ""
    c_blue " Next steps:"
    echo "   1. chmod +x deploy.sh"
    echo "   2. ./deploy.sh"
    echo ""
    exit 0
else
    c_red "═══════════════════════════════════════════════════════════════"
    c_red " ✗ MISSING REQUIRED VARIABLES"
    c_red "═══════════════════════════════════════════════════════════════"
    echo ""
    exit 1
fi
