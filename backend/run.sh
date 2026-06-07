#!/bin/bash
pkill -9 -f uvicorn
docker stop local-mongo 2>/dev/null || true
docker rm local-mongo 2>/dev/null || true
docker run -d --name local-mongo -p 27017:27017 mongo:latest
python3 -m uvicorn server:app --host 0.0.0.0 --port 8000
