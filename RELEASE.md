# Release Checklist

## Offline backend tests

Run the backend unit suite against explicit local-only configuration and a disposable MongoDB database. Do not load workstation or production `.env` values into release tests. Require the suite to report pass/skip/failure totals separately; do not treat skipped tests as passing. Current operationally sensitive areas include cryptocurrency payout/reconciliation, pool transfers, compliance, admin APIs, email, and payment webhooks.

## Integration tests

Start the API only on `127.0.0.1` with an isolated database name. Seed synthetic users with test-only credentials. Disable background pool reconciliation/resync/rebalancing and external notifications. Use fake provider clients or test-mode credentials. Never use production to exercise payouts, pool transfers, outreach, or webhook retries.

## Release gate

1. Run the backend test suite and any required frontend tests/build with lockfile-based dependencies.
2. Run syntax/type/lint checks and `git diff --check`.
3. Inspect authentication/authorization checks for admin and transfer endpoints, data migrations, payout/reconciliation changes, and secrets handling.
4. Verify production background jobs and outbound actions remain disabled unless separately approved.
5. Confirm the intended commit and deployment target; after deployment, verify health/schema readiness and re-check safety flags.

A successful health response is not proof that payout, compliance, or payment flows are safe. Keep rollback instructions and a known-good revision available.
