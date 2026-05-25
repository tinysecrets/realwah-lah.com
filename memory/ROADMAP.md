# Roadmap

Prioritized backlog for WAH-LAH. P0 = blocks launch, P1 = launch-week, P2 = post-launch polish.

---

## P0 — Before live traffic

### Credentials / environment
- **Stripe**: replace `sk_test_placeholder_replace_with_real_key` in `/app/backend/.env` with a real test or live key. Without this, end-to-end deposit → pool payout will 500 at the Stripe call.
- **Resend API key**: set `RESEND_API_KEY` so password-reset and welcome emails actually send (currently returns dev-link in response body for local testing).
- **Playwright chromium on production server**: `playwright install chromium` + system deps. Preview container is set up; prod is not.

### Validation / operator tasks
- **Run "Test Transfer" once per distributor proxy** via admin UI → copy the diagnostic trace for each. The first real-credential attempt will reveal any transfer-form selectors that need refinement in `HUB_CONFIGS`. Fix iteratively.
- **Confirm coverage for every game**: open the Routing Matrix in admin → confirm no red rows. Games currently only served by 1 proxy (`juwa2`, `noble` via Sugar Sweeps only) need either a 2nd hub with coverage OR explicit "deposit disabled" messaging in the UI.

### Code / architecture
- **Apply pool gate to `/api/redemption/request` BTC payout path** — currently redemption only runs JIT registration gate, not a pool-based credit pull. Decide: do we need to pull credits FROM the game back TO the proxy before issuing BTC? If yes, implement `execute_pool_pull()` mirror of `execute_pool_transfer()`.

---

## P1 — Launch week

### Payments & payouts
- **BTCPay (or CoinGate) integration** for real BTC payouts. Currently `/redemption/request` creates a record but no BTC actually moves.
- **Crypto payout gateway wiring** — use `middleware/payout_engine.py` framework; configure gateway URL + store ID.
- **KYC flow** for redemptions ≥ $500. Needs policy + ID-verification provider choice (Persona, Veriff, Onfido).

### Pool operational safety ⭐ my top recommendation
- **"Pilot Launch Checklist" widget** at top of the pool tab. Auto-checks 4 things before you open real traffic:
  1. Every game has ≥ 2 active proxies (single-point-of-failure check).
  2. Every proxy has pinged green in the last 24h.
  3. No proxy is at > 80% of its daily cap.
  4. `STRIPE_API_KEY` is not the placeholder value.
  
  When all 4 green → display "READY FOR LIVE TRAFFIC" banner. Any red → actionable fix list. Turns operational readiness into a single glance.
- **Pool auto-scaling alert** — ping on Telegram/email when `daily_capacity_remaining` drops below 20%. Pair with a one-click "Duplicate proxy config" button in admin so you can add a pool member in ~60 seconds at 3am on a Saturday.
- **Nightly balance resync cron** — scheduled job pings each proxy's dashboard to read current balance; updates `balance_cached`. Feeds the "Auto-disable proxy whose balance < $X" feature.

### Emails / UX
- **Resend email templates**: promo-redeemed, referral-rewarded, ticket-response, weekly VIP summary.
- **2FA recovery codes** — generate 10 on 2FA enable; let user re-download once.
- **Automatic VIP-tier deposit bonus** applied at checkout (config exists; needs UI + checkout-side logic).

### Admin tooling
- **"Platform connectivity" health check** — button in admin that pings every proxy in parallel and reports a colored grid. Already have `/ping` per proxy; just needs a "Ping all" aggregator.
- **Admin-editable `HUB_CONFIGS`** — move selectors from Python code into DB so ops can tweak selectors without redeploying when a site's DOM changes. Huge maintainability win.
- **Auto-refresh Routing Matrix every 30s** — live capacity drain view.

---

## P2 — Post-launch polish

### Code health
- **Refactor `App.js`** (~1900 lines) into `GameCard.jsx`, `Dashboard.jsx`, `DepositMethods.jsx`, `AuthPages.jsx`, etc. Makes the codebase maintainable and speeds up future edits.
- **Remove legacy `middleware/sugar_sweeps_bridge.py`** — superseded by `GenericHubBridge`. Keep it in git history but delete from active imports.
- **Test suite for `GenericHubBridge`** — add unit tests using Playwright against a local static HTML fixture page so we can CI the selector-matching logic.

### Analytics & retention
- **Mixpanel or PostHog** analytics integration.
- **Real-time credits sync** with game platforms (webhook or polling).
- **Live chat in support** (Intercom-style or custom WebSocket).
- **Mobile app** (React Native wrap of existing routes).

### Gamification
- **First-deposit bonus + daily streak reward** overlay on game cards (typically +20-30% conversion on sweepstakes).
- **Tournaments / leaderboards** per game platform.
- **VIP badges on leaderboards** — tie into existing VIP tier engine.

### Legal / compliance
- **Terms-of-service update flow** — force re-acknowledgment on policy changes.
- **Responsible gaming enhancements** — deposit limits per-user, self-exclusion period, time-played warnings.

---

## Backlog (ideas not yet promoted)
- Admin can download a per-proxy CSV of today's transfer volume.
- Proxy "warm-up" mode: new proxy starts with $100/tx & $500/day for the first 7 days, then ramps to full caps automatically.
- Routing Matrix export to PDF for compliance review.
- IP rotation per proxy (residential proxy pool, $) — only if platforms start blocking by IP.
