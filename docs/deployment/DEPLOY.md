# Wah-Lah Architecture & Deployment — Render + Vercel + MongoDB Atlas

> Goal: `wah-lah.com` runs on **stable, low-cost infrastructure** you control.
> End state: backend on **Render** (`real-wah-lah-com`), frontend on **Vercel**,
> data on **MongoDB Atlas**, DNS at **Cloudflare** (the `wah-lah-api-proxy` Worker
> fronts the API). **No Fly.io. No Cloudflare Pages. No Stripe.** Older docs that
> mention those describe the abandoned 2025 stack.

## TL;DR architecture

```
                ┌──────────────────────────┐
                │      Cloudflare DNS       │
                └──────────┬───────────────┘
                           │
   wah-lah.com  ───►  Vercel       (React SPA, rewrites all → index.html)
     www.wah-lah.com ──►  Vercel   (same project)
                           │
   api.wah-lah.com ───►  Cloudflare Worker `wah-lah-api-proxy`
                           │
                           ▼
                   Render web service `real-wah-lah-com`
                   (FastAPI + background workers, port 10000)
                           │
                           ▼
                     MongoDB Atlas M0  (free 512MB cloud)
```

---

## Step 0 — Prerequisites (you do these once)

Account checklist (all free-tier):

- [ ] **GitHub** — host the code so Render and Vercel can pull it
- [ ] **Render** → https://dashboard.render.com (sign up with GitHub)
- [ ] **Vercel** → https://vercel.com (sign up with GitHub)
- [ ] **Cloudflare** → you already have one (`REDACTED_EMAIL`), DNS for `wah-lah.com`
- [ ] **MongoDB Atlas** → https://www.mongodb.com/cloud/atlas/register

No local CLI tooling is required (no `flyctl`). The optional **Render CLI** can
script env-var updates:
```bash
# macOS: brew install render
# Linux: curl -fsSL https://raw.githubusercontent.com/render-oss/cli/main/bin/install.sh | sh
```

---

## Step 1 — Push code to GitHub

`render.yaml` (Blueprint) and `frontend/vercel.json` tell Render/Vercel how to
build. Push the repo to GitHub (e.g. `tinysecrets/realwah-lah.com`).

---

## Step 2 — Set up MongoDB Atlas (5 min)

