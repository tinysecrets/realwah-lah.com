# Verification Report — secured replacement tree

**Source:** `realwah-lah.com` @ `8f26e47` (20 MB incl. `.git`)
**Result:** this tree (11 MB, no `.git`, no `memory/`) — intended as the new source of truth.
**Date:** 2026-09-10 · **Method:** full-tree audit → patch → compile → unit tests → live smoke tests.

## What was removed (the leak)

- Deleted `memory/` entirely — it contained a live scout `ADMIN_TOKEN`/`LEADS_TOKEN`,
  operator Gmail, Cloudflare zone ID, KV namespace ID, worker URLs, and Resend IDs.
- Scrubbed the Cash App/Chime payment tag from `docs/` (4 files) → `$CARD_PAYMENT_TAG` placeholder.
- Scrubbed the operator Gmail default from `backend/.env.example` and `services/on_duty.py`.
- Scrubbed the hardcoded tag assertion from `backend/tests/test_iter7_postemergent.py`
  → env-driven `EXPECTED_CARD_PAYMENT_TAG` with skip-if-unset.
- Pruned deleted paths from `.secrets.baseline`.
- Final grep for the burned payment tag, operator mailbox, leaked token, and zone ID (excl. `.github`, lockfiles): **clean**.
  The only remaining infra identifier is the scout-force KV namespace ID in
  `scout-force/wrangler.toml`, which is required to deploy and is not a credential.

## What was fixed (by file)

