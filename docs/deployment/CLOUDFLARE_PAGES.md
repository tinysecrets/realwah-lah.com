# wah-lah.com — Frontend Deployment (Vercel)

> **The frontend is hosted on Vercel, not Cloudflare Pages.** The `vercel.json` in
> `frontend/` configures the SPA (rewrites all routes → `index.html`, security
> headers, cache headers for `/assets/*`). This file replaces the old
> Cloudflare Pages guide. Filename kept for history.

Account: `REDACTED_EMAIL`
Domain: `wah-lah.com`
API: `https://api.wah-lah.com` (Cloudflare Worker `wah-lah-api-proxy` → Render `real-wah-lah-com`)

---

## Architecture

```
wah-lah.com      → Vercel (this guide)
www.wah-lah.com  → Vercel (same project)
api.wah-lah.com  → Cloudflare Worker wah-lah-api-proxy (Proxied) → Render
```

The React app calls `https://api.wah-lah.com` via `REACT_APP_BACKEND_URL` (see `frontend/src/config.ts`).

---

## Step 1 — Create the Vercel project

1. Go to [vercel.com](https://vercel.com) → **Add New** → **Project**
2. Authorize GitHub → select `tinysecrets/realwah-lah.com`
3. Build settings:

| Field | Value |
|-------|-------|
| Project name | `wah-lah` |
| Framework preset | Auto-detect (it finds `frontend/package.json`) |
| Root directory | `frontend` |
| Build command | default (`npm run build`) — detects from lockfile |
| Output directory | `dist` (also pinned by `vercel.json` → `outputDirectory`) |

4. **Environment variables** → Production:

| Variable | Value |
|----------|-------|
| `REACT_APP_BACKEND_URL` | `https://api.wah-lah.com` |
| `VITE_BACKEND_URL` | `https://api.wah-lah.com` |

5. **Deploy** — first build takes ~2 min. Test the preview URL `<project>.vercel.app`.

---

## Step 2 — Custom domains

In Vercel → project → **Settings** → **Domains**:

1. Add `wah-lah.com`
2. Add `www.wah-lah.com`

Vercel gives you the DNS target `cname.vercel-dns.com` (or CNAME values). Add them at Cloudflare.

---

## Step 3 — DNS records (manual check)

Cloudflare → **wah-lah.com** → **DNS** → confirm:

| Type | Name | Content | Proxy |
|------|------|---------|-------|
| CNAME | `@` | `cname.vercel-dns.com` | Proxied (orange) |
| CNAME | `www` | `cname.vercel-dns.com` | Proxied (orange) |
| CNAME | `api` | `wah-lah-api-proxy.<username>.workers.dev` | **Proxied (orange)** |

**Important:** `api` must stay **Proxied** because the Worker is the TLS edge in
front of Render. (On the old Fly stack this was grey/DNS-only — not anymore.)

---

## Step 4 — SSL / HTTPS

- Vercel: automatic for `wah-lah.com` / `www` — no action needed.
- API: TLS by the Cloudflare Worker + Render; nothing to configure.

---

## Step 5 — Verify live

```bash
# Frontend loads
curl -I https://wah-lah.com

# API health (via Worker → Render)
curl https://api.wah-lah.com/api/health

# SPA routing (React Router — vercel.json rewrites to index.html)
curl -I https://wah-lah.com/boss
# Should return 200
```

Open `https://wah-lah.com` in a browser → register or log in.

---

## Auto-deploy on push

Every push to `main` triggers a Vercel build automatically (Git integration).
Prefer this over manual redeploys.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| SPA works but `/boss` 404s | `vercel.json` `rewrites` must map `/(.*)` → `/index.html` (already present) |
| `undefined/api` in browser | `REACT_APP_BACKEND_URL` not set at build time — check Vercel env vars & redeploy |
| Login works on `.vercel.app` but not `wah-lah.com` | Check Render `CORS_ORIGINS` includes `https://wah-lah.com` |
| 520/502 on API POSTs | `api` DNS record is grey-cloud/DNS-only (points at Render directly) — switch to the Worker + orange proxy |
| Stale frontend | Vercel → project → Redeploy (or push an empty commit) |

---

## Redeploy frontend only

```bash
# Vercel dashboard: project → Deployments → redeploy
# Or push any commit to main
git commit --allow-empty -m "trigger vercel redeploy" && git push
```