# 🔐 Environment Variables & Secrets Rotation Guide
## Fly.io Deployment on Port 8001

**Last Updated:** 2026-06-01  
**Scope:** Production-grade secret management for `tinysecrets/realwah-lah.com`  
**Target Port:** 8001 (FastAPI backend via Fly.io)

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
- In **Fly.io production**, `.env` does NOT exist; secrets come from `flyctl secrets set` (encrypted storage)

---

### 1.2 Critical Environment Variables Referenced in Code

#### **MongoDB Connection** (lines 60–62)
```python
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]
```
- **`MONGO_URL`** (required): MongoDB Atlas connection string
  - Format: `mongodb+srv://USERNAME:PASSWORD@cluster.mongodb.net/?retryWrites=true&w=majority`
- **`DB_NAME`** (required): Database name (default: `wahlah_prod`)

---

#### **JWT Authentication** (lines 87–88)
```python
def get_jwt_secret() -> str:
    return os.environ["JWT_SECRET"]
```
- **`JWT_SECRET`** (required): 64-byte random string for signing JWT tokens
- Used by: Auth endpoints, token validation
- ⚠️ **Changing this logs out all active users**

---

#### **Cookie Security** (lines 84–85)
```python
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
COOKIE_SAMESITE = os.environ.get("COOKIE_SAMESITE", "lax").lower()
```
- **`COOKIE_SECURE`**: Set to `"true"` on HTTPS (production)
- **`COOKIE_SAMESITE`**: Set to `"lax"` or `"strict"` for CSRF protection

---

#### **Payment Processing** (lines 760, 810, 855)
```python
stripe_checkout = StripeCheckout(api_key=os.environ["STRIPE_API_KEY"], ...)
```
- **`STRIPE_API_KEY`** (required): Secret key (sk_live_... or sk_test_...)
- **`STRIPE_WEBHOOK_SECRET`** (required): whsec_... for webhook validation
- **`STRIPE_PUBLISHABLE_KEY`** (frontend env var): pk_live_...

---

#### **Email Service** (line 760)
```python
from services.email_service import email_service
email_service.send_welcome_email(email, user_name)
```
- **`RESEND_API_KEY`** (required): API key from https://resend.com
- **`EMAIL_FROM`** (optional): Sender email (default: onboarding@resend.dev)
- **`CUSTOM_EMAIL_FROM`** (optional): Custom sender after domain verified

---

#### **LLM (Boss Genie)** (seen in code imports)
- **`CEREBRAS_API_KEY`** (required): API key from https://cloud.cerebras.ai
- **`CEREBRAS_MODEL`** (optional): Model name (default: qwen-3-235b-a22b-instruct-2507)

---

#### **Cloudflare DNS Management** (compliance/geoblock services)
- **`CLOUDFLARE_API_TOKEN`** (required): API token with Zone:DNS:Edit permission
- **`CLOUDFLARE_ZONE_ID`** (required): Zone ID for wah-lah.com

---

#### **Admin Account** (lines 1896–1897, 1908–1915)
```python
admin_email = os.environ.get("ADMIN_EMAIL", "admin@wah-lah.com").lower().strip()
admin_password = os.environ.get("ADMIN_PASSWORD", "SugarCity2024!")
```
- **`ADMIN_EMAIL`** (required): Email for admin login
- **`ADMIN_PASSWORD`** (required): Admin password (16+ chars recommended)

---

#### **CORS & Domain Configuration** (lines 1757, 1785)
```python
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:3000")
canonical = os.environ.get("CANONICAL_HOST", "wah-lah.com").lower()
```
- **`CORS_ORIGINS`**: Comma-separated allowed origins (e.g., `https://wah-lah.com,https://www.wah-lah.com`)
- **`CANONICAL_HOST`**: Primary domain for redirects (default: wah-lah.com)
- **`ENFORCE_CANONICAL_HOST`**: Set to `"true"` in production

---

