# Wah-Lah Migration — Emergent → Fly.io + Cloudflare Pages + MongoDB Atlas

> Goal: get `wah-lah.com` running on **stable, free** infrastructure that you control,
> independent of Emergent's preview/deploy lifecycle. End state: backend on Fly.io,
> frontend on Cloudflare Pages, data on MongoDB Atlas, DNS at Cloudflare.

## TL;DR architecture

```
                  ┌──────────────────────────┐
                  │   Cloudflare DNS          │
                  └──────────┬───────────────┘
                             │
   wah-lah.com  ───►  Cloudflare Pages  (React static site, free, SSL auto)
                             │
   api.wah-lah.com  ───►  Fly.io app  (FastAPI + Playwright, 1GB RAM)
                             │
                             ▼
                       MongoDB Atlas M0  (free 512MB cloud)
```

---

## Step 0 — Prerequisites (you do these once)

You'll need accounts (all free or free-tier):

- [ ] **GitHub** account — host the code so Fly.io and CF Pages can pull it
- [ ] **Fly.io** account → https://fly.io/app/sign-up (requires credit card; usage stays under $0–5/mo for our setup)
- [ ] **Cloudflare** account → you already have one (`Jrs092393@gmail.com`)
- [ ] **MongoDB Atlas** account → https://www.mongodb.com/cloud/atlas/register

Install on your local machine:
```bash
# flyctl
curl -L https://fly.io/install.sh | sh

# git (you probably have it)
git --version
```

---

## Step 1 — Push code to GitHub

In the Emergent chat input box, click **"Save to Github"**. This creates/updates a
GitHub repo with the entire `/app` workspace. Note the URL it gives you, e.g.
`https://github.com/Jrs092393/wah-lah`.

---

## Step 2 — Set up MongoDB Atlas (5 min)

