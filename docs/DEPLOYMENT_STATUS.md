# WAH-LAH DEPLOYMENT CHECKLIST

## Status Summary (as of May 30, 2026)

### ✅ COMPLETED & VERIFIED

| Variable | Status | Value |
|----------|--------|-------|
| Fly.io App Name | ✓ Set | `wah-lah` |
| Fly.io Token | ✓ Set | `FlyV1 fm2_lJPE...` |
| Cloudflare API Token | ✓ Set | `cfut_tKZpdWOjOaBw5xjzhtGn6Qm9gLKgZdz0hqPw49Lx690d7f53` |
| Cloudflare Zone ID | ✓ Set | `85b7fca6c8481125fc386a03fc1b4028` |
| MongoDB Atlas URL | ✓ Set | `mongodb+srv://wahlahdeployed:...@cluster0.y6owcec.mongodb.net` |
| Admin Email | ✓ Set | `admin@wah-lah.com` |
| Admin Password | ✓ Set | `Dontplay$$$12` |
| Resend API Key | ✓ Set | `re_ELT1wUz9_DprZju7Efmj9qwCLbYF8UNhf` |
| Cerebras Model | ✓ Set | `qwen-3-235b-a22b-instruct-2507` |
| Payment Tag | ✓ Set | `$jrs092393` |
| Domain | ✓ Configured | `wah-lah.com` |

### ❌ STILL NEEDED

| Variable | Source | How to Get |
|----------|--------|-----------|
| `STRIPE_API_KEY` | Stripe Dashboard | https://dashboard.stripe.com/apikeys → Secret Key (sk_live_...) |
| `STRIPE_PUBLISHABLE_KEY` | Stripe Dashboard | https://dashboard.stripe.com/apikeys → Publishable Key (pk_live_...) |
| `CEREBRAS_API_KEY` | Cerebras Console | https://cloud.cerebras.ai/platform/ → API Keys → Create (csk_...) |

---

## DNS Records Ready to Deploy

Once deploy completes, add these records to Cloudflare DNS:

```
Type    Name    Content                Value
──────────────────────────────────────────────────
A       @       <Fly IPv4>             (from: flyctl ips list -a wah-lah)
AAAA    @       <Fly IPv6>             (from: flyctl ips list -a wah-lah)
CNAME   www     wah-lah.fly.dev        proxied=ON
CNAME   api     wah-lah.fly.dev        proxied=ON
```

---

## Pre-Deploy Tasks

1. **Rotate Stripe keys** (CRITICAL — keys were exposed in chat)
   - Go to: https://dashboard.stripe.com/apikeys
   - Click Secret key → ⋯ → Roll → Now
   - Copy new `sk_live_...` → paste into deploy.sh as `STRIPE_API_KEY`
   - Copy `pk_live_...` → paste as `STRIPE_PUBLISHABLE_KEY`

2. **Create Cerebras API key**
   - Go to: https://cloud.cerebras.ai/platform/
   - API Keys → Create API Key → copy `csk_...`
   - Paste into deploy.sh as `CEREBRAS_API_KEY`

3. **Verify Cloudflare DNS is active**
   - https://dash.cloudflare.com → wah-lah.com
   - Nameservers should point to Cloudflare (if domain transferred)

4. **Verify MongoDB Atlas is ready**
   - https://cloud.mongodb.com → Cluster0 → Connect → should show green ✓
   - Database user `wahlah_deployed` exists with the password in `MONGO_URL`

---

## Deploy Steps (When Ready)

```bash
cd /workspaces/Wah-lah.com

# 1. Make deploy script executable
chmod +x deploy.sh

# 2. Run deploy
./deploy.sh

# Expected output:
# ==> [1/7] Preflight         ✓
# ==> [2/7] Crypto secrets    ✓
# ==> [3/7] Setting secrets   ✓
# ==> [4/7] Deploying         (takes 2-4 min)
# ==> [5/7] Adding certs      ✓
# ==> [6/7] Fly IPs           → copy these
# ==> [7/7] Smoke test        ✓
```

---

## Post-Deploy Tasks

### 1. Add DNS Records to Cloudflare
- https://dash.cloudflare.com → wah-lah.com → DNS → Records
- Paste the Fly IPs from deploy script output
- Set to proxied (orange cloud)

### 2. Add Stripe Webhook
- https://dashboard.stripe.com/webhooks
- Add endpoint: `https://api.wah-lah.com/api/webhook/stripe`
- Events: `checkout.session.completed`, `checkout.session.expired`
- Copy `whsec_...` → run:
  ```bash
  flyctl secrets set STRIPE_WEBHOOK_SECRET='whsec_...' -a wah-lah
  ```

### 3. Verify Resend Domain
- https://resend.com/domains → wah-lah.com
- Add to Cloudflare DNS if not done (TXT, MX, DKIM)
- Wait ~5min for verification (emails won't work without this)

### 4. Live Smoke Test
- Register at: https://wah-lah.com
- Claim 100 AMOE credits
- Make $5 Stripe deposit
- Try gift card redemption
- Verify admin login works

---

## Current Configuration Summary

**Primary Domain**: wah-lah.com
**Frontend URL**: https://wah-lah.com
**API Base**: https://api.wah-lah.com
**Admin Panel**: https://wah-lah.com/admin
**Health Check**: https://wah-lah.com/api/health

**Services**:
- Fly.io (backend + frontend)
- MongoDB Atlas (database)
- Cloudflare (DNS + DDoS protection)
- Stripe (payments)
- Resend (email)
- Cerebras (LLM for Boss Genie)

**Blocked States**: WA, ID, MT, NV, LA, TN, MI, UT, AZ

---

## Emergency Contacts

| Service | Issue | Recovery |
|---------|-------|----------|
| Fly.io | App down | `flyctl logs -a wah-lah` |
| MongoDB | DB unreachable | https://cloud.mongodb.com → check cluster status |
| Cloudflare | DNS not resolving | Check nameservers at domain registrar |
| Stripe | Payments failing | Check API key in Stripe dashboard |

---

## File Changes Made

✓ `/workspaces/Wah-lah.com/deploy.sh` — Added Cloudflare credentials
✓ `/workspaces/Wah-lah.com/check-deploy-readiness.sh` — Created deployment checker
✓ `/workspaces/Wah-lah.com/DEPLOYMENT_STATUS.md` — This file

---

**Last Updated**: May 30, 2026  
**Prepared by**: GitHub Copilot  
**Status**: Awaiting Stripe & Cerebras credentials
