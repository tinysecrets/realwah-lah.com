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
import os
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

# Deposits live in one of two collections depending on the rail; distribution
# tasks point at either. Status writes touch whichever holds the deposit.
DEPOSIT_COLLECTIONS = ("btc_deposits", "manual_deposits")


def overdue_hours() -> float:
    """Hours an awaiting task may sit before it counts as overdue."""
    try:
        return max(0.5, float(os.environ.get("DISTRIBUTOR_OVERDUE_HOURS", "4")))
    except ValueError:
        return 4.0


def _coll(db, name: str):
    """Resolve a collection by getitem (Motor) or attribute (test fakes)."""
    try:
        return db[name]
    except Exception:
        return getattr(db, name, None)


async def _touch_deposit_transfer(db, deposit_id: str, update: dict) -> None:
    """Write pool_transfer_* fields to whichever collection holds the deposit."""
    if not deposit_id:
        return
    for coll in DEPOSIT_COLLECTIONS:
        try:
            handle = _coll(db, coll)
            if handle is None:
                continue
            res = await handle.update_one({"id": deposit_id}, {"$set": update})
            if res.modified_count:
                return
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("deposit touch failed %s/%s: %s", coll, deposit_id, e)


def _task_age_hours(doc) -> float:
    try:
        created = datetime.fromisoformat(doc.get("created_at") or "")
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - created).total_seconds() / 3600)
    except (ValueError, TypeError):
        return 0.0


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
    platform_amount: Optional[float] = None,
    tx_hash: Optional[str] = None,
    game_id: Optional[str] = None,
) -> str:
    """Queue a manual-distribution task. Returns the task id.

    Safe to call from a webhook retry: if a task already exists for the deposit
    it is a no-op returning the existing id.

    Units: ``amount_credits`` is INTERNAL (2,200); ``platform_amount`` is what
    the operator actually types into the game backend in DOLLARS (22.00).
    Computed here when omitted so every caller gets it right by default.
    """
    existing = await db.distribution_tasks.find_one({"deposit_id": deposit_id})
    if existing:
        return str(existing["_id"])

    from config.currency_config import credits_to_platform_amount
    if platform_amount is None:
        platform_amount = credits_to_platform_amount(amount_credits)

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
        "platform_amount": float(platform_amount),
        "platform_unit": "USD",
        "tx_hash": tx_hash,
        "status": STATUS_AWAITING,
        "created_at": now,
        "updated_at": now,
    }
    result = await db.distribution_tasks.insert_one(doc)
    task_id = str(result.inserted_id)
    logger.info(
        "self-distributor task queued: task=%s deposit=%s platform=%s recipient=%s "
        "credits=%s platform_amount=%s",
        task_id, deposit_id, platform, recipient_username,
        doc["amount_credits"], doc["platform_amount"],
    )
    return task_id


