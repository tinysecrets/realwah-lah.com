"""Competition (sweepstakes) service: entry crediting, leaderboard, winner draw.

Entry streams are intentionally limited to events WAH-LAH can audit per user:
  * purchase  -> ``PURCHASE_BONUS`` bonus grants (1 entry per $1). Keyed to the
                 bonus grant, NOT the purchase row, because the BTC path can
                 produce two completed purchase rows per deposit but exactly
                 one bonus grant (never double-counts).
  * amoe_daily -> one free entry per successful ``claim_amoe_daily`` (no
                 purchase necessary, satisfies the legally required AMOE).

A turnover/play stream (e.g. "every $1 wagered = 1 entry") can be added later
without schema changes because ``award_entries`` accepts an arbitrary source
and ``competition.rules.entry_*`` keys are open-ended.

Best-effort semantics: award failures must never break a purchase or an AMOE
claim, so the callers wrap award calls in try/except.
"""
from __future__ import annotations

import logging
import random
import uuid
from datetime import datetime, timezone
from typing import List, Optional

logger = logging.getLogger(__name__)

COMPETITION_STATUSES = {"upcoming", "live", "drawing", "concluded", "cancelled"}
DEFAULT_RULES = {"entry_per_purchase_usd": 1.0, "entry_amoe_daily": 1.0}
ENTRY_LEDGER = "competition_entries"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def mask_email(email: Optional[str]) -> str:
    if not email or "@" not in email:
        return "Player***"
    local, _, domain = email.partition("@")
    shown = local[:2] + "***" if len(local) > 2 else (local[:1] + "***" if local else "***")
    return f"{shown}@{domain}"


# ---------------------------------------------------------------------------
# Competition lookup
# ---------------------------------------------------------------------------
async def get_by_id(db, competition_id: str):
    return await db["competitions"].find_one({"id": competition_id})


async def get_live_competition(db):
    return await db["competitions"].find_one({"status": "live"})


async def get_live_or_upcoming(db):
    for status in ("live", "upcoming"):
        comp = await db["competitions"].find_one(
            {"status": status}, sort=[("starts_at", 1)]
        )
        if comp:
            return comp
    return None


# ---------------------------------------------------------------------------
# Entry awarding
# ---------------------------------------------------------------------------
async def award_entries(
    db,
    *,
    competition_id: str,
    user_id: str,
    user_email: str,
    source: str,
    quantity: int,
    source_ref: str,
) -> bool:
    """Best-effort, idempotent entry award. False if no live competition or
    duplicate key (safe to ignore by callers)."""
    if quantity < 1:
        return False
    exists = await db[ENTRY_LEDGER].find_one(
        {"competition_id": competition_id, "user_id": user_id,
         "source": source, "source_ref": source_ref}
    )
    if exists:
        return False
    try:
        await db[ENTRY_LEDGER].insert_one({
            "id": str(uuid.uuid4()),
            "competition_id": competition_id,
            "user_id": user_id,
            "user_email": user_email,
            "source": source,
            "quantity": int(quantity),
            "source_ref": source_ref,
            "created_at": utcnow(),
        })
        return True
    except Exception:
        logger.warning("competition entry award failed (comp=%s user=%s src=%s)",
                       competition_id, user_id, source)
        return False


async def award_purchase_entries(
    db, *, user_id: str, user_email: str, purchase_id: str, purchase_amount_usd: float
) -> int:
    """Award purchase entries for a completed purchase (1 per ${rule})."""
    comp = await get_live_competition(db)
    if not comp:
        return 0
    rule = float((comp.get("rules") or {}).get("entry_per_purchase_usd", 1.0) or 1.0)
    if rule <= 0:
        return 0
    quantity = int((purchase_amount_usd or 0.0) / rule)
    if quantity < 1:
        return 0
    await award_entries(
        db, competition_id=comp["id"], user_id=user_id, user_email=user_email,
        source="purchase", quantity=quantity, source_ref=purchase_id,
    )
    return quantity


async def award_amoe_entries(db, *, user_id: str, user_email: str, grant_id: str) -> int:
    """Award the free AMOE daily entry after a successful daily claim."""
    comp = await get_live_competition(db)
    if not comp:
        return 0
    rule = float((comp.get("rules") or {}).get("entry_amoe_daily", 1.0) or 1.0)
    quantity = int(rule)
    if quantity < 1:
        return 0
    await award_entries(
        db, competition_id=comp["id"], user_id=user_id, user_email=user_email,
        source="amoe_daily", quantity=quantity, source_ref=grant_id,
    )
    return quantity


