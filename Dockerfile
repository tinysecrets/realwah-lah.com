# syntax=docker/dockerfile:1.6
# WAH-LAH Gaming Hub & Sweepstakes Casino
# Unified Vite frontend + FastAPI backend in one Fly app

# ==================== Stage 1: frontend ====================
FROM node:20-slim AS frontend
WORKDIR /fe

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
# Empty backend URL → relative `/api/*` calls (same-origin, no CORS)
ENV VITE_BACKEND_URL=""
RUN npm run build

# ==================== Stage 2: backend ====================
FROM python:3.12.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    FRONTEND_DIR=/app/frontend_dist

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates tini \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
COPY --from=frontend /fe/dist /app/frontend_dist

RUN useradd -u 10001 -m wah && chown -R wah:wah /app
USER wah

EXPOSE 8001

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001"]