def _task_view(doc: Dict[str, Any]) -> Dict[str, Any]:
    age = _task_age_hours(doc)
    # Backfill for tasks queued before platform_amount existed.
    platform_amount = doc.get("platform_amount")
    if platform_amount is None:
        from config.currency_config import credits_to_platform_amount
        platform_amount = credits_to_platform_amount(doc.get("amount_credits") or 0)
    return {
        "id": str(doc["_id"]),
        "age_hours": round(age, 1),
        "overdue": bool(doc.get("status") == STATUS_AWAITING and age >= overdue_hours()),
        "platform_amount": platform_amount,
        "platform_unit": doc.get("platform_unit", "USD"),
        "send_instruction": (
            f"Send ${float(platform_amount):.2f} to '{doc.get('recipient_username')}' "
            f"on {doc.get('platform')}"
        ),
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
    await _touch_deposit_transfer(db, deposit_id, {
        "pool_transfer_status": "done",
        "pool_transfer_message": f"Sent by {admin_email} (self-distributor)",
        "pool_transfer_completed_at": now,
        "self_distributor": {"task_id": task_id, "confirmed_by": admin_email},
    })

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
    await _touch_deposit_transfer(db, deposit_id, {
        "pool_transfer_status": "failed",
        "pool_transfer_message": f"Self-distributor failed: {reason or 'see task'}",
        "pool_transfer_completed_at": now,
    })
    return True, "Task marked failed."


async def retry_task(db, task_id: str, admin_email: str) -> Tuple[bool, str]:
    """Re-queue a failed task (failed -> awaiting_send).

    Atomic compare-and-set; the deposit flips back to awaiting_manual_send
    so the whole pipeline agrees the credits still need sending.
    """
    doc = await _find_task(db, task_id)
    if not doc:
        return False, "Task not found"
    if doc.get("status") != STATUS_FAILED:
        return False, f"Only failed tasks can be retried (task is {doc.get('status')})"

    now = datetime.now(timezone.utc).isoformat()
    result = await db.distribution_tasks.update_one(
        {"_id": doc["_id"], "status": STATUS_FAILED},
        {"$set": {
            "status": STATUS_AWAITING,
            "failed_reason": "",
            "retried_by": admin_email,
            "retried_at": now,
            "updated_at": now,
        }},
    )
    if result.modified_count == 0:
        return False, "Task was already processed"
    await _touch_deposit_transfer(db, doc.get("deposit_id"), {
        "pool_transfer_status": "awaiting_manual_send",
        "pool_transfer_message": f"Re-queued by {admin_email}",
    })
    logger.info("self-distributor retried: task=%s by=%s", task_id, admin_email)
    return True, "Task re-queued for sending."


async def cancel_task(db, task_id: str, admin_email: str, reason: str = "") -> Tuple[bool, str]:
    """Terminal-cancel an awaiting or failed task (no credits move).

    Used for duplicates and operator error. Terminal on purpose: if the
    credits DO still need sending, reconcile a fresh deposit instead of
    resurrecting a cancelled row — the ledger stays unambiguous.
    """
    doc = await _find_task(db, task_id)
    if not doc:
        return False, "Task not found"
    if doc.get("status") not in (STATUS_AWAITING, STATUS_FAILED):
        return False, f"Task is already {doc.get('status')} — cannot cancel"

    now = datetime.now(timezone.utc).isoformat()
    result = await db.distribution_tasks.update_one(
        {"_id": doc["_id"], "status": doc.get("status")},
        {"$set": {
            "status": STATUS_CANCELLED,
            "cancelled_by": admin_email,
            "cancel_reason": (reason or "")[:500],
            "cancelled_at": now,
            "updated_at": now,
        }},
    )
    if result.modified_count == 0:
        return False, "Task was already processed"
    await _touch_deposit_transfer(db, doc.get("deposit_id"), {
        "pool_transfer_status": "cancelled",
        "pool_transfer_message": f"Cancelled by {admin_email}: {reason or 'see task'}",
        "pool_transfer_completed_at": now,
    })
    logger.info("self-distributor cancelled: task=%s by=%s", task_id, admin_email)
    return True, "Task cancelled."


async def summary(db) -> Dict[str, Any]:
    """Counts + credits volume + today's distributor P&L, for the admin widget."""
    total = await db.distribution_tasks.count_documents({})
    awaiting = await db.distribution_tasks.count_documents({"status": STATUS_AWAITING})
    done = await db.distribution_tasks.count_documents({"status": STATUS_DONE})
    failed = await db.distribution_tasks.count_documents({"status": STATUS_FAILED})
    cancelled = await db.distribution_tasks.count_documents({"status": STATUS_CANCELLED})

    awaiting_docs = await db.distribution_tasks.find(
        {"status": STATUS_AWAITING}
    ).sort("created_at", 1).to_list(10_000)
    from config.currency_config import credits_to_platform_amount
    pending_credits = sum((d.get("amount_credits") or 0) for d in awaiting_docs)
    cutoff = overdue_hours()
    overdue_docs = [d for d in awaiting_docs if _task_age_hours(d) >= cutoff]
    overdue_credits = sum((d.get("amount_credits") or 0) for d in overdue_docs)
    oldest = awaiting_docs[0] if awaiting_docs else None

    today = datetime.now(timezone.utc).date().isoformat()
    done_today_docs = await db.distribution_tasks.find({"status": STATUS_DONE}).to_list(10_000)
    done_today_docs = [d for d in done_today_docs if (d.get("sent_at") or "") >= today]
    sent_today_credits = sum((d.get("amount_credits") or 0) for d in done_today_docs)
    pending_platform_amount = credits_to_platform_amount(pending_credits)
    overdue_platform_amount = credits_to_platform_amount(overdue_credits)
    sent_today_platform = credits_to_platform_amount(sent_today_credits)

    fees_today = 0.0
    try:
        fee_rows = await db.revenue_ledger.find({}).to_list(10_000)
        fees_today = sum(
            float(r.get("fee_usd") or 0)
            for r in fee_rows if (r.get("created_at") or "") >= today
        )
    except Exception:  # pragma: no cover - defensive
        logger.warning("summary fee scan failed")

    mode = await get_mode(db)
    return {
        "mode": mode,
        "statuses": {
            "awaiting_send": awaiting,
            "done": done,
            "failed": failed,
            "cancelled": cancelled,
            "total": total,
        },
        "pending_credits": pending_credits,
        "pending_platform_amount": pending_platform_amount,
        "overdue": {
            "count": len(overdue_docs),
            "credits": overdue_credits,
            "platform_amount": overdue_platform_amount,
            "hours": cutoff,
        },
        "oldest_awaiting": _task_view(oldest) if oldest else None,
        "today": {
            "tasks_done": len(done_today_docs),
            "credits_sent": sent_today_credits,
            "platform_sent": sent_today_platform,
            "fees_usd": round(fees_today, 2),
        },
        "queue_instruction": (
            "On the game backend, send the PLATFORM amount (dollars) to the "
            "player's username — NOT the internal credits. Then POST "
            "confirm-sent on each task."
        ),
    }