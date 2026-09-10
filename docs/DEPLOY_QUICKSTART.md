# WAH-LAH — Deploy Quickstart (Plain English)

> "Which secret goes where, and what services do I actually need?"
> This file answers exactly that. Read top-to-bottom; stop when confused; ask.

---

## 1. Do I need Firebase? Render? Vercel?

**Yes — Render + Vercel (plus Atlas + Cloudflare).** Your live stack is exactly **four** services:

| Service | What it does | Cost |
|---|---|---|
| **Render** | Runs the FastAPI backend 24/7 (Blueprints: `render.yaml`, root `Dockerfile`, port 10000). | ~$7/mo |
| **Vercel** | Serves the React SPA (`frontend/`, `vercel.json` for SPA fallback + security headers). | Free/Pro |
| **MongoDB Atlas** | Stores users, transactions, redemptions, KYC records, etc. | Free tier OK to start |
| **Cloudflare** | DNS for `wah-lah.com`, plus the `wah-lah-api-proxy` Worker that fronts Render (`api.wah-lah.com`). | Free |

Firebase shows up as a `try: import firebase_admin` line that silently falls back when Firebase isn't installed — you don't need it.

> **No Fly.io, no Cloudflare Pages, no Stripe in this project.** The entire live stack is **Render** (backend, `render.yaml` Blueprint) + **Vercel** (frontend, `frontend/vercel.json`) + **MongoDB Atlas** + **Cloudflare** (DNS). Any doc in this repo that says "Fly.io", "flyctl", or "Cloudflare Pages" is stale and describes the abandoned 2025-era stack. The backend service on Render is named **`real-wah-lah-com`**.

---

## 2. Where do deployment secrets go?

Secrets are **NOT** in your code, **NOT** in `.env`, **NOT** in git. They live as **environment variables in the Render dashboard** for the backend (Service `real-wah-lah-com` → **Environment**) and in **Vercel project settings** for the frontend.

Every key that exists in `render.yaml` with `sync: false` **must be set manually** in the Render dashboard — Render validates it exists but never stores a value for you. Keys with a literal `value:` are already set for you by the Blueprint.

Set these in Render → `real-wah-lah-com` → **Environment** → **Add Environment Variable** (one at a time; values are masked after save):

| Env var | Value source |
|---|---|
| `MONGO_URL` | Atlas connection string (see §3) |
| `MONGODB_URI` | Same Atlas connection string |
| `JWT_SECRET` | `<run: python3 -c "import secrets;print(secrets.token_urlsafe(64))">` |
| `CORS_ORIGINS` | `https://wah-lah.com,https://www.wah-lah.com` |
| `RESEND_API_KEY` | `re_...` from https://resend.com/api-keys |
| `RESEND_FROM_EMAIL` | `WAH-LAH <noreply@wah-lah.com>` |
| `ADMIN_EMAIL` | `admin@wah-lah.com` |
| `ADMIN_PASSWORD` | `<a 16+ char random password>` |
| `PUBLIC_API_URL` | `https://api.wah-lah.com` |
| `BTC_PAYOUT_XPRV` | Locally-custodied HD payout xprv (custody gateway) |
| `BLOCKCYPHER_TOKEN` | BlockCypher API token (BTC deposit confirmations) |
| `BLOCKCYPHER_STATIC_ADDRESS` | Static receive address for BTC deposits |
| `CEREBRAS_API_KEY` | `csk-...` from Cerebras |
| `PERSONA_API_KEY` / `*_TEMPLATE_ID_*` / `PERSONA_WEBHOOK_SECRET` | Persona dashboard (KYC) |
| `BTCPAY_API_URL` / `BTCPAY_API_KEY` / `BTCPAY_STORE_ID` / `BTCPAY_WEBHOOK_SECRET` | BTCPay server (only if not using `custody` gateway) |

All other backend vars (port 10000, compliance thresholds, `POOL_*` gates, cookie security, etc.) already carry real values from `render.yaml`.

**Key idea:** Render env vars are injected into the running container — the same way the local `backend/.env` works in dev. You **never** put real `sk_live_...` keys in a `.env` file you commit.

---

## 3. Which MongoDB URL goes where? (THE BIG ONE)

There are **TWO** MongoDB URLs in your life. They serve different worlds:

### A. Local dev (the one currently in `backend/.env`)
```
MONGO_URL=mongodb://localhost:27017
DB_NAME=wahlah_db
```
- Runs on **your dev machine**.
- Free, local, throwaway.
- You **do NOT use this on Render**. It would try to connect to localhost inside the Render container, find nothing, and crash.

