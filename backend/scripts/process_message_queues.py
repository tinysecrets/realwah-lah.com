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

    # Atomically rotate the queue file to avoid losing entries appended during processing.
    pid = os.getpid()
    processing_file = qfile.with_name(qfile.name + f'.processing.{pid}')
    try:
        # Move the current queue to a processing file (atomic on most OSes)
        qfile.replace(processing_file)
        # Create a new empty queue file at the original path so webhooks can append
        qfile.open('a').close()
        logger.info(f'Rotated queue {qfile} -> {processing_file}')
    except Exception as e:
        logger.warning(f'Queue rotation failed, will read in-place: {e}')
        processing_file = qfile

    recs = []
    with processing_file.open('r') as fh:
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

    # remove processing file after processing (do not remove the live queue)
    try:
        if processing_file.exists() and processing_file != qfile:
            processing_file.unlink()
            logger.info(f'Removed processing file {processing_file}')
    except Exception as e:
        logger.warning(f'Could not remove processing file {processing_file}: {e}')

logger.info(f'Processed {processed} updates')
print(f'Processed {processed} updates')