#### **Compliance & Revenue Settings** (lines 1896+ and deploy.sh)
```bash
BLOCKED_STATES='WA,ID,MT,NV,LA,TN,MI,UT,AZ'
KYC_BASIC_THRESHOLD_USD='500'
KYC_ENHANCED_THRESHOLD_USD='5000'
CTR_THRESHOLD_USD='10000'
SAR_FREQ_WINDOW_HOURS='24'
SAR_FREQ_THRESHOLD='3'
```
- **`BLOCKED_STATES`**: Comma-separated state abbreviations to block (sweepstakes compliance)
- **`KYC_BASIC_THRESHOLD_USD`**: Threshold for basic KYC (default: 500)
- **`KYC_ENHANCED_THRESHOLD_USD`**: Threshold for enhanced KYC (default: 5000)
- **`CTR_THRESHOLD_USD`**: Currency Transaction Report threshold (default: 10000)
- **`SAR_FREQ_THRESHOLD`**: Suspicious Activity Report frequency (default: 3 per 24h)

---

#### **Sugar Sweeps Bot Integration** (lines 2042–2055)
```python
if os.environ.get("SUGAR_SWEEPS_USERNAME") and os.environ.get("SUGAR_SWEEPS_PASSWORD"):
    sugar_sweeps_bridge = SugarSweepsBridge()
```
- **`SUGAR_SWEEPS_USERNAME`** (optional): Distributor account email
- **`SUGAR_SWEEPS_PASSWORD`** (optional): Distributor account password
- Leave blank to skip bot initialization on startup (safe)

---

#### **Genie Sidekick** (genie-sidekick/backend/server.py, lines 36–52)
```python
JWT_SECRET = os.environ.get("JWT_SECRET", "")
ADMIN_EMAIL = (os.environ.get("ADMIN_EMAIL") or "").strip()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD") or ""
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "genie_sidekick")
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")]
```
- Same JWT_SECRET, ADMIN_EMAIL, ADMIN_PASSWORD, MONGO_URL as main backend
- Separate DB_NAME: `genie_sidekick` (default)

---

## 📦 PART 2: Complete `flyctl secrets set` Command

### 2.1 Full Command (Copy & Paste Ready)

Save this to a file called `deploy-secrets.sh` and fill in your values:

