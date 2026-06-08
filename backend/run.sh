#!/bin/bash
pkill -9 -f uvicorn
docker stop local-mongo 2>/dev/null
docker rm local-mongo 2>/dev/null
docker run -d --name local-mongo 2>/dev/null
python3 -m uvicorn server:app --host 0.0.0.0 --port 8000
