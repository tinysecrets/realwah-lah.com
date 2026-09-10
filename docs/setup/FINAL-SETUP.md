# Final Manual Steps — wah-lah.com Production Hardening

> **No Fly.io anywhere in this project.** These steps now point at Render, Vercel,
> and Cloudflare only. Old "give me a Fly token" instructions are gone.

## ⚠️ Critical finding from the pool ping

Production proxy pool is **empty** (0 distributors). Migration to Atlas brought a fresh DB. You need to re-add your distributor proxy credentials before any real player deposit can flow.

**To add proxies:**
1. Go to https://wah-lah.com/admin (login as admin)
2. Click **Distributor Pool** tab
3. Click **+ Add Proxy** for each distributor (BP-Proxy, BSW-Proxy, etc.) — fill in:
   - Label (e.g. `BP-Proxy`)
   - Hub type (e.g. `sugar_sweeps`, `fire_kirin`)
   - Username + Password (the credentials YOU use to log into that distributor's hub)
   - Base URL (the hub's login page URL)
4. After adding all 6, click **Ping All** to verify everything's reachable
5. Top up balances on each distributor account so transfers can flow

## A. Backend env vars — set in the Render dashboard (NOT GitHub secrets)

Open: https://dashboard.render.com → Service **`real-wah-lah-com`** → **Environment**

Add every `sync: false` var from `render.yaml`. Minimum set:

| Name | Value |
|---|---|
| `MONGO_URL` | `mongodb+srv://wahlah_app:REPLACE_WITH_PASSWORD@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0` |
| `MONGODB_URI` | (same Atlas URL) |
| `JWT_SECRET` | long random string |
| `RESEND_API_KEY` | `re_REPLACE_WITH_RESEND_API_KEY` |
| `ALERT_EMAILS` | `REDACTED_EMAIL` (alerts for watchdog / reconciler / pool resync) |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | admin login |

Saving env vars restarts the service — no scroll, no deploy needed.

## B. Deploy pipeline — nothing to upload (git-driven)

The backend deploys through **Render's git integration** (`autoDeploy: true` in
`render.yaml`) and the frontend through **Vercel's git integration**
(`frontend/vercel.json`). **Do not create or upload any Fly/Cloudflare workflow.**

`.github/workflows/` in this repo already contains the CI checks (`codeql.yml`,
`main.yml`) that run on push — no `FLY_API_TOKEN`, no `CLOUDFLARE_API_TOKEN`
secrets are required for deployment.

## C. genie-sidekick (separate helper project)

`genie-sidekick/` is a **separate, self-contained scaffold** (its own Dockerfile
and `fly-deploy.yml` for repos that choose to run a Discord bot elsewhere). It is
**not** deployed as part of `wah-lah.com`; do not wire its Fly workflow into the
main repo's pipeline. If you run it at all, deploy it on the platform you pick for
it — the main project's deployment is Render + Vercel only.

---

## What you'll have after these 5 minutes

- ✅ Push to main → backend auto-redeploys on Render + frontend auto-deploys on Vercel (no deploys CLI, no Fly)
- ✅ Backend health-gated blue-green rollout via Render (`/api/health`)
- ✅ All production secrets live in Render Environment (masked, not in git)
- ✅ Worker-in-process background jobs (on-duty watchdog, deposit reconciler, pool resync) on the same Render instance

## Then revoke tokens
- **GitHub PATs:** https://github.com/settings/personal-access-tokens → revoke any
  overly broad or unused tokens (e.g. `genie-sidekick-deploy`). Render/Vercel auth
  is OAuth-based, so no deploy token lingers in the repo.
- (No Fly token exists to revoke — this project never had one in production.)

(GitHub Actions repo secrets that are still needed for CI can stay — they're
stored encrypted on GitHub, independent of any PAT.)