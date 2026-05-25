# PRD — WAH-LAH (wah-lah.com)

## Original problem statement
> "Get everything in order and running — https://fly.io/dashboard"
> Codebase: https://github.com/tinysecrets/Wahlah.com.git
> User notes:
> - App name: `wah-lah`
> - Domain (purchased): `wah-lah.com`
> - "Your job is to not put no emergent in it but just be of service and go through it; fix whatever is and watch on fly. Simplify or organize. Do not take away things that are needed or that will break."

## What this app is
WAH-LAH (a.k.a. Sugar City Sweeps) is a sweepstakes / fish-game lobby platform:
- One login → seven game platforms (Fire Kirin, Juwa, Panda Master, Orion Stars, Game Vault, etc.)
- Deposit via Stripe card, Cash App ($WahLah), Chime, or crypto
- Game Credits + Sugar Tokens dual-currency model (legal sweepstakes compliance)
- AMOE (Alternate Method of Entry): 100 FREE credits / 24h, no purchase necessary
- BTC redemption with full compliance chain (geoblock → OFAC → tiered KYC → admin hold)
- Sugar Sweeps Master-Tank Playwright bridge for automated P2P credit transfers
- Admin panel: users, transactions, payouts, master control, nerve center, distributor pool

## Architecture (target)
```
wah-lah.com  ──►  Cloudflare Pages    (React SPA)
api.wah-lah.com  ──►  Fly.io (app=wah-lah, region=iad, 1GB RAM)  ──►  MongoDB Atlas M0
```
In this preview pod everything runs locally: FastAPI on :8001, React on :3000, MongoDB local.

## Tech stack
- Backend: FastAPI 0.110, Motor 3.3, MongoDB, bcrypt+JWT cookies, Stripe (`emergentintegrations`), Playwright (production only), Sentry, Resend, Cerebras LLM (Boss Genie)
- Frontend: React 19 + CRA + craco, Radix UI, Tailwind, Recharts, react-router 7
- Deploy: Dockerfile (multi-stage), `fly.toml`, optional `render.yaml`

## What's been implemented (2026-05-25 — restore session)
- Re-cloned `tinysecrets/Wahlah.com` from GitHub into a fresh Emergent pod where `/app` only had the default scaffold.
- Preserved Emergent's `/app/.git`, `/app/.emergent`, `/app/backend/.env` (MONGO_URL+DB_NAME), `/app/frontend/.env` (REACT_APP_BACKEND_URL).
- Regenerated full backend `.env` with dev-safe values: `JWT_SECRET`, `STRIPE_API_KEY=sk_test_emergent` (pod test key), Fernet `PROXY_ENCRYPTION_KEY`, `EMERGENT_LLM_KEY` (Universal Key), `BLOCKED_STATES`, KYC/AML thresholds, cookie security flags, `CORS_ORIGINS=*`.
- Installed missing Python deps: `python-dotenv`, `python-multipart`, `resend`, `playwright`, `pyotp`, `qrcode`, `email-validator`, `dnspython`. Installed Playwright Chromium and symlinked `/root/.cache/ms-playwright → /pw-browsers` so SugarSweepsBridge launches headed cleanly.
- Installed missing frontend dep `dompurify` (used by BossMode.jsx). Frontend now compiles clean.
- Admin auto-seed verified: `admin@wahlah.com` / `WahLahAdmin2026$` → `POST /api/auth/login` returns 200 + JWT.
- Verified dashboard renders end-to-end after login: 7 game cards (Fire Kirin, Juwa, Juwa 2, Ultra Panda, Panda Master, Orion Stars, Game Vault), AMOE 100-credit/24h banner, Play/Deposit/Redeem/Ledger/Settings/Concierge tabs, animated Genie mascot, gold-velvet Arabian Nights theme.
- All four supervisor services green: backend (8001), frontend (3000), mongodb, nginx-code-proxy.

