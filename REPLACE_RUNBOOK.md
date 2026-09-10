# Cutover Runbook — promote this tree to the one true source

This directory (`wah-lah-secured`) is a cleaned, hardened replacement for the
old repo. The old git history contains a live admin token and operator PII, so
cutover has three phases: **rotate → replace → purge**. Do them in order.

## Phase 0 — Safety (before touching anything)

```bash
# 1. Fresh backup of the live database (Atlas → Backup → Take snapshot now)
# 2. Note the current Render deploy id (for one-click rollback)
# 3. Announce a maintenance window (approvals paused, site stays up)
```

## Phase 1 — Rotate every exposed credential FIRST

History-purging does NOT un-leak a secret — assume the old token is burned.
Rotate in this order (site keeps running throughout):

1. **Scout tokens** (were committed in plaintext):
   ```bash
   NEW_TOKEN=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
   # Render → real-wah-lah-com → Environment → SCOUT_LEADS_TOKEN = $NEW_TOKEN
   cd scout-force && npx wrangler secret put LEADS_TOKEN   # paste $NEW_TOKEN
   npx wrangler secret put ADMIN_TOKEN                     # fresh random, different value
   ```
   Verify: `curl /api/admin/scout/leads` (admin) still works; Worker `/health` ok.
2. **`JWT_SECRET`** — rotate via Render env + redeploy. (All sessions invalidate;
   users simply log in again.)
3. **`ADMIN_PASSWORD`** — `python3 scripts/set_admin.py`, then enable 2FA on the
   admin account (`/api/ext/2fa/setup` → `/enable`) and confirm primary login
   now requires the TOTP code.
4. **Review the rest** (`SECURITY.md` inventory): BlockCypher, Resend, Cerebras,
   Persona, Cloudflare API token. Rotate any that ever appeared in chat logs,
   screenshots, or AI session files.

## Phase 2 — Replace the repo source

Option A — clean history (recommended):

```bash
cd /path/to/wah-lah-secured
git init -b main
git add -A
git commit -m "Secure baseline: fail-closed compliance, hardened auth/money paths, PII scrubbed"
git remote add origin https://github.com/<org>/<repo>.git
git push --force --set-upstream origin main   # after confirming with all collaborators
```

Option B — keep history, purge secrets with BFG (history is rewritten either way):

```bash
# 1. Mirror the OLD repo
git clone --mirror https://github.com/<org>/<old-repo>.git old.git
# 2. Delete the secret-bearing paths from ALL history
java -jar bfg.jar --delete-files SESSION_RESUME.md --delete-files PRD.md \
  --delete-files CHANGELOG.md --delete-files ROADMAP.md --delete-files test_credentials.md old.git
# 3. Replace secret TEXT everywhere (put each burned value in secrets.txt, one per line)
java -jar bfg.jar --replace-text secrets.txt old.git
cd old.git && git reflog expire --expire=now --all && git gc --prune=now --aggressive
git push --force
# 4. Then overlay this secured tree as a new commit on top and push.
```

After either option:

- Enable GitHub push protection + secret scanning alerts (Settings → Code security).
- Require PR reviews on `main` (even solo — it forces CI to run).
- Archive or delete the old repo / old clones so nobody pushes the dirty tree back.

## Phase 3 — Deploy + verify

```bash
# Render auto-deploys on push. Then:
curl https://api.wah-lah.com/api/health                       # {"status":"ok",...}
curl https://api.wah-lah.com/api/onduty/status                # watchdog green
# Auth: register → login → 2FA (admin) → logout → refresh-rotation works
# Money (small amounts): checkout/create → webhook/reconcile → redemption → approve
# Gates: blocked-state IP → 403; sanctioned BTC addr → 451; kill-switch off → 503
```

Set on Render (new vars this baseline expects):

| Key | Value |
|---|---|
| `APP_ENV` | `production` |
| `TRUST_PROXY_HEADERS` | `true` |
| `GEOBLOCK_FAIL_CLOSED` | `true` |
| `BTC_MIN_CONFIRMATIONS` | `2` |
| `BTC_PAYOUT_MAX_SAT` | `500000` (tune to your max single payout) |
| `SCOUT_LEADS_TOKEN` | fresh rotated value (match Worker `LEADS_TOKEN`) |
| `ALERT_EMAILS` | monitored operator mailbox |
| `RATE_LIMIT_*` | defaults in `render.yaml` are fine |
| `BTC_FALLBACK_USD` | leave UNSET unless you accept stale-price risk |

## Rollback

- **App**: Render → service → Deploys → Rollback to the noted deploy id.
- **Repo**: the old remote is untouched until you force-push; keep a local clone
  of it until Phase 3 verification passes.
- **Secrets**: rotations are one-way by design — keep the new values in your
  password manager before revoking the old ones.
