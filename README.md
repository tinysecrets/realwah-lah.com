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
