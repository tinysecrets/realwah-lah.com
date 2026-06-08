# wah-lah.com — Cloudflare Pages Setup

Account: `REDACTED_EMAIL`  
Domain: `wah-lah.com`  
API: `https://api.wah-lah.com` (Fly.io — separate from Pages)

---

## Architecture

```
wah-lah.com      → Cloudflare Pages (this guide)
www.wah-lah.com  → Cloudflare Pages (same project)
api.wah-lah.com  → Fly.io wah-lah.fly.dev (grey-cloud DNS only)
```

The React app calls `https://api.wah-lah.com` at **build time** via `REACT_APP_BACKEND_URL`.

---

## Step 1 — Create Pages project

1. Go to [Cloudflare Dashboard](https://dash.cloudflare.com) → **Workers & Pages**
2. **Create** → **Pages** → **Connect to Git**
3. Authorize GitHub → select `tinysecrets/realwah-lah.com`
4. Build settings:

| Field | Value |
|-------|-------|
| Project name | `wah-lah` |
| Production branch | `main` |
| Framework preset | None (or Create React App) |
| Build command | `cd frontend && yarn install --frozen-lockfile && yarn build` |
| Build output directory | `frontend/build` |
| Root directory | *(leave empty)* |

5. **Environment variables** → Production:

| Variable | Value |
|----------|-------|
| `REACT_APP_BACKEND_URL` | `https://api.wah-lah.com` |
| `NODE_VERSION` | `20` |
| `CI` | `false` |

`CI=false` prevents Create React App from failing the build on lint warnings.

6. **Save and Deploy** — first build takes ~3–5 min.

Test the preview URL: `https://wah-lah.pages.dev` (name may vary).

---

## Step 2 — Custom domains

In Pages → your project → **Custom domains** → **Set up a domain**:

1. Add `wah-lah.com`
2. Add `www.wah-lah.com`

Cloudflare auto-creates DNS records if the zone is already on your account.

---

## Step 3 — DNS records (manual check)

Cloudflare → **wah-lah.com** → **DNS** → confirm:

| Type | Name | Content | Proxy |
|------|------|---------|-------|
| CNAME | `@` | `wah-lah.pages.dev` | Proxied (orange) |
| CNAME | `www` | `wah-lah.pages.dev` | Proxied (orange) |
| CNAME | `api` | `wah-lah.fly.dev` | **DNS only** (grey) |

**Important:** `api` must be **grey cloud** (DNS only). Orange proxy on the API breaks POST requests and cookies.

---

## Step 4 — SSL / HTTPS

- Pages: automatic — no action needed
- API: run once on Fly:
  ```bash
  flyctl certs add api.wah-lah.com -a wah-lah
  flyctl certs show api.wah-lah.com -a wah-lah
  ```

---

## Step 5 — Verify live

```bash
# Frontend loads
curl -I https://wah-lah.com

# API health
curl https://api.wah-lah.com/api/health

# SPA routing (React Router)
curl -I https://wah-lah.com/boss
# Should return 200 (served by index.html via _redirects)
```

Open `https://wah-lah.com` in a browser → register or log in.

---

## Auto-deploy on push

Every push to `main` that touches `frontend/` triggers a new Pages build automatically (Git integration).

Or use the GitHub Action (requires repo secrets):

| Secret | Where to get it |
|--------|-----------------|
| `CLOUDFLARE_API_TOKEN` | Cloudflare → My Profile → API Tokens → Edit Cloudflare Workers |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare → any zone → Overview → right sidebar |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Build fails on warnings | Set `CI=false` in Pages env vars |
| `undefined/api` in browser | `REACT_APP_BACKEND_URL` not set — redeploy after adding it |
| Login works on `.pages.dev` but not `wah-lah.com` | Check Fly `CORS_ORIGINS` includes `https://wah-lah.com` |
| 520/502 on API POSTs | `api` DNS record is proxied — switch to grey cloud |
| Direct URL `/boss` returns 404 | `_redirects` missing from build — confirm `frontend/public/_redirects` exists |

---

## Redeploy frontend only

```bash
# Dashboard: Pages → wah-lah → Deployments → Retry deployment
# Or push any commit to main
git commit --allow-empty -m "trigger pages redeploy" && git push
```
