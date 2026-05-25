# WAH-LAH — Deploy Quickstart (Plain English)

> "Which secret goes where, and what services do I actually need?"
> This file answers exactly that. Read top-to-bottom; stop when confused; ask.

---

## 1. Do I need Firebase? Render? Vercel?

**NO.** None of them. Your stack is exactly **three** services:

| Service | What it does | Cost |
|---|---|---|
| **Fly.io** | Runs the FastAPI backend + serves the React frontend, 24/7. | ~$5–15/mo |
| **MongoDB Atlas** | Stores users, transactions, redemptions, KYC records, etc. | Free tier OK to start |
| **Cloudflare** | DNS for `wah-lah.com`, plus the proxy/SSL in front of Fly. | Free |

That's it. Render shows up in the repo (`render.yaml`) but it's an **alternate** path — you can ignore it. Firebase shows up as a `try: import firebase_admin` line that silently falls back when Firebase isn't installed — you don't need it.

---

## 2. Where do Fly secrets go?

Secrets on Fly are **NOT** in your code, **NOT** in `.env`, **NOT** in git. They live in Fly's encrypted storage. You set them once with the `flyctl` CLI on your laptop:

```bash
# Step 1: install flyctl (one-time)
curl -L https://fly.io/install.sh | sh

# Step 2: log in (uses the Fly token)
flyctl auth token <PASTE YOUR FRESH FLY TOKEN HERE>

# Step 3: set ALL secrets in one command
flyctl secrets set \
  STRIPE_API_KEY='sk_live_REPLACE_ME_WITH_REAL_SECRET_KEY' \
  STRIPE_WEBHOOK_SECRET='whsec_FROM_STRIPE_DASHBOARD' \
  STRIPE_PUBLISHABLE_KEY='pk_live_51TLgNtBLQEBXCqI3vViN2KRKxvMJRu654TDPCjROdHlxBfhmI1YvXTH0XdPRwousU7azj8Y3W2X0E8rATJus4A0i00HRiOBhuF' \
  RESEND_API_KEY='re_XoCukbnW_9HrggHNkNxxk5sCPTQ6JKmFU' \
  CEREBRAS_API_KEY='csk-h49pehx9vcxjef2hy25c6xt49c5dkwfw8wed4kk4fhvderw8' \
  CEREBRAS_MODEL='qwen-3-235b-a22b-instruct-2507' \
  CLOUDFLARE_API_TOKEN='cfat_jlsRkUqN1CTsFns8bnTOVFZcox6Bn9KN6wej3fz2093a3e66' \
  CLOUDFLARE_ZONE_ID='31b2071a68a4d40bbe8636cda2b9d7b2' \
  MONGO_URL='mongodb+srv://USER:PASS@cluster0.xxxx.mongodb.net/?retryWrites=true&w=majority' \
  DB_NAME='wahlah_prod' \
  JWT_SECRET='<run: python3 -c "import secrets;print(secrets.token_urlsafe(64))">' \
  PROXY_ENCRYPTION_KEY='<run: python3 -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())">' \
  ADMIN_EMAIL='admin@wah-lah.com' \
  ADMIN_PASSWORD='<a 16+ char random password>' \
  CARD_PAYMENT_TAG='$jrs092393' \
  EMAIL_FROM='WAH-LAH <onboarding@resend.dev>' \
  CUSTOM_EMAIL_FROM='WAH-LAH <noreply@wah-lah.com>' \
  FRONTEND_URL='https://wah-lah.com' \
  CORS_ORIGINS='https://wah-lah.com,https://www.wah-lah.com' \
  COOKIE_SECURE='true' \
  COOKIE_SAMESITE='lax' \
  ENFORCE_CANONICAL_HOST='true' \
  BLOCKED_STATES='WA,ID,MT,NV,LA,TN,MI,UT,AZ' \
  KYC_BASIC_THRESHOLD_USD='500' \
  KYC_ENHANCED_THRESHOLD_USD='5000' \
  CTR_THRESHOLD_USD='10000' \
  -a wahlah    # ← the app name in fly.toml

# Step 4: confirm secrets are set
flyctl secrets list -a wahlah

# Step 5: deploy
flyctl deploy -a wahlah
```