### B. Production (the one you set as `MONGO_URL` in Render)
```
MONGO_URL=mongodb+srv://wahlah_user:REPLACE_WITH_PASSWORD@cluster0.abcde.mongodb.net/?retryWrites=true&w=majority
DB_NAME=wahlah_prod
```
- Cloud-hosted by **MongoDB Atlas** (https://cloud.mongodb.com).
- This is the one that holds real user data when live.
- Cost: free up to 512MB on the M0 tier — fine for launch; bump to M10 when you cross 5k users.

### How to get the Atlas URL (step-by-step):
1. Go to https://cloud.mongodb.com → sign up / log in.
2. **Create cluster** → choose AWS → region close to your backend (Render defaults to Oregon, so `us-west-2` is fine).
3. Cluster screen → **Connect** → **Drivers** → Python → copy the connection string. It looks like:
   `mongodb+srv://<username>:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority`
4. In Atlas → **Database Access** → add a user (e.g. `wahlah_user`) with a strong password. Replace `<username>:<password>` in the URL.
5. In Atlas → **Network Access** → "Add IP Address" → **Allow Access from Anywhere** (0.0.0.0/0). Render's egress IPs vary; this is standard practice for cloud hosts.
6. Set it as the **`MONGO_URL`** env var in the Render dashboard (and mirror it to `MONGODB_URI`).

You only do this once. After that the URL lives in the Render dashboard forever.

---

## 5. Did we enhance the bot scraping?

**Yes**, and here's what changed:

- The old `SugarSweepsBridge` (Playwright-based DOM scraping) used to crash startup with `Email field not found` whenever credentials were missing, and it failed in production because Vercel blocks datacenter IPs (Render, AWS, all of them).
- We built a second, faster bridge — **`HttpHubBridge`** in `backend/services/hub_http_bridge.py`. It bypasses the browser entirely and calls `https://api.sugarsweeps.com` directly. No DOM, no anti-bot challenge, ~10× faster login.
- On boot the backend now **skips the Playwright bridge entirely if `SUGAR_SWEEPS_USERNAME` and `SUGAR_SWEEPS_PASSWORD` aren't set**. That's why startup is quiet now.
- When you set those two env vars in Render, the bridge wakes up and does login + balance sync at startup.

**To turn it on in production:**

Set `SUGAR_SWEEPS_USERNAME` and `SUGAR_SWEEPS_PASSWORD` as env vars in the Render dashboard (Service `real-wah-lah-com` → Environment). No redeploy needed — Render restarts the service with the new env vars.

(If you also want the HTTP fast-path enabled per-distributor, that's done from the **Admin → Distributor Pool** screen in the UI — add the hub credential, set ping/transfer caps, hit Test.)

---

## 6. The exact order to launch

1. **ROTATE EVERY KEY YOU PASTED IN CHAT** (Resend, Cerebras, Cloudflare, admin passwords). They're compromised. Do it before exposing this to real traffic.
2. **Create MongoDB Atlas cluster** → copy the `mongodb+srv://...` URL.
4. **Verify your domain in Resend** → https://resend.com/domains → add `wah-lah.com` → add the TXT/MX records to Cloudflare DNS. Without this, emails will be marked spam.
5. **Set the `sync: false` env vars** in Render (Service `real-wah-lah-com` → Environment) — full list in §2, with `MONGO_URL` first.
6. **Push to `main`** — Render (autoDeploy: true) builds the Docker image and rolls out the backend; Vercel builds and deploys the SPA. Watch both dashboards for green deploys.
7. **Domains/TLS**: nothing to configure — Vercel serves `wah-lah.com`/`www` certs automatically, Render serves `api.wah-lah.com` (fronted by the Cloudflare `wah-lah-api-proxy` Worker), all TLS auto-managed.
8. **Smoke test on the live URL**: register a player → AMOE claim → small deposit ($5) → verify gift card redemption flow → check `/api/health` returns 200, then `https://api.wah-lah.com/api/health` via the Worker.

---

## 7. What lives where (final cheat sheet)

| Thing | Lives in |
|---|---|
| Source code | This repo / GitHub |
| Dev/preview env vars | `backend/.env` (gitignored) |
| Production env vars | Render Dashboard → Environment (Service `real-wah-lah-com`) / Vercel project settings |
| User data, transactions, KYC records | MongoDB Atlas |
| Static frontend assets | Vercel (CDN) — `frontend/dist` |
| DNS (wah-lah.com) | Cloudflare |
| TLS certs | Auto-managed by Vercel/Render/Cloudflare |
| Cron jobs (gift card auto-fulfill, ledger snapshots) | In-process APScheduler on Render (already wired) |
| LLM (Boss Genie chat) | Cerebras API (paid per token; very cheap) |
| Transactional email | Resend |
| Player payments (Cash App / Chime) | Tag `$CARD_PAYMENT_TAG` (set in env; never commit the real tag) — manual reconcile in Admin → Transactions |
| Player payouts (gift cards) | 8 brand integrations + manual admin queue |
| Player payouts (BTC) | Lightning/on-chain, gated by KYC tiers in compliance service |

Live stack: Render (backend) + Vercel (frontend) + MongoDB Atlas + Cloudflare (DNS + proxy Worker).

---

## 8. Once live: how does money come in?

1. **Free credits funnel** → player signs up, claims 100 AMOE credits/24h (legal sweepstakes compliance).
2. **First deposit nudge** → Player Genie concierge (if enabled) suggests upgrade after first big win.
4. **Cash App / Chime deposit** → player sends to `$CARD_PAYMENT_TAG` (set in env; never commit the real tag) with their game tag in the note → admin manually credits via Admin → Transactions → "Mark Paid."
5. **Crypto deposit** → BTC/Lightning address shown on payment screen → manual reconcile.
6. **Redemption** → player can cash out as gift card (instant, ≤$500) or BTC (KYC required, ≤$5k basic / >$5k enhanced).

The whole compliance + payout chain is built. The only thing standing between you and live revenue is **production secrets in the Render dashboard + the MongoDB Atlas URL**.

Welcome to launch.
