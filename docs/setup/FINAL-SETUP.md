# Final Manual Steps — wah-lah.com Production Hardening

Three quick GitHub web UI tasks (~5 min total). No PAT needed.

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

## A. Add 4 GitHub Actions secrets to WAHLAH-DEPLOYD
Open: https://github.com/tinysecrets/WAHLAH-DEPLOYD/settings/secrets/actions

Click **New repository secret** four times and add these:

| Name | Value |
|---|---|
| `FLY_API_TOKEN` | (your Fly token — same one you gave me) |
| `MONGO_URL` | `mongodb+srv://wahlah_app:CyYsQnzzJ7T92DBU@cluster0.xskmz96.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0` |
| `RESEND_API_KEY` | `re_EpJ9Qevj_5PE5PeG1D3xbzXQr7JdivLQm` |
| `ALERT_EMAIL` | `Jrs092393@gmail.com` |

## B. Upload the 3 workflow files via GitHub web UI
The workflow files are sitting in `/app/.github/workflows/` but my PAT couldn't push workflows. Drag-and-drop them into GitHub:

1. Open: https://github.com/tinysecrets/WAHLAH-DEPLOYD/tree/main/.github/workflows
2. Click **Add file → Upload files**
3. From your local clone of the repo, drag in these 3 files:
   - `.github/workflows/fly-deploy.yml` *(may already exist — overwrite if so)*
   - `.github/workflows/uptime-monitor.yml`
   - `.github/workflows/atlas-backup.yml`
4. Commit message: `Add CI workflows`
5. Commit directly to main

## C. Add 1 GitHub Actions secret to genie-sidekick
Open: https://github.com/tinysecrets/genie-sidekick/settings/secrets/actions

| Name | Value |
|---|---|
| `FLY_API_TOKEN` | (same Fly token) |

Then upload `genie-sidekick/.github/workflows/fly-deploy.yml` to that repo via the same drag-drop trick.

---

## What you'll have after these 5 minutes

- ✅ Push to main → backend auto-redeploys to Fly within 3 min (no flyctl on your machine ever)
- ✅ Uptime check every 5 min → Resend email if wah-lah.com goes down
- ✅ Daily Mongo backups uploaded as GitHub Releases, 7-day rolling retention
- ✅ Same auto-deploy pipeline for genie-sidekick

## Then revoke tokens
- **Fly:** https://fly.io/user/personal_access_tokens → revoke `wah-lah-deploy`
- **GitHub PAT:** https://github.com/settings/personal-access-tokens → revoke `genie-sidekick-deploy`

(GitHub Actions secrets stay — they're stored encrypted on GitHub independent of the original PAT.)
