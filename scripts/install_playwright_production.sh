#!/usr/bin/env bash
# Installs Playwright chromium + required system dependencies.
# Run ONCE on the production server before first deploy, and after major
# Playwright version bumps.
#
# Usage:
#   sudo bash scripts/install_playwright_production.sh
#
# This script is idempotent — safe to run multiple times.

set -e

echo "=========================================="
echo "Sugar City Sweeps — Playwright installer"
echo "=========================================="

# 1. Make sure pip package is present (should already be in requirements.txt)
pip show playwright > /dev/null 2>&1 || pip install playwright

# 2. Download chromium + headless_shell
echo ""
echo "→ Downloading chromium + chromium_headless_shell..."
playwright install chromium

# 3. Install native deps (fonts, libs) — requires root
echo ""
echo "→ Installing OS libraries (may prompt for sudo)..."
playwright install-deps chromium || {
  echo "⚠ install-deps failed (likely non-Ubuntu distro)."
  echo "  Manually install: libnss3 libatk-bridge2.0-0 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libgbm1 libasound2 libpango-1.0-0 libcairo2"
}

# 4. Sanity check
echo ""
echo "→ Sanity check: launching headless browser..."
python3 - <<'PY'
import asyncio
from playwright.async_api import async_playwright

async def check():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        await browser.close()
        print("  ✓ chromium launch OK")

asyncio.run(check())
PY

echo ""
echo "=========================================="
echo "✓ Playwright is ready on this server."
echo "=========================================="
