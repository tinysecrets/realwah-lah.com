#!/usr/bin/env bash
# Quick smoke test for wah-lah.com production wiring.
set -euo pipefail

DOMAIN="${DOMAIN:-wah-lah.com}"
API="${API:-api.wah-lah.com}"

c_ok()   { printf "\033[0;32m✓\033[0m %s\n" "$*"; }
c_fail() { printf "\033[0;31m✗\033[0m %s\n" "$*"; }
c_info() { printf "\033[0;34m→\033[0m %s\n" "$*"; }

check_url() {
  local label="$1"
  local url="$2"
  local expect="${3:-200}"

  c_info "Checking $label: $url"
  code="$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 "$url" || echo "000")"
  if [[ "$code" == "$expect" ]]; then
    c_ok "$label returned $code"
  else
    c_fail "$label returned $code (expected $expect)"
    return 1
  fi
}

echo "wah-lah.com domain verification"
echo "================================"

FAIL=0
check_url "Frontend root" "https://${DOMAIN}/" || FAIL=1
check_url "SPA route /boss" "https://${DOMAIN}/boss" || FAIL=1
check_url "API health" "https://${API}/api/health" || FAIL=1

echo
if [[ $FAIL -eq 0 ]]; then
  c_ok "All checks passed — wah-lah.com is wired correctly."
else
  c_fail "Some checks failed. See docs/deployment/CLOUDFLARE_PAGES.md"
  exit 1
fi
