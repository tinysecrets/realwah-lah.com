#!/usr/bin/env bash
# Get Cloudflare Zone ID for wah-lah.com using the API token

set -euo pipefail

c_blue()  { printf "\033[0;34m%s\033[0m\n" "$*"; }
c_green() { printf "\033[0;32m%s\033[0m\n" "$*"; }
c_red()   { printf "\033[0;31m%s\033[0m\n" "$*"; }

CLOUDFLARE_API_TOKEN="${1:-}"
if [[ -z "$CLOUDFLARE_API_TOKEN" ]]; then
    c_red "Usage: ./get-cloudflare-zone.sh <cfut_token>"
    exit 1
fi

c_blue "🔍 Fetching Zone ID for wah-lah.com..."

RESPONSE=$(curl -s -X GET "https://api.cloudflare.com/client/v4/zones?name=wah-lah.com" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  -H "Content-Type: application/json")

# Check for errors
if echo "$RESPONSE" | grep -q '"success":false'; then
    c_red "❌ API error. Check your token or domain name."
    echo "$RESPONSE" | grep -o '"errors":\[.*\]' || echo "$RESPONSE"
    exit 1
fi

# Extract Zone ID
ZONE_ID=$(echo "$RESPONSE" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)

if [[ -z "$ZONE_ID" ]]; then
    c_red "❌ Zone not found. Is wah-lah.com added to your Cloudflare account?"
    exit 1
fi

c_green "✓ Zone ID found:"
echo ""
echo "  CLOUDFLARE_ZONE_ID=\"$ZONE_ID\""
echo ""
c_blue "👉 Add this line to deploy.sh"