```bash
#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# FILL IN ALL VALUES BELOW BEFORE RUNNING
# ============================================================================

# --- Stripe (https://dashboard.stripe.com/apikeys) ---
STRIPE_API_KEY="sk_live_REPLACE_WITH_YOUR_SECRET_KEY"  # SECRET key (not pk_)
STRIPE_WEBHOOK_SECRET="whsec_REPLACE_WITH_YOUR_WEBHOOK_SECRET"  # From webhook endpoint settings

# --- Resend (https://resend.com/api-keys) ---
RESEND_API_KEY="re_REPLACE_WITH_YOUR_API_KEY"

# --- Cerebras (https://cloud.cerebras.ai) ---
CEREBRAS_API_KEY="csk-REPLACE_WITH_YOUR_API_KEY"
CEREBRAS_MODEL="qwen-3-235b-a22b-instruct-2507"

# --- Cloudflare (https://dash.cloudflare.com → My Profile → API Tokens) ---
CLOUDFLARE_API_TOKEN="cfat_REPLACE_WITH_YOUR_API_TOKEN"
CLOUDFLARE_ZONE_ID="REPLACE_WITH_ZONE_ID"

# --- MongoDB Atlas (https://cloud.mongodb.com) ---
MONGO_URL="mongodb+srv://wahlah_app:REPLACE_WITH_PASSWORD@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority"
DB_NAME="wahlah_prod"

# --- Admin Account ---
ADMIN_EMAIL="Jrs092393@gmail.com"
ADMIN_PASSWORD="REPLACE_WITH_STRONG_PASSWORD_16_CHARS_MINIMUM"

# --- Email Configuration ---
EMAIL_FROM="WAH-LAH <onboarding@resend.dev>"
CUSTOM_EMAIL_FROM="WAH-LAH <noreply@wah-lah.com>"

# --- Payment Tags ---
CARD_PAYMENT_TAG="$jrs092393"

# --- (OPTIONAL) Sugar Sweeps Bot Creds ---
SUGAR_SWEEPS_USERNAME=""  # Leave blank to skip bot
SUGAR_SWEEPS_PASSWORD=""

# ============================================================================
# DON'T EDIT BELOW (unless you know what you're doing)
# ============================================================================

APP_NAME="wah-lah"

# Validate required vars
REQUIRED=(
    "STRIPE_API_KEY" "STRIPE_WEBHOOK_SECRET" "RESEND_API_KEY"
    "CEREBRAS_API_KEY" "CLOUDFLARE_API_TOKEN" "CLOUDFLARE_ZONE_ID"
    "MONGO_URL" "ADMIN_EMAIL" "ADMIN_PASSWORD"
)

for var in "${REQUIRED[@]}"; do
    if [[ -z "${!var:-}" ]]; then
        echo "❌ MISSING: $var"
        exit 1
    fi
done

echo "🔐 Setting secrets on Fly.io app: $APP_NAME"
echo ""

# Build array of secret args
SECRET_ARGS=(
    "STRIPE_API_KEY=$STRIPE_API_KEY"
    "STRIPE_WEBHOOK_SECRET=$STRIPE_WEBHOOK_SECRET"
    "RESEND_API_KEY=$RESEND_API_KEY"
    "EMAIL_FROM=$EMAIL_FROM"
    "CUSTOM_EMAIL_FROM=$CUSTOM_EMAIL_FROM"
    "CEREBRAS_API_KEY=$CEREBRAS_API_KEY"
    "CEREBRAS_MODEL=$CEREBRAS_MODEL"
    "CLOUDFLARE_API_TOKEN=$CLOUDFLARE_API_TOKEN"
    "CLOUDFLARE_ZONE_ID=$CLOUDFLARE_ZONE_ID"
    "MONGO_URL=$MONGO_URL"
    "DB_NAME=$DB_NAME"
    "ADMIN_EMAIL=$ADMIN_EMAIL"
    "ADMIN_PASSWORD=$ADMIN_PASSWORD"
    "CARD_PAYMENT_TAG=$CARD_PAYMENT_TAG"
    "FRONTEND_URL=https://wah-lah.com"
    "CORS_ORIGINS=https://wah-lah.com,https://www.wah-lah.com,https://api.wah-lah.com"
    "COOKIE_SECURE=true"
    "COOKIE_SAMESITE=lax"
    "ENFORCE_CANONICAL_HOST=true"
    "CANONICAL_HOST=wah-lah.com"
    "BLOCKED_STATES=WA,ID,MT,NV,LA,TN,MI,UT,AZ"
    "KYC_BASIC_THRESHOLD_USD=500"
    "KYC_ENHANCED_THRESHOLD_USD=5000"
    "CTR_THRESHOLD_USD=10000"
    "SAR_FREQ_WINDOW_HOURS=24"
    "SAR_FREQ_THRESHOLD=3"
    "CASHTAG_KEEP_RATE=0.12"
    "GIFTCARD_FEE_RATE=0.05"
    "BTC_FEE_RATE=0.10"
    "PROXY_DEFAULT_PER_TRANSFER_CAP=500"
    "PROXY_DEFAULT_DAILY_CAP=5000"
    "PROXY_COOLDOWN_FAILURES=3"
    "PROXY_LOCK_FAILURES=5"
    "PROXY_COOLDOWN_MINUTES=30"
)

# Optional: Sugar Sweeps creds
if [[ -n "$SUGAR_SWEEPS_USERNAME" && -n "$SUGAR_SWEEPS_PASSWORD" ]]; then
    SECRET_ARGS+=(
        "SUGAR_SWEEPS_USERNAME=$SUGAR_SWEEPS_USERNAME"
        "SUGAR_SWEEPS_PASSWORD=$SUGAR_SWEEPS_PASSWORD"
    )
fi

# Set secrets on Fly.io
flyctl secrets set -a "$APP_NAME" "${SECRET_ARGS[@]}"

echo "✅ All secrets set on Fly.io"
echo ""
echo "📋 Verifying secrets:"
flyctl secrets list -a "$APP_NAME"
```

---

### 2.2 Manual Individual Commands

If you prefer to set secrets one at a time:

