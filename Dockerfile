# syntax=docker/dockerfile:1.6
# WAH-LAH Monorepo — Unified deployment
# Builds: Backend (FastAPI) + Genie Sidekick (FastAPI + Vite frontend)

# ======================== Stage 1: Genie Frontend ========================
FROM node:20-slim AS genie-frontend
WORKDIR /genie-fe

COPY genie-sidekick/frontend/package*.json ./
RUN npm ci

COPY genie-sidekick/frontend/ ./
ENV VITE_BACKEND_URL=""
RUN npm run build

# ======================== Stage 2: Backend ==============================
FROM python:3.12.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8001 \
    FRONTEND_DIR=/app/genie_dist

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates tini \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ ./

# Copy genie frontend build
COPY --from=genie-frontend /genie-fe/dist /app/genie_dist

# Non-root user
RUN useradd -u 10001 -m wahlah && chown -R wahlah:wahlah /app
USER wahlah

EXPOSE 8001

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001"]
