# WAH-LAH — Operator Runbook (daily money flow)

> Internal operator doc. Contains NO secrets — every credential referenced here
> lives in Render / Cloudflare / Vercel dashboards.

## Topology (live)

```text
wah-lah.com ──► Vercel (React SPA, frontend/)
api.wah-lah.com ──► Cloudflare Worker (wah-lah-api-proxy/) ──► Render web service ──► MongoDB Atlas
scout-force Worker ──(cron 6h)──► POST /api/admin/scout/leads (SCOUT_LEADS_TOKEN)
```

## Daily (30 min — the distributor loop)

1. **Morning glance:** `GET /api/admin/stats` — mode, today's deposits/fees,
   awaiting queue depth, payout holds, KYC load. One call, whole business.
2. **Cash App / Chime queue:** confirm each inbound payment in the provider app,
   then reconcile (idempotent on `receipt` — safe to retry/double-click):
   ```bash
   POST /api/admin/cashtag/reconcile
   {"user_id": "<id>", "amount_usd": 25, "source": "cashapp",
    "receipt": "CA-<provider-confirmation-#>", "platform": "Fire Kirin",
    "note": "verified in app"}
   ```
   System credits NET after the `cashtag` fee, writes the fee to
   `revenue_ledger`, and — in manual mode — queues a distributor task.
   Whale comp: same call with `"apply_fee": false` (0% fee, audited).
3. **Distributor queue:** `GET /api/ext/distributor/summary` — overdue count,
   oldest awaiting, today's credits sent + fees. Pull `GET
   /api/ext/distributor/queue`, send the **`platform_amount` dollars** on the
   game backend by hand (e.g. a $25 Cash App deposit net of fee = 2,200
   internal credits = **send $22.00** — games display dollars), then
   `POST .../confirm-sent`. Can't send → `mark-failed`; ready again → `retry`;
   duplicate → `cancel`.
4. **Redemption queue:** `GET /api/ext/compliance/admin/payouts/queue` — approve or
   reject. Approval auto-sends BTC ONLY when `btc_payouts_enabled` is on; otherwise
   it 503s and you pay manually.
5. **Gift cards:** fulfill pending redemptions from the admin queue.
6. **P&L glance:** `GET /api/admin/revenue/summary?days=1` and `?days=7`.
   Full money trail anytime: `GET /api/admin/transactions`.

## Weekly

- Review `admin_access_log` + `geoblock_events` + `aml_events` + `ofac_hits` for anomalies.
- Check hot-wallet balance vs `BTC_PAYOUT_MAX_SAT`; sweep surplus to cold storage.
- Verify Atlas backups + `ALERT_EMAILS` delivery (send a test alert).

## Monthly

- P&L close from `revenue_ledger`; reconcile against provider statements.
- Rate review (`GET /api/admin/revenue/settings`); promos via `POST` (capped at 50%).
- Rotate one credential class per month (see `SECURITY.md` inventory).
- Review `BLOCKED_STATES` + KYC thresholds with counsel as needed.

## Incident playbooks

**Suspected account takeover / leaked session:**
`POST /api/auth/logout` (revokes that session) → if widespread, run
`revoke_all_user_tokens(user_id)` via admin shell → force password reset.

**Price oracle down:** pricing halts loudly (no silent fallback unless
`BTC_FALLBACK_USD` is explicitly set). Deposits/payouts pause until Coinbase or
Kraken recovers. Do NOT set a stale fallback during volatility.

**Hot wallet compromise:** stop approvals → sweep remaining funds to cold storage
from a clean machine → rotate xprv per `SECURITY.md` → audit `payout_gateway_result`.

**Backend down:** the Worker returns generic 502s; check Render deploys + Atlas
status; roll back via Render → Deploys → Rollback.

## Key endpoints

| Purpose | Endpoint |
|---|---|
| Liveness | `GET /api/health` |
| Watchdog | `GET /api/onduty/status` |
| Revenue | `GET /api/admin/revenue/summary?days=N` |
| Rate tune | `GET/POST /api/admin/revenue/settings` |
| Payout queue | `GET /api/ext/compliance/admin/payouts/queue` |
| Payout action | `POST /api/ext/compliance/admin/payouts/action` |
| KYC queue | `GET /api/ext/compliance/admin/kyc/queue` |
| Pool resync | `POST /api/ext/pool/admin/resync` |
| Rebalance (dry default) | `POST /api/ext/pool/admin/health/rebalance?dry_run=true` |
| Scout leads | `GET /api/admin/scout/leads` |
| Feature flags | `GET/PATCH /api/ext/compliance/admin/feature-flags` |
| Reconcile CashApp/Chime | `POST /api/admin/cashtag/reconcile` |
| Users / credit adjust | `GET /api/admin/users`, `PATCH /api/admin/users/{id}` |
| Money feed | `GET /api/admin/transactions` (kinds: purchase, btc_deposit, manual_deposit, redemption, grant, adjustment) |
| Distributor stats | `GET /api/admin/stats` |
| Queue retry/cancel | `POST /api/ext/distributor/queue/{id}/retry`, `.../cancel` |
| Deposit tag + fees | `GET /api/payment/card-info` |
| Public proof stats | `GET /api/public/stats` (landing band; cached 60s) |
| Public payout feed | `GET /api/public/payouts/recent?limit=12` (masked, completed-only) |
| Player ledger | `GET /api/user/transactions?kind=&skip=&limit=` (same feed as admin, scoped + stripped) |
| Genie chat | `POST /api/genie/chat` {session_id?, message} (needs `CEREBRAS_API_KEY` or fallback) |
| Ticket respond | `POST /api/admin/analytics/support-tickets/{id}/respond` {message} |
| Ticket detail (player) | `GET /api/user/support/tickets/{id}` (owner-scoped thread) |
