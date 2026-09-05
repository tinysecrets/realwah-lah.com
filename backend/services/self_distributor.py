"""
Self-Distributor mode: the operator IS the distributor.

When enabled, a confirmed deposit that would normally auto-route through the
third-party proxy pool (``execute_pool_transfer``) instead creates a manual
``distribution_tasks`` record. The operator pulls up the queue, sends the
credits on the game backend by hand ("type a number and send"), then confirms.
WAH-LAH keeps the full margin and never buys credits wholesale from a hub.

Mode is persisted in ``distribution_settings`` (doc ``_id: "settings"``):

    {"mode": "auto" | "manual"}

Default is ``auto`` — the existing automated pool behavior is untouched until
the operator flips the toggle. Full dispatch flow stays idempotent: deposits are
guarded by ``pool_transfer_status`` (pending -> awaiting_manual_send -> done),
so concurrent webhook retries can never double-send credits.

Task lifecycle (``distribution_tasks._id`` = task id, ``status`` field):

    awaiting_send -> done          (operator confirmed they sent it)
    awaiting_send -> failed        (could not send; needs admin attention)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

logger = logging.getLogger(__name__)

SETTINGS_ID = "settings"
MODE_AUTO = "auto"
MODE_MANUAL = "manual"

# Statuses a task can sit in.
STATUS_AWAITING = "awaiting_send"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"


# ---------------------------------------------------------------
# Mode
# ---------------------------------------------------------------
async def get_mode(db) -> str:
    """Current distribution mode: 'auto' (proxy pool) or 'manual' (self)."""
    try:
        doc = await db.distribution_settings.find_one({"_id": SETTINGS_ID})
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("distribution_settings fetch failed: %s", e)
        return MODE_AUTO
    mode = (doc or {}).get("mode", MODE_AUTO)
    return mode if mode in (MODE_AUTO, MODE_MANUAL) else MODE_AUTO


async def set_mode(db, mode: str, updated_by: str = "system") -> Dict[str, Any]:
    """Persist the distribution mode and return the current settings doc."""
    if mode not in (MODE_AUTO, MODE_MANUAL):
        raise ValueError(f"mode must be '{MODE_AUTO}' or '{MODE_MANUAL}'")
    now = datetime.now(timezone.utc).isoformat()
    await db.distribution_settings.update_one(
        {"_id": SETTINGS_ID},
        {"$set": {"mode": mode, "updated_at": now, "updated_by": updated_by}},
        upsert=True,
    )
    return await get_settings(db)


def _coerce_mode(doc) -> str:
    mode = (doc or {}).get("mode", MODE_AUTO)
    return mode if mode in (MODE_AUTO, MODE_MANUAL) else MODE_AUTO


async def get_settings(db) -> Dict[str, Any]:
    doc = await db.distribution_settings.find_one({"_id": SETTINGS_ID}) or {}
    return {
        "mode": _coerce_mode(doc),
        "updated_by": doc.get("updated_by"),
        "updated_at": doc.get("updated_at"),
        "available_modes": [MODE_AUTO, MODE_MANUAL],
    }


# ---------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------
async def create_manual_task(
    db,
    *,
    deposit_id: str,
    user_id: str,
    user_email: str,
    platform: str,
    recipient_username: str,
    amount_credits: float,
    tx_hash: Optional[str] = None,
    game_id: Optional[str] = None,
) -> str:
    """Queue a manual-distribution task. Returns the task id.

    Safe to call from a webhook retry: if a task already exists for the deposit
    it is a no-op returning the existing id.
    """
    existing = await db.distribution_tasks.find_one({"deposit_id": deposit_id})
    if existing:
        return str(existing["_id"])

    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": uuid4().hex,
        "deposit_id": deposit_id,
        "user_id": user_id,
        "user_email": user_email,
        "platform": platform,
        "game_id": game_id or platform,
        "recipient_username": recipient_username,
        "amount_credits": float(amount_credits),
        "tx_hash": tx_hash,
        "status": STATUS_AWAITING,
        "created_at": now,
        "updated_at": now,
    }
    result = await db.distribution_tasks.insert_one(doc)
    task_id = str(result.inserted_id)
    logger.info(
        "self-distributor task queued: task=%s deposit=%s platform=%s recipient=%s credits=%s",
        task_id, deposit_id, platform, recipient_username, doc["amount_credits"],
    )
    return task_id


def _task_view(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(doc["_id"]),
        "key": doc.get("id"),
        "deposit_id": doc.get("deposit_id"),
        "user_id": doc.get("user_id"),
        "user_email": doc.get("user_email"),
        "platform": doc.get("platform"),
        "game_id": doc.get("game_id"),
        "recipient_username": doc.get("recipient_username"),
        "amount_credits": doc.get("amount_credits"),
        "tx_hash": doc.get("tx_hash"),
        "status": doc.get("status"),
        "created_at": doc.get("created_at"),
        "sent_at": doc.get("sent_at"),
        "note": doc.get("note"),
    }


async def _find_task(db, task_id: str) -> Optional[Dict[str, Any]]:
    """Resolve a task by its UUID `id` field or its Mongo ``_id`` string.

    The queue exposes ``id`` as the ObjectId string (codebase convention); callers
    may also pass the internal uuid field. Accept both.
    """
    doc = await db.distribution_tasks.find_one({"id": task_id})
    if doc:
        return doc
    try:
        from bson import ObjectId
        return await db.distribution_tasks.find_one({"_id": ObjectId(task_id)})
    except Exception:
        return None


async def list_tasks(db, status: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    query: Dict[str, Any] = {}
    if status:
        query["status"] = status
    cursor = db.distribution_tasks.find(query).sort("created_at", -1).limit(limit)
    docs = await cursor.to_list(limit)
    return [_task_view(d) for d in docs]


async def get_task(db, task_id: str) -> Optional[Dict[str, Any]]:
    doc = await _find_task(db, task_id)
    return _task_view(doc) if doc else None


async def confirm_sent(
    db, task_id: str, admin_email: str, note: str = ""
) -> Tuple[bool, str]:
    """Mark a task done after the operator physically sent the credits.

    Atomic compare-and-set ``awaiting_send -> done`` so a double confirm (or a
    raced retry) can never mark the same task twice. Also completes the deposit
    and decrements the user's playthrough balance to match the pool flow.
    """
    doc = await _find_task(db, task_id)
    if not doc:
        return False, "Task not found"
    if doc.get("status") != STATUS_AWAITING:
        return False, f"Task is already {doc.get('status')} — cannot confirm twice"

    now = datetime.now(timezone.utc).isoformat()
    result = await db.distribution_tasks.update_one(
        {"_id": doc["_id"], "status": STATUS_AWAITING},
        {"$set": {
            "status": STATUS_DONE,
            "sent_at": now,
            "confirmed_by": admin_email,
            "note": note or "",
            "updated_at": now,
        }},
    )
    if result.modified_count == 0:
        return False, "Task was already processed"

    deposit_id = doc.get("deposit_id")
    if deposit_id:
        await db.btc_deposits.update_one(
            {"id": deposit_id},
            {"$set": {
                "pool_transfer_status": "done",
                "pool_transfer_message": f"Sent by {admin_email} (self-distributor)",
                "pool_transfer_completed_at": now,
                "self_distributor": {"task_id": task_id, "confirmed_by": admin_email},
            }},
        )

    try:
        user_id = doc.get("user_id")
        if user_id:
            from bson import ObjectId
            await db.users.update_one(
                {"_id": ObjectId(user_id)},
                [{"$set": {
                    "playthrough_balance": {
                        "$max": [0, {"$subtract": ["$playthrough_balance", doc.get("amount_credits", 0)]}]
                    }
                }}],
            )
    except Exception as e:
        logger.warning("Failed to decrement playthrough for user %s: %s", doc.get("user_id"), e)

    logger.info(
        "self-distributor confirmed: task=%s deposit=%s credits=%s by=%s",
        task_id, deposit_id, doc.get("amount_credits"), admin_email,
    )
    return True, "Task marked sent. Deposit unlocked."


async def mark_failed(db, task_id: str, admin_email: str, reason: str = "") -> Tuple[bool, str]:
    """Flag a task as failed (couldn't send). Deposit surfaces as failed for admin retry."""
    doc = await _find_task(db, task_id)
    if not doc:
        return False, "Task not found"
    if doc.get("status") != STATUS_AWAITING:
        return False, f"Task is already {doc.get('status')}"

    now = datetime.now(timezone.utc).isoformat()
    result = await db.distribution_tasks.update_one(
        {"_id": doc["_id"], "status": STATUS_AWAITING},
        {"$set": {
            "status": STATUS_FAILED,
            "failed_at": now,
            "failed_reason": reason or "",
            "confirmed_by": admin_email,
            "updated_at": now,
        }},
    )
    if result.modified_count == 0:
        return False, "Task was already processed"

    deposit_id = doc.get("deposit_id")
    if deposit_id:
        await db.btc_deposits.update_one(
            {"id": deposit_id},
            {"$set": {
                "pool_transfer_status": "failed",
                "pool_transfer_message": f"Self-distributor failed: {reason or 'see task'}",
                "pool_transfer_completed_at": now,
            }},
        )
    return True, "Task marked failed."


async def summary(db) -> Dict[str, Any]:
    """Counts + credits volume, for the admin dashboard widget."""
    total = await db.distribution_tasks.count_documents({})
    awaiting = await db.distribution_tasks.count_documents({"status": STATUS_AWAITING})
    done = await db.distribution_tasks.count_documents({"status": STATUS_DONE})
    failed = await db.distribution_tasks.count_documents({"status": STATUS_FAILED})

    cursor = db.distribution_tasks.find({"status": STATUS_AWAITING}, {"amount_credits": 1})
    pending_credits = sum((d.get("amount_credits") or 0) for d in await cursor.to_list(10_000))

    mode = await get_mode(db)
    return {
        "mode": mode,
        "statuses": {
            "awaiting_send": awaiting,
            "done": done,
            "failed": failed,
            "total": total,
        },
        "pending_credits": pending_credits,
        "queue_instruction": (
            "Send credits manually on the game backend, then POST "
            "confirm-sent on each task."
        ),
    }