1. Sign in at https://cloud.mongodb.com
2. **Create a new project** → name it `wah-lah`
3. **Build a database** → choose **M0 Free** → AWS / `us-east-1` (matches Fly's `iad` region) → cluster name `wah-lah-prod`
4. Once the cluster is provisioning (~3 min):
   - **Database Access** → Add New Database User → username `wahlah_app`, autogenerate password (copy it!), built-in role: `Atlas admin`
   - **Network Access** → Add IP Address → **Allow access from anywhere** (`0.0.0.0/0`). Required because Fly.io machines have rotating IPs.
5. Click **Connect** on your cluster → **Drivers** → copy the connection string. It looks like:
   ```
   mongodb+srv://wahlah_app:<password>@wah-lah-prod.xxxxx.mongodb.net/?retryWrites=true&w=majority
   ```
   Replace `<password>` with the password from step 4. **Save this string** — Fly needs it.

---

## Step 3 — Deploy backend to Fly.io

From your local machine (in the cloned wah-lah repo):

```bash
flyctl auth login                        # opens browser, sign in
flyctl launch --no-deploy --copy-config  # uses existing fly.toml
# When asked: "An existing fly.toml file was found... copy?" → Yes
# When asked about Postgres/Redis → No, No
# It creates the Fly app named "wah-lah" (or whatever you change in fly.toml)
```

Set production secrets — copy from your current `/app/backend/.env`:

```bash
flyctl secrets set \
  MONGO_URL='mongodb+srv://wahlah_app:YOUR_PASS@wah-lah-prod.xxxxx.mongodb.net/?retryWrites=true&w=majority' \
  DB_NAME='sugar_city_sweeps' \
  JWT_SECRET='<generate a long random string>' \
  ADMIN_EMAIL='jrs092393@gmail.com' \
  ADMIN_PASSWORD='<your-16+-char-admin-password>' \
  STRIPE_API_KEY='rk_live_...' \
  RESEND_API_KEY='re_...' \
  EMAIL_FROM='WAH-LAH <onboarding@resend.dev>' \
  CUSTOM_EMAIL_FROM='WAH-LAH <noreply@wah-lah.com>' \
  FRONTEND_URL='https://wah-lah.com' \
  CORS_ORIGINS='https://wah-lah.com,https://www.wah-lah.com' \
  CARD_PAYMENT_TAG='$WahLah' \
  CLOUDFLARE_API_TOKEN='cfut_...' \
  CEREBRAS_API_KEY='csk-...' \
  CEREBRAS_MODEL='qwen-3-235b-a22b-instruct-2507' \
  PROXY_ENCRYPTION_KEY='<generate a 32-byte Fernet key with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">' \
  PROXY_DEFAULT_PER_TRANSFER_CAP=500 \
  PROXY_DEFAULT_DAILY_CAP=5000 \
  PROXY_COOLDOWN_FAILURES=3 \
  PROXY_LOCK_FAILURES=5 \
  PROXY_COOLDOWN_MINUTES=30 \
  BLOCKED_STATES='WA,ID,MT,NV,LA,TN,MI,UT,AZ' \
  KYC_BASIC_THRESHOLD_USD=500 \
  KYC_ENHANCED_THRESHOLD_USD=5000 \
  CTR_THRESHOLD_USD=10000 \
  SAR_FREQ_WINDOW_HOURS=24 \
  SAR_FREQ_THRESHOLD=3 \
  ENFORCE_CANONICAL_HOST=false
```

Deploy:
```bash
flyctl deploy
```

Build takes ~5 min (Playwright Chromium pull). When done, Fly prints the public URL,
something like `https://wah-lah.fly.dev`. Test:
```bash
curl https://wah-lah.fly.dev/api/health
# → {"status":"ok","service":"wah-lah",...}
```

If `/api/health` returns 200, backend is live.

---

## Step 4 — Deploy frontend to Cloudflare Pages

1. Cloudflare dashboard → **Workers & Pages** → **Create application** → **Pages** → **Connect to Git**
2. Authorize Cloudflare to access your GitHub
3. Select your `wah-lah` repo → **Begin setup**
4. Build configuration:
   - **Framework preset:** Create React App
   - **Build command:** `cd frontend && yarn install --frozen-lockfile && yarn build`
   - **Build output directory:** `frontend/build`
   - **Root directory:** *(leave blank — repo root)*
5. **Environment variables** (production):
   - `REACT_APP_BACKEND_URL` = `https://api.wah-lah.com` *(we'll point this in Step 5)*
   - `NODE_VERSION` = `20`
6. **Save and Deploy**.

CF Pages will give you a `<project>.pages.dev` URL once the build finishes. Test it.

---

## Step 5 — Wire up DNS at Cloudflare

In Cloudflare → `wah-lah.com` → **DNS → Records** → **Add record** for each:

| Type  | Name | Target                      | Proxy   | TTL  |
|-------|------|------------------------------|---------|------|
| CNAME | `@`  | `<your-project>.pages.dev`   | Proxied | Auto |
| CNAME | `www`| `<your-project>.pages.dev`   | Proxied | Auto |
| CNAME | `api`| `wah-lah.fly.dev`            | DNS only (grey cloud) | Auto |

**Why `api` is DNS-only:** Cloudflare proxy adds a layer that broke POSTs before.
Fly.io serves its own SSL, so we don't need Cloudflare in front of the API.

Then in **Cloudflare Pages** → your project → **Custom domains** → add both `wah-lah.com` and `www.wah-lah.com`.

Then in **Fly.io** → your app → **Certificates**:
```bash
flyctl certs add api.wah-lah.com
```
Fly auto-provisions a Let's Encrypt cert (5–60 sec).

---

## Step 6 — Verify end-to-end

```bash
curl https://api.wah-lah.com/api/health
# → 200 ok

curl -X POST https://api.wah-lah.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"jrs092393@gmail.com","password":"<your-admin-password>"}'
# → 200 + JWT cookies (this was the broken endpoint!)
```

Visit `https://wah-lah.com` → log in. Done.

---

## Operations cheat-sheet

```bash
# Tail Fly logs
flyctl logs

# SSH into the running machine
flyctl ssh console

# Restart
flyctl apps restart wah-lah

# Update a secret
flyctl secrets set FOO=bar

# Scale RAM if Playwright OOMs
flyctl scale memory 2048
```

CF Pages auto-redeploys on every push to `main`. Fly does NOT auto-deploy — run
`flyctl deploy` after each backend change.

---

## Cost estimate

| Service           | Free tier             | Realistic monthly cost |
|-------------------|-----------------------|------------------------|
| Fly.io backend    | $5 credit             | $0–5 (with 1GB always-on, ~$3) |
| Cloudflare Pages  | Unlimited             | $0                     |
| MongoDB Atlas M0  | 512MB cluster forever | $0                     |
| Cloudflare DNS    | Free                  | $0                     |
| **Total**         |                       | **~$0–5 / month**      |

If you outgrow Atlas M0 (>512MB), upgrade to M10 ($57/mo) only when it actually fills up.

---

## Rollback plan

If anything goes sideways: re-add the original Cloudflare Pages binding for the static
site (or even just keep the preview URL working). The Emergent preview URL is still live
during this whole migration as a backup — `https://wahlah-deploy.preview.emergentagent.com`.
