# syntax=docker/dockerfile:1.6
# ----------------------------------------------------------------------
# Wah-Lah unified image — React frontend + FastAPI backend in one Fly app.
#
# Stage 1 builds the React static bundle. Stage 2 is the production
# Python/Playwright runtime that serves both the API and the static SPA.
# ----------------------------------------------------------------------

# ============================ Stage 1: frontend ============================
FROM node:20-slim AS frontend

WORKDIR /fe

# install deps first for layer cache
COPY frontend/package.json frontend/yarn.lock ./
RUN yarn install --frozen-lockfile --network-timeout 600000

# Build with empty backend URL so API calls become relative `/api/...`
# (same-origin with the FastAPI server). CI=false silences ESLint
# warnings-as-errors so we don't choke on legacy hook-deps warnings.
COPY frontend/ ./
ENV REACT_APP_BACKEND_URL=""
ENV CI=false
RUN yarn build

# ============================ Stage 2: backend =============================
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    FRONTEND_DIR=/app/frontend_build

WORKDIR /app

# System packages required for Playwright + healthcheck curl
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates tini \
    && rm -rf /var/lib/apt/lists/*

# ---------- Python dependencies ----------
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
        --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/

# ---------- Playwright Chromium ----------
RUN python -m playwright install --with-deps chromium

# ---------- App code ----------
COPY backend/ ./

# ---------- React build artifacts ----------
COPY --from=frontend /fe/build /app/frontend_build

# Non-root user for safety
RUN useradd -u 10001 -m wahlah \
    && chown -R wahlah:wahlah /app /ms-playwright
USER wahlah

EXPOSE 8001

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