```bash
# Stripe
flyctl secrets set \
  STRIPE_API_KEY='sk_live_YOUR_SECRET_KEY' \
  STRIPE_WEBHOOK_SECRET='whsec_YOUR_WEBHOOK_SECRET' \
  -a wah-lah

# Resend
flyctl secrets set RESEND_API_KEY='re_YOUR_API_KEY' -a wah-lah

# Cerebras
flyctl secrets set \
  CEREBRAS_API_KEY='csk-YOUR_API_KEY' \
  CEREBRAS_MODEL='qwen-3-235b-a22b-instruct-2507' \
  -a wah-lah

# Cloudflare
flyctl secrets set \
  CLOUDFLARE_API_TOKEN='cfat_YOUR_API_TOKEN' \
  CLOUDFLARE_ZONE_ID='YOUR_ZONE_ID' \
  -a wah-lah

# MongoDB
flyctl secrets set MONGO_URL='mongodb+srv://user:pass@cluster.mongodb.net/?retryWrites=true&w=majority' -a wah-lah

# Admin
flyctl secrets set \
  ADMIN_EMAIL='Jrs092393@gmail.com' \
  ADMIN_PASSWORD='YOUR_STRONG_PASSWORD' \
  -a wah-lah

# Email
flyctl secrets set \
  EMAIL_FROM='WAH-LAH <onboarding@resend.dev>' \
  CUSTOM_EMAIL_FROM='WAH-LAH <noreply@wah-lah.com>' \
  -a wah-lah

# CORS & Security
flyctl secrets set \
  CORS_ORIGINS='https://wah-lah.com,https://www.wah-lah.com,https://api.wah-lah.com' \
  COOKIE_SECURE='true' \
  COOKIE_SAMESITE='lax' \
  ENFORCE_CANONICAL_HOST='true' \
  -a wah-lah

# Compliance
flyctl secrets set \
  BLOCKED_STATES='WA,ID,MT,NV,LA,TN,MI,UT,AZ' \
  KYC_BASIC_THRESHOLD_USD='500' \
  KYC_ENHANCED_THRESHOLD_USD='5000' \
  CTR_THRESHOLD_USD='10000' \
  SAR_FREQ_WINDOW_HOURS='24' \
  SAR_FREQ_THRESHOLD='3' \
  -a wah-lah
```

---

### 2.3 Verify Secrets Were Set

```bash
flyctl secrets list -a wah-lah
```

Expected output:
```
NAME                              CREATED AT
ADMIN_EMAIL                       2026-06-01T12:00:00Z
ADMIN_PASSWORD                    2026-06-01T12:00:01Z
CEREBRAS_API_KEY                  2026-06-01T12:00:02Z
... (all secrets listed)
```

---

## 🔄 PART 3: Safe Secret Rotation Checklist

### ⚠️ **CRITICAL: DO NOT SKIP STEP 0**

### **Step 0: Rotate Keys BEFORE Deployment** (EMERGENCY)

The following keys are **exposed in documentation** and **MUST be rotated immediately**:
- ❌ `STRIPE_API_KEY`: sk_live_... (example in DEPLOY_QUICKSTART.md)
- ❌ `RESEND_API_KEY`: re_... (example in deploy.sh)
- ❌ `CEREBRAS_API_KEY`: csk-... (example in deploy.sh)
- ❌ `CLOUDFLARE_API_TOKEN`: cfat_... (example in deploy.sh)

**Action:**
1. Go to each service dashboard
2. **Revoke the old key** 
3. **Create a new key**
4. Use the new key in deploy-secrets.sh

---

### **Step 1: Preflight Checks** (5 min)

```bash
# Install/update flyctl
curl -L https://fly.io/install.sh | sh
export PATH="$HOME/.fly/bin:$PATH"

# Authenticate to Fly.io
flyctl auth login
# This opens a browser — sign in, copy the token

# Verify you can access the app
flyctl status -a wah-lah
# Should show: App: wah-lah, Status: Running
```

---

### **Step 2: Generate Crypto Secrets** (2 min)

Generate **new** values for crypto-sensitive env vars:

