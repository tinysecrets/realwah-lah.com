# Wah-Lah Deploy Sequence

Deploy is **git-driven**: Render (backend) and Vercel (frontend) both
auto-deploy on every push to `main`. **No Fly.io, no deploy tokens, no CLI.**

## One-time setup

1. **Render**: create the Blueprint from `render.yaml` (creates web service
   `real-wah-lah-com`, runtime docker, `autoDeploy: true`, health `/api/health`).
2. **Render env vars**: add every `sync: false` var from `render.yaml` in
   Service → `real-wah-lah-com` → Environment (list in
   `docs/ENVIRONMENT_SECRETS_ROTATION_GUIDE.md` Part 2.1). Most important:
   `MONGO_URL`, `MONGODB_URI`, `JWT_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`.
3. **Vercel**: import the repo (root dir `frontend`, build auto-detected,
   output `dist` per `frontend/vercel.json`). Add the `wah-lah.com` and
   `www.wah-lah.com` custom domains.
4. **Cloudflare DNS** (zone `wah-lah.com`):
   ```text
   wah-lah.com      CNAME → cname.vercel-dns.com    (Proxied)
   www.wah-lah.com  CNAME → cname.vercel-dns.com    (Proxied)
   api.wah-lah.com  CNAME → wah-lah-api-proxy.<user>.workers.dev  (Proxied)
   ```

## Normal deploy

```bash
git add -A
git commit -m "Describe the change"
git push origin main
```

Render + Vercel both pick up the push and deploy automatically. Watch:

- Render → Dashboard → `real-wah-lah-com` → Events (build → health check → live)
- Vercel → project → Deployments

## Manual redeploy without a code change

- **Backend**: Render → `real-wah-lah-com` → **Manual Deploy** → **Deploy latest image** (optionally **Clear build cache & deploy**).
- **Frontend**: Vercel → project → **Redeploy**.

## Verify

```text
https://api.wah-lah.com/api/health   → 200 ok
https://wah-lah.com                 → SPA loads
https://wah-lah.com/api/health      → 200 ok (SPA rewrite falls through to the API) — confirm routing if needed
```

## Current recovery note

The domain registration is active through Cloudflare Registrar until
`2027-04-22`. If a backend deploy fails, check Render → `real-wah-lah-com` →
**Events** + **Logs** for the failing step (commonly a missing `sync: false` env
var or a Docker build error), fix it, and watch the auto-deploy retry. The Render
web service name is **`real-wah-lah-com`**.