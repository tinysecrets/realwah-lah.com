<<<<<<< HEAD
# WAH-LAH Monorepo

**Unified deployment: `wah-lah` on Fly.io**

Both WAH-LAH (backend + frontend) and Genie Sidekick run from this single repo.

```
wah-lah.com      → Cloudflare Pages (React)
api.wah-lah.com  → Fly.io (FastAPI + Genie)
```

## Deploy to Fly.io

All secrets already set on `wah-lah`. Just deploy:

```bash
flyctl deploy -a wah-lah
```

## Local Dev

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn server:app --reload --port 8001
```

### WAH-LAH Frontend
```bash
cd frontend
yarn install && yarn start
```

### Genie Sidekick (Local)
```bash
# Backend
cd genie-sidekick/backend
pip install -r requirements.txt
uvicorn server:app --reload --port 8000

# Frontend (separate terminal)
cd genie-sidekick/frontend
npm install && npm run dev
```

## Old Apps (Safe to Delete)

These are suspended and no longer used:

```bash
flyctl apps destroy realwah-lah-com
flyctl apps destroy realwah-lah-com-sfupba
flyctl apps destroy genie-sidekick
```

Do NOT delete until `wah-lah` deployment confirms working.
=======
# WAH-LAH (wah-lah.com)

Monorepo for the WAH-LAH sweepstakes platform.

| Layer | Host | Path |
|-------|------|------|
| Frontend | Cloudflare Pages | `frontend/` |
| Backend API | Fly.io (`wah-lah`) | `backend/` |
| Database | MongoDB Atlas | via `MONGO_URL` secret |

```
wah-lah.com      → Cloudflare Pages (React SPA)
api.wah-lah.com  → Fly.io (FastAPI + Playwright)
                       ↓
                 MongoDB Atlas
```

## Quick start (local)

```bash
# Backend
cp .env-examples/.wahlah-secrets.env.example backend/.env
# Edit backend/.env — use a local MongoDB or Atlas URI
pip install -r backend/requirements.txt
cd backend && uvicorn server:app --reload --port 8001

# Frontend (separate terminal)
cp frontend/.env.production.example frontend/.env
# Set REACT_APP_BACKEND_URL=http://localhost:8001
yarn --cwd frontend install
yarn --cwd frontend start
```

## Production deploy

### 1. Secrets file (never commit)

```bash
bash scripts/setup-secrets.sh
# Edit .wahlah-secrets.env with Atlas URI, Stripe, Resend, Cerebras, Cloudflare
bash scripts/check-deploy-readiness.sh
```

Owner defaults in the template:
- Admin email: `REDACTED_EMAIL`
- Cash App tag: `REDACTED_CASHTAG`

### 2. Backend → Fly.io

```bash
flyctl auth login
flyctl apps create wah-lah   # first time only
bash scripts/deploy-all.sh
```

Or step by step:

```bash
npm run deploy:secrets
npm run deploy:backend
```

### 3. Frontend → Cloudflare Pages (`wah-lah.com`)

Full guide: [`docs/deployment/CLOUDFLARE_PAGES.md`](docs/deployment/CLOUDFLARE_PAGES.md)

Cloudflare dashboard → **Workers & Pages** → Connect Git → `tinysecrets/realwah-lah.com`:

| Setting | Value |
|---------|-------|
| Project name | `wah-lah` |
| Build command | `cd frontend && yarn install --frozen-lockfile && yarn build` |
| Output directory | `frontend/build` |
| `REACT_APP_BACKEND_URL` | `https://api.wah-lah.com` |
| `NODE_VERSION` | `20` |
| `CI` | `false` |

Custom domains: `wah-lah.com` + `www.wah-lah.com`

Verify after deploy:

```bash
bash scripts/verify-wahlah-domain.sh
```

### 4. DNS (Cloudflare)

| Type | Name | Target | Proxy |
|------|------|--------|-------|
| CNAME | `@` | `<project>.pages.dev` | Proxied |
| CNAME | `www` | `<project>.pages.dev` | Proxied |
| CNAME | `api` | `wah-lah.fly.dev` | DNS only |

```bash
flyctl certs add api.wah-lah.com -a wah-lah
```

## Repo layout

```
backend/              FastAPI app (server.py)
frontend/             React 19 + CRA → Cloudflare Pages
scripts/              deploy-*.sh, setup-secrets.sh, run_local.sh
.env-examples/        secret templates (safe to commit)
infra/                render.yaml (alternate), legacy fly paths
genie-sidekick/       separate Boss Genie sidecar (optional)
fly.toml              Fly.io config (repo root)
Dockerfile            Backend production image
docs/deployment/      Extended guides
memory/               PRD, roadmap, changelog
tests/                manual + integration tests
```

Save and push:

```bash
bash scripts/save_and_push.sh "your commit message"
```

## Health check

```bash
curl https://api.wah-lah.com/api/health
# {"status":"ok","service":"wah-lah",...}
```
>>>>>>> codespace-trout
