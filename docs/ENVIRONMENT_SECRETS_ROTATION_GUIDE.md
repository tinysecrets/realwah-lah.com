# 🔐 Environment Variables & Secrets Rotation Guide
## Render Deployment (Docker, port 10000)

**Last Updated:** 2026-09-07  
**Scope:** Production-grade secret management for `tinysecrets/realwah-lah.com`  
**Backend:** Render web service `real-wah-lah-com` (`render.yaml` Blueprint, runtime docker, `PORT=10000`)  
**Frontend:** Vercel (`frontend/`, `vercel.json` → `dist`)  
**Note:** This project has **no Fly.io, no flyctl, and no Stripe**. Older versions of this doc were written against the abandoned Fly stack — ignore any `flyctl` text.

---

## 📋 PART 1: Code Review — How Environment Variables Are Used

### 1.1 Backend Configuration Entry Point
**File:** `backend/server.py` (lines 1–6)

```python
from dotenv import load_dotenv
from pathlib import Path
import os

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')
```

**What happens:**
- On app startup, `dotenv` loads `.env` file from `backend/` directory
- In **local dev**, this reads `backend/.env` (git-ignored, contains dev secrets)
- In **production (Render)**, `.env` does NOT exist; values come from **Render environment variables** (Service → `real-wah-lah-com` → **Environment**), injected into the container at runtime

### 1.2 Critical Environment Variables Referenced in Code

#### **MongoDB Connection** (lines 60–62)
```python
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]
```
- **`MONGO_URL`** (required): MongoDB Atlas connection string
  - Format: `mongodb+srv://USERNAME:PASSWORD@cluster.mongodb.net/?retryWrites=true&w=majority`
- **`DB_NAME`** (required): Database name (default: `wahlah_prod`; already set via `render.yaml`)

#### **JWT Authentication** (lines 87–88)
```python
def get_jwt_secret() -> str:
    return os.environ["JWT_SECRET"]
```
- **`JWT_SECRET`** (required): 64-byte random string for signing JWT tokens
- Used by: Auth endpoints, token validation
- ⚠️ **Changing this logs out all active users**

#### **Cookie Security** (lines 84–85)
```python
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
COOKIE_SAMESITE = os.environ.get("COOKIE_SAMESITE", "lax").lower()
```
- **`COOKIE_SECURE`**: Set to `"true"` on HTTPS (production; already `"true"` in `render.yaml`)
- **`COOKIE_SAMESITE`**: Set to `"lax"` or `"strict"` for CSRF protection

#### **Email Service** (line 760)
```python
from services.email_service import email_service
email_service.send_welcome_email(email, user_name)
```
- **`RESEND_API_KEY`** (required): API key from https://resend.com
- **`EMAIL_FROM`** (optional): Sender email (default: onboarding@resend.dev)
- **`CUSTOM_EMAIL_FROM`** (optional): Custom sender after domain verified

#### **LLM (Boss Genie)** (seen in code imports)
- **`CEREBRAS_API_KEY`** (required): API key from https://cloud.cerebras.ai
- **`CEREBRAS_MODEL`** (optional): Model name (default in `render.yaml`: qwen-3-235b-a22b-instruct-2507)

#### **Cloudflare** (worker / DNS tooling)
- **`CLOUDFLARE_API_TOKEN`** (where used): API token with Zone:DNS:Edit permission
- **`CLOUDFLARE_ZONE_ID`** (where used): Zone ID for wah-lah.com

#### **Admin Account**
```python
admin_email = os.environ.get("ADMIN_EMAIL", "admin@wah-lah.com").lower().strip()
admin_password = os.environ.get("ADMIN_PASSWORD")
if not admin_password:
    raise RuntimeError("ADMIN_PASSWORD env var is not set")
```
- **`ADMIN_EMAIL`** (required): Email for admin login
- **`ADMIN_PASSWORD`** (required): Admin password (16+ chars recommended)