## What's been implemented (2026-05-22 — previous session)
- Migrated `tinysecrets/Wahlah.com` repo into `/app`, preserving `.emergent/`, `.git/`, and protected `.env` keys.
- Generated dev `.env` files (admin creds, JWT secret, Fernet key, placeholder Stripe key) so the app boots cleanly in the preview pod.
- Fixed a startup-blocking bug in `backend/server.py`: `os.environ.get("SENTRY_DSN")` was called before `import os`. Moved `import os` to the top and gated `sentry_sdk.init()` on `SENTRY_DSN` being set.
- Installed missing Python deps that weren't in the base venv: `sentry-sdk[fastapi]`, `playwright` (browser intentionally not installed in pod), `pyotp`, `qrcode`, `resend`, `cerebras-cloud-sdk`, `litellm`.
- Ran `yarn install` for frontend (40s, ~1500 packages).
- Rewrote `fly.toml` — merged duplicate `app=` and `[http_service]` blocks; final app name = `wah-lah`, region = `iad`, healthcheck at `/api/health`.
- Removed Emergent badge & `assets.emergent.sh/scripts/emergent-main.js` from `frontend/public/index.html` (the user-facing branding); kept dev-only `@emergentbase/visual-edits` package and `emergentintegrations` Stripe library because both are infrastructure, not branding.
- Sanitized `/api/admin/p2p-transfer` 503 response so Playwright install path no longer leaks.
- Added `COOKIE_SECURE` + `COOKIE_SAMESITE` env-driven cookie security. Dev = `false` (HTTP local), production must set `COOKIE_SECURE=true` (HTTPS on Fly).
- Auto-seeded admin user verified: `admin@wah-lah.com` / `WahLah2026!`.
- Testing agent (iteration_6): 24/24 backend tests PASS, 0 critical issues.

## Personas
- **End user** (21+): registers, gets auto-generated game username (`sugar{xx}{nnn}` / `Abc123`), claims 100 daily free credits, deposits via card/Cash App/Chime/crypto, plays games, redeems BTC.
- **Admin** (`admin@wah-lah.com`): manages users, approves/rejects payouts, monitors master control + nerve center + distributor pool, manual P2P injection.
- **Compliance officer**: payout-queue review, KYC tier approvals, OFAC/AML event audits.

## Service status (this pod)
| Service | Status | Notes |
|---|---|---|
| Backend (FastAPI on :8001) | RUNNING | `/api/health` → 200 |
| Frontend (React on :3000) | RUNNING | Renders WAH-LAH landing page |
| MongoDB (local 27017) | RUNNING | DB: `wahlah_dev` |
| Sugar Sweeps Playwright bot | OFFLINE (by design) | Chromium not installed in pod — production-only on Fly |
| Stripe checkout | placeholder key | Replace with `sk_live_…` via `flyctl secrets set` |
| Resend email | empty key | Welcome email logs warning, doesn't fail |

## Prioritized backlog
### P0 — Pre-launch blockers (user action)
1. Set real production secrets on Fly: `flyctl secrets set MONGO_URL=… STRIPE_API_KEY=… RESEND_API_KEY=… CEREBRAS_API_KEY=…` (full list in `docs/deployment/DEPLOY.md` Step 3).
2. Create MongoDB Atlas M0 cluster and point `MONGO_URL` at it.
3. Run `flyctl deploy` from local machine, then `flyctl certs add api.wah-lah.com`.
4. Wire DNS at Cloudflare (`@`, `www` → CF Pages; `api` → `wah-lah.fly.dev` DNS-only).
5. Set `CORS_ORIGINS=https://wah-lah.com,https://www.wah-lah.com` (currently `*` for dev).
6. Set `COOKIE_SECURE=true` for production (now env-driven; dev defaults to `false`).

### P1 — Nice to have
- Split `server.py` (1856 lines) into modules: `auth.py`, `games.py`, `currency.py`, `amoe.py`, `admin.py`, `payments.py`, `p2p.py`. Maintainability win.
- Honor `X-Forwarded-For` for brute-force lockout so one shared egress IP can't lock out a whole user pool.
- Add Pydantic ObjectId validator for `user_id` / `platform_id` body fields to return clean 422 vs internal bson errors.

### P2 — Future
- Real Stripe live keys, Resend live key, Cerebras live key.
- End-to-end test of Sugar Sweeps Playwright transfer with $1 Fire Kirin injection (needs Chromium installed on Fly).
- Withdrawal/redemption flow E2E (currently manual admin approval).
- Referral program, VIP tiers, analytics dashboard.

## Local dev quick-reference
```bash
# Backend
sudo supervisorctl restart backend
curl https://fly-ops.preview.emergentagent.com/api/health

# Frontend
sudo supervisorctl restart frontend
# Visit https://fly-ops.preview.emergentagent.com

# Admin login
curl -X POST https://fly-ops.preview.emergentagent.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@wah-lah.com","password":"WahLah2026!"}'
```

## Deployment quick-reference (fly.io)
See `docs/deployment/DEPLOY.md` for the full guide. TL;DR:
```bash
flyctl auth login
flyctl secrets set MONGO_URL=… JWT_SECRET=… STRIPE_API_KEY=… [+18 more]
flyctl deploy
flyctl certs add api.wah-lah.com
```

## Test credentials
See `/app/memory/test_credentials.md`.
