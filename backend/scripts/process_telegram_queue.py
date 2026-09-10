#!/usr/bin/env python3
import os
import json
from pathlib import Path
from services.agent_bridge import call_openrouter_system, apply_patch_and_create_pr
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

QUEUE_FILE = Path(__file__).resolve().parents[1] / 'tmp' / 'telegram_queue.jsonl'
if not QUEUE_FILE.exists():
    print('No queue file found; nothing to do')
    raise SystemExit(0)

processed = 0
remaining = []
with QUEUE_FILE.open('r') as fh:
    for line in fh:
        try:
            rec = json.loads(line)
            remaining.append(rec)
        except Exception:
            continue

# process sequentially
for rec in remaining:
    try:
        update = rec.get('update', {})
        # extract user text
        message = update.get('message') or update.get('edited_message') or {}
        text = message.get('text') or message.get('caption') or ''
        user = message.get('from', {})
        username = user.get('username') or user.get('first_name') or 'telegram-user'
        if not text:
            logger.info('No text in message; skipping')
            continue
        # craft prompt for OpenRouter
        prompt = f"User @{username} requested via Telegram: {text}\n\nContext: repository root is available. If the change requires adding or updating assets, include a note and list required filenames. Produce a unified git diff (patch) that implements the requested change. If change is large, prefer minimal safe edits. Respond ONLY with the patch."
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
        # apply patch and create PR
        title = f"Telegram: {text[:80]}"
        result = apply_patch_and_create_pr(patch, title)
        logger.info(f'Processed record; result: {result}')
        processed += 1
    except Exception as e:
        logger.exception('Processing error')

# clear queue after processing
if processed > 0:
    # overwrite queue (simple design: remove file)
    try:
        QUEUE_FILE.unlink()
        logger.info('Cleared processed queue')
    except Exception as e:
        logger.warning(f'Could not remove queue file: {e}')

print(f'Processed {processed} Telegram updates')
