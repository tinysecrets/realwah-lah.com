# Justin — Do These 4 Things Before Going Live

> 15 minutes total. Each one in order. Open 4 browser tabs.

---

## Tab 1: Rotate Resend

1. Go to → **https://resend.com/api-keys**
2. Find your current key → **⋯** → **Delete**
3. Click **Create API Key** → name it `wahlah-prod` → permission: **Full Access** → **Add**
4. Copy the `re_...` key on screen.
5. **Render** → Service `real-wah-lah-com` → **Environment** → update `RESEND_API_KEY`.

While you're there:
1. Go to → **https://resend.com/domains**
2. If `wah-lah.com` isn't there yet, click **Add Domain** → enter `wah-lah.com`
3. Resend gives you 3 DNS records to add to Cloudflare (TXT, MX, DKIM). Add them in Cloudflare DNS — takes 2 minutes.
4. Wait ~5 minutes for verification. **Without this, your emails go to spam.**

---

## Tab 2: Rotate Cerebras

1. Go to → **https://cloud.cerebras.ai/platform/**
2. **API Keys** tab → find the leaked key → **Revoke**
3. **Create API Key** → name `wahlah-prod` → copy the `csk-...`
4. **Render** → Service `real-wah-lah-com` → **Environment** → update `CEREBRAS_API_KEY`.

---

## Tab 3: Rotate Cloudflare

1. Go to → **https://dash.cloudflare.com/profile/api-tokens**
2. Find the leaked token → **⋯** → **Roll** (or Delete + Create New)
3. If creating new: use the **Edit zone DNS** template, restrict to zone `wah-lah.com`, expire in 1 year.
4. Copy the new `cfat_...` token on screen.
5. Set it as `CLOUDFLARE_API_TOKEN` wherever it's used (deploy automation / the `wah-lah-api-proxy` Worker secrets if it makes API calls).
6. For `CLOUDFLARE_ZONE_ID`: go to dash.cloudflare.com → click `wah-lah.com` → on the right sidebar, "API" section → copy **Zone ID**.

> The Cloudflare zone on `wah-lah.com` is DNS for the whole stack. Don't delete records when rotating tokens — only the tokens themselves.

---

## Tab 4: No Fly token, nothing to rotate here

This project **does not use Fly.io and has no `flyctl`, no `deploy.sh`, and no `FLY_API_TOKEN`.** The backend deploys through **Render's git integration** (`autoDeploy: true` in `render.yaml`) and the frontend through **Vercel's git integration** — both triggered by a push to `main`. You will never need a Fly account or token for this project.

The only deploy-related secrets that exist are GitHub repo secrets used by `.github/workflows/` (build/lint) — listed at **https://github.com/tinysecrets/realwah-lah.com/settings/secrets/actions**. Review them and remove any that are no longer used.

---

## Now: Set up MongoDB Atlas (10 minutes, free tier)

1. Go to → **https://cloud.mongodb.com**
2. Sign up with your email if you don't have an account (free, no card required for M0 tier)
3. **Build a Database** → choose **M0 (FREE)** → AWS → **us-west-2 (Oregon, near Render)** → click **Create**
4. **Username & Password screen**:
   - Username: `wahlah_app`
   - Password: click **Autogenerate Secure Password** → COPY IT → click **Create User**
5. **Network Access screen**:
   - Click **Add IP Address** → **Allow Access From Anywhere** (0.0.0.0/0) → **Add Entry**
   - (Render's egress IPs vary. This is normal & secure with a strong DB password.)
6. **Click "Finish and Close"**
7. On the main Database page → click **Connect** → **Drivers** → Python 3.12 →
   the connection string shown looks like:
   `mongodb+srv://wahlah_app:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority`
8. **Replace `<password>` with the actual password** you copied in step 4.
9. **Render** → Service `real-wah-lah-com` → **Environment** → set **both** `MONGO_URL` and `MONGODB_URI` to that full URL.

---

## Last thing: the admin account

1. **`ADMIN_PASSWORD`**: pick a long random password. Justin will use this to log into `wah-lah.com/admin`. Suggestion:
   ```bash
   python3 -c "import secrets;print(secrets.token_urlsafe(24))"
   ```
   Save it in your password manager.
2. **Render** → Service `real-wah-lah-com` → **Environment** → set `ADMIN_EMAIL` and `ADMIN_PASSWORD`.

---

## Deploy

Backend + frontend are **git-driven**. No deploy script:

```bash
git add -A
git commit -m "deploy: <what changed>"
git push origin main
```

- **Render** picks up the push, builds the Docker image (`render.yaml` → root `Dockerfile`), health-checks `/api/health`, and rolls out — usually < 10 minutes.
- **Vercel** picks up the same push, builds `frontend/` (`vercel.json` → `dist`), and ships the SPA.

Watch both dashboards for green deploys: dashboard.render.com → `real-wah-lah-com`; vercel.com → the `wah-lah` project.

Confirm: browse to `https://api.wah-lah.com/api/health` → expect `{"status":"ok",...}`.

---

## After the first deploy: point the domain (already done — verify only)

Cloudflare DNS for `wah-lah.com` should be:

| Type | Name | Content | Proxy |
|---|---|---|---|
| CNAME | `@`   | `cname.vercel-dns.com` | 🟠 Proxied (Vercel SPA) |
| CNAME | `www` | `cname.vercel-dns.com` | 🟠 Proxied (Vercel SPA) |
| CNAME | `api` | the `wah-lah-api-proxy` Worker route (`workers.dev` subdomain) | 🟠 Proxied (Cloudflare Worker → Render) |

**`api` must stay proxied-orange so the Worker can forward** — unlike the old DNS-only setup for Fly, the Worker needs Cloudflare in front to route TLS + POSTs/cookies. Render service hostname is `real-wah-lah-com.onrender.com` (internal DNS only).

Cloudflare → SSL/TLS → Overview → set to **Full (strict)**.

Browse to https://wah-lah.com → you should see the WAH-LAH landing page with the genie mascot. 🪔

---

## If something breaks

```bash
# Backend runtime logs → Render Dashboard: real-wah-lah-com → Logs
# Backend deploy events → Render Dashboard: real-wah-lah-com → Events
# Frontend logs / deploys → Vercel project → Deployments
# Health → https://api.wah-lah.com/api/health
```

Most common deploy failures and fixes:
- `MONGO_URL connection refused` → Atlas IP allowlist didn't include 0.0.0.0/0, or `MONGO_URL`/`MONGODB_URI` weren't both set in Render Environment. Fix in Atlas or Render.
- `CORS error in browser` → `CORS_ORIGINS` in Render doesn't match the actual frontend URL. Update it in Render → Environment (Render restarts the service with the new value).
- Email goes to spam → Resend domain not verified yet. Wait, or check the DKIM record in Cloudflare.
- Render deploy failed → open **Events** for `real-wah-lah-com`; the build log names the step that failed (usually a missing `sync: false` env var or a Docker problem).

You got this. 🐐