```bash
# Generate new JWT_SECRET (64 bytes)
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
# Output: aPZL0rE5mK2...  ← COPY THIS

# Generate new PROXY_ENCRYPTION_KEY (Fernet)
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Output: H3rK9xL2m0n...  ← COPY THIS
```

Save these values for Step 5.

---

### **Step 3: Create Backup of Current Secrets** (2 min)

```bash
# Export current secrets to a local file (for rollback)
flyctl secrets list -a wah-lah > /tmp/wah-lah-secrets-backup-$(date +%Y%m%d-%H%M%S).txt

# Keep this file safe (not in git) for 30 days in case of rollback
chmod 600 /tmp/wah-lah-secrets-backup-*.txt
```

---

### **Step 4: Prepare New Secrets File** (5 min)

Edit `deploy-secrets.sh`:

```bash
# Get your real values from:
# - https://dashboard.stripe.com/apikeys (new SECRET key)
# - https://resend.com/api-keys
# - https://cloud.cerebras.ai
# - https://dash.cloudflare.com (My Profile → API Tokens)
# - https://cloud.mongodb.com (Atlas connection string)
# - Generated values from Step 2

# Fill in deploy-secrets.sh
nano deploy-secrets.sh
```

---

### **Step 5: Stage Secrets (No Restart Yet)** (1 min)

```bash
# Stage all secrets without restarting machines
chmod +x deploy-secrets.sh
./deploy-secrets.sh  # This sets secrets but doesn't deploy
```

**Output should show:**
```
🔐 Setting secrets on Fly.io app: wah-lah
... (all secrets listed)
✅ All secrets set on Fly.io
```

---

### **Step 6: Verify Secrets Before Deploy** (2 min)

```bash
# List all secrets
flyctl secrets list -a wah-lah

# Check a specific secret value (without printing it to terminal)
flyctl secrets show ADMIN_EMAIL -a wah-lah
# Output: admin_email=Jrs092393@gmail.com (masked in display)
```

---

### **Step 7: Deploy with New Secrets** (3–5 min)

```bash
# Deploy the app (will use staged secrets automatically)
flyctl deploy -a wah-lah --remote-only --strategy=rolling

# Watch the deployment
flyctl logs -a wah-lah
# Watch for "Admin user created" or "Admin user already exists"
```

---

### **Step 8: Smoke Test on Port 8001** (3 min)

```bash
# Test health endpoint
curl https://api.wah-lah.com/api/health
# Expected: {"status":"ok","service":"wah-lah",...}

# Test admin login (from the deployed app)
curl -X POST https://api.wah-lah.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"Jrs092393@gmail.com","password":"YOUR_NEW_PASSWORD"}'
# Expected: JWT token in response (or 401 if password wrong)

# Visit https://wah-lah.com in browser
# Should load React SPA and not have any 500 errors in console
```

---

### **Step 9: Monitor for 1 Hour** (continuous)

```bash
# Tail logs for errors
flyctl logs -a wah-lah -f

# Watch for:
# ✅ No "MongoDB connection refused"
# ✅ No "Invalid JWT_SECRET"
# ✅ No "Stripe API key invalid"
# ✅ Health checks passing (20s interval)
```

---

### **Step 10: Cleanup** (1 min)

```bash
# Remove backup file after 1 hour of successful operation
rm /tmp/wah-lah-secrets-backup-*.txt

# Verify no secrets leaked to git
git log --all --source --full-history -S 'sk_live_' -- .
# Should return nothing (if it returns matches, force-push to remove)
```

---

## 🚨 PART 4: Rollback Procedure (If Anything Breaks)

If the deployment fails and the app won't start:

### **Quick Rollback (5 min)**

```bash
# 1. Revert to previous image
flyctl images list -a wah-lah
# Find the previous IMAGE_ID

flyctl images select -a wah-lah  # Choose the previous one
# Or: flyctl deploy -a wah-lah --image-label old_tag

# 2. Restore secrets from backup
# (If new secrets were invalid, restore old ones)
# Manually `flyctl secrets set` the old values

# 3. Restart
flyctl apps restart wah-lah

# 4. Verify
flyctl logs -a wah-lah
curl https://api.wah-lah.com/api/health
```