1. Sign in at https://cloud.mongodb.com
2. **Create a new project** → name it `wah-lah`
3. **Build a database** → choose **M0 Free** → AWS / `us-west-2` (Oregon — near Render's default region) → cluster name `wah-lah-prod`
4. Once the cluster is provisioning (~3 min):
   - **Database Access** → Add New Database User → username `wahlah_app`, autogenerate password (copy it!), built-in role: `Atlas admin`
   - **Network Access** → Add IP Address → **Allow access from anywhere** (`0.0.0.0/0`). Render's egress IPs vary; this is the standard setup for cloud-hosted backends.
5. Click **Connect** → **Drivers** → copy the connection string:
   ```
   mongodb+srv://wahlah_app:<password>@wah-lah-prod.xxxxx.mongodb.net/?retryWrites=true&w=majority
   ```
   Replace `<password>` and **save this** — Render needs it as `MONGO_URL` (and `MONGODB_URI`).

---

## Step 3 — Create the Render web service (once)

1. Render + GitHub → **New** → **Blueprint** → select the repo → Render reads `render.yaml`.
2. Blueprint creates service **`real-wah-lah-com`** (runtime docker, root `Dockerfile`, health check `/api/health`, `autoDeploy: true`).
3. For every `sync: false` env var in `render.yaml`, go to the service → **Environment** → add the value (see `docs/ENVIRONMENT_SECRETS_ROTATION_GUIDE.md` Part 2.1). At minimum:
   ```
   MONGO_URL=     # Atlas string from Step 2
   MONGODB_URI=   # same
   JWT_SECRET=    # python3 -c "import secrets;print(secrets.token_urlsafe(64))"
   ADMIN_EMAIL=
   ADMIN_PASSWORD=
   RESEND_API_KEY=
   CEREBRAS_API_KEY=
   ```
4. Render does a first build + deploy. When green:
   ```bash
   curl https://real-wah-lah-com.onrender.com/api/health   # → {"status":"ok",...}
   ```

---

## Step 4 — Connect Vercel for the frontend

1. Vercel → **Add New Project** → import the repo.
2. Configure:
   - **Root directory:** `frontend`
   - Framework preset: auto (React/Vite); build: `npm install && npm run build`
   - Output directory: auto (`dist` — `vercel.json` sets `outputDirectory: "dist"`)
   - Env var (production): `REACT_APP_BACKEND_URL=https://api.wah-lah.com`
3. **Deploy.** Vercel gives you `<project>.vercel.app`. Test the SPA there.
4. **Custom domains**: add `wah-lah.com` and `www.wah-lah.com` in Vercel → project → **Domains**; Vercel auto-provisions TLS and gives you the `cname.vercel-dns.com` records to add at Cloudflare.

---

## Step 5 — Wire up `api.wah-lah.com` at Cloudflare

The API is fronted by the **`wah-lah-api-proxy` Cloudflare Worker** (repo: `workers/wah-lah-api-proxy` or equivalent) so we keep the Worker routing, TLS and any headers, and can change the upstream without touching DNS.

Cloudflare → `wah-lah.com` → **DNS → Records**:

| Type  | Name | Target                      | Proxy   |
|-------|------|------------------------------|---------|
| CNAME | `@`  | `cname.vercel-dns.com`       | Proxied |
| CNAME | `www`| `cname.vercel-dns.com`       | Proxied |
| CNAME | `api`| `wah-lah-api-proxy.<username>.workers.dev` | **Proxied** |

**Why `api` must be Proxied (orange):** the Worker is the TLS-terminating edge for `api.wah-lah.com` and forwards to Render. (On the old Fly stack this record was grey/DNS-only — that is no longer the case.)

Render service hostname is `real-wah-lah-com.onrender.com` — do **not** point DNS at it directly; go through the Worker.

---

## Step 6 — Verify end-to-end

```bash
curl https://api.wah-lah.com/api/health
# → 200 ok

curl -X POST https://api.wah-lah.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"REDACTED_EMAIL","password":"<your-admin-password>"}'
# → 200 + JWT cookies
```

Visit `https://wah-lah.com` → log in. Done.

---

## Operations cheat-sheet

```bash
# Backend logs            → Render dashboard → real-wah-lah-com → Logs
# Deploy history/rollback → Render dashboard → real-wah-lah-com → Deploys → ⋯ → Rollback
# Env vars                → Render dashboard → real-wah-lah-com → Environment (Save = restart)
# Frontend deploys/logs   → Vercel dashboard → project → Deployments
# Wire a manual backend deploy without code changes
#   → Render → real-wah-lah-com → Manual Deploy → Deploy latest image (clears cache optional)
```

**Deploy flow:** push to `main` → Render builds/rolls out the backend (`autoDeploy: true`) **and** Vercel builds/rolls out the SPA. No manual deploy step.

---

## Cost estimate

| Service          | Free tier             | Realistic monthly cost |
|------------------|-----------------------|------------------------|
| Render backend   | 750 CPU/mo, 512MB     | $0–7 (Docker needs the paid/starter tier for custom instances) |
| Vercel frontend  | Personal plan         | $0                     |
| MongoDB Atlas M0 | 512MB cluster forever | $0                     |
| Cloudflare DNS + Worker | Free / Workers free tier | $0                    |
| **Total**        |                       | **~$0–7 / month**      |

If you outgrow Atlas M0 (>512MB), upgrade to M10 ($57/mo) only when it actually fills up.

---

## Rollback plan

If anything goes sideways: **Renderer → Deploys → Rollback** restores the last
green backend image in seconds; Vercel's git history lets you redeploy an old
frontend commit. The DB is untouched by either, so a bad deploy never corrupts data.