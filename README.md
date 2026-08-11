# WAH-LAH (wah-lah.com)

Monorepo for the WAH-LAH sweepstakes platform (backend + frontend) and the Genie Sidekick sidecar.

Repo layout

```
backend/              FastAPI app (server.py)
frontend/             React SPA (Cloudflare Pages)
genie-sidekick/       sidecar agent (optional)
scripts/              deployment helpers
backend/.env.example   environment template (do not commit secrets)
```

Quick start (local)

```bash
# Backend
cp backend/.env.example backend/.env
# Edit backend/.env — set MONGODB_URI or other runtime secrets
pip install -r backend/requirements.txt
cd backend && PYTHONPATH=. uvicorn server:app --reload --port 8001

# Frontend (separate terminal)
cp frontend/.env.production.example frontend/.env
# Set REACT_APP_BACKEND_URL=http://localhost:8001
cd frontend && yarn install && yarn start
```

Deploy notes

- Keep secrets (OPENROUTER_API_KEY, GITHUB_TOKEN, WHATSAPP_TOKEN, etc.) in host/CI secret stores — do NOT commit them.
- Use `backend/.env.example` as a template; a helper script exists at `backend/scripts/populate_env_from_env.sh` to write backend/.env from runtime environment variables (local only).

Health check

```
curl http://localhost:8001/api/health
# {"status":"ok","service":"wah-lah",...}
```

Contributing

- Make feature branches, open PRs against `main`, and run the suite locally before submitting.

Contact

- Admin: REDACTED_EMAIL
