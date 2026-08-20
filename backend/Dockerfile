# syntax=docker/dockerfile:1.6

FROM python:3.11.16-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

RUN python -m venv .venv
COPY backend/requirements.txt ./
RUN .venv/bin/pip install -r requirements.txt

FROM python:3.11.16-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY --from=builder /app/.venv .venv/
COPY backend/ ./

EXPOSE 8001

CMD [".venv/bin/uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001"]