**Key idea:** Fly secrets are injected as environment variables into the running container — the same way the local `.env` file works in dev. You **never** put real `sk_live_...` keys in a `.env` file you commit.

---

## 3. Which MongoDB URL goes where? (THE BIG ONE)

There are **TWO** MongoDB URLs in your life. They serve different worlds:

### A. Local dev (the one currently in `backend/.env`)
```
MONGO_URL=mongodb://localhost:27017
DB_NAME=wahlah_db
```
- Runs on **your dev machine** (or the Emergent preview pod).
- Free, local, throwaway.
- You **do NOT use this on Fly**. It would try to connect to localhost inside the Fly container, find nothing, and crash.

### B. Production (the one you put in `flyctl secrets set MONGO_URL=...`)
```
MONGO_URL=mongodb+srv://wahlah_user:Sup3rL0ngPassword@cluster0.abcde.mongodb.net/?retryWrites=true&w=majority
DB_NAME=wahlah_prod
```
- Cloud-hosted by **MongoDB Atlas** (https://cloud.mongodb.com).
- This is the one that holds real user data when live.
- Cost: free up to 512MB on the M0 tier — fine for launch; bump to M10 when you cross 5k users.

### How to get the Atlas URL (step-by-step):
1. Go to https://cloud.mongodb.com → sign up / log in.
2. **Create cluster** → choose AWS → region closest to your Fly region (Fly defaults to IAD = Virginia, so pick AWS us-east-1).
3. Cluster screen → **Connect** → **Drivers** → Python → copy the connection string. It looks like:
   `mongodb+srv://<username>:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority`
4. In Atlas → **Database Access** → add a user (e.g. `wahlah_user`) with a strong password. Replace `<username>:<password>` in the URL.
5. In Atlas → **Network Access** → "Add IP Address" → **Allow Access from Anywhere** (0.0.0.0/0). Fly's container IP rotates; this is normal.
6. Paste the final URL into `flyctl secrets set MONGO_URL='...'`.

You only do this once. After that the URL lives in Fly secrets forever.

---

## 4. Stripe secret vs publishable — what you sent vs what backend needs

| Key shape | Where it lives | Can it charge cards? |
|---|---|---|
| `pk_live_…` (PUBLISHABLE) — what you sent | Frontend (safe to ship in JS) | NO. It can only render the Stripe payment widget. |
| `sk_live_…` (SECRET) — what backend needs | Fly secrets (NEVER frontend) | YES. Charges cards, creates checkout sessions, signs webhooks. |
| `rk_live_…` (RESTRICTED SECRET) | Fly secrets (same use as sk_live) | YES, but only for the scopes you grant. Safer for production. |
| `whsec_…` (WEBHOOK SECRET) | Fly secrets | Used to verify Stripe is the one calling your webhook. |

**Action**: Go to https://dashboard.stripe.com/apikeys → **reveal & copy the SECRET key** (not the publishable). Then set `flyctl secrets set STRIPE_API_KEY='sk_live_...'`.

Even better: create a **restricted key** (rk_live_) with scopes only for Checkout + PaymentIntents — that way if it leaks, only Checkout can be drained, not your whole account.

---

## 5. Did we enhance the bot scraping?

**Yes**, and here's what changed:

- The old `SugarSweepsBridge` (Playwright-based DOM scraping) used to crash startup with `Email field not found` whenever credentials were missing, and it failed in production because Vercel blocks datacenter IPs (Fly, AWS, all of them).
- We built a second, faster bridge — **`HttpHubBridge`** in `backend/services/hub_http_bridge.py`. It bypasses the browser entirely and calls `https://api.sugarsweeps.com` directly. No DOM, no anti-bot challenge, ~10× faster login.
- On boot the backend now **skips the Playwright bridge entirely if `SUGAR_SWEEPS_USERNAME` and `SUGAR_SWEEPS_PASSWORD` aren't set**. That's why startup is quiet now.
- When you set those two env vars in Fly secrets, the bridge wakes up and does login + balance sync at startup.

**To turn it on in production:**

```bash
flyctl secrets set \
  SUGAR_SWEEPS_USERNAME='jrs092393@gmail.com' \
  SUGAR_SWEEPS_PASSWORD='<the distributor account password>' \
  -a wahlah
```

(If you also want the HTTP fast-path enabled per-distributor, that's done from the **Admin → Distributor Pool** screen in the UI — add the hub credential, set ping/transfer caps, hit Test.)

---

## 6. The exact order to launch

1. **ROTATE EVERY KEY YOU PASTED IN CHAT** (Stripe, Resend, Cerebras, Cloudflare, Fly). They're compromised. Do it before deploying.
2. **Create MongoDB Atlas cluster** → copy the `mongodb+srv://...` URL.
3. **Get the real Stripe SECRET key** (`sk_live_...`) from Stripe dashboard.
4. **Verify your domain in Resend** → https://resend.com/domains → add `wah-lah.com` → add the TXT/MX records to Cloudflare DNS. Without this, emails will be marked spam.
5. **Run `flyctl secrets set` with the full command block from §2.**
6. **`flyctl deploy -a wahlah`** — Dockerfile is clean (no Emergent PyPI mirror needed).
7. **Add the apex domain**: `flyctl certs add wah-lah.com -a wahlah` and `flyctl certs add www.wah-lah.com -a wahlah`. Then in Cloudflare DNS, add A/AAAA records pointing to Fly's IPs.
8. **Smoke test on the live URL**: register a player → AMOE claim → small Stripe deposit ($5) → verify gift card redemption flow → check `/api/health` returns 200.
9. **Stripe webhook**: go to https://dashboard.stripe.com/webhooks → add endpoint `https://api.wah-lah.com/api/webhook/stripe` → events `checkout.session.completed`, `checkout.session.expired` → copy the `whsec_...` signing secret → `flyctl secrets set STRIPE_WEBHOOK_SECRET=whsec_...`.

---

## 7. What lives where (final cheat sheet)

| Thing | Lives in |
|---|---|
| Source code | This repo / GitHub |
| Dev/preview env vars | `backend/.env` (gitignored) |
| Production env vars | Fly secrets (`flyctl secrets set`) |
| User data, transactions, KYC records | MongoDB Atlas |
| Static frontend assets | Served by FastAPI inside the Fly container (single-domain setup) |
| DNS (wah-lah.com) | Cloudflare |
| TLS certs | Fly auto-issues via Let's Encrypt when you `flyctl certs add` |
| Cron jobs (gift card auto-fulfill, ledger snapshots) | Fly Machines or in-process APScheduler (already wired) |
| LLM (Boss Genie chat) | Cerebras API (paid per token; very cheap) |
| Transactional email | Resend |
| Player payments (cards) | Stripe |
| Player payments (Cash App / Chime) | Tag `$jrs092393` — manual reconcile in Admin → Transactions |
| Player payouts (gift cards) | 8 brand integrations + manual admin queue |
| Player payouts (BTC) | Lightning/on-chain, gated by KYC tiers in compliance service |

You don't need Render. You don't need Firebase. You don't need Vercel. Three services.

---

## 8. Once live: how does money come in?

1. **Free credits funnel** → player signs up, claims 100 AMOE credits/24h (legal sweepstakes compliance).
2. **First deposit nudge** → Player Genie concierge (if enabled) suggests upgrade after first big win.
3. **Stripe deposit** → card → instant credits to game account via JIT platform registration.
4. **Cash App / Chime deposit** → player sends to `$jrs092393` with their game tag in the note → admin manually credits via Admin → Transactions → "Mark Paid."
5. **Crypto deposit** → BTC/Lightning address shown on payment screen → manual reconcile.
6. **Redemption** → player can cash out as gift card (instant, ≤$500) or BTC (KYC required, ≤$5k basic / >$5k enhanced).

The whole compliance + payout chain is built. The only thing standing between you and live revenue is **production secrets in Fly + the Stripe SECRET key + MongoDB Atlas URL**.

Welcome to launch.
