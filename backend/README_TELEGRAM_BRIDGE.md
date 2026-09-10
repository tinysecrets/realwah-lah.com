WAH-LAH Telegram → Agent Bridge

Overview

This bridge accepts Telegram messages (and media) and converts natural-language edit requests into safe code edits via OpenRouter. Edits are applied in an isolated branch, a build/tests pass are attempted, and a GitHub PR is created for human review.

Quick start

1. Copy example env
   cp backend/.env.example backend/.env
   Edit backend/.env and set required values:
   - TELEGRAM_BOT_TOKEN (optional, needed to fetch media attachments)
   - TELEGRAM_WEBHOOK_SECRET (recommended)
   - TELEGRAM_ALLOWED_USERS (comma-separated usernames or ids)
   - OPENROUTER_API_KEY
   - GITHUB_REPO (optional, owner/repo)
   - BRIDGE_BUILD_CMD, BRIDGE_TEST_CMD (optional overrides)

2. Configure gh CLI
   - Install GitHub CLI and authenticate: gh auth login (use a PAT with repo access) or gh auth status
   - Ensure the host repo is the same repository or set GITHUB_REPO in env

3. Register Telegram webhook (recommended)
   Use your bot token and optionally set the secret token (so requests include X-Telegram-Bot-Api-Secret-Token):
   curl -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
     -d "url=https://your-host.example.com/api/telegram/webhook" \
     -d "secret_token=${TELEGRAM_WEBHOOK_SECRET}"

4. Test processing manually
   - Send a message to your bot (from an allowed user) or POST a sample update to /api/telegram/webhook
   - Run the processor once:
     python3 backend/scripts/process_telegram_queue.py
   - If OPENROUTER_API_KEY and gh auth are configured, the script will request a patch, apply it in a branch, run build/tests, push the branch, and create a PR.
   - Inspect backend/tmp/telegram_queue.jsonl and backend/tmp/password_reset_*.html for queued items and previews.

5. Run as a worker
   - Local quick run: ./backend/run_bridge_worker.sh
   - Systemd (example): copy backend/systemd/telegram-bridge.service to /etc/systemd/system/telegram-bridge.service, edit WorkingDirectory and EnvironmentFile to your paths, then:
     sudo systemctl daemon-reload
     sudo systemctl enable --now telegram-bridge.service

Security & hardening

- Keep TELEGRAM_ALLOWED_USERS limited to trusted admins.
- Use TELEGRAM_WEBHOOK_SECRET when registering webhook to validate incoming requests.
- Review PRs before merging — the bridge intentionally creates PRs rather than writing to main.
- Add rate limiting at the reverse proxy level to prevent abuse.
- Optionally require PR approval from an additional human reviewer before merging.

Cloudflare & Render

- Store Cloudflare API tokens and zone/account IDs in your host/CI secret store (do not commit). Use these tokens for DNS updates, cache purge, or Pages deployments.
- For Render, set RENDER_API_KEY and RENDER_SERVICE_ID as secrets in Render's dashboard; use them to trigger service restarts or deployments from the bridge if desired.

CI / GitHub Actions

- Prefer storing OPENROUTER_API_KEY, GITHUB_TOKEN, and other secrets in GitHub Actions secrets (or your CI provider). Do NOT place keys in the repo.
- Example: use secrets.OPENROUTER_API_KEY and secrets.GITHUB_TOKEN in actions/workflows that may call the bridge or run automated tests.

Troubleshooting

- If PR creation fails, ensure gh is authenticated and GITHUB_REPO is set or repository remote points to GitHub.
- If OpenRouter calls fail, verify OPENROUTER_API_KEY and OPENROUTER_API_URL.
- Build/test failures are recorded in the PR branch for manual inspection.

Files of interest

- backend/routes/telegram_bridge.py — webhook and media handling
- backend/scripts/process_telegram_queue.py — processor that calls OpenRouter and applies patches
- backend/services/agent_bridge.py — Git/patch/PR logic
- backend/.env.example — env var template
- backend/run_bridge_worker.sh — simple supervisor loop
- backend/systemd/telegram-bridge.service — example systemd unit (edit before use)

