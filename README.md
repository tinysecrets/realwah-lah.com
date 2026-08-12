1| # WAH-LAH (wah-lah.com)
2| 
3| Monorepo for the WAH-LAH sweepstakes platform (backend + frontend) and the Genie Sidekick sidecar.
4| 
5| Repo layout
6| 
7| ```
8| backend/              FastAPI app (server.py)
9| frontend/             React SPA (Cloudflare Pages)
10| genie-sidekick/       sidecar agent (optional)
11| scripts/              deployment helpers
12| backend/.env.example   environment template (do not commit secrets)
13| ```
14| 
15| Quick start (local)
16| 
17| ```bash
18| # Backend
19| cp backend/.env.example backend/.env
20| # Edit backend/.env — set MONGODB_URI or other runtime secrets
21| pip install -r backend/requirements.txt
22| cd backend && PYTHONPATH=. uvicorn server:app --reload --port 8001
23| 
24| # Frontend (separate terminal)
25| cp frontend/.env.production.example frontend/.env
26| # Set REACT_APP_BACKEND_URL=http://localhost:8001
27| cd frontend && yarn install && yarn start
28| ```
29| 
30| Recommended Python runtime for development
31| 
32| We recommend using Python 3.11.16 for local development to avoid build failures when compiling extensions (pydantic-core uses PyO3 and may not build cleanly on newer CPython like 3.14).
33| 
34| Using pyenv (recommended):
35| 
36| ```bash
37| pyenv install 3.11.16
38| pyenv local 3.11.16
39| python -m venv .venv
40| source .venv/bin/activate
41| python -m pip install --upgrade pip setuptools wheel
42| pip install -r backend/requirements.txt
43| ```
44| 
45| Docker (isolated test):
46| 
47| ```bash
48| docker run --rm -it -v "$PWD/backend":/app -w /app python:3.11.16-slim bash -c "apt-get update && apt-get install -y build-essential && python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt"
49| ```
50| 
51| Deploy notes
52| 
53| - Keep secrets (OPENROUTER_API_KEY, GITHUB_TOKEN, WHATSAPP_TOKEN, etc.) in host/CI secret stores — do NOT commit them.
54| - Use `backend/.env.example` as a template; a helper script exists at `backend/scripts/populate_env_from_env.sh` to write backend/.env from runtime environment variables (local only).
55| 
56| Health check
57| 
58| ```
59| curl http://localhost:8001/api/health
60| # {"status":"ok","service":"wah-lah",...}
61| ```
62| 
63| Contributing
64| 
65| - Make feature branches, open PRs against `main`, and run the suite locally before submitting.
66| 
67| Contact
68| 
69| - Admin: REDACTED_EMAIL
70| 