| # | File | Fix |
|---|---|---|
| 1 | `backend/server.py` | Trusted-proxy gating (`TRUST_PROXY_HEADERS`) for rate-limit + login keys; CORS locked (no `*`, explicit methods/headers); security-headers + canonical-host middleware; admin access audit log; JWT secret ≥32 enforced; `jti` + denylist + logout revocation + refresh rotation + `revoke_all_user_tokens`; bcrypt 72-byte cap; **2FA enforced on primary login** (was bypassable); brute-force key uses real client IP; samesite validation; revoked-tokens TTL index; stale Fly.io refs removed |
| 2 | `backend/services/compliance/geoblock.py` | **Fail-closed rewrite**: lookup errors deny (`GEOBLOCK_FAIL_CLOSED`, default true); safe default blocked states when env unset; localhost bypass dev-only; proxy-header trust gated |
| 3 | `backend/routes/payment.py` | Fixed **broken async gates** (`check_geoblock`/`check_btc_address` were never awaited, wrong arity/semantics — redemptions 500'd): now awaited, correct semantics, geoblock events recorded, 403 region / 451 OFAC / 503 fail-closed |
| 4 | `backend/services/btc_processor.py` | Webhook verify fails closed with no token; price oracle tries Coinbase→Kraken, then explicit `BTC_FALLBACK_USD` or **raises** (no silent $60k); confirmations default 2, floor 1 |
| 5 | `backend/services/btc_payout.py` | Fixed bech32-rejecting address check (`is_plausible_btc_address`); single-address funding correctness (index 0 only — multi-index spends could never sign); `BTC_PAYOUT_MAX_SAT` per-tx ceiling |
| 6 | `backend/routes/scout.py` | Timing-safe token compare; 200-lead batch cap (DB-flood guard) |
| 7 | `backend/routes/extensions.py` | **Password-reset token leak closed**: `dev_token` only on explicit non-prod `APP_ENV` (unset no longer leaks — Render never set it); 72-byte password caps |
| 8 | `backend/services/on_duty.py` | Hardcoded operator email removed; unset `ALERT_EMAILS` warns and runs without email |
| 9 | `backend/routes/compliance.py` | KYC upload path traversal closed (doc_type allowlist, alnum ext, sanitized user id, generic MIME error); **`btc_payouts_enabled` kill switch enforced** before auto-send (was bypassed) |
| 10 | `scout-force/src/worker.js` | `/run` fails closed without `ADMIN_TOKEN` (was literal `"scout-force"`); HTTPS-only webhook; dead fake-mongo helpers removed |
| 11 | `wah-lah-api-proxy/src/worker.js` | `/api/*` path allowlist, method allowlist, generic 502 (no exception text), security headers, hop-by-hop strip, TLS-only target |
| 12 | `render.yaml` | `APP_ENV=production`, `TRUST_PROXY_HEADERS=true`, rate-limit vars, confirmations 2, fallback `sync:false`, `BTC_PAYOUT_MAX_SAT`, `GEOBLOCK_FAIL_CLOSED`, `SCOUT_LEADS_TOKEN` (was missing), `ALERT_EMAILS` |
| 13 | `.env.example`, `backend/.env.example` | All new vars documented; PII defaults removed |
| 14 | `.github/workflows/main.yml` | New `secret-scan` job (PII patterns + `detect-secrets` vs baseline) |
| 15 | `.github/workflows/codeql.yml` | Bumped `v3` → `v4` actions |
| 16 | `package.json` | Fixed stale Cloudflare-Pages description → Vercel + Worker proxy |
| 17 | **New:** `SECURITY.md` | Disclosure policy, secret inventory + rotation runbook, xprv replacement procedure, prod checklist |
| 18 | **New:** `docs/OPERATIONS.md` | Sanitized daily/weekly/monthly operator routine + incident playbooks (replaces `memory/`) |
| 19 | **New:** `REPLACE_RUNBOOK.md` | Rotate → replace → purge cutover plan with rollback |

Untouched by design: `frontend/` (no secrets found — only `REACT_APP_BACKEND_URL`
fallbacks), `genie-sidekick/` (fully env-driven, no embedded secrets),
`Dockerfile` (already non-root + healthcheck), `scripts/set_admin.py` (already safe).

## Evidence (all run against THIS tree)

- `python -m compileall -q backend` → **clean**
- Self-contained suites (`hub_http_bridge`, `self_distributor_unit`, `legal_router`,
  `pool_pull`, `deposit_reconciler`, `pool_resync`, `competition`) → **95 passed, 1 skipped**
- `test_btc_payout.py` (covers new validator, cap path, index-0 signing) → **9 passed**
- Full collection → **277 tests, 0 collection errors**
- `node --check` on both workers → **clean** · `render.yaml` YAML parse → **clean**
- Live `TestClient` smoke: `/api/health` 200 + `nosniff`/`SAMEORIGIN`/HSTS headers;
  short `JWT_SECRET` rejected; `CORS_ORIGINS=*` refused at boot; evil `Host` → 421
  on API paths with `/api/health` still reachable.

## Distributor-upgrade test evidence

- New `backend/tests/test_distributor_ops.py` (self-contained, runs in CI):
  **17 passed** — reconcile fee-split/NET-credit/ledger/duplicate-receipt/whale/
  platform-validation, users safe-projection + audited adjust, unified feed +
  stats, card-info enabled/disabled, retry/cancel/overdue/confirm-on-manual-rail,
  platform-denomination converters + send-instruction + platform totals.
- Full self-contained suite: **139 passed, 181 skipped** (skips are
  `RUN_BACKEND_TESTS`-gated) · in-process money suites with the flag:
  **86 passed** (settlement ×14, distributor ×32, pool-pull, btc payout/processor).
  Collection: **320 tests, 0 errors**.
- Live app boot: **144 routes** incl. all 8 distributor endpoints, the 2 public
  proof endpoints, and the Ledger/Concierge loop
  (`/api/user/transactions`, `/api/user/support/tickets/{id}`,
  `/api/admin/analytics/support-tickets/{id}/respond`).
- `RUN_BACKEND_TESTS=1` files that phone the old Emergent preview hosts
  (`test_extensions`, `test_wahlah_backend`, …) fail with remote 404s — they
  test the retired deploy, not this tree; pre-existing and environmental.

## Before you cut over (non-negotiable)

1. **Rotate first** — the old scout token in git history is burned. Follow
   `REPLACE_RUNBOOK.md` Phase 1 (scout tokens → JWT → admin password + 2FA → rest).
2. History still holds the secret until you purge (BFG) or start clean history —
   the runbook covers both options. Purging alone does NOT un-leak: rotate anyway.
3. Set the new Render vars (`APP_ENV`, `SCOUT_LEADS_TOKEN`, `ALERT_EMAILS`,
   `BTC_PAYOUT_MAX_SAT`, …) before the first deploy from this tree.
4. Fund/verify the hot wallet at `m/0'/0/0` only — other indexes no longer spend.

## Known gaps — what does NOT work (pre-existing, unchanged by this baseline)

These endpoints are called by the frontend (or docs/tests) but have **no
backend route in either tree** — they 404 today and 404 after cutover:

**Operator money flow — ✅ BUILT (distributor upgrade):**
- `POST /api/admin/cashtag/reconcile` now exists: receipt-idempotent, fee split
  via the revenue engine, credits NET, records the keep, and routes into the
  same manual-queue / auto-pool dispatch as BTC deposits. The legacy
  `POST /api/admin/middleware/inject` remains absent (superseded — do not build).

**Admin tabs — ✅ core built, remainder still 404:**
- BUILT: `GET/PATCH /api/admin/users` (audited credit adjustments),
  `GET /api/admin/transactions` (unified money feed),
  `GET /api/admin/stats` (morning glance).
- STILL MISSING: `POST /api/admin/payments/manual` (use reconcile instead),
  `/api/admin/middleware/*` (legacy, skip), `/api/ext/admin/*` (analytics
  detail, promo CRUD, support respond/close — promo/referral are unbuilt
  products), `/api/ext/pool/admin/ping-all` (per-proxy `/ping` works).

**Player features — ✅ card-info built, rest still 404:**
- BUILT: `GET /api/payment/card-info` (tag + live fee disclosure).
- STILL MISSING: `GET /api/user/transactions`, `POST /api/withdraw/request`
  (covered today by `/api/giftcard/*`), `/api/ext/promo/*`, `/api/ext/referral/*`.

**Queue lifecycle — ✅ upgraded:**
- `POST /api/ext/distributor/queue/{id}/retry` (failed → awaiting),
  `.../cancel` (terminal), overdue tracking (`DISTRIBUTOR_OVERDUE_HOURS`,
  default 4), and today's distributor P&L in `GET /api/ext/distributor/summary`.
  Confirm/failed now complete deposits on BOTH rails (BTC + manual).

**Landing-page trust (payout proof) — ✅ built:**
- New public router `routes/public_stats.py` (no auth, masked names only):
  `GET /api/public/stats` (live players / paid-out USD / platforms / payouts)
  and `GET /api/public/payouts/recent` (newest-first completed payouts).
  Only `approved` BTC redemptions + `fulfilled` gift cards count; pending/held
  rows never appear; 60s in-memory cache; 7 self-contained tests green.
- Landing page: hardcoded stats counters replaced with live figures,
  "Standing Ovations" payout section + scrolling winners ticker (polls every
  60s), honest empty state ("The stage is set…"), new lead FAQ "Will I
  actually get paid?", "six portals" wording fixed. Sections fail silent
  (hide) if the API is unreachable — never placeholder figures.
- Frontend `vite build` clean; vitest 13/13 green (`LandingProof` ×3,
  `Concierge` Q/A cycle ×3, `AdminDailyOps` ×3, existing ×4).

**Player Ledger — ✅ fixed at the source (was a missing endpoint, not a UI bug):**
- Root cause: `GET /api/user/transactions` never existed, so the Ledger tab
  404'd for every player. Fixed by building the endpoint on a new single
  source of truth, `services/money_feed.py`, which the admin feed now also
  delegates to (identical output, verified by the unchanged distributor suite).
- Feed now covers 7 rails (gift cards added), matches legacy ObjectId and
  string user ids, strips `btc_address`/`actor` for players, and ships a
  deposited/received/pending summary. 12 self-contained tests; fixtures mirror
  the real reconcile/redemption/giftcard/adjustment writers.
- Ledger tab rewritten: summary header, per-rail filters, status pills.
- Post-deploy check (needs prod data): for a known user, diff
  `GET /api/user/transactions` against `GET /api/admin/transactions` filtered
  to that user — same function, must match exactly.

**Concierge — ✅ actually answers (Genie backend was orphaned, now wired):**
- Root cause: the player Genie backend (`POST /api/genie/chat`, Cerebras →
  OpenAI-compatible fallback, escalation tickets) was complete with ZERO UI
  calling it. Concierge tab rebuilt: Genie chat (sessions, history, quick
  asks, escalation banner, offline fallback) + ticket threads showing
  operator replies. No Emergent/legacy path anywhere in the chain (verified).
- Loop closed operator-side: `POST .../support-tickets/{id}/respond` plus
  owner-scoped ticket detail; admin ticket list now includes threads.
- 6 backend Q/A tests (mocked LLM: ask/reply/history/escalation/503) + 3
  frontend cycle tests. Prod needs `CEREBRAS_API_KEY` (or fallback key) or
  chat 503s into the ticket fallback by design.

**Admin panel — ✅ rebuilt from "unadmin" to operational:**
- Fixed: Users/Transactions tabs crashed (`.map` on response envelopes);
  Dashboard read nonexistent fields (all zeros → real morning-glance +
  queue deep-links); "Add Credits" posted to a dead endpoint (now audited
  PATCH adjustments); user save used PUT 404 (now PATCH, extended with
  role + game-account fields, tested).
- New Daily Ops tab: CashApp/Chime reconcile form (fee split preview,
  whale-comp toggle), distributor queue (mode switch, send instructions,
  confirm/fail/retry/cancel), tickets (threads, reply, close).
- Frontend: 13/13 vitest (3 Concierge + 3 Daily Ops + 7 existing), build clean.

**Platform denomination — ✅ fixed (was a 100x overpay bug):**
- Internal Game Credits (100 = $1) used to flow raw into hub-bound amounts, so a
  $25 deposit (2,200 credits net) would have sent $2,200 instead of $22.
- One conversion point now: `credits_to_platform_amount()` in
  `config/currency_config.py`. Tasks carry both units and print
  `send_instruction` ("Send $22.00 to 'user' on Platform"); the auto-transfer
  dispatcher converts once at the boundary; ledger/playthrough stay in credits.
- Pull reclaim (`pool_pull`) resolves targets on BOTH rails (was BTC-only) and
  converts to platform dollars before dispatch.

**Needs a small frontend tweak after cutover:**
- Primary login form posts `{email, password}` only, so 2FA-enabled accounts
  get `401 "2FA code required"` on the main form and must use the 2FA toggle
  (`/ext/auth/login-2fa`, which keeps working). Pass `totp_code` through the
  primary form to make it seamless.

**Safe defaults requiring operator action (by design):**
- BTC auto-send off until `btc_payouts_enabled` flag + hot wallet at `m/0'/0/0`
  + `BTC_PAYOUT_MAX_SAT` tuned; 2-confirmation deposits; oracle-halt with no
  fallback set; scout ingest until tokens rotated on both sides; on-duty email
  until `ALERT_EMAILS` set; geoblock denies while ipapi.co is unreachable.
