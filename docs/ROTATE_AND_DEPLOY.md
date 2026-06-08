# Justin — Do These 5 Things Before Deploy

> 15 minutes total. Each one in order. Open 5 browser tabs.

---

## Tab 1: Rotate Stripe (the dangerous one — do this first)

1. Go to → **https://dashboard.stripe.com/apikeys**
2. Click the **Secret key** row → **⋯** menu → **Roll key**
3. Stripe asks "Expire current key in: 1 hour / 12 hours / 7 days / Now" → pick **Now**.
4. New `sk_live_...` shows on screen ONCE — copy it.
5. Also copy the **Publishable key** (`pk_live_...`) from that same page — that one doesn't need to rotate but you'll need it for the deploy script.
6. **Paste both into `deploy.sh`** under `STRIPE_API_KEY` (the secret) and `STRIPE_PUBLISHABLE_KEY`.

⚠️ **You won't see the secret again.** If you close the tab without copying, you have to roll it again.

---

## Tab 2: Rotate Resend

1. Go to → **https://resend.com/api-keys**
2. Find your current key → **⋯** → **Delete**
3. Click **Create API Key** → name it `wahlah-prod` → permission: **Full Access** → **Add**
4. Copy the `re_...` key on screen.
5. **Paste into `deploy.sh`** under `RESEND_API_KEY`.

While you're there:
1. Go to → **https://resend.com/domains**
2. If `wah-lah.com` isn't there yet, click **Add Domain** → enter `wah-lah.com`
3. Resend gives you 3 DNS records to add to Cloudflare (TXT, MX, DKIM). Add them in Cloudflare DNS — takes 2 minutes.
4. Wait ~5 minutes for verification. **Without this, your emails go to spam.**

---

## Tab 3: Rotate Cerebras

1. Go to → **https://cloud.cerebras.ai/platform/**
2. **API Keys** tab → find the leaked key → **Revoke**
3. **Create API Key** → name `wahlah-prod` → copy the `csk-...`
4. **Paste into `deploy.sh`** under `CEREBRAS_API_KEY`.

---

## Tab 4: Rotate Cloudflare

1. Go to → **https://dash.cloudflare.com/profile/api-tokens**
2. Find the leaked token → **⋯** → **Roll** (or Delete + Create New)
3. If creating new: use the **Edit zone DNS** template, restrict to zone `wah-lah.com`, expire in 1 year.
4. Copy the new `cfat_...` token on screen.
5. **Paste into `deploy.sh`** under `CLOUDFLARE_API_TOKEN`.
6. For `CLOUDFLARE_ZONE_ID`: go to dash.cloudflare.com → click `wah-lah.com` → on the right sidebar, "API" section → copy **Zone ID**. **Paste into `deploy.sh`**.

---

## Tab 5: Rotate Fly token (do this last because you need it for deploy)

1. Go to → **https://fly.io/user/personal_access_tokens** (or run `flyctl auth login` on laptop)
2. Find the leaked tokens → **Revoke** both
3. Click **Create Token** → name `wahlah-deploy-2026` → copy the `FlyV1 fm2_...`
4. **Paste into `deploy.sh`** under `FLY_TOKEN`.

---

## Now: Set up MongoDB Atlas (10 minutes, free tier)

1. Go to → **https://cloud.mongodb.com**
2. Sign up with your email if you don't have an account (free, no card required for M0 tier)
3. **Build a Database** → choose **M0 (FREE)** → AWS → **us-east-1 (N. Virginia)** → click **Create**
4. **Username & Password screen**: 
   - Username: `wahlah_app`
   - Password: click **Autogenerate Secure Password** → COPY IT → click **Create User**
5. **Network Access screen**:
   - Click **Add IP Address** → **Allow Access From Anywhere** (0.0.0.0/0) → **Add Entry**
   - (Fly's container IPs rotate. This is normal & secure with strong DB password.)
6. **Click "Finish and Close"**
7. On the main Database page → click **Connect** → **Drivers** → Python 3.12 →
   the connection string shown looks like:  
   `mongodb+srv://wahlah_app:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority`
8. **Replace `<password>` with the actual password** you copied in step 4.
9. **Paste the FULL URL into `deploy.sh`** under `MONGO_URL`.

---

## Last 2 things in deploy.sh

1. **`ADMIN_PASSWORD`**: pick a long random password. Justin will use this to log into wah-lah.com/admin. Suggestion: 
   ```bash
   python3 -c "import secrets;print(secrets.token_urlsafe(24))"
   ```
   Save it in your password manager.

2. **`STRIPE_WEBHOOK_SECRET`**: skip this for now. You can leave it blank. After deploy is live, you go to https://dashboard.stripe.com/webhooks, add the endpoint `https://api.wah-lah.com/api/webhook/stripe`, copy the `whsec_...` that appears, then run:
   ```bash
   flyctl secrets set STRIPE_WEBHOOK_SECRET='whsec_...' -a wah-lah
   ```

---

## Deploy

```bash
cd /path/to/Wahlah.com-repo
chmod +x deploy.sh
./deploy.sh
```

About 3-5 minutes. Watch the terminal. When you see "🪔 You are live." — point a browser at `https://wah-lah.com/api/health` to confirm 200.

---

## After deploy: point the domain

Cloudflare DNS for `wah-lah.com`:

1. Go to Cloudflare → `wah-lah.com` → **DNS**
2. Add records (the deploy script printed the Fly IPs — use those):

| Type | Name | Content | Proxy |
|---|---|---|---|
| A    | `@`   | <FLY_IPv4> | 🟠 Proxied |
| AAAA | `@`   | <FLY_IPv6> | 🟠 Proxied |
| A    | `www` | <FLY_IPv4> | 🟠 Proxied |
| A    | `api` | <FLY_IPv4> | 🟠 Proxied |

Cloudflare → SSL/TLS → Overview → set to **Full (strict)**.

Browse to https://wah-lah.com → you should see the WAH-LAH landing page with the genie mascot. 🪔

---

## If something breaks

```bash
flyctl logs -a wah-lah                   # see runtime logs
flyctl ssh console -a wah-lah            # shell into the running container
flyctl status -a wah-lah                 # health check status
flyctl secrets list -a wah-lah           # confirm secrets are set (values masked)
```

Most common deploy failures and fixes:
- `MONGO_URL connection refused` → Atlas IP allowlist didn't include 0.0.0.0/0. Fix in Atlas → Network Access.
- `STRIPE_API_KEY authentication failed` → you used the publishable (pk_live) instead of the secret (sk_live). Re-set with `flyctl secrets set STRIPE_API_KEY=sk_live_...`
- `CORS error in browser` → CORS_ORIGINS in secrets doesn't match your actual frontend URL. Update with `flyctl secrets set CORS_ORIGINS='https://wah-lah.com,https://www.wah-lah.com'`
- Email goes to spam → Resend domain not verified yet. Wait, or check the DKIM record in Cloudflare.

You got this. 🐐