### **Emergency Disable If Completely Broken**

```bash
# Scale to zero (stops charges, kills active requests)
flyctl scale --count=0 -a wah-lah

# Point DNS back to emergency backup
# (via Cloudflare dashboard, temporarily point to old IP or emergency URL)

# After fixing, scale back up
flyctl scale --count=1 -a wah-lah
```

---

## 📋 PART 5: Secret Rotation Schedule (Best Practices)

| Secret | Rotation Frequency | Why | How |
|--------|-------------------|-----|-----|
| `JWT_SECRET` | Never (unless compromised) | Rotates all users out | `flyctl secrets set JWT_SECRET=...` |
| `ADMIN_PASSWORD` | Quarterly | Staff turnover, good hygiene | `flyctl secrets set ADMIN_PASSWORD=...` + notify team |
| `STRIPE_API_KEY` | Annually | Preventive, Stripe recommends | Dashboard → Create restricted key (safer) |
| `CEREBRAS_API_KEY` | Annually | Usage limits, prevent leaks | https://cloud.cerebras.ai settings |
| `CLOUDFLARE_API_TOKEN` | Quarterly | High-impact (DNS control) | Create new token with same permissions, rotate |
| `MONGO_URL` password | Annually | Database security | MongoDB Atlas → Database Access → rotate user |
| `RESEND_API_KEY` | Annually | Email service access | https://resend.com/api-keys |
| `SUGAR_SWEEPS_USERNAME` / `PASSWORD` | Quarterly | Distributor account rotation | Distributor sends new creds |

---

## 📝 Port 8001 Configuration Notes

### **Dockerfile Verification** (lines 61–64)
```dockerfile
EXPOSE 8001
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
```
✅ Correctly exposes port **8001**

### **fly.toml Configuration** (lines 17, 40)
```toml
[http_service]
  internal_port = 8001
  force_https = true
  
[[vm]]
  memory = "1024mb"
```
✅ Maps container port 8001 to Fly HTTP service  
✅ Forces HTTPS (no plain HTTP)  
✅ 1GB RAM allocated (sufficient for FastAPI + Playwright)

### **Health Check** (lines 29–34)
```toml
[[http_service.checks]]
  interval = "20s"
  timeout = "5s"
  grace_period = "30s"
  method = "GET"
  path = "/api/health"
```
✅ Health check every 20s on `/api/health`  
✅ Must return 200 within 5s

---

## ✅ Final Verification Checklist

Before calling deployment complete:

- [ ] All API keys rotated (Stripe, Resend, Cerebras, Cloudflare)
- [ ] `deploy-secrets.sh` filled with new values
- [ ] `flyctl secrets set` command run successfully
- [ ] `flyctl secrets list` shows all variables
- [ ] DNS records pointing to Fly.io IPs (A, AAAA records for @ and www)
- [ ] SSL certs provisioned: `flyctl certs list -a wah-lah`
- [ ] Health check passing: `curl https://api.wah-lah.com/api/health` returns 200
- [ ] Admin login works: `/api/auth/login` accepts new password
- [ ] Logs show no MongoDB, JWT, or Stripe errors
- [ ] React SPA loads at https://wah-lah.com
- [ ] No secrets in browser console (check DevTools)
- [ ] Stripe webhook configured: https://dashboard.stripe.com/webhooks

---

## 🎯 TL;DR — Quick Start

```bash
# 1. Rotate your keys at each service dashboard (CRITICAL)

# 2. Edit deploy-secrets.sh with new values
nano deploy-secrets.sh

# 3. Stage and deploy
chmod +x deploy-secrets.sh
./deploy-secrets.sh
flyctl deploy -a wah-lah --remote-only --strategy=rolling

# 4. Verify
curl https://api.wah-lah.com/api/health
flyctl logs -a wah-lah -f

# 5. Smoke test
# - Visit https://wah-lah.com
# - Try login
# - Make small deposit (if enabled)
```

**Deployment complete! 🚀**

---

**Questions?** Check `flyctl logs -a wah-lah` for detailed error messages.
