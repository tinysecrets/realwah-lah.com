FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8001

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ca-certificates \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt \
 && python -m playwright install --with-deps chromium

COPY backend /app/backend
COPY scripts /app/scripts

EXPOSE 8001

CMD ["uvicorn", "backend.server:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
