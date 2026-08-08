<<<<<<< HEAD
# syntax=docker/dockerfile:1.6
# WAH-LAH backend — Fly.io deployment
# Builds only the wah-lah FastAPI backend. Genie Sidekick is a separate Fly app.

FROM python:3.12.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8001

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates tini \
    && rm -rf /var/lib/apt/lists/*

# Python deps first (better layer caching)
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Backend code
COPY backend/ ./

# Non-root user
RUN useradd -u 10001 -m wahlah && chown -R wahlah:wahlah /app
USER wahlah

EXPOSE 8001

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001"]
=======
# Use the official lightweight Python image
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Copy requirements from the local backend folder into the container
COPY backend/requirements.txt /app/requirements.txt

# Install dependencies
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the rest of the backend application code
COPY backend/ /app/

# Expose the port the app runs on
EXPOSE 8001

# Command to run the application
CMD ["python", "main.py"]
>>>>>>> codespace-trout