# ---------------------------------------------------------------------------
# Reads: entries, leaderboard, totals
# ---------------------------------------------------------------------------
async def get_user_entry_total(db, competition_id: str, user_id: str) -> int:
    rows = await db[ENTRY_LEDGER].aggregate([
        {"$match": {"competition_id": competition_id, "user_id": user_id}},
        {"$group": {"_id": None, "total": {"$sum": "$quantity"}}},
    ]).to_list(1)
    return int(rows[0]["total"]) if rows else 0


async def get_leaderboard(db, competition_id: str, limit: int = 20, include_email: bool = False) -> List[dict]:
    rows = await db[ENTRY_LEDGER].aggregate([
        {"$match": {"competition_id": competition_id}},
        {"$group": {"_id": "$user_id", "user_email": {"$first": "$user_email"},
                    "entries": {"$sum": "$quantity"}}},
        {"$sort": {"entries": -1}},
        {"$limit": int(limit)},
    ]).to_list(int(limit))
    board = []
    for rank, row in enumerate(rows, start=1):
        board.append({
            "rank": rank,
            "user_id": str(row["_id"]),
            "name": row.get("user_email") if include_email else mask_email(row.get("user_email")),
            "entries": int(row["entries"]),
        })
    return board


async def get_competition_totals(db, competition_id: str) -> dict:
    rows = await db[ENTRY_LEDGER].aggregate([
        {"$match": {"competition_id": competition_id}},
        {"$group": {"_id": None, "total_entries": {"$sum": "$quantity"},
                    "players": {"$addToSet": "$user_id"}}},
    ]).to_list(1)
    if not rows:
        return {"total_entries": 0, "total_players": 0}
    players = rows[0].get("players") or []
    return {"total_entries": int(rows[0].get("total_entries") or 0), "total_players": len(players)}


async def recent_winners(db, limit: int = 5) -> List[dict]:
    out = []
    cursor = db["competitions"].find({"status": "concluded", "winner": {"$ne": None}})
    async for comp in cursor.sort("draws_at", -1).limit(int(limit)):
        w = comp.get("winner") or {}
        out.append({
            "competition_id": comp.get("id"),
            "name": comp.get("name"),
            "prize_usd": comp.get("prize_usd"),
            "draws_at": comp.get("draws_at"),
            "winner_name": mask_email(w.get("user_email") or w.get("name")),
            "winner_entries": w.get("entries"),
            "prize_status": comp.get("prize_status"),
        })
    return out


# ---------------------------------------------------------------------------
# Public payload for the player-facing promo page
# ---------------------------------------------------------------------------
async def public_payload(db, user_id: Optional[str] = None) -> dict:
    comp = await get_live_or_upcoming(db)
    data = {
        "competition": None,
        "recent_winners": await recent_winners(db),
    }
    if comp:
        cid = comp["id"]
        data["competition"] = {
            "id": cid,
            "name": comp.get("name"),
            "prize_usd": comp.get("prize_usd"),
            "status": comp.get("status"),
            "starts_at": comp.get("starts_at"),
            "draws_at": comp.get("draws_at"),
            "rules": comp.get("rules") or DEFAULT_RULES,
            "totals": await get_competition_totals(db, cid),
            "leaderboard": await get_leaderboard(db, cid, limit=20),
        }
        if user_id:
            data["competition"]["my_entries"] = await get_user_entry_total(db, cid, user_id)
    return data


# ---------------------------------------------------------------------------
# Admin: create / update / cancel
# ---------------------------------------------------------------------------
async def _ensure_ledger_index(db) -> None:
    try:
        await db[ENTRY_LEDGER].create_index(
            [("competition_id", 1), ("user_id", 1), ("source", 1), ("source_ref", 1)],
            unique=True,
        )
    except Exception:
        pass  # best-effort; awards are also guarded at application level