#### **CORS & Domain Configuration**
```python
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:3000")
canonical = os.environ.get("CANONICAL_HOST", "wah-lah.com").lower()
```
- **`CORS_ORIGINS`**: Comma-separated allowed origins (e.g., `https://wah-lah.com,https://www.wah-lah.com`)
- **`CANONICAL_HOST`**: Primary domain for redirects (default: wah-lah.com)
- **`ENFORCE_CANONICAL_HOST`**: Set to `"true"` in production

#### **Compliance & Revenue Settings** (render.yaml)
```bash
BLOCKED_STATES='WA,ID,MT,NV,LA,TN,MI,UT,AZ'
KYC_BASIC_THRESHOLD_USD='500'
KYC_ENHANCED_THRESHOLD_USD='5000'
CTR_THRESHOLD_USD='10000'
SAR_FREQ_WINDOW_HOURS='24'
SAR_FREQ_THRESHOLD='3'
```

#### **Sugar Sweeps Bot Integration**
```python
if os.environ.get("SUGAR_SWEEPS_USERNAME") and os.environ.get("SUGAR_SWEEPS_PASSWORD"):
    sugar_sweeps_bridge = SugarSweepsBridge()
```
- **`SUGAR_SWEEPS_USERNAME`** (optional): Distributor account email
- **`SUGAR_SWEEPS_PASSWORD`** — RETIRED with the legacy middleware bridge (removed from this tree). Leave unset; nothing reads it anymore.

#### **Genie Sidekick** (genie-sidekick/backend/server.py)
- Separate helper app in this repo. Uses the same `JWT_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `MONGO_URL`; separate default `DB_NAME` (`genie_sidekick`). **Do not deploy it on Render unless you actually run it** — it is not part of the live `real-wah-lah-com` service.

---

## 📦 PART 2: The Complete Render Env Var Set

Render validates every key listed in `render.yaml`. Two kinds:
- **`value:` set** → already provisioned by the Blueprint (port, compliance thresholds, `POOL_*` gates, cookie security, etc.) — you don't touch these.
- **`sync: false`** → **you must manually add them** in Dashboard → `real-wah-lah-com` → **Environment**.

### 2.1 The `sync: false` checklist (set each in Render)

| Env var | Value source |
|---|---|
| `MONGO_URL` | Atlas connection string (Part 3) |
| `MONGODB_URI` | Same Atlas connection string |
| `JWT_SECRET` | `python3 -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `CORS_ORIGINS` | `https://wah-lah.com,https://www.wah-lah.com` |
| `RESEND_API_KEY` | https://resend.com/api-keys (`re_...`) |
| `RESEND_FROM_EMAIL` | `WAH-LAH <noreply@wah-lah.com>` |
| `ADMIN_EMAIL` | admin login email |
| `ADMIN_PASSWORD` | 16+ char random password (password manager) |
| `PUBLIC_API_URL` | `https://api.wah-lah.com` |
| `BTC_PAYOUT_XPRV` | Locally-custodied HD payout xprv (custody gateway) |
| `BLOCKCYPHER_TOKEN` | BlockCypher API token (BTC deposits) |
| `BLOCKCYPHER_STATIC_ADDRESS` | BTC receive address |
| `CEREBRAS_API_KEY` | Cerebras `csk-...` |
| `PERSONA_API_KEY` / `PERSONA_TEMPLATE_ID_BASIC` / `PERSONA_TEMPLATE_ID_ENHANCED` / `PERSONA_WEBHOOK_SECRET` | Persona dashboard |
| `BTCPAY_API_URL` / `BTCPAY_API_KEY` / `BTCPAY_STORE_ID` / `BTCPAY_WEBHOOK_SECRET` | BTCPay server (only if not using `BTC_GATEWAY_TYPE=custody`) |
| `SENTRY_DSN` | Sentry (optional logging) |

### 2.2 Optional env vars (add only when enabling the feature)

