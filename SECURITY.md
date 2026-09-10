# Security Policy — WAH-LAH

## The rules (short version)

1. **No secrets in git. Ever.** Payment tags, API keys, tokens, xprvs, connection
   strings, and personal mailboxes live in host secret stores (Render env,
   Cloudflare Worker secrets, Vercel env) — never in code, docs, or tests.
2. **Compliance gates fail CLOSED.** Geoblock, OFAC, KYC, and webhook signature
   checks deny on error. Any PR that flips a gate to fail-open must be rejected.
3. **Money moves need two facts:** a human approval AND the on-chain/KYC record
   to match. Kill switches (`btc_payouts_enabled`, `POOL_*_ENABLED`) default off.
4. **Hot-wallet discipline:** the BTC payout sender spends ONLY `m/0'/0/0`.
   Keep it small, sweep the rest to cold storage, cap with `BTC_PAYOUT_MAX_SAT`.

## Reporting a vulnerability

Email the operator security mailbox (see `ALERT_EMAILS` on Render). Include:

- What you found and where (file + line, or URL + request)
- Impact you were able to demonstrate (do NOT move real funds, do NOT exfiltrate user data)
- Suggested fix, if you have one

We will acknowledge within 48 hours. Please do not disclose publicly until a
fix is deployed.

## Secret inventory (where each credential lives)

| Secret | Lives in | Rotated via |
|---|---|---|
| `JWT_SECRET` | Render env | Render dashboard → rotate → redeploy (all sessions invalidate) |
| `MONGO_URL` / `MONGODB_URI` | Render env | Atlas → rotate password → update Render |
| `BTC_PAYOUT_XPRV` | Render env | Sweep funds to a NEW wallet, replace xprv (see below) |
| `SCOUT_LEADS_TOKEN` | Render env + Worker secret | Generate → set BOTH → verify `/run` + lead ingest |
| `ADMIN_TOKEN` (scout-force) | Worker secret | `wrangler secret put ADMIN_TOKEN` |
| `BLOCKCYPHER_TOKEN` | Render env | accounts.blockcypher.com → update Render |
| `RESEND_API_KEY` | Render env | resend.com/api-keys → update Render |
| `CEREBRAS_API_KEY` | Render env | cloud.cerebras.ai → update Render |
| `PERSONA_*` | Render env | withpersona.com → update Render |
| `PROXY_ENCRYPTION_KEY` | Render env | ⚠️ rotation invalidates stored seat passwords — re-enter after |
| `ADMIN_PASSWORD` | Operator memory + password manager | `scripts/set_admin.py` |
| `CARD_PAYMENT_TAG` | Render env | Payment provider → update Render + fee disclosure |

## Rotating the BTC payout wallet (xprv)

The xprv cannot be "changed" — the wallet must be replaced:

1. Generate a NEW HD wallet offline (hardware wallet recommended).
2. Record its `m/0'/0/0` funding address; verify `funding_address(0)` matches after step 4.
3. Sweep ALL funds from the old funding address to the new one.
4. Set the new xprv as `BTC_PAYOUT_XPRV` on Render, redeploy.
5. Send a tiny test payout, confirm broadcast, then resume normal approvals.
6. Destroy the old xprv material.

## CI enforcement

- `secret-scan` job (`.github/workflows/main.yml`) greps for known PII/secret
  patterns and runs `detect-secrets` against `.secrets.baseline`.
- CodeQL runs on every push to `main` plus weekly.
- Pre-commit (`detect-secrets`, `detect-private-key`, large-file guard) should
  be installed by every contributor: `pip install pre-commit && pre-commit install`.

## Production checklist (before every deploy that touches auth, money, or compliance)

- [ ] `APP_ENV=production`, `COOKIE_SECURE=true`, `CORS_ORIGINS` = wah-lah.com only
- [ ] `GEOBLOCK_FAIL_CLOSED=true`, `TRUST_PROXY_HEADERS=true`
- [ ] `BTC_MIN_CONFIRMATIONS >= 2`, `BTC_PAYOUT_MAX_SAT` set
- [ ] `SCOUT_LEADS_TOKEN` set on Render AND Worker (matching, high-entropy)
- [ ] `ALERT_EMAILS` set (operator mailbox that is actually monitored)
- [ ] No `dev_token` / debug paths reachable (gated on explicit non-prod `APP_ENV`)
- [ ] `python -m compileall -q backend` + self-contained pytest suites green
