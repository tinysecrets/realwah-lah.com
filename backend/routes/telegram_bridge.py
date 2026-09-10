from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
import os
import json
from pathlib import Path
import requests
import logging

logger = logging.getLogger(__name__)

QUEUE_FILE = Path(__file__).resolve().parents[1] / 'tmp' / 'telegram_queue.jsonl'
QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()


def build_telegram_router():
    router = APIRouter(prefix="/telegram", tags=["telegram"])

    @router.post('/webhook')
    async def telegram_webhook(request: Request):
        # Optional secret token header check (Telegram supports X-Telegram-Bot-Api-Secret-Token)
        webhook_secret = os.environ.get('TELEGRAM_WEBHOOK_SECRET', '').strip()
        if webhook_secret:
            header_secret = request.headers.get('X-Telegram-Bot-Api-Secret-Token')
            if header_secret != webhook_secret:
                logger.warning('Incoming Telegram webhook secret mismatch')
                raise HTTPException(status_code=403, detail='Forbidden')

        if not TELEGRAM_BOT_TOKEN:
            logger.warning('Telegram token not configured; webhook will accept payloads but will not fetch files')
        try:
            payload = await request.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

        # extract basic sender info and enforce allowed users if configured
        message = payload.get('message') or payload.get('edited_message') or {}
        user = message.get('from', {}) or {}
        username = (user.get('username') or '').lower()
        user_id = str(user.get('id') or '')
        allowed = os.environ.get('TELEGRAM_ALLOWED_USERS', '').strip()
        if allowed:
            allowed_set = {s.strip().lower() for s in allowed.split(',') if s.strip()}
            if username not in allowed_set and user_id not in allowed_set:
                logger.info(f'Telegram user not allowed: {username} ({user_id})')
                # Do not enqueue; respond with forbidden
                raise HTTPException(status_code=403, detail='User not allowed')

        # Save the raw update to the queue for later processing
        record = {"received_at": int(__import__('time').time()), "update": payload, 'from_user': {'username': username, 'id': user_id}}

        # If there's a photo, attempt to fetch the largest version and store it in assets
        try:
            if 'photo' in message and TELEGRAM_BOT_TOKEN:
                photos = message['photo']
                # photo list sorted by size asc; pick last
                file_id = photos[-1]['file_id']
                # get file path
                tfetch = requests.get(f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile?file_id={file_id}', timeout=10)
                if tfetch.status_code == 200:
                    j = tfetch.json()
                    file_path = j.get('result', {}).get('file_path')
                    if file_path:
                        file_url = f'https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}'
                        r = requests.get(file_url, timeout=20)
                        if r.status_code == 200:
                            assets_dir = Path(__file__).resolve().parents[2] / 'frontend' / 'public' / 'assets' / 'game_assets'
                            assets_dir.mkdir(parents=True, exist_ok=True)
                            local_name = file_path.split('/')[-1]
                            save_path = assets_dir / local_name
                            save_path.write_bytes(r.content)
                            logger.info(f"Saved telegram photo to {save_path}")
                            record['saved_asset'] = str(save_path.relative_to(Path.cwd()))
        except Exception as e:
            logger.warning(f"Failed to fetch telegram file: {e}")

        # append to queue
        with QUEUE_FILE.open('a') as fh:
            fh.write(json.dumps(record) + "\n")

        return JSONResponse({"ok": True, "queued": True})

    return router