```bash
SUGAR_SWEEPS_USERNAME / SUGAR_SWEEPS_PASSWORD   # wake the Playwright hub bridge
ALERT_EMAILS                                    # comma-separated; alerts for on-duty watchdog,
                                                # deposit reconciler, personalization events
```

> **How to apply**: Render → `real-wah-lah-com` → **Environment** → **Add Environment Variable**. Saving restarts the service with the new value automatically — no separate deploy step.

> **No `deploy.sh` exists in this repo.** The old `flyctl secrets set` scripts from earlier docs are gone.

---

## 🔄 PART 3: Safe Secret Rotation Checklist

### ⚠️ **CRITICAL: DO NOT SKIP STEP 0**

### **Step 0: Rotate Keys BEFORE Launch** (EMERGENCY)

Keys that have appeared in documentation or chat **MUST be rotated immediately**:
- ❌ `RESEND_API_KEY`, ❌ `CEREBRAS_API_KEY`, ❌ `CLOUDFLARE_API_TOKEN`, admin passwords

**Action:**
1. Go to each service dashboard
2. **Revoke the old key**
3. **Create a new key**
4. Update the value in Render → Environment (and anywhere else it's used)

### **Step 1: Preflight** (5 min)

1. Open https://dashboard.render.com → Service `real-wah-lah-com` → **Events**. Confirm the last deploy was successful.
2. Confirm Health: `curl https://api.wah-lah.com/api/health` → `{"status":"ok",...}`.
3. (Optional) Install the Render CLI for scripted env updates:
   ```bash
   # macOS: brew install render
   # Linux: curl -fsSL https://raw.githubusercontent.com/render-oss/cli/main/bin/install.sh | sh
   ```

### **Step 2: Generate Crypto Secrets** (2 min)

```bash
# Generate new JWT_SECRET (64 bytes)
python3 -c "import secrets; print(secrets.token_urlsafe(64))"

# Generate new PROXY_ENCRYPTION_KEY (Fernet) — for encrypted distributor credentials
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Save these for the next step. Changing `JWT_SECRET` logs every user out — schedule it deliberately.

### **Step 3: Snapshot Current Values** (2 min)

The Render dashboard shows each env var's masked value but does **not** export plaintext. Before rotating, note which vars you're changing and keep the new values in your password manager. Rotation of `MONGO_URL`/`JWT_SECRET` should be treated as a maintenance window.

### **Step 4: Apply New Values in Render**

Render → `real-wah-lah-com` → **Environment** → edit the var → **Save**. Render restarts the service.

### **Step 5: Verify** (3 min)

```bash
curl https://api.wah-lah.com/api/health            # → 200 ok
curl -X POST https://api.wah-lah.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"REDACTED_EMAIL","password":"YOUR_NEW_PASSWORD"}'
# Expected: JWT cookie set (or 401 if password wrong)
```
Then open https://wah-lah.com, log in as admin, and watch Render → Logs for a clean boot (no `MONGO_URL`/`JWT_SECRET` errors).

### **Step 6: Monitor for 1 Hour**

- Render → Logs: no "MongoDB connection refused", no "Invalid JWT_SECRET"
- Render → Events: health checks passing
- Health endpoint stays green for all 60 minutes

### **Step 7: Cleanup** (1 min)

```bash
# Verify no secrets leaked to git
git grep -n -E 'sk_live_|re_[A-Za-z0-9]{20}' -- . || echo "clean"
# Backend .env is gitignored — confirm: git check-ignore backend/.env
```

---

## 🚨 PART 4: Rollback Procedure (If Anything Breaks)

Backend deploys are **image-based and immutable** on Render — you do not SSH or restart containers manually.

### **Rollback to a previous good deploy** (2 min)
Render → `real-wah-lah-com` → **Deploys** → find the last green deploy → **⋯** → **Rollback**. Render re-deploys that image instantly; env vars stay as currently set. Use this when a code push introduced a crash.

### **Recover from a bad env var** (1 min)
Env vars don't break the build — they break the boot. Render → **Environment** → fix/remove the bad value → **Save** (auto-restart). Check **Logs** for the startup traceback for exactly which var is missing/invalid.

### **Emergency disable**
Render → `real-wah-lah-com` → **Settings** → **Suspend Service**. Suspending stops billing for a free/starter service and halts traffic immediately (health returns 503). Resume the same way. *(Do not "delete" — deletion is permanent and also removes the env var list.)*

---

## 📋 PART 5: Secret Rotation Schedule (Best Practices)

| Secret | Rotation Frequency | Why | How |
|--------|-------------------|-----|-----|
| `JWT_SECRET` | Never (unless compromised) | Rotates all users out | Render → Environment → update + Save |
| `ADMIN_PASSWORD` | Quarterly | Staff turnover, good hygiene | Render → Environment + notify team |
| `CEREBRAS_API_KEY` | Annually | Usage limits, prevent leaks | https://cloud.cerebras.ai settings → Render |
| `CLOUDFLARE_API_TOKEN` | Quarterly | High-impact (DNS control) | Create new token, update where used |
| `MONGO_URL` password | Annually | Database security | MongoDB Atlas → Database Access → rotate user → Render |
| `RESEND_API_KEY` | Annually | Email service access | https://resend.com/api-keys → Render |
| `SUGAR_SWEEPS_USERNAME` / `PASSWORD` | Quarterly | Distributor account rotation | Distributor sends new creds → Render |

---

## 🖥️ Render Configuration Notes

### **render.yaml** (repo root)
```yaml
services:
  - type: web
    name: real-wah-lah-com
    runtime: docker
    dockerfilePath: ./Dockerfile
    dockerContext: .
    healthCheckPath: /api/health
    autoDeploy: true
    envVars:
      - key: PORT
        value: "10000"
      # ...
```
- ✅ FastAPI listens on **port 10000** (`PORT` env var)
- ✅ Health check **`/api/health`** gates the deploy
- ✅ **`autoDeploy: true`** — every push to `main` triggers a backend build + rollout

### **Rollout model**
- Single web instance on Render (Docker). All background work (on-duty watchdog, deposit reconciler, pool resync worker) runs inside this one process via FastAPI lifespan.
- TLS for `api.wah-lah.com` is terminated by the Cloudflare `wah-lah-api-proxy` Worker in front of Render; Render itself also serves HTTPS at its `.onrender.com` hostname.

---

## ✅ Final Verification Checklist

Before calling deployment complete:

- [ ] All API keys rotated (Resend, Cerebras, Cloudflare, admin)
- [ ] All `sync: false` env vars present in Render Environment (Part 2.1)
- [ ] Latest deploy green in Render → Events; `autoDeploy` working on a test push
- [ ] Vercel frontend deploy green; `https://wah-lah.com` loads the SPA
- [ ] Health: `curl https://api.wah-lah.com/api/health` returns 200
- [ ] Admin login works: `/api/auth/login` accepts the password
- [ ] Logs show no MongoDB or JWT errors
- [ ] No secrets in browser console (check DevTools)
- [ ] `git grep -E 'sk_live_|re_[A-Za-z0-9]{20}'` returns nothing

---

## 🎯 TL;DR — Quick Start

```
1. Rotate your keys at each service dashboard (CRITICAL)
2. Render → real-wah-lah-com → Environment → add the sync:false vars (Part 2.1)
3. Set MONGO_URL + MONGODB_URI to the Atlas connection string
4. Push to main → Render builds + health-checks + rolls out; Vercel ships the SPA
5. Verify: curl https://api.wah-lah.com/api/health
6. Smoke test: visit https://wah-lah.com, log in, make a small deposit
```

**Deployment complete! 🚀**

---

**Questions?** Render → `real-wah-lah-com` → **Logs** shows detailed error messages. If the service won't start, the build/boot output names the failing env var.