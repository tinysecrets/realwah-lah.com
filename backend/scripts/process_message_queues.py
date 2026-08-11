#!/usr/bin/env python3
"""Process both Telegram and WhatsApp queued updates.
Reads backend/tmp/telegram_queue.jsonl and backend/tmp/whatsapp_queue.jsonl (if present),
calls OpenRouter to generate patches, applies them safely with agent_bridge, runs build/tests,
and creates PRs via gh CLI. Designed for manual run or as a worker.
"""
import os
import json
from pathlib import Path
import logging

# Ensure backend package imports resolve
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.agent_bridge import call_openrouter_system, apply_patch_and_create_pr

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('process_message_queues')

ROOT = Path(__file__).resolve().parents[1]
TELEGRAM_QUEUE = ROOT / 'tmp' / 'telegram_queue.jsonl'
WHATSAPP_QUEUE = ROOT / 'tmp' / 'whatsapp_queue.jsonl'

queues = []
if TELEGRAM_QUEUE.exists():
    queues.append(('telegram', TELEGRAM_QUEUE))
if WHATSAPP_QUEUE.exists():
    queues.append(('whatsapp', WHATSAPP_QUEUE))

if not queues:
    logger.info('No queue files found; nothing to do')
    raise SystemExit(0)

processed = 0

for qname, qfile in queues:
    logger.info(f'Processing queue: {qname} ({qfile})')
    recs = []
    with qfile.open('r') as fh:
        for line in fh:
            try:
                recs.append(json.loads(line))
            except Exception:
                continue

    for rec in recs:
        try:
            # Normalize input
            if qname == 'telegram':
                update = rec.get('update', {})
                message = update.get('message') or update.get('edited_message') or {}
                text = message.get('text') or message.get('caption') or ''
                user = message.get('from', {})
                username = user.get('username') or user.get('first_name') or 'telegram-user'
            else:  # whatsapp
                text = rec.get('text') or ''
                username = rec.get('from_user') or rec.get('from') or 'whatsapp-user'

            if not text:
                logger.info('No text in message; skipping')
                continue

            prompt = (
                f"User @{username} requested via {qname}: {text}\n\n"
                "Context: repository root is available. If the change requires adding or updating assets, include a note and list required filenames. "
                "Produce a unified git diff (patch) that implements the requested change. If change is large, prefer minimal safe edits. Respond ONLY with the patch."
            )
            logger.info('Calling OpenRouter for generated patch')
            try:
                patch = call_openrouter_system(prompt)
            except Exception as e:
                logger.error(f'OpenRouter call failed: {e}')
                continue

            # strip markdown fences if present
            if '```' in patch:
                parts = patch.split('```')
                if len(parts) >= 2:
                    patch = parts[1]

            title = f"{qname.capitalize()}: {text[:80]}"
            result = apply_patch_and_create_pr(patch, title)
            logger.info(f'Processed record; result: {result}')
            processed += 1
        except Exception:
            logger.exception('Processing error for record')

    # remove queue file after processing
    try:
        qfile.unlink()
        logger.info(f'Removed queue file {qfile}')
    except Exception as e:
        logger.warning(f'Could not remove queue file {qfile}: {e}')

logger.info(f'Processed {processed} updates')
print(f'Processed {processed} updates')
