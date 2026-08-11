from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
import os
import json
from pathlib import Path
import requests
import logging
import hmac
import hashlib

logger = logging.getLogger(__name__)

QUEUE_FILE = Path(__file__).resolve().parents[1] / 'tmp' / 'whatsapp_queue.jsonl'
QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)

WHATSAPP_TOKEN = os.environ.get('WHATSAPP_TOKEN', '').strip()
WHATSAPP_APP_SECRET = os.environ.get('WHATSAPP_APP_SECRET', '').strip()


def verify_signature(body: bytes, signature_header: str) -> bool:
    """Verify X-Hub-Signature-256 using WHATSAPP_APP_SECRET"""
    if not WHATSAPP_APP_SECRET:
        return True
    if not signature_header:
        return False
    try:
        sig = signature_header.split('sha256=')[-1]
        mac = hmac.new(WHATSAPP_APP_SECRET.encode('utf-8'), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(mac, sig)
    except Exception:
        return False


def build_whatsapp_router():
    router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

    @router.post('/webhook')
    async def whatsapp_webhook(request: Request):
        body = await request.body()
        sig = request.headers.get('X-Hub-Signature-256', '')
        if not verify_signature(body, sig):
            logger.warning('WhatsApp webhook signature verification failed')
            raise HTTPException(status_code=403, detail='Invalid signature')
        try:
            payload = json.loads(body.decode('utf-8'))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f'Invalid JSON: {e}')

        # WhatsApp messages are nested; extract message objects
        entries = payload.get('entry', [])
        for entry in entries:
            changes = entry.get('changes', [])
            for change in changes:
                value = change.get('value', {})
                messages = value.get('messages') or []
                for msg in messages:
                    from_user = msg.get('from') or ''
                    msg_type = msg.get('type')
                    text = ''
                    if msg_type == 'text':
                        text = msg.get('text', {}).get('body', '')
                    elif msg_type in ('image', 'audio', 'video', 'document'):
                        # handle media
                        media = msg.get(msg_type, {})
                        media_id = media.get('id')
                        # attempt to fetch media if token present
                        saved_asset = None
                        if media_id and WHATSAPP_TOKEN:
                            try:
                                # Get media URL
                                phone_id = os.environ.get('WHATSAPP_PHONE_ID', '')
                                # Fetch media info
                                info_url = f'https://graph.facebook.com/v17.0/{media_id}?access_token={WHATSAPP_TOKEN}'
                                rinfo = requests.get(info_url, timeout=10)
                                if rinfo.status_code == 200:
                                    j = rinfo.json()
                                    media_url = j.get('url')
                                    if media_url:
                                        r = requests.get(media_url, headers={'Authorization': f'Bearer {WHATSAPP_TOKEN}'}, timeout=20)
                                        if r.status_code == 200:
                                            assets_dir = Path(__file__).resolve().parents[2] / 'frontend' / 'public' / 'assets' / 'game_assets'
                                            assets_dir.mkdir(parents=True, exist_ok=True)
                                            local_name = media_url.split('/')[-1].split('?')[0]
                                            save_path = assets_dir / local_name
                                            save_path.write_bytes(r.content)
                                            saved_asset = str(save_path.relative_to(Path.cwd()))
                                            logger.info(f"Saved whatsapp media to {save_path}")
                            except Exception as e:
                                logger.warning(f'Failed to fetch whatsapp media: {e}')
                        record = {"received_at": int(__import__('time').time()), "from_user": from_user, "type": msg_type, "text": text}
                        if saved_asset:
                            record['saved_asset'] = saved_asset
                        with QUEUE_FILE.open('a') as fh:
                            fh.write(json.dumps(record) + "\n")
        return JSONResponse({"status": "ok"})

    return router