async def create_competition(db, payload: dict, created_by: str = "admin") -> dict:
    now = utcnow()
    status = payload.get("status", "upcoming")
    if status not in COMPETITION_STATUSES:
        status = "upcoming"
    rules = {**DEFAULT_RULES, **(payload.get("rules") or {})}
    doc = {
        "id": str(uuid.uuid4()),
        "name": payload.get("name") or "Million Dollar Sweepstakes",
        "prize_usd": float(payload.get("prize_usd") or 1_000_000),
        "status": status,
        "starts_at": payload.get("starts_at") or now,
        "draws_at": payload.get("draws_at"),
        "legal_copy": payload.get("legal_copy") or
            "No purchase necessary. Free entries available daily via "
            "Alternative Method of Entry. Void where prohibited.",
        "rules": rules,
        "winner": None,
        "prize_status": None,
        "created_by": created_by,
        "created_at": now,
        "updated_at": now,
    }
    await db["competitions"].insert_one(doc)
    await _ensure_ledger_index(db)
    return doc


async def update_competition(db, competition_id: str, payload: dict, updated_by: str = "admin") -> dict:
    comp = await get_by_id(db, competition_id)
    if not comp:
        raise ValueError("Competition not found")
    allow = {"name", "prize_usd", "status", "starts_at", "draws_at", "legal_copy", "prize_status"}
    changes = {k: v for k, v in payload.items() if k in allow and v is not None}
    if "status" in changes and changes["status"] not in COMPETITION_STATUSES:
        changes.pop("status")
    if "rules" in payload:
        rules = {**(comp.get("rules") or {}), **(payload["rules"] or {})}
        changes["rules"] = rules
    if not changes:
        return comp
    changes["updated_at"] = utcnow()
    await db["competitions"].update_one({"id": competition_id}, {"$set": changes})
    return await get_by_id(db, competition_id)


async def cancel_competition(db, competition_id: str, updated_by: str = "admin") -> dict:
    return await update_competition(
        db, competition_id, {"status": "cancelled"}, updated_by=updated_by
    )


# ---------------------------------------------------------------------------
# Draw / prize
# ---------------------------------------------------------------------------
async def run_draw(db, competition_id: str, run_by: str = "admin", rng=None) -> dict:
    """Weighted random selection among all entry holders. Idempotent for an
    already-concluded competition."""
    comp = await get_by_id(db, competition_id)
    if not comp:
        raise ValueError("Competition not found")

    if comp.get("status") == "concluded" and comp.get("winner"):
        return {"competition": comp, "winner": comp["winner"], "already_drawn": True}

    if comp.get("status") not in ("live", "drawing", "upcoming"):
        raise ValueError(f"Cannot draw a {comp.get('status')} competition")

    rows = await db[ENTRY_LEDGER].aggregate([
        {"$match": {"competition_id": competition_id}},
        {"$group": {"_id": "$user_id", "user_email": {"$first": "$user_email"},
                    "entries": {"$sum": "$quantity"}}},
    ]).to_list(100000)
    if not rows:
        raise ValueError("No entries to draw from")

    rng = rng or random
    population = [str(r["_id"]) for r in rows]
    weights = [int(r["entries"]) for r in rows]
    winner_user_id = rng.choices(population, weights=weights, k=1)[0]
    winner_row = next(r for r in rows if str(r["_id"]) == winner_user_id)

    winner_email = winner_row.get("user_email")
    winner_name = winner_email
    try:
        user = await db["users"].find_one({"id": winner_user_id}) or \
            await db["users"].find_one({"_id": winner_user_id})
        if user:
            winner_name = user.get("name") or user.get("email") or winner_email
    except Exception:
        pass

    winner = {
        "user_id": winner_user_id,
        "user_email": winner_email,
        "name": winner_name,
        "masked_name": mask_email(winner_email),
        "entries": int(winner_row["entries"]),
        "selected_at": utcnow(),
    }
    await db["competitions"].update_one(
        {"id": competition_id},
        {"$set": {
            "status": "concluded",
            "winner": winner,
            "prize_status": "pending_payout",
            "draws_at": comp.get("draws_at") or utcnow(),
            "updated_at": utcnow(),
        }},
    )
    comp = await get_by_id(db, competition_id)
    return {"competition": comp, "winner": winner, "already_drawn": False}


async def mark_prize_paid(db, competition_id: str, updated_by: str = "admin") -> dict:
    comp = await get_by_id(db, competition_id)
    if not comp:
        raise ValueError("Competition not found")
    await db["competitions"].update_one(
        {"id": competition_id},
        {"$set": {"prize_status": "paid", "prize_paid_at": utcnow(), "updated_at": utcnow()}},
    )
    return await get_by_id(db, competition_id)