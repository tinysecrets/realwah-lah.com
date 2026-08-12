# WAH-LAH (wah-lah.com)

Monorepo for the WAH-LAH sweepstakes platform (backend + frontend) and the Genie Sidekick sidecar.

## Repository Layout

```
backend/              FastAPI app (server.py) - main business logic and APIs
frontend/             React SPA (Cloudflare Pages) - user interface
genie-sidekick/       sidecar agent (optional) - standalone AI service
docs/                 documentation and deployment guides
tests/                integration and end-to-end tests
.env.example          root environment template
backend/.env.example  backend-specific environment template
```

## Quick Start (Local Development)

### Using npm scripts (recommended):

```bash
# Install all dependencies
npm run install

# Run backend (terminal 1)
npm run backend:run

# Run frontend (terminal 2)
npm run frontend:start

# Test health endpoint
npm run backend:health
```

### Manual setup:

**Backend:**
```bash
cp backend/.env.example backend/.env
# Edit backend/.env - set MONGODB_URI, API keys, and other secrets
pip install -r backend/requirements.txt
cd backend && PYTHONPATH=. uvicorn server:app --reload --port 8001
```

**Frontend (separate terminal):**
```bash
cp frontend/.env.production.example frontend/.env.production
# Set REACT_APP_BACKEND_URL=http://localhost:8001
cd frontend && yarn install && yarn start
```

## Recommended Python Runtime for Development

We recommend using Python 3.11.16 for local development to avoid build failures when compiling extensions (pydantic-core uses PyO3 and may not build cleanly on newer CPython like 3.14).

### Using pyenv (recommended):

```bash
pyenv install 3.11.16
pyenv local 3.11.16
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install -r backend/requirements.txt
```

### Docker (isolated test):

```bash
docker run --rm -it -v "$PWD/backend":/app -w /app python:3.11.16-slim bash -c "apt-get update && apt-get install -y build-essential && python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt"
```

## Health Check

```bash
curl http://localhost:8001/api/health
# {"status":"ok","service":"wah-lah",...}
```

## Deploy Notes

- Keep secrets (OPENROUTER_API_KEY, GITHUB_TOKEN, WHATSAPP_TOKEN, etc.) in host/CI secret stores - do NOT commit them.
- Use `backend/.env.example` as a template; a helper script exists at `backend/scripts/populate_env_from_env.sh` to write backend/.env from runtime environment variables (local only).

## Contributing

- Make feature branches, open PRs against `main`, and run the suite locally before submitting.
- Run health checks and tests before pushing: `npm run backend:health` and `npm run backend:test`

## Contact

- Admin: REDACTED_EMAIL
