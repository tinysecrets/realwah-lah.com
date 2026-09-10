"""Pool Pull Service — the credit loop (Phase 0).

Money flow today: a deposit is funded to the player's game account on a
platform using credits drawn from a distributor seat
(``execute_pool_transfer``). When the player later redeems Game Credits for
BTC, those platform credits can sit in their game account while BTC leaves —
a wholesale leak. ``pool_pull`` tries to reclaim the credits from the player's
game account BACK to the seat first, so redemptions self-finance.

Design rules
------------
* Best-effort only: a pull that can't happen must NEVER block, fail, or
  double-spend a redemption. If no seat is pull-capable yet the redemption
  processes exactly as it does today (wholesale payout).
* Opt-in: pulls only fire when ``POOL_PULL_ENABLED=true`` (default off).
* Auditable: every attempt is written to the ``pool_pulls`` collection and the
  redemption doc gains ``pool_pull_status`` / ``pool_pull_message`` /
  ``pool_pull_detail`` so ops can see the loop in action.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

POOL_PULL_COLLECTION = "pool_pulls"

# Statuses that represent a genuine pull attempt against the credit loop
# (as opposed to nothing to reclaim — skipped_no_platform).
PULL_ATTEMPT_STATUSES = ("done", "failed", "unsupported")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now() -> datetime:
    return _now()


def _noises(v) -> Optional[str]:
    return (v or "").strip() or None


def _enabled() -> bool:
    val = os.environ.get("POOL_PULL_ENABLED", "false").strip().lower()
    return val in ("1", "true", "yes", "on")


async def record_pull(db, doc: Dict[str, Any]) -> str:
    """Persist a single pull attempt to ``pool_pulls``. Returns the log id."""
    doc.setdefault("id", uuid.uuid4().hex)
    doc.setdefault("created_at", _now().isoformat())
    await db[POOL_PULL_COLLECTION].insert_one(dict(doc))
    return doc["id"]


async def resolve_pull_target(db, user: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], str]:
    """Determine which platform to reclaim credits from for a redemption.

    Pulls replicate the deposit flow: credits were funded to the user's
    ``game_username`` on the ``platform`` of their most recent completed
    deposit — on EITHER rail (BTC or manual Cash App/Chime) — so that is the
    target. Returns (platform, recipient, skip_reason).
    """
    recipient = _noises(user.get("game_username"))
    if not recipient:
        return None, None, "no_game_username"
    user_id = str(user.get("_id") or user.get("id") or "").strip()
    if not user_id:
        return None, None, "no_user_id"
    candidates = []
    for coll in ("btc_deposits", "manual_deposits"):
        try:
            handle = db[coll] if hasattr(db, "__getitem__") else getattr(db, coll)
            items = await handle.find(
                {"user_id": user_id, "status": "completed"}, {"platform": 1}
            ).sort("completed_at", -1).to_list(1)
            candidates.extend(items or [])
        except Exception as e:
            logger.warning("pool_pull target lookup failed on %s: %s", coll, e)
            return None, None, "target_lookup_error"
    if not candidates:
        return None, None, "no_funded_platform"
    candidates.sort(key=lambda d: d.get("completed_at") or "", reverse=True)
    platform = candidates[0].get("platform")
    if not platform:
        return None, None, "no_funded_platform"
    return platform, recipient, ""


async def run_redemption_pull(db, redemption: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, str]:
    """Attempt to reclaim credits for one redemption. Never raises.

    Returns a status dict mirroring what was stamped on the redemption doc:
    ``done`` | ``unsupported`` | ``failed`` | ``skipped_no_platform``.
    """
    redemption_id = str(redemption.get("id") or redemption.get("_id") or "")
    user_id = str(user.get("_id") or user.get("id") or "")
    amount = float(redemption.get("game_credits") or 0)
    started = _now().isoformat()

    await db.redemption_requests.update_one(
        {"id": redemption_id},
        {"$set": {"pool_pull_status": "in_progress", "pool_pull_started_at": started}},
    )

    platform, recipient, skip_reason = await resolve_pull_target(db, user)
    if not platform:
        detail = {"reason": skip_reason}
        await record_pull(db, {
            "ref_kind": "redemption",
            "ref_id": redemption_id,
            "user_id": user_id or None,
            "recipient_username": recipient,
            "platform": None,
            "amount": amount,
            "status": "skipped_no_platform",
            "message": f"Skipped: {skip_reason}",
            "detail": detail,
            "completed_at": _now().isoformat(),
        })
        await db.redemption_requests.update_one(
            {"id": redemption_id},
            {"$set": {
                "pool_pull_status": "skipped_no_platform",
                "pool_pull_message": skip_reason,
                "pool_pull_completed_at": _now().isoformat(),
            }},
        )
        return {"status": "skipped_no_platform", "reason": skip_reason}

    from config.currency_config import credits_to_platform_amount
    from routes.distributor_pool import execute_pool_pull

    # UNITS: redemptions are denominated in INTERNAL credits; the hub pull
    # moves PLATFORM dollars. Convert here; both figures are logged.
    platform_amount = credits_to_platform_amount(amount)

    try:
        ok, msg, detail = await execute_pool_pull(
            db,
            recipient_username=recipient,
            amount=platform_amount,
            amount_credits=amount,
            platform=platform,
            ref_kind="redemption",
            ref_id=redemption_id,
            user_id=user_id or None,
        )
    except Exception as e:
        logger.exception("pool_pull dispatch crashed")
        ok, msg, detail = False, f"pool_pull dispatch crash: {e}", {}

    status = detail.get("pull_status") or ("done" if ok else "failed")
    await db.redemption_requests.update_one(
        {"id": redemption_id},
        {"$set": {
            "pool_pull_status": status,
            "pool_pull_message": msg,
            "pool_pull_detail": detail,
            "pool_pull_completed_at": _now().isoformat(),
        }},
    )
    logger.info(
        "[pool:pull] redemption=%s platform=%s recipient=%s credits=%s platform_amount=%s status=%s msg=%s",
        redemption_id, platform, recipient, amount, platform_amount, status, msg,
    )
    return {"status": status, "message": msg}


async def pool_pull_kpis(db, window_hours: int = 24) -> Dict[str, Any]:
    """Recycling KPIs for the credit loop over the last ``window_hours``.

    * ``redemption_credits`` — gross Game Credits redeemed (denominator).
    * ``pull_attempted_credits`` / ``pull_done_credits`` — pool_pull attempts
      and successes against that redemption volume.
    * ``pull_success_rate`` — done / attempted.
    * ``recycled_credit_ratio`` — done / redeemed (capped at 1.0); the playbook
      KPI that answers "what share of redemptions self-financed through the
      credit loop".
    """
    started = _now() - timedelta(hours=max(1, int(window_hours)))
    started_iso = started.isoformat()

    redeems = await db.redemption_requests.find(
        {"created_at": {"$gte": started_iso}}, {"game_credits": 1}
    ).to_list(100000)
    redemption_total = float(sum(r.get("game_credits") or 0 for r in redeems))

    attempts = await db[POOL_PULL_COLLECTION].find(
        {"ref_kind": "redemption", "created_at": {"$gte": started_iso}},
        {"status": 1, "amount": 1},
    ).to_list(200000)
    attempted_total = float(sum(
        a.get("amount") or 0 for a in attempts if a.get("status") in PULL_ATTEMPT_STATUSES
    ))
    done_total = float(sum(
        a.get("amount") or 0 for a in attempts if a.get("status") == "done"
    ))

    return {
        "window_hours": max(1, int(window_hours)),
        "redemption_credits": round(redemption_total, 2),
        "pull_attempted_credits": round(attempted_total, 2),
        "pull_done_credits": round(done_total, 2),
        "pull_success_rate": round(done_total / attempted_total, 4) if attempted_total else 0.0,
        "recycled_credit_ratio": round(min(1.0, done_total / redemption_total), 4) if redemption_total else 0.0,
    }


async def _safe_run(db, redemption: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, str]:
    """Run one redemption pull so it can never crash the request loop.

    A background task that raises produces an un-retrieved exception warning
    and no audit trail. This wrapper turns any crash into a recorded
    ``failed`` status on the redemption doc instead.
    """
    try:
        return await run_redemption_pull(db, redemption, user)
    except Exception as e:  # pragma: no cover — defensive only
        logger.exception("pool_pull task crashed")
        redemption_id = str(redemption.get("id") or redemption.get("_id") or "")
        try:
            await db.redemption_requests.update_one(
                {"id": redemption_id},
                {"$set": {
                    "pool_pull_status": "failed",
                    "pool_pull_message": f"pool_pull task crash: {e}",
                    "pool_pull_completed_at": _now().isoformat(),
                }},
            )
        except Exception:
            logger.exception("pool_pull crash-stamp failed")
        return {"status": "failed", "message": f"pool_pull task crash: {e}"}


def dispatch_redemption_pull(db, redemption: Dict[str, Any], user: Dict[str, Any]):
    """Fire the redemption pull in the background when enabled (no-op otherwise).

    Returns the background task, or None when pool_pull is off, the redemption
    has no credits / id, or the user is unknown. It never blocks the request.
    """
    if not _enabled():
        return None
    amount = float(redemption.get("game_credits") or 0)
    if amount <= 0 or not redemption.get("id"):
        return None
    if not isinstance(user, dict) or not (user.get("_id") or user.get("id")):
        return None
    task = asyncio.create_task(_safe_run(db, redemption, user))
    